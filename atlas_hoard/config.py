"""Process-level configuration read from the environment (never from the DB)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .guard import parse_allowed_hosts

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 5193


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(raw: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


def _float(raw: str, default: float, low: float, high: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


@dataclass
class Config:
    """Everything the process needs before the database exists."""

    data_dir: Path = field(default_factory=lambda: REPO_ROOT / "data")
    port: int = DEFAULT_PORT
    port_strict: bool = False
    allowed_hosts: tuple[str, ...] = ()
    data_dir_configured: bool = False
    geocode: bool = True  # ATLAS_GEOCODE=0 switches Nominatim off for good (the UI cannot turn it back on)
    allow_private_urls: bool = False  # ATLAS_ALLOW_PRIVATE_URLS=1: URL capture may reach loopback / LAN hosts
    file_roots: tuple[Path, ...] = ()  # ATLAS_FILE_ROOTS: when set, local-file sources must live under one of them
    fetch_timeout_s: float = 20.0
    fetch_max_bytes: int = 4_000_000
    stale_days: int = 730  # an observation older than this with no valid_to is marked stale
    user_agent: str = "AtlasHoard/0.1 (local research workspace; https://github.com/Luissalet)"
    wikidata_url: str = "https://www.wikidata.org/w/api.php"
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "atlas.db"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "mcp-token"

    @property
    def url_path(self) -> Path:
        return self.data_dir / "url"

    @property
    def backend_json_path(self) -> Path:
        return self.data_dir / "backend.json"

    @classmethod
    def from_env(cls) -> "Config":
        raw_dir = _env("ATLAS_DATA_DIR")
        port = _int(_env("ATLAS_PORT") or _env("PORT") or str(DEFAULT_PORT), DEFAULT_PORT, 1, 65535)
        roots = tuple(Path(p).expanduser() for p in _env("ATLAS_FILE_ROOTS").split(os.pathsep) if p.strip())
        return cls(
            data_dir=Path(raw_dir).expanduser() if raw_dir else REPO_ROOT / "data",
            port=port,
            port_strict=_env("PORT_STRICT") == "1",
            allowed_hosts=parse_allowed_hosts(_env("ATLAS_ALLOWED_HOSTS")),
            data_dir_configured=bool(raw_dir),
            geocode=_env("ATLAS_GEOCODE", "1") != "0",
            allow_private_urls=_env("ATLAS_ALLOW_PRIVATE_URLS") == "1",
            file_roots=roots,
            fetch_timeout_s=_float(_env("ATLAS_FETCH_TIMEOUT_S"), 20.0, 2.0, 120.0),
            stale_days=_int(_env("ATLAS_STALE_DAYS"), 730, 30, 36500),
        )
