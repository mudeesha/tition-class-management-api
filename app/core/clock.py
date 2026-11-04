"""The current local time. Tests replace `now` to check date rules (late joins, door scans)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings

_zone = ZoneInfo(settings.timezone)


def now() -> datetime:
    return datetime.now(_zone)


def today() -> date:
    return now().date()
