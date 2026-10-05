"""Loopback-only stdlib HTTP server. No cloud, network disks, telemetry or CORS."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import json
import logging
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from . import __version__
from .contracts import catalogue
from .store import StoreError
from .hoard_link import family

UI = Path(__file__).parent / "ui"
MAX_BODY = 256 * 1024


def make_server(store, token, port=0):
    session = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, body, status=200, content_type="application/json; charset=utf-8", cookie=False):
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if cookie:
                self.send_header("Set-Cookie", f"atlas_session={session}; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()
            self.wfile.write(raw)

        def same_origin(self):
            host = self.headers.get("Host", "")
            if host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
                return False
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                return False
            origin = self.headers.get("Origin")
            return not origin or origin in ("http://" + host,)

        def authorized(self):
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer ") and secrets.compare_digest(auth[7:], token):
                return "agent"
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
            except Exception:
                logging.getLogger("atlas").exception("Local storage operation failed")
                return None
            value = cookies.get("atlas_session")
            if value and secrets.compare_digest(value.value, session):
                return "ui"
            return None

        def do_GET(self):
            if not self.same_origin():
                return self.reply({"ok": False, "error": "origin refused"}, 403)
            path = urlsplit(self.path).path
            if path == "/api/health":
                return self.reply({"ok": True, **family.health_block(), "service": "atlas-hoard", "version": __version__})
            if path == "/":
                return self.reply((UI / "index.html").read_bytes(), content_type="text/html; charset=utf-8", cookie=True)
            static = {"/icon.png": (UI / "icon.png", "image/png"),
                      "/app.js": (UI / "app.js", "text/javascript; charset=utf-8"),
                      "/style.css": (UI / "style.css", "text/css; charset=utf-8"),
                      "/hoard-theme.css": (Path(__file__).parent / "hoard_link/ui/hoard-theme.css", "text/css; charset=utf-8")}
            if path in static:
                file, mime = static[path]
                return self.reply(file.read_bytes(), content_type=mime)
            if not self.authorized():
                return self.reply({"ok": False, "error": "authentication required"}, 401)
            if path == "/api/agent/tools":
                return self.reply({"tools": catalogue(), "instructions": "Atlas is shared live filesystem storage. Open/save native files at returned paths. Project membership restricts API access; it is not an OS sandbox."})
            if path == "/api/status":
                return self.reply({"ok": True, "root": str(store.root), "version": __version__, **store.dispatch("atlas_projects", caller="ui")})
            return self.reply({"ok": False, "error": "not found"}, 404)

        def do_POST(self):
            identity = self.authorized()
            if not self.same_origin() or not identity:
                self.close_connection = True
                return self.reply({"ok": False, "error": "request refused"}, 403 if identity else 401)
            if urlsplit(self.path).path != "/api/agent/call":
                return self.reply({"ok": False, "error": "not found"}, 404)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    self.close_connection = True
                    return self.reply({"ok": False, "error": "body must be 1..256 KiB"}, 413)
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise StoreError("request must be an object")
                if identity == "agent" and not body.get("caller"):
                    raise StoreError("caller identity is required; an older Hub must be restarted after its contract update")
                caller = "ui" if identity == "ui" else body["caller"]
                # Direct Atlas token is its operator credential; Hub attests sibling
                # identity after authenticating that sibling's own token.
                tool = body.get("name") or body.get("tool")
                arguments = body.get("arguments", {})
                result = store.dispatch(tool, arguments, caller)
                family.record_call(tool, ok=True, caller=caller)
                return self.reply({"ok": True, "tool": tool, "result": result})
            except StoreError as exc:
                return self.reply({"ok": False, "error": str(exc)}, exc.status)
            except (ValueError, TypeError, KeyError):
                return self.reply({"ok": False, "error": "invalid request"}, 400)
            except Exception:
                logging.getLogger("atlas").exception("Local storage operation failed")
                return self.reply({"ok": False, "error": "storage operation failed; inspect local logs"}, 500)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
