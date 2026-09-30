"""Wiring: database, Hoard Link, the external providers (fetcher, Wikidata, Nominatim, family apps) and settings.

Every provider is injectable so the whole app runs offline in tests; the domain modules
(cases, sources, entities, relations, ...) take this object as their first argument.
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any, Callable

from . import APP_ID, SERVICE, __version__
from . import relations as relations_mod
from .config import Config
from .db import Database
from .enrichers.geocode import CachedGeocoder, NominatimGeocoder
from .enrichers.wikidata import HttpWikidataClient
from .errors import AtlasError
from .fetch import HttpFetcher
from .hoard_link import family
from .hoard_link.config import LinkConfig
from .util import jdump, jload

log = logging.getLogger("atlas")

DEFAULT_FAMILY_SOURCES = ["borges", "links"]
DEFAULT_FAMILY_TOOLS = {"borges": "library_search", "links": "search_links"}


def write_token(config: Config) -> str:
    """The MCP token is persistent: created once, reused on every later start."""
    config.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        existing = config.token_path.read_text(encoding="utf-8").strip()
    except OSError:
        existing = ""
    if len(existing) >= 32:
        return existing
    token = secrets.token_hex(32)
    config.token_path.write_text(token, encoding="utf-8")
    try:
        config.token_path.chmod(0o600)
    except OSError:
        pass
    return token


def write_url(config: Config) -> None:
    try:
        config.url_path.write_text(f"http://127.0.0.1:{config.port}", encoding="utf-8")
    except OSError:
        pass


class Services:
    def __init__(self, config: Config, *, link: Any = None, fetcher: Any = None, wikidata: Any = None, geocoder: Any = None,
                 family_call: Callable[..., dict] | None = None, emit_fn: Callable[[str, dict], None] | None = None,
                 clock_fn: Callable[[], float] = time.time):
        self.config = config
        self.clock = clock_fn
        self.started_at = time.time()
        config.data_dir.mkdir(parents=True, exist_ok=True)
        self.token = write_token(config)
        write_url(config)
        self.db = Database(config.db_path)
        relations_mod.seed_predicates(self.db)
        if link is not None:
            self.link_sync = link  # test double, already "sync-shaped"
            self._link = None
        else:
            from .hoard_link.link import Link
            link_config = LinkConfig.load(config.backend_json_path if config.backend_json_path.is_file() else None, app=APP_ID)
            self._link = Link(link_config)
            self.link_sync = self._link.sync
        self.fetcher = fetcher or HttpFetcher(timeout_s=config.fetch_timeout_s, max_bytes=config.fetch_max_bytes,
                                              user_agent=config.user_agent, allow_private=config.allow_private_urls)
        self.wikidata = wikidata or HttpWikidataClient(url=config.wikidata_url, user_agent=config.user_agent, timeout_s=config.fetch_timeout_s)
        self.geocoder = CachedGeocoder(self.db, geocoder or NominatimGeocoder(url=config.nominatim_url, user_agent=config.user_agent,
                                                                              timeout_s=config.fetch_timeout_s), clock=clock_fn)
        self._family_call = family_call or (lambda app, tool, args: family.call(app, tool, args, timeout=30.0))
        self._emit = emit_fn

    # ---------------- lifecycle ----------------
    def start(self) -> None:
        pass

    def stop(self) -> None:
        if self._link is not None:
            try:
                self.link_sync.close()
            except Exception:  # noqa: BLE001
                pass
        self.db.close()

    # ---------------- events ----------------
    def emit(self, type_: str, data: dict[str, Any]) -> None:
        """Announce something on the hub bus (ids and short titles only); never raises."""
        try:
            if self._emit is not None:
                self._emit(type_, data)
            else:
                family.emit(type_, data)
        except Exception:  # noqa: BLE001
            pass

    # ---------------- family ----------------
    def family_call(self, app: str, tool: str, arguments: dict) -> dict:
        """Call another app's tool through the hub; always returns ``{ok, result|error}``, never raises."""
        try:
            reply = self._family_call(app, tool, arguments)
            return reply if isinstance(reply, dict) else {"ok": True, "result": reply}
        except Exception as error:  # noqa: BLE001 - the hub or the app may simply not be running
            return {"ok": False, "error": f"{type(error).__name__}: {error}"}

    # ---------------- settings ----------------
    def geocode_enabled(self) -> bool:
        return self.config.geocode and self.db.get_setting("geocode_enabled", "1") != "0"

    def family_sources(self) -> list[str]:
        value = jload(self.db.get_setting("family_sources"), None)
        return [str(x) for x in value] if isinstance(value, list) else list(DEFAULT_FAMILY_SOURCES)

    def family_tools(self) -> dict[str, str]:
        value = jload(self.db.get_setting("family_tools"), None)
        tools = dict(DEFAULT_FAMILY_TOOLS)
        if isinstance(value, dict):
            tools.update({str(k): str(v) for k, v in value.items()})
        return tools

    def get_settings(self) -> dict[str, Any]:
        return {
            "geocode": {"enabled": self.geocode_enabled(), "env_disabled": not self.config.geocode, "setting": self.db.get_setting("geocode_enabled", "1") != "0"},
            "family_sources": self.family_sources(), "family_tools": self.family_tools(),
            "stale_days": self.config.stale_days, "allow_private_urls": self.config.allow_private_urls,
            "file_roots": [str(p) for p in self.config.file_roots],
        }

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        from . import history
        if "geocode_enabled" in patch:
            self.db.set_setting("geocode_enabled", "1" if patch["geocode_enabled"] else "0")
        if "family_sources" in patch:
            sources = patch["family_sources"]
            if not isinstance(sources, list) or not all(isinstance(x, str) and x.strip() for x in sources):
                raise AtlasError("family_sources must be a list of app ids.")
            self.db.set_setting("family_sources", jdump([s.strip().lower() for s in sources]))
        if "family_tools" in patch:
            tools = patch["family_tools"]
            if not isinstance(tools, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in tools.items()):
                raise AtlasError("family_tools must map an app id to the name of its search tool.")
            self.db.set_setting("family_tools", jdump({k.strip().lower(): v.strip() for k, v in tools.items()}))
        history.record(self, None, "settings.updated", "settings", None, "Settings updated: " + ", ".join(sorted(patch)))
        return self.get_settings()

    # ---------------- status ----------------
    def counts(self) -> dict[str, int]:
        one = lambda sql: self.db.one(sql)["c"]  # noqa: E731
        return {"cases": one("SELECT COUNT(*) c FROM cases"), "sources": one("SELECT COUNT(*) c FROM sources"),
                "entities": one("SELECT COUNT(*) c FROM entities WHERE merged_into IS NULL"),
                "relations": one("SELECT COUNT(*) c FROM relations"), "hypotheses": one("SELECT COUNT(*) c FROM hypotheses")}

    def status(self) -> dict[str, Any]:
        try:
            model = self.link_sync.status()
        except Exception as error:  # noqa: BLE001
            model = {"error": f"{type(error).__name__}: {error}"}
        return {"service": SERVICE, "version": __version__, "counts": self.counts(), "model": model,
                "geocode": self.get_settings()["geocode"], "family": {**family.status(), "sources": self.family_sources()},
                "uptime_s": int(time.time() - self.started_at), "db": str(self.config.db_path) if self.config.data_dir_configured else "data/atlas.db"}
