from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import ZONE, get_settings
from app.db import get_db
from app.models import Iscrizione
from app.schemas import MESSAGGI_ERRORE, IscrizioneIn
from app.security import client_ip, limiter_iscrizioni
from app.services import iscrizioni_aperte

router = APIRouter(prefix="/api")


def _errore(status: int, codice: str, messaggio: str, **extra) -> JSONResponse:
    return JSONResponse({"errore": codice, "messaggio": messaggio, **extra}, status_code=status)


def _duplicato(db: Session, dati: IscrizioneIn) -> JSONResponse | None:
    per_tel = db.scalar(select(Iscrizione).where(Iscrizione.telefono == dati.telefono))
    per_email = db.scalar(select(Iscrizione).where(Iscrizione.email == dati.email))
    if per_tel is None and per_email is None:
        return None
    if per_tel is not None and per_tel is per_email:
        # Stessa persona che reinvia (es. risposta persa per rete lenta): è già in gara
        return JSONResponse({"stato": "gia_iscritto"}, status_code=200)
    campo = "telefono" if per_tel is not None else "email"
    etichetta = "numero di telefono" if campo == "telefono" else "indirizzo email"
    return _errore(
        409,
        "duplicato",
        f"Esiste già un'iscrizione con questo {etichetta}. È ammessa una sola iscrizione per persona.",
        campo=campo,
    )


@router.post("/iscrizioni", status_code=201)
def crea_iscrizione(dati: IscrizioneIn, request: Request, db: Session = Depends(get_db)):
    if not limiter_iscrizioni.consenti(client_ip(request)):
        return _errore(429, "troppe_richieste", "Troppe richieste, riprova tra qualche secondo.")

    if dati.website:
        # Bot: risposta identica al successo, nessun salvataggio
        return {"stato": "iscritto"}

    if not iscrizioni_aperte(db):
        return _errore(403, "chiuse", "Le iscrizioni all'estrazione sono chiuse.")

    settings = get_settings()
    if dati.zona_codice and dati.zona_codice in settings.zone_codes:
        zona, da_qr = settings.zone_codes[dati.zona_codice], True
    elif dati.zona in ZONE:
        zona, da_qr = dati.zona, False
    else:
        return _errore(
            422, "validazione", MESSAGGI_ERRORE["zona"], campi={"zona": MESSAGGI_ERRORE["zona"]}
        )

    if (risposta := _duplicato(db, dati)) is not None:
        return risposta

    db.add(
        Iscrizione(
            nome=dati.nome,
            cognome=dati.cognome,
            telefono=dati.telefono,
            email=dati.email,
            instagram=dati.instagram,
            zona=zona,
            zona_da_qr=da_qr,
            consenso_regolamento=dati.accetta_regolamento,
            consenso_privacy=dati.accetta_privacy,
            consenso_marketing=dati.accetta_marketing,
            informativa_versione=settings.informativa_versione,
            ip=client_ip(request)[:45],
            user_agent=(request.headers.get("user-agent") or "")[:300] or None,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Due invii simultanei: il vincolo UNIQUE ha bloccato il secondo
        db.rollback()
        return _duplicato(db, dati) or _errore(409, "duplicato", "Iscrizione già presente.")

    return {"stato": "iscritto"}


@router.get("/stato")
def stato(db: Session = Depends(get_db)):
    return {
        "aperte": iscrizioni_aperte(db),
        "zone": [{"id": k, "nome": v} for k, v in ZONE.items()],
    }


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True}
