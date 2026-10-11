import re

from tests.conftest import iscrizione



def test_admin_richiede_login(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"
    assert client.get("/admin/api/stats").status_code == 401
    assert client.get("/admin/export/marketing.csv", follow_redirects=False).status_code == 303


def test_login_errato(client):
    r = client.post("/admin/login", data={"password": "sbagliata"})
    assert r.status_code == 401


def test_cookie_falsificato(client):
    client.cookies.set("cb_admin", "falso", path="/admin")
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_dashboard_e_stats(client, admin):
    client.post("/api/iscrizioni", json=iscrizione(1, zona_codice="qr-v", accetta_marketing=True))
    client.post("/api/iscrizioni", json=iscrizione(2))
    s = admin.get("/admin/api/stats").json()
    assert s["totale"] == 2 and s["per_zona"]["vip"] == 1 and s["marketing"] == 1
    r = admin.get("/admin")
    assert r.status_code == 200 and "Rossi1" in r.text
    assert r.headers["cache-control"] == "no-store"


def test_estrazione_vincitore_e_riserve_esclusi_dopo(client, admin):
    for n in range(5):
        client.post("/api/iscrizioni", json=iscrizione(n))
    r = admin.post("/admin/estrazioni", data={"zona": "", "riserve": "2"}, follow_redirects=False)
    assert r.status_code == 303 and "e=1" in r.headers["location"]

    from app.models import Estrazione
    from app.db import get_db
    from app.main import app

    db = next(app.dependency_overrides[get_db]())
    e1 = db.get(Estrazione, 1)
    assert e1.pool_size == 5 and len(e1.estratti) == 3
    assert len(e1.pool_hash) == 64
    ids1 = {x.iscrizione_id for x in e1.estratti}
    assert len(ids1) == 3

    admin.post("/admin/estrazioni", data={"zona": "", "riserve": "5"})
    db.expire_all()
    e2 = db.get(Estrazione, 2)
    assert e2.pool_size == 2
    assert ids1.isdisjoint({x.iscrizione_id for x in e2.estratti})

    r = admin.post("/admin/estrazioni", data={"zona": ""}, follow_redirects=False)
    assert "pool_vuoto" in r.headers["location"]

    # Annullare rimette in gara
    admin.post("/admin/estrazioni/1/annulla")
    admin.post("/admin/estrazioni", data={"zona": "", "riserve": "0"})
    db.expire_all()
    e3 = db.get(Estrazione, 3)
    assert e3.pool_size == 3 and e3.estratti[0].iscrizione_id in ids1


def test_estrazione_filtrata_per_zona(client, admin):
    client.post("/api/iscrizioni", json=iscrizione(1, zona_codice="qr-v"))
    for n in range(2, 6):
        client.post("/api/iscrizioni", json=iscrizione(n))
    r = admin.post("/admin/estrazioni", data={"zona": "vip", "riserve": "3"})
    assert "Rossi1" in re.search(r'class="vincitore">([^<]+)<', r.text).group(1)
    assert "1 in gara" in r.text


def test_elimina_iscrizione_mantiene_log(client, admin):
    client.post("/api/iscrizioni", json=iscrizione(1))
    admin.post("/admin/estrazioni", data={"riserve": "0"})
    admin.post("/admin/iscrizioni/1/elimina")
    assert admin.get("/admin/api/stats").json()["totale"] == 0
    r = admin.get("/admin?e=1")
    assert "Mario Rossi1" in r.text


def test_export_marketing_solo_consenzienti(client, admin):
    client.post("/api/iscrizioni", json=iscrizione(1, accetta_marketing=True))
    client.post("/api/iscrizioni", json=iscrizione(2, accetta_marketing=False))
    r = admin.get("/admin/export/marketing.csv")
    assert r.status_code == 200
    assert r.text.startswith("﻿nome;cognome")
    assert "mario1@example.com" in r.text and "mario2@example.com" not in r.text
    tutti = admin.get("/admin/export/iscritti.csv").text
    assert "mario1@example.com" in tutti and "mario2@example.com" in tutti
