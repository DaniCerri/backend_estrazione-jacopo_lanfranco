from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def adesso() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Iscrizione(Base):
    __tablename__ = "iscrizioni"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    cognome: Mapped[str] = mapped_column(String(80))
    # E.164 normalizzato: una sola iscrizione per numero
    telefono: Mapped[str] = mapped_column(String(20), unique=True)
    # Sempre minuscola: una sola iscrizione per email
    email: Mapped[str] = mapped_column(String(254), unique=True)
    instagram: Mapped[str | None] = mapped_column(String(30))
    zona: Mapped[str] = mapped_column(String(20), index=True)
    # True se la zona arriva dal QR, False se scelta a mano nel form
    zona_da_qr: Mapped[bool] = mapped_column(Boolean)

    # Prova dei consensi: valori, versione dei testi accettati e momento (created_at)
    consenso_regolamento: Mapped[bool] = mapped_column(Boolean)
    consenso_privacy: Mapped[bool] = mapped_column(Boolean)
    consenso_marketing: Mapped[bool] = mapped_column(Boolean, index=True)
    informativa_versione: Mapped[str] = mapped_column(String(20))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=adesso)


class Estrazione(Base):
    __tablename__ = "estrazioni"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=adesso)
    # None = tutte le zone
    zona_filtro: Mapped[str | None] = mapped_column(String(20))
    # Partecipanti in gara al momento dell'estrazione
    pool_size: Mapped[int] = mapped_column(Integer)
    # SHA-256 degli ID in gara ordinati: fotografia verificabile della lista estratta
    pool_hash: Mapped[str] = mapped_column(String(64))
    # Un'estrazione annullata (es. prova) rimette in gara i suoi estratti
    annullata: Mapped[bool] = mapped_column(Boolean, default=False)

    estratti: Mapped[list["Estratto"]] = relationship(
        back_populates="estrazione",
        order_by="Estratto.posizione",
        cascade="all, delete-orphan",
    )


class Estratto(Base):
    __tablename__ = "estratti"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estrazione_id: Mapped[int] = mapped_column(ForeignKey("estrazioni.id", ondelete="CASCADE"))
    # SET NULL: se l'iscrizione viene cancellata il log resta
    iscrizione_id: Mapped[int | None] = mapped_column(
        ForeignKey("iscrizioni.id", ondelete="SET NULL"), index=True
    )
    # 0 = vincitore, 1..N = riserve in ordine
    posizione: Mapped[int] = mapped_column(Integer)
    # Copia del nominativo per l'integrità del log
    nominativo: Mapped[str] = mapped_column(String(170))

    estrazione: Mapped[Estrazione] = relationship(back_populates="estratti")
    iscrizione: Mapped[Iscrizione | None] = relationship()


class Impostazione(Base):
    __tablename__ = "impostazioni"

    chiave: Mapped[str] = mapped_column(String(50), primary_key=True)
    valore: Mapped[str] = mapped_column(String(200))
