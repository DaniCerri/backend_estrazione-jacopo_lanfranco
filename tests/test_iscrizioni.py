from tests.conftest import iscrizione


def test_iscrizione_da_qr(client):
    r = client.post("/api/iscrizioni", json=iscrizione(zona_codice="qr-v", instagram="@Mario.R"))
    assert r.status_code == 201
    assert r.json() == {"stato": "iscritto"}


def test_salva_prova_tecnica(client, admin):
    client.post("/api/iscrizioni", json=iscrizione(), headers={"user-agent": "UA-test"})
    assert "UA-test" not in admin.get("/admin").text  # non esposto in dashboard
    from app.models import Iscrizione
    from tests.conftest import sessione

    i = sessione().get(Iscrizione, 1)
    assert i.user_agent == "UA-test" and i.ip
    assert i.dichiarazione_maggiore_eta and i.informativa_versione == "1.0"
    assert i.consenso_menzione_instagram is False


def test_menzione_instagram_solo_con_nickname(client):
    from app.models import Iscrizione
    from tests.conftest import sessione

    client.post("/api/iscrizioni", json=iscrizione(1, consenso_menzione_instagram=True))
    client.post("/api/iscrizioni", json=iscrizione(2, instagram="chef.fan", consenso_menzione_instagram=True))
    db = sessione()
    assert db.get(Iscrizione, 1).consenso_menzione_instagram is False
    assert db.get(Iscrizione, 2).consenso_menzione_instagram is True


def test_maggiore_eta_obbligatoria(client):
    r = client.post("/api/iscrizioni", json=iscrizione(accetta_maggiore_eta=False))
    assert r.status_code == 422 and "accetta_maggiore_eta" in r.json()["campi"]


def test_zona_manuale(client):
    r = client.post("/api/iscrizioni", json=iscrizione(zona_codice=None, zona="premium"))
    assert r.status_code == 201


def test_zona_mancante_o_codice_sconosciuto(client):
    r = client.post("/api/iscrizioni", json=iscrizione(zona_codice="falso"))
    assert r.status_code == 422
    assert "zona" in r.json()["campi"]


def test_validazione_campi(client):
    r = client.post(
        "/api/iscrizioni",
        json=iscrizione(telefono="123", email="no", nome="M", accetta_privacy=False),
    )
    assert r.status_code == 422
    assert set(r.json()["campi"]) == {"telefono", "email", "nome", "accetta_privacy"}


def test_telefono_normalizzato_e_dedup(client):
    assert client.post("/api/iscrizioni", json=iscrizione(1, telefono="333 100 0001")).status_code == 201
    # Stesso numero scritto diversamente, email diversa -> duplicato
    r = client.post(
        "/api/iscrizioni", json=iscrizione(1, telefono="+393331000001", email="altra@example.com")
    )
    assert r.status_code == 409
    assert r.json()["campo"] == "telefono"


def test_dedup_email_case_insensitive(client):
    client.post("/api/iscrizioni", json=iscrizione(1))
    r = client.post("/api/iscrizioni", json=iscrizione(2, email="MARIO1@example.com"))
    assert r.status_code == 409
    assert r.json()["campo"] == "email"


def test_reinvio_stessa_persona_idempotente(client):
    client.post("/api/iscrizioni", json=iscrizione(1))
    r = client.post("/api/iscrizioni", json=iscrizione(1))
    assert r.status_code == 200
    assert r.json() == {"stato": "gia_iscritto"}


def test_honeypot_non_salva(client, admin):
    r = client.post("/api/iscrizioni", json=iscrizione(website="http://spam"))
    assert r.status_code == 201
    assert admin.get("/admin/api/stats").json()["totale"] == 0


def test_iscrizioni_chiuse(client, admin):
    admin.post("/admin/iscrizioni/stato", data={"aperte": "false"})
    assert client.get("/api/stato").json()["aperte"] is False
    r = client.post("/api/iscrizioni", json=iscrizione())
    assert r.status_code == 403
    admin.post("/admin/iscrizioni/stato", data={"aperte": "true"})
    assert client.post("/api/iscrizioni", json=iscrizione()).status_code == 201
