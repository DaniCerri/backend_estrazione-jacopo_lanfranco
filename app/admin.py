import csv
import io
import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import ZONE, get_settings
from app.db import get_db
from app.models import Estrazione, Estratto, Iscrizione
from app.security import (
    ADMIN_COOKIE,
    ADMIN_SESSIONE_SECONDI,
    client_ip,
    crea_token_admin,
    is_admin,
    limiter_login_globale,
    limiter_login_ip,
    richiedi_admin,
    richiedi_admin_api,
)
from app.services import (
    PoolVuoto,
    estrai,
    imposta_iscrizioni_aperte,
    statistiche,
)

ROMA = ZoneInfo("Europe/Rome")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["ZONE"] = ZONE


def _ora_locale(dt: datetime | None, formato: str = "%d/%m %H:%M:%S") -> str:
    return dt.astimezone(ROMA).strftime(formato) if dt else ""


templates.env.filters["ora"] = _ora_locale

router = APIRouter(prefix="/admin")
protetto = APIRouter(prefix="/admin", dependencies=[Depends(richiedi_admin)])


def _vai(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# --- Login -----------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
def pagina_login(request: Request):
    if is_admin(request):
        return _vai("/admin")
    return templates.TemplateResponse(request, "login.html", {"errore": None})


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, password: str = Form(...)):
    ip = client_ip(request)
    if not (limiter_login_ip.consenti(ip) and limiter_login_globale.consenti("*")):
        return templates.TemplateResponse(
            request, "login.html", {"errore": "Troppi tentativi. Riprova tra qualche minuto."},
            status_code=429,
        )
    if not secrets.compare_digest(password.encode(), get_settings().admin_password.encode()):
        return templates.TemplateResponse(
            request, "login.html", {"errore": "Password errata."}, status_code=401
        )
    risposta = _vai("/admin")
    risposta.set_cookie(
        ADMIN_COOKIE,
        crea_token_admin(),
        max_age=ADMIN_SESSIONE_SECONDI,
        path="/admin",
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
    )
    return risposta


@router.post("/logout")
def logout():
    risposta = _vai("/admin/login")
    risposta.delete_cookie(ADMIN_COOKIE, path="/admin")
    return risposta


# --- Dashboard -------------------------------------------------------------


@protetto.get("", response_class=HTMLResponse)
def dashboard(
    request: Request,
    e: int | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
):
    estrazioni = list(
        db.scalars(
            select(Estrazione)
            .options(selectinload(Estrazione.estratti).selectinload(Estratto.iscrizione))
            .order_by(Estrazione.id.desc())
        )
    )
    evidenziata = next((x for x in estrazioni if x.id == e), None)
    iscritti = list(db.scalars(select(Iscrizione).order_by(Iscrizione.id.desc())))
    estratti_validi = {
        es.iscrizione_id
        for x in estrazioni
        if not x.annullata
        for es in x.estratti
        if es.iscrizione_id
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stats": statistiche(db),
            "estrazioni": estrazioni,
            "evidenziata": evidenziata,
            "iscritti": iscritti,
            "estratti_validi": estratti_validi,
            "msg": msg,
        },
    )


@router.get("/api/stats", dependencies=[Depends(richiedi_admin_api)])
def api_stats(db: Session = Depends(get_db)):
    return statistiche(db)


@protetto.post("/iscrizioni/stato")
def cambia_stato_iscrizioni(aperte: bool = Form(...), db: Session = Depends(get_db)):
    imposta_iscrizioni_aperte(db, aperte)
    return _vai("/admin")


@protetto.post("/iscrizioni/{iscrizione_id}/elimina")
def elimina_iscrizione(iscrizione_id: int, db: Session = Depends(get_db)):
    if (i := db.get(Iscrizione, iscrizione_id)) is not None:
        db.delete(i)
        db.commit()
    return _vai("/admin?msg=eliminata#iscritti")


# --- Estrazione ------------------------------------------------------------


@protetto.post("/estrazioni")
def nuova_estrazione(
    zona: str = Form(""),
    riserve: int = Form(2, ge=0, le=10),
    db: Session = Depends(get_db),
):
    filtro = zona if zona in ZONE else None
    try:
        estrazione = estrai(db, filtro, riserve)
    except PoolVuoto:
        return _vai("/admin?msg=pool_vuoto#estrazione")
    return _vai(f"/admin?e={estrazione.id}#esito")


@protetto.post("/estrazioni/{estrazione_id}/annulla")
def annulla_estrazione(estrazione_id: int, db: Session = Depends(get_db)):
    if (x := db.get(Estrazione, estrazione_id)) is not None:
        x.annullata = True
        db.commit()
    return _vai("/admin#storico")


# --- Export CSV ------------------------------------------------------------

COLONNE = ["nome", "cognome", "email", "telefono", "instagram", "zona"]


def _csv(righe: list[Iscrizione], nome_file: str, colonne_extra: list[str]) -> Response:
    buf = io.StringIO()
    # ; e BOM UTF-8: Excel in italiano apre il file con colonne e accenti corretti
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    w.writerow(COLONNE + colonne_extra + ["data_iscrizione", "versione_informativa"])
    for i in righe:
        extra = {
            "consenso_marketing": "si" if i.consenso_marketing else "no",
        }
        w.writerow(
            [i.nome, i.cognome, i.email, i.telefono, i.instagram or "", ZONE.get(i.zona, i.zona)]
            + [extra[c] for c in colonne_extra]
            + [_ora_locale(i.created_at, "%d/%m/%Y %H:%M"), i.informativa_versione]
        )
    data = datetime.now(ROMA).strftime("%Y%m%d-%H%M")
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome_file}-{data}.csv"'},
    )


@protetto.get("/export/marketing.csv")
def export_marketing(db: Session = Depends(get_db)):
    """Solo chi ha dato il consenso facoltativo a essere ricontattato: è la lista per lo chef."""
    righe = list(
        db.scalars(
            select(Iscrizione).where(Iscrizione.consenso_marketing).order_by(Iscrizione.id)
        )
    )
    return _csv(righe, "contatti-marketing", [])


@protetto.get("/export/iscritti.csv")
def export_iscritti(db: Session = Depends(get_db)):
    """Tutti gli iscritti: solo per la gestione dell'estrazione, non per marketing."""
    righe = list(db.scalars(select(Iscrizione).order_by(Iscrizione.id)))
    return _csv(righe, "iscritti-estrazione", ["consenso_marketing"])
