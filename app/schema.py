import logging

from sqlalchemy import Engine, func, inspect, select

from app.models import Base, Iscrizione

log = logging.getLogger("uvicorn.error")


def prepara_schema(engine: Engine) -> None:
    """Crea le tabelle. Se esistono con uno schema diverso (versione precedente del
    software) le ricrea, ma solo se non contengono iscrizioni: i dati non si toccano mai."""
    insp = inspect(engine)
    diverse = [
        t.name
        for t in Base.metadata.sorted_tables
        if insp.has_table(t.name)
        and {c["name"] for c in insp.get_columns(t.name)} != set(t.columns.keys())
    ]
    if diverse:
        iscritti = 0
        if insp.has_table(Iscrizione.__tablename__):
            with engine.connect() as conn:
                iscritti = conn.scalar(select(func.count()).select_from(Iscrizione.__table__))
        if iscritti:
            raise RuntimeError(
                f"Schema del database non compatibile ({', '.join(diverse)}) e ci sono "
                f"{iscritti} iscrizioni: serve una migrazione manuale, nessun dato è stato toccato."
            )
        log.warning("Schema del database non compatibile (%s), nessuna iscrizione: ricreo le tabelle.",
                    ", ".join(diverse))
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
