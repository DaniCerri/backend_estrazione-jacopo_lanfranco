import hashlib
import os
import secrets

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import ZONE
from app.models import Estrazione, Estratto, EventoAdmin, Impostazione, Iscrizione, adesso

ISCRIZIONI_APERTE = "iscrizioni_aperte"


def registra(db: Session, azione: str, dettaglio: str | None = None, ip: str | None = None) -> None:
    """Aggiunge una riga al registro azioni admin. Il commit lo fa il chiamante."""
    db.add(EventoAdmin(azione=azione, dettaglio=dettaglio, ip=ip))


def iscrizioni_aperte(db: Session) -> bool:
    imp = db.get(Impostazione, ISCRIZIONI_APERTE)
    return imp is None or imp.valore == "1"


def imposta_iscrizioni_aperte(db: Session, aperte: bool, ip: str | None = None) -> None:
    db.merge(Impostazione(chiave=ISCRIZIONI_APERTE, valore="1" if aperte else "0"))
    registra(db, "iscrizioni_aperte" if aperte else "iscrizioni_chiuse", ip=ip)
    db.commit()


def marketing_attivo():
    return Iscrizione.consenso_marketing.is_(True) & Iscrizione.marketing_revocato_at.is_(None)


def statistiche(db: Session) -> dict:
    per_zona = dict.fromkeys(ZONE, 0)
    for zona, n in db.execute(select(Iscrizione.zona, func.count()).group_by(Iscrizione.zona)):
        per_zona[zona] = n
    marketing = db.scalar(select(func.count()).select_from(Iscrizione).where(marketing_attivo()))
    return {
        "totale": sum(per_zona.values()),
        "per_zona": per_zona,
        "marketing": marketing or 0,
        "aperte": iscrizioni_aperte(db),
    }


def _gia_estratti():
    return (
        select(Estratto.iscrizione_id)
        .join(Estrazione)
        .where(Estrazione.annullata.is_(False), Estratto.iscrizione_id.is_not(None))
    )


def partecipanti_in_gara(db: Session) -> list[int]:
    """Tutti gli iscritti non ancora estratti in un'estrazione valida. Nessun filtro:
    parità di trattamento (art. 8 DPR 430/2001)."""
    q = select(Iscrizione.id).where(Iscrizione.id.not_in(_gia_estratti())).order_by(Iscrizione.id)
    return list(db.scalars(q))


def impronta_pool(pool: list[int]) -> str:
    """SHA-256 degli ID ordinati separati da virgola: ricalcolabile dall'export partecipanti."""
    return hashlib.sha256(",".join(map(str, sorted(pool))).encode()).hexdigest()


def versione_software() -> str:
    commit = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")[:12] or "locale"
    regione = os.environ.get("RAILWAY_REPLICA_REGION", "")
    return f"chef-battle-backend@{commit}" + (f" ({regione})" if regione else "")


class PoolVuoto(Exception):
    pass


def estrai(db: Session, riserve: int, ip: str | None = None) -> Estrazione:
    """Estrae 1 vincitore + N riserve ordinate in un'unica operazione.
    Generatore: secrets.SystemRandom (CSPRNG del sistema operativo, os.urandom)."""
    pool = partecipanti_in_gara(db)
    if not pool:
        raise PoolVuoto
    scelti = secrets.SystemRandom().sample(pool, min(len(pool), 1 + riserve))

    estrazione = Estrazione(
        pool_size=len(pool),
        pool_hash=impronta_pool(pool),
        versione_software=versione_software(),
    )
    iscritti = {i.id: i for i in db.scalars(select(Iscrizione).where(Iscrizione.id.in_(scelti)))}
    for posizione, iscrizione_id in enumerate(scelti):
        i = iscritti[iscrizione_id]
        estrazione.estratti.append(
            Estratto(iscrizione_id=i.id, posizione=posizione, nominativo=f"{i.nome} {i.cognome}")
        )
    db.add(estrazione)
    db.flush()
    registra(
        db,
        "estrazione",
        f"#{estrazione.id} pool={len(pool)} sha256={estrazione.pool_hash} "
        f"estratti={','.join(map(str, scelti))}",
        ip,
    )
    db.commit()
    return estrazione


def annulla(db: Session, estrazione: Estrazione, motivo: str, ip: str | None = None) -> None:
    estrazione.annullata = True
    estrazione.motivo_annullamento = motivo
    estrazione.annullata_at = adesso()
    registra(db, "annullamento", f"#{estrazione.id}: {motivo}", ip)
    db.commit()


def revoca_marketing(db: Session, iscrizione: Iscrizione, canale: str, ip: str | None = None) -> None:
    if iscrizione.marketing_revocato_at is None and iscrizione.consenso_marketing:
        iscrizione.marketing_revocato_at = adesso()
        registra(db, "revoca_marketing", f"iscrizione #{iscrizione.id} via {canale}", ip)
        db.commit()


def anonimizza_non_necessari(db: Session) -> int:
    """Retention: cancella chi non è stato estratto e non ha un consenso marketing attivo.
    Vincitori e riserve restano (obblighi fiscali e verbale), i consenzienti restano per il marketing."""
    da_cancellare = select(Iscrizione.id).where(
        Iscrizione.id.not_in(_gia_estratti()), ~marketing_attivo()
    )
    ids = list(db.scalars(da_cancellare))
    if ids:
        db.execute(delete(Iscrizione).where(Iscrizione.id.in_(ids)))
    registra(db, "retention", f"cancellate {len(ids)} iscrizioni")
    db.commit()
    return len(ids)
