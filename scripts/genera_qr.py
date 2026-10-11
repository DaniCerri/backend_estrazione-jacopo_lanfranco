"""Genera un QR per zona (SVG per la stampa + PNG di anteprima).

Uso: uv run python scripts/genera_qr.py https://dominio-del-sito.it [--out qr]
I codici arrivano da ZONE_CODES (.env o variabile d'ambiente).
"""

import argparse
from pathlib import Path
from urllib.parse import urlencode

import segno

from app.config import ZONE, get_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", help="URL pubblico del sito, es. https://chefbattle.it")
    parser.add_argument("--out", default="qr", type=Path)
    args = parser.parse_args()

    codici = get_settings().zone_codes
    mancanti = set(ZONE) - set(codici.values())
    if mancanti:
        raise SystemExit(f"ZONE_CODES non copre: {sorted(mancanti)}")

    args.out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    for codice, zona in codici.items():
        url = f"{base}/?{urlencode({'z': codice})}"
        # Correzione errori "Q": regge stampe rovinate e luce scarsa in sala
        qr = segno.make(url, error="q")
        qr.save(args.out / f"qr-{zona}.svg", scale=10, border=4)
        qr.save(args.out / f"qr-{zona}.png", scale=12, border=4)
        print(f"{ZONE[zona]:<8} {url}")


if __name__ == "__main__":
    main()
