import pytest
from sqlalchemy import create_engine, inspect, text

from app.schema import prepara_schema

VECCHIA = "CREATE TABLE iscrizioni (id INTEGER PRIMARY KEY, nome VARCHAR(80), consenso_privacy BOOLEAN)"


def test_ricrea_schema_vecchio_se_vuoto():
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(text(VECCHIA))
    prepara_schema(engine)
    colonne = {c["name"] for c in inspect(engine).get_columns("iscrizioni")}
    assert "presa_visione_privacy" in colonne and "consenso_privacy" not in colonne


def test_non_tocca_schema_vecchio_con_dati():
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(text(VECCHIA))
        c.execute(text("INSERT INTO iscrizioni (nome) VALUES ('Anna')"))
    with pytest.raises(RuntimeError, match="1 iscrizioni"):
        prepara_schema(engine)
    with engine.connect() as c:
        assert c.scalar(text("SELECT COUNT(*) FROM iscrizioni")) == 1


def test_schema_attuale_invariato():
    engine = create_engine("sqlite://")
    prepara_schema(engine)
    with engine.begin() as c:
        c.execute(text("INSERT INTO impostazioni (chiave, valore) VALUES ('x', '1')"))
    prepara_schema(engine)
    with engine.connect() as c:
        assert c.scalar(text("SELECT COUNT(*) FROM impostazioni")) == 1
