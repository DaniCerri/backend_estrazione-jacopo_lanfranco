from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import admin, api
from app.config import get_settings
from app.db import get_engine
from app.schema import prepara_schema
from app.schemas import MESSAGGI_ERRORE


@asynccontextmanager
async def lifespan(_: FastAPI):
    prepara_schema(get_engine())
    yield


debug = get_settings().debug
app = FastAPI(
    title="Chef Battle — Estrazione",
    lifespan=lifespan,
    docs_url="/api/docs" if debug else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if debug else None,
)


@app.exception_handler(RequestValidationError)
async def errore_validazione(request: Request, exc: RequestValidationError):
    # Formato semplice per il form: {campo: messaggio in italiano}
    campi: dict[str, str] = {}
    for err in exc.errors():
        loc = err.get("loc", ())
        campo = str(loc[-1]) if len(loc) > 1 else "body"
        campi.setdefault(campo, MESSAGGI_ERRORE.get(campo, "Valore non valido."))
    return JSONResponse(
        {"errore": "validazione", "messaggio": "Controlla i campi evidenziati.", "campi": campi},
        status_code=422,
    )


@app.middleware("http")
async def header_sicurezza(request: Request, call_next):
    risposta = await call_next(request)
    risposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    risposta.headers.setdefault("Referrer-Policy", "same-origin")
    if get_settings().cookie_secure:
        risposta.headers["Strict-Transport-Security"] = "max-age=31536000"
    if request.url.path.startswith(("/admin", "/api/disiscrizione")):
        risposta.headers["X-Frame-Options"] = "DENY"
        risposta.headers["X-Robots-Tag"] = "noindex, nofollow"
        risposta.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
    if request.url.path.startswith(("/admin", "/api")) and not request.url.path.startswith(
        "/admin/static"
    ):
        risposta.headers["Cache-Control"] = "no-store"
    return risposta


app.include_router(api.router)
app.include_router(admin.router)
app.include_router(admin.protetto)
app.mount("/admin/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
