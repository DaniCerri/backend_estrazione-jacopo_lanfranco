# Chef Battle — Back-end estrazione

FastAPI + Postgres. API iscrizioni per il form e dashboard `/admin` per l'estrazione live.

## Sviluppo

```bash
cp .env.example .env   # imposta ADMIN_PASSWORD, SECRET_KEY, COOKIE_SECURE=false
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
```

Senza `DATABASE_URL` usa SQLite locale (`dev.db`). Le tabelle vengono create all'avvio.

## Endpoint

| Metodo | Path | Note |
|---|---|---|
| POST | `/api/iscrizioni` | 201 iscritto · 200 già iscritto (stessa persona) · 409 duplicato · 403 chiuse · 422 `{campi}` · 429 |
| GET | `/api/stato` | iscrizioni aperte + zone |
| GET | `/api/health` | healthcheck Railway |
| GET | `/admin` | dashboard (login con `ADMIN_PASSWORD`) |

Payload iscrizione: `nome, cognome, telefono, email, instagram?, accetta_regolamento, accetta_privacy, accetta_marketing, zona_codice? | zona?, website` (honeypot, lasciare vuoto).

## Zone e QR

```bash
uv run python -m app.manage genera-codici          # -> ZONE_CODES={...}
uv run python scripts/genera_qr.py https://dominio  # -> qr/qr-<zona>.svg/.png
```

Il QR apre `https://dominio/?z=<codice>`. Senza codice il form chiede la zona.

## Comandi

```bash
python -m app.manage stats
python -m app.manage reset --conferma CANCELLA-TUTTO   # dopo le prove, prima dell'evento
```

Su Railway: `railway run python -m app.manage <comando>`.

## Deploy Railway

Servizio da questo repo (Dockerfile) + plugin Postgres, region EU West.
Variabili: `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `ADMIN_PASSWORD`, `SECRET_KEY`, `ZONE_CODES`, `INFORMATIVA_VERSIONE`.
Il front-end (nginx) fa da proxy per `/api` e `/admin` verso `back-end.railway.internal`: il browser vede un solo dominio.
