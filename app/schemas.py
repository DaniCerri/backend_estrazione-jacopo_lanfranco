import re
from typing import Annotated, Literal

import phonenumbers
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]

INSTAGRAM_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")

# Messaggi per campo restituiti al form in caso di errore di validazione
MESSAGGI_ERRORE = {
    "nome": "Inserisci un nome valido (minimo 2 caratteri).",
    "cognome": "Inserisci un cognome valido (minimo 2 caratteri).",
    "telefono": "Inserisci un numero valido (es. +39 333 1234567).",
    "email": "Formato email non valido.",
    "instagram": "Nickname Instagram non valido.",
    "accetta_regolamento": "È necessario accettare il Regolamento della serata.",
    "accetta_privacy": "È necessario confermare la presa visione della Privacy Policy.",
    "zona": "Seleziona la tua zona.",
}


class IscrizioneIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nome: Nome
    cognome: Nome
    telefono: str = Field(max_length=30)
    email: EmailStr = Field(max_length=254)
    instagram: str | None = Field(default=None, max_length=40)
    accetta_regolamento: Literal[True]
    accetta_privacy: Literal[True]
    accetta_marketing: bool = False
    # Codice opaco letto dal QR; in alternativa zona scelta a mano
    zona_codice: str | None = Field(default=None, max_length=40)
    zona: str | None = Field(default=None, max_length=20)
    # Honeypot: campo nascosto nel form, solo i bot lo compilano
    website: str | None = Field(default=None, max_length=200)

    @field_validator("telefono")
    @classmethod
    def _normalizza_telefono(cls, v: str) -> str:
        try:
            numero = phonenumbers.parse(v, "IT")
        except phonenumbers.NumberParseException as e:
            raise ValueError("numero non valido") from e
        if not phonenumbers.is_valid_number(numero):
            raise ValueError("numero non valido")
        return phonenumbers.format_number(numero, phonenumbers.PhoneNumberFormat.E164)

    @field_validator("email")
    @classmethod
    def _email_minuscola(cls, v: str) -> str:
        return v.lower()

    @field_validator("instagram")
    @classmethod
    def _normalizza_instagram(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lstrip("@").strip()
        if not v:
            return None
        if not INSTAGRAM_RE.match(v):
            raise ValueError("nickname non valido")
        return v
