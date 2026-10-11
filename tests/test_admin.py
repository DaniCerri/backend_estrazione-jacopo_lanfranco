import csv
import hashlib
import io
import re

from app.models import Estrazione, EventoAdmin, Iscrizione
from tests.conftest import iscrizione, sessione


def _righe_csv(testo: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(testo.lstrip("﻿")), delimiter=";"))


def test_admin_richiede_login(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"
    assert client.get("/admin/api/stats").status_code == 401
    for url in ("/admin/export/marketing.csv", "/admin/export/in-gara.csv"):
        assert client.get(url, follow_redirects=False).status_code == 303
    assert client.post("/admin/estrazioni", follow_redirects=False).status_code == 303


def test_login_errato_registrato(client):
    assert client.post("/admin/login", data={"password": "sbagliata"}).status_code == 401
    assert sessione().query(EventoAdmin).filter_by(azione="login_fallito").count() == 1


def test_cookie_falsificato(client):
    client.cookies.set("cb_admin", "falso", path="/admin")
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_dashboard_e_stats(client, admin):
    client.post("/api/iscrizioni", json=iscrizione(1, zona_codice="qr-v", accetta_marketing=True))
    client.post("/api/iscrizioni", json=iscrizione(2))
    s = admin.get("/admin/api/stats").json()
    assert s["totale"] == 2 and s["per_zona"]["vip"] == 1 and s["marketing"] == 1
    assert s["in_gara"] == 2 and len(s["in_gara_hash"]) == 64
    r = admin.get("/admin")
    assert r.status_code == 200 and "Rossi1" in r.text
    assert r.headers["cache-control"] == "no-store"


def test_estrazione_vincitore_e_riserve_esclusi_dopo(client, admin):
    for n in range(5):
        client.post("/api/iscrizioni", json=iscrizione(n, zona_codice=["qr-n", "qr-v"][n % 2]))
    r = admin.post("/admin/estrazioni", data={"riserve": "2"}, follow_redirects=False)
    assert r.status_code == 303 and "e=1" in r.headers["location"]

    db = sessione()
    e1 = db.get(Estrazione, 1)
    # Nessun filtro per zona: in gara tutti
    assert e1.pool_size == 5 and len(e1.estratti) == 3
    assert len(e1.pool_hash) == 64 and e1.versione_software.startswith("chef-battle-backend@")
    ids1 = {x.iscrizione_id for x in e1.estratti}
    assert len(ids1) == 3

    admin.post("/admin/estrazioni", data={"riserve": "5"})
    db.expire_all()
    e2 = db.get(Estrazione, 2)
    assert e2.pool_size == 2
    assert ids1.isdisjoint({x.iscrizione_id for x in e2.estratti})

    r = admin.post("/admin/estrazioni", data={}, follow_redirects=False)
    assert "pool_vuoto" in r.headers["location"]

    # Annullare richiede motivo, resta nel log e rimette in gara
    r = admin.post("/admin/estrazioni/1/annulla", data={})
    assert r.status_code == 422
    admin.post("/admin/estrazioni/1/annulla", data={"motivo": "estrazione di prova"})
    admin.post("/admin/estrazioni", data={"riserve": "0"})
    db.expire_all()
    e1, e3 = db.get(Estrazione, 1), db.get(Estrazione, 3)
    assert e1.annullata and e1.motivo_annullamento == "estrazione di prova" and len(e1.estratti) == 3
    assert e3.pool_size == 3 and e3.estratti[0].iscrizione_id in ids1
    azioni = [ev.azione for ev in db.query(EventoAdmin).order_by(EventoAdmin.id)]
    assert azioni.count("estrazione") == 3 and "annullamento" in azioni


def test_estrazione_rifiutata_se_lista_cambiata(client, admin):
    client.post("/api/iscrizioni", json=iscrizione(1))
    hash_letto = admin.get("/admin/api/stats").json()["in_gara_hash"]
    client.post("/api/iscrizioni", json=iscrizione(2))
    r = admin.post("/admin/estrazioni", data={"hash_atteso": hash_letto}, follow_redirects=False)
    assert "lista_cambiata" in r.headers["location"]
    nuovo = admin.get("/admin/api/stats").json()["in_gara_hash"]
    r = admin.post("/admin/estrazioni", data={"hash_atteso": nuovo}, follow_redirects=False)
    assert "e=1" in r.headers["location"]


def test_export_in_gara_ricalcola_hash(client, admin):
    for n in range(4):
        client.post("/api/iscrizioni", json=iscrizione(n))
    admin.post("/admin/estrazioni", data={"riserve": "0"})
    righe = _righe_csv(admin.get("/admin/export/in-gara.csv").text)
    assert righe[0] == ["id", "nominativo", "zona", "data_iscrizione"]
    assert len(righe) == 4  # intestazione + 3 rimasti in gara
    assert not any("@" in c for r in righe for c in r)  # niente recapiti
    ids = ",".join(r[0] for r in righe[1:])
    assert hashlib.sha256(ids.encode()).hexdigest() == admin.get("/admin/api/stats").json()["in_gara_hash"]


def test_verbale_estrazione(client, admin):
    client.post("/api/iscrizioni", json=iscrizione(1))
    admin.post("/admin/estrazioni", data={"riserve": "0"})
    testo = admin.get("/admin/estrazioni/1/verbale.csv").text
    assert "sha256_lista" in testo and "vincitore;Mario Rossi1" in testo


def test_elimina_richiede_motivo_e_mantiene_log(client, admin):
    client.post("/api/iscrizioni", json=iscrizione(1))
    admin.post("/admin/estrazioni", data={"riserve": "0"})
    assert admin.post("/admin/iscrizioni/1/elimina", data={}).status_code == 422
    admin.post("/admin/iscrizioni/1/elimina", data={"motivo": "richiesta dell'interessato"})
    assert admin.get("/admin/api/stats").json()["totale"] == 0
    r = admin.get("/admin?e=1")
    assert "Mario Rossi1" in r.text and "richiesta dell&#39;interessato" in r.text


def test_export_marketing_solo_consensi_attivi_con_link_revoca(client, admin):
    client.post("/api/iscrizioni", json=iscrizione(1, accetta_marketing=True))
    client.post("/api/iscrizioni", json=iscrizione(2, accetta_marketing=False))
    client.post("/api/iscrizioni", json=iscrizione(3, accetta_marketing=True))
    admin.post("/admin/iscrizioni/3/revoca-marketing")
    righe = _righe_csv(admin.get("/admin/export/marketing.csv").text)
    assert [r[2] for r in righe[1:]] == ["mario1@example.com"]
    link = righe[1][-1]
    assert "/api/disiscrizione?t=" in link

    # Link di revoca: GET non revoca, POST sì
    token = link.split("t=")[1]
    assert client.get(f"/api/disiscrizione?t={token}").status_code == 200
    assert admin.get("/admin/api/stats").json()["marketing"] == 1
    r = client.post("/api/disiscrizione", data={"t": token})
    assert r.status_code == 200 and "Fatto" in r.text
    assert admin.get("/admin/api/stats").json()["marketing"] == 0
    assert client.post("/api/disiscrizione", data={"t": "falso"}).status_code == 400

    tutti = _righe_csv(admin.get("/admin/export/iscritti.csv").text)
    assert len(tutti) == 4 and "ip" in tutti[0]


def test_retention(client, admin):
    client.post("/api/iscrizioni", json=iscrizione(1, accetta_marketing=True))
    for n in range(2, 6):
        client.post("/api/iscrizioni", json=iscrizione(n))
    admin.post("/admin/estrazioni", data={"riserve": "1"})
    from app.services import anonimizza_non_necessari

    db = sessione()
    estratti = {x.iscrizione_id for x in db.get(Estrazione, 1).estratti}
    anonimizza_non_necessari(db)
    rimasti = {i.id for i in db.query(Iscrizione)}
    assert rimasti == estratti | {1}
