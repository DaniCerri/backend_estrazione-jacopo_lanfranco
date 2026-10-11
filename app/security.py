import hashlib
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import get_settings

ADMIN_COOKIE = "cb_admin"
ADMIN_SESSIONE_SECONDI = 12 * 60 * 60


def client_ip(request: Request) -> str:
    # Dietro Railway edge + nginx: il primo indirizzo di X-Forwarded-For è il client.
    # Falsificabile, quindi usato solo per rate limit, mai per decisioni di sicurezza.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


class RateLimiter:
    """Finestra scorrevole in memoria. Basta un solo processo uvicorn."""

    def __init__(self, limite: int, finestra_secondi: float) -> None:
        self.limite = limite
        self.finestra = finestra_secondi
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def consenti(self, chiave: str) -> bool:
        ora = time.monotonic()
        with self._lock:
            q = self._hits[chiave]
            while q and q[0] <= ora - self.finestra:
                q.popleft()
            if len(q) >= self.limite:
                return False
            q.append(ora)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# Tutta la sala può uscire dallo stesso NAT: limite largo, la difesa vera è il dedup.
limiter_iscrizioni = RateLimiter(get_settings().rate_limit_per_minute, 60)
limiter_login_ip = RateLimiter(10, 15 * 60)
limiter_login_globale = RateLimiter(50, 15 * 60)


def _serializer() -> URLSafeTimedSerializer:
    s = get_settings()
    # Il salt dipende dalla password: cambiarla invalida tutte le sessioni
    impronta = hashlib.sha256(s.admin_password.encode()).hexdigest()[:16]
    return URLSafeTimedSerializer(s.secret_key, salt=f"admin:{impronta}")


def _serializer_disiscrizione() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="disiscrizione")


def crea_token_disiscrizione(iscrizione_id: int) -> str:
    return _serializer_disiscrizione().dumps(iscrizione_id)


def leggi_token_disiscrizione(token: str) -> int | None:
    try:
        return int(_serializer_disiscrizione().loads(token))
    except (BadSignature, ValueError, TypeError):
        return None


def crea_token_admin() -> str:
    return _serializer().dumps({"admin": True})


def is_admin(request: Request) -> bool:
    token = request.cookies.get(ADMIN_COOKIE)
    if not token:
        return False
    try:
        _serializer().loads(token, max_age=ADMIN_SESSIONE_SECONDI)
    except BadSignature:
        return False
    return True


def richiedi_admin(request: Request) -> None:
    if not is_admin(request):
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})


def richiedi_admin_api(request: Request) -> None:
    if not is_admin(request):
        raise HTTPException(status_code=401)
