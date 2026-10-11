import os

os.environ.update(
    DATABASE_URL="sqlite:///:memory:",
    ADMIN_PASSWORD="password-di-test",
    SECRET_KEY="x" * 40,
    ZONE_CODES='{"qr-n":"normale","qr-p":"premium","qr-v":"vip"}',
    COOKIE_SECURE="false",
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app.main import app
from app.models import Base
from app.security import limiter_iscrizioni, limiter_login_globale, limiter_login_ip


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[db_module.get_db] = override
    for limiter in (limiter_iscrizioni, limiter_login_ip, limiter_login_globale):
        limiter.reset()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin(client):
    r = client.post("/admin/login", data={"password": "password-di-test"}, follow_redirects=False)
    assert r.status_code == 303
    return client


def iscrizione(n: int = 1, **kw) -> dict:
    dati = {
        "nome": "Mario",
        "cognome": f"Rossi{n}",
        "telefono": f"+39 333 {1000000 + n}",
        "email": f"mario{n}@example.com",
        "accetta_regolamento": True,
        "accetta_privacy": True,
        "zona_codice": "qr-n",
    }
    dati.update(kw)
    return dati
