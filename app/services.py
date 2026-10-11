import hashlib
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import ZONE
from app.models import Estrazione, Estratto, Impostazione, Iscrizione

ISCRIZIONI_APERTE = "iscrizioni_aperte"


def iscrizioni_aperte(db: Session) -> bool:
    imp = db.get(Impostazione, ISCRIZIONI_APERTE)
    return imp is None or imp.valore == "1"


def imposta_iscrizioni_aperte(db: Session, aperte: bool) -> None:
    db.merge(Impostazione(chiave=ISCRIZIONI_APERTE, valore="1" if aperte else "0"))
    db.commit()


def statistiche(db: Session) -> dict:
    per_zona = dict.fromkeys(ZONE, 0)
    for zona, n in db.execute(select(Iscrizione.zona, func.count()).group_by(Iscrizione.zona)):
        per_zona[zona] = n
    marketing = db.scalar(
        select(func.count()).select_from(Iscrizione).where(Iscrizione.consenso_marketing)
    )
    return {
        "totale": sum(per_zona.values()),
        "per_zona": per_zona,
        "marketing": marketing or 0,
        "aperte": iscrizioni_aperte(db),
    }


class PoolVuoto(Exception):
    pass


def partecipanti_in_gara(db: Session, zona: str | None) -> list[int]:
    """Iscritti non ancora estratti in un'estrazione valida, eventualmente filtrati per zona."""
    gia_estratti = (
        select(Estratto.iscrizione_id)
        .join(Estrazione)
        .where(Estrazione.annullata.is_(False), Estratto.iscrizione_id.is_not(None))
    )
    q = select(Iscrizione.id).where(Iscrizione.id.not_in(gia_estratti)).order_by(Iscrizione.id)
    if zona:
        q = q.where(Iscrizione.zona == zona)
    return list(db.scalars(q))


def impronta_pool(pool: list[int]) -> str:
    return hashlib.sha256(",".join(map(str, sorted(pool))).encode()).hexdigest()


def estrai(db: Session, zona: str | None, riserve: int) -> Estrazione:
    """Estrae 1 vincitore + N riserve con un generatore crittografico (os.urandom)."""
    pool = partecipanti_in_gara(db, zona)
    if not pool:
        raise PoolVuoto
    scelti = secrets.SystemRandom().sample(pool, min(len(pool), 1 + riserve))

    estrazione = Estrazione(zona_filtro=zona, pool_size=len(pool), pool_hash=impronta_pool(pool))
    iscritti = {i.id: i for i in db.scalars(select(Iscrizione).where(Iscrizione.id.in_(scelti)))}
    for posizione, iscrizione_id in enumerate(scelti):
        i = iscritti[iscrizione_id]
        estrazione.estratti.append(
            Estratto(
                iscrizione_id=i.id,
                posizione=posizione,
                nominativo=f"{i.nome} {i.cognome}",
            )
        )
    db.add(estrazione)
    db.commit()
    return estrazione
