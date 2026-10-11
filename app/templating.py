from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

from app.config import ZONE

ROMA = ZoneInfo("Europe/Rome")


def ora_locale(dt: datetime | None, formato: str = "%d/%m %H:%M:%S") -> str:
    return dt.astimezone(ROMA).strftime(formato) if dt else ""


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["ZONE"] = ZONE
templates.env.filters["ora"] = ora_locale
