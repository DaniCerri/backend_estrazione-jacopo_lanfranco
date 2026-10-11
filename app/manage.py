"""Comandi di servizio. Uso: python -m app.manage <comando>

Su Railway: railway run python -m app.manage <comando>
"""

import argparse
import json
import secrets

from sqlalchemy import delete

from app.config import ZONE
from app.db import get_engine, get_sessionmaker
from app.models import Base, Estrazione, Estratto, EventoAdmin, Impostazione, Iscrizione
from app.services import anonimizza_non_necessari, registra, statistiche


def crea_tabelle(_: argparse.Namespace) -> None:
    Base.metadata.create_all(get_engine())
    print("Tabelle create.")


def genera_codici(_: argparse.Namespace) -> None:
    codici = {secrets.token_urlsafe(6): zona for zona in ZONE}
    print("ZONE_CODES=" + json.dumps(codici))


def stats(_: argparse.Namespace) -> None:
    with get_sessionmaker()() as db:
        print(json.dumps(statistiche(db), indent=2))


def reset(args: argparse.Namespace) -> None:
    if args.conferma != "CANCELLA-TUTTO":
        raise SystemExit("Operazione irreversibile: aggiungi --conferma CANCELLA-TUTTO")
    with get_sessionmaker()() as db:
        for model in (Estratto, Estrazione, Iscrizione, Impostazione, EventoAdmin):
            db.execute(delete(model))
        registra(db, "reset", "dati di prova cancellati da riga di comando")
        db.commit()
    print("Tutti i dati sono stati cancellati.")


def retention(args: argparse.Namespace) -> None:
    if args.conferma != "CANCELLA":
        raise SystemExit(
            "Cancella gli iscritti non estratti e senza consenso marketing attivo.\n"
            "Da eseguire alla scadenza indicata nell'informativa. Aggiungi --conferma CANCELLA"
        )
    with get_sessionmaker()() as db:
        n = anonimizza_non_necessari(db)
    print(f"Cancellate {n} iscrizioni.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("crea-tabelle").set_defaults(fn=crea_tabelle)
    sub.add_parser("genera-codici", help="Codici opachi per i QR delle zone").set_defaults(
        fn=genera_codici
    )
    sub.add_parser("stats").set_defaults(fn=stats)
    p = sub.add_parser("reset", help="Cancella iscrizioni ed estrazioni (es. dopo i test)")
    p.add_argument("--conferma", default="")
    p.set_defaults(fn=reset)
    p = sub.add_parser("retention", help="Cancella i dati non più necessari (fine conservazione)")
    p.add_argument("--conferma", default="")
    p.set_defaults(fn=retention)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
