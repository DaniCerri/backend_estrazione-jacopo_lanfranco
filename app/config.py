from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Zone di posti della serata: id interno -> etichetta mostrata
ZONE: dict[str, str] = {
    "normale": "Normale",
    "premium": "Premium",
    "vip": "VIP",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    admin_password: str = Field(min_length=10)
    secret_key: str = Field(min_length=32)
    # Codice opaco contenuto nel QR (?z=<codice>) -> id zona
    zone_codes: dict[str, str] = {}
    cookie_secure: bool = True
    # Versione dei testi legali mostrati dal front-end, salvata con ogni iscrizione
    informativa_versione: str = "1.0"
    # URL pubblico del sito: serve per i link di disiscrizione nell'export
    public_base_url: str = "http://localhost:5173"
    rate_limit_per_minute: int = 120
    debug: bool = False

    @field_validator("database_url")
    @classmethod
    def _usa_psycopg(cls, v: str) -> str:
        # Railway espone postgres:// o postgresql:// -> driver psycopg 3
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @field_validator("zone_codes")
    @classmethod
    def _zone_valide(cls, v: dict[str, str]) -> dict[str, str]:
        sconosciute = set(v.values()) - ZONE.keys()
        if sconosciute:
            raise ValueError(f"Zone sconosciute in ZONE_CODES: {sorted(sconosciute)}")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
