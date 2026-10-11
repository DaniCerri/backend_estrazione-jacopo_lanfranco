import csv
import io
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import ZONE, get_settings
from app.db import get_db
from app.models import Estrazione, Estratto, EventoAdmin, Iscrizione
from app.security import (
    ADMIN_COOKIE,
    ADMIN_SESSIONE_SECONDI,
    client_ip,
    crea_token_admin,
    crea_token_disiscrizione,
    is_admin,
    limiter_login_globale,
    limiter_login_ip,
    richiedi_admin,
    richiedi_admin_api,
)
from app.services import (
    PoolVuoto,
    annulla,
    estrai,
    impronta_pool,
    imposta_iscrizioni_aperte,
    marketing_attivo,
    partecipanti_in_gara,
    registra,
    revoca_marketing,
    statistiche,
)
from app.templating import ROMA, ora_locale, templates

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
def login(request: Request, password: str = Form(...), db: Session = Depends(get_db)):
    ip = client_ip(request)
    if not (limiter_login_ip.consenti(ip) and limiter_login_globale.consenti("*")):
        return templates.TemplateResponse(
            request, "login.html", {"errore": "Troppi tentativi. Riprova tra qualche minuto."},
            status_code=429,
        )
    if not secrets.compare_digest(password.encode(), get_settings().admin_password.encode()):
        registra(db, "login_fallito", ip=ip)
        db.commit()
        return templates.TemplateResponse(
            request, "login.html", {"errore": "Password errata."}, status_code=401
        )
    registra(db, "login", ip=ip)
    db.commit()
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
    pool = partecipanti_in_gara(db)
    eventi = list(db.scalars(select(EventoAdmin).order_by(EventoAdmin.id.desc()).limit(100)))
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stats": statistiche(db),
            "estrazioni": estrazioni,
            "evidenziata": evidenziata,
            "iscritti": iscritti,
            "estratti_validi": estratti_validi,
            "in_gara": len(pool),
            "in_gara_hash": impronta_pool(pool),
            "eventi": eventi,
            "msg": msg,
        },
    )


@router.get("/api/stats", dependencies=[Depends(richiedi_admin_api)])
def api_stats(db: Session = Depends(get_db)):
    pool = partecipanti_in_gara(db)
    return {**statistiche(db), "in_gara": len(pool), "in_gara_hash": impronta_pool(pool)}


@protetto.post("/iscrizioni/stato")
def cambia_stato_iscrizioni(
    request: Request, aperte: bool = Form(...), db: Session = Depends(get_db)
):
    imposta_iscrizioni_aperte(db, aperte, client_ip(request))
    return _vai("/admin")


@protetto.post("/iscrizioni/{iscrizione_id}/elimina")
def elimina_iscrizione(
    request: Request,
    iscrizione_id: int,
    motivo: str = Form(..., min_length=3, max_length=300),
    db: Session = Depends(get_db),
):
    if (i := db.get(Iscrizione, iscrizione_id)) is not None:
        registra(db, "elimina_iscrizione", f"#{i.id}: {motivo}", client_ip(request))
        db.delete(i)
        db.commit()
    return _vai("/admin?msg=eliminata#iscritti")


@protetto.post("/iscrizioni/{iscrizione_id}/revoca-marketing")
def revoca_marketing_admin(request: Request, iscrizione_id: int, db: Session = Depends(get_db)):
    """Per le richieste di revoca arrivate via email o di persona."""
    if (i := db.get(Iscrizione, iscrizione_id)) is not None:
        revoca_marketing(db, i, "richiesta all'organizzazione", client_ip(request))
    return _vai("/admin?msg=revocato#iscritti")


# --- Estrazione ------------------------------------------------------------


@protetto.post("/estrazioni")
def nuova_estrazione(
    request: Request,
    riserve: int = Form(3, ge=0, le=10),
    hash_atteso: str = Form(""),
    db: Session = Depends(get_db),
):
    # Se nel frattempo è arrivata un'iscrizione, la lista mostrata (e magari letta al
    # notaio) non è più quella in gara: si ferma e si ricarica.
    if hash_atteso and hash_atteso != impronta_pool(partecipanti_in_gara(db)):
        return _vai("/admin?msg=lista_cambiata#estrazione")
    try:
        estrazione = estrai(db, riserve, client_ip(request))
    except PoolVuoto:
        return _vai("/admin?msg=pool_vuoto#estrazione")
    return _vai(f"/admin?e={estrazione.id}#esito")


@protetto.post("/estrazioni/{estrazione_id}/annulla")
def annulla_estrazione(
    request: Request,
    estrazione_id: int,
    motivo: str = Form(..., min_length=3, max_length=300),
    db: Session = Depends(get_db),
):
    if (x := db.get(Estrazione, estrazione_id)) is not None and not x.annullata:
        annulla(db, x, motivo, client_ip(request))
    return _vai("/admin#storico")


# --- Export CSV ------------------------------------------------------------


def _csv(intestazione: list[str], righe: list[list], nome_file: str) -> Response:
    buf = io.StringIO()
    # ; e BOM UTF-8: Excel in italiano apre il file con colonne e accenti corretti
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    w.writerow(intestazione)
    w.writerows(righe)
    data = datetime.now(ROMA).strftime("%Y%m%d-%H%M")
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome_file}-{data}.csv"'},
    )


def _data(dt: datetime | None) -> str:
    return ora_locale(dt, "%d/%m/%Y %H:%M:%S")


@protetto.get("/export/marketing.csv")
def export_marketing(request: Request, db: Session = Depends(get_db)):
    """Solo consensi marketing attivi (non revocati): è la lista da consegnare allo chef.
    Ogni riga ha il suo link di revoca da inserire nelle comunicazioni."""
    righe = list(db.scalars(select(Iscrizione).where(marketing_attivo()).order_by(Iscrizione.id)))
    base = get_settings().public_base_url.rstrip("/")
    registra(db, "export_marketing", f"{len(righe)} righe", client_ip(request))
    db.commit()
    return _csv(
        ["nome", "cognome", "email", "telefono", "data_consenso", "versione_informativa",
         "link_disiscrizione"],
        [
            [i.nome, i.cognome, i.email, i.telefono, _data(i.created_at), i.informativa_versione,
             f"{base}/api/disiscrizione?t={crea_token_disiscrizione(i.id)}"]
            for i in righe
        ],
        "contatti-marketing",
    )


@protetto.get("/export/iscritti.csv")
def export_iscritti(request: Request, db: Session = Depends(get_db)):
    """Tutti gli iscritti con la prova dei consensi: solo per gestione estrazione e controlli."""
    righe = list(db.scalars(select(Iscrizione).order_by(Iscrizione.id)))
    registra(db, "export_iscritti", f"{len(righe)} righe", client_ip(request))
    db.commit()
    si = lambda b: "si" if b else "no"  # noqa: E731
    return _csv(
        ["id", "nome", "cognome", "email", "telefono", "instagram", "zona", "zona_da_qr",
         "maggiore_eta", "regolamento", "privacy_presa_visione", "marketing",
         "marketing_revocato", "menzione_instagram", "versione_informativa", "data_iscrizione",
         "ip", "user_agent"],
        [
            [i.id, i.nome, i.cognome, i.email, i.telefono, i.instagram or "",
             ZONE.get(i.zona, i.zona), si(i.zona_da_qr), si(i.dichiarazione_maggiore_eta),
             si(i.consenso_regolamento), si(i.presa_visione_privacy), si(i.consenso_marketing),
             _data(i.marketing_revocato_at), si(i.consenso_menzione_instagram),
             i.informativa_versione, _data(i.created_at), i.ip or "", i.user_agent or ""]
            for i in righe
        ],
        "iscritti-estrazione",
    )


@protetto.get("/export/in-gara.csv")
def export_in_gara(request: Request, db: Session = Depends(get_db)):
    """Lista in gara per il notaio, senza recapiti. L'impronta SHA-256 mostrata in dashboard
    si ricalcola dagli ID: sha256("1,2,5,...") con gli ID in ordine crescente."""
    pool = partecipanti_in_gara(db)
    righe = list(db.scalars(select(Iscrizione).where(Iscrizione.id.in_(pool)).order_by(Iscrizione.id)))
    registra(db, "export_in_gara", f"{len(pool)} in gara sha256={impronta_pool(pool)}",
             client_ip(request))
    db.commit()
    return _csv(
        ["id", "nominativo", "zona", "data_iscrizione"],
        [[i.id, f"{i.nome} {i.cognome}", ZONE.get(i.zona, i.zona), _data(i.created_at)]
         for i in righe],
        f"in-gara-{len(pool)}-{impronta_pool(pool)[:12]}",
    )


@protetto.get("/estrazioni/{estrazione_id}/verbale.csv")
def verbale_estrazione(estrazione_id: int, db: Session = Depends(get_db)):
    x = db.get(Estrazione, estrazione_id)
    if x is None:
        return _vai("/admin#storico")
    righe = [
        ["estrazione", f"#{x.id}"],
        ["data_ora", _data(x.created_at)],
        ["partecipanti_in_gara", x.pool_size],
        ["sha256_lista", x.pool_hash],
        ["generatore", "secrets.SystemRandom (CSPRNG del sistema operativo)"],
        ["software", x.versione_software],
        ["stato", f"ANNULLATA il {_data(x.annullata_at)}: {x.motivo_annullamento}" if x.annullata else "valida"],
    ]
    for es in x.estratti:
        ruolo = "vincitore" if es.posizione == 0 else f"riserva_{es.posizione}"
        righe.append([ruolo, f"{es.nominativo} (id {es.iscrizione_id})"])
    return _csv(["voce", "valore"], righe, f"verbale-estrazione-{x.id}")
