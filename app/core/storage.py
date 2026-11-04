"""Files kept on the server's disk, e.g. tute PDFs. Only this module knows where they live,
so moving to cloud storage later means changing this file only."""

from pathlib import Path
from uuid import uuid4

from app.core.config import settings


def _root() -> Path:
    return Path(settings.storage_dir).resolve()


def save(folder: str, data: bytes, suffix: str) -> str:
    """Stores the bytes and returns the name to keep in the database."""
    name = f"{folder}/{uuid4().hex}{suffix}"
    path = _root() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return name


def path_of(name: str) -> Path:
    path = (_root() / name).resolve()
    if _root() not in path.parents:
        raise ValueError("Bad file name")
    return path


def delete(name: str) -> None:
    path_of(name).unlink(missing_ok=True)
