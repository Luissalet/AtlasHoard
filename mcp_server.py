"""Minimal stdio MCP bridge; all data operations go to the local HTTP owner."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

from atlas_hoard.contracts import catalogue
from atlas_hoard.hoard_link._hubclient import fetch_detailed


def main():
    base = os.environ.get("ATLAS_URL", "http://127.0.0.1:5203").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password:
        raise ValueError("Atlas MCP only connects to local HTTP")
    path = Path(os.environ.get("ATLAS_TOKEN_FILE", str(Path(__file__).parent / "data/mcp-token")))
    for line in sys.stdin:
        req = None
        try:
            req = json.loads(line)
            if "id" not in req:
                continue
            method, params = req.get("method"), req.get("params", {})
            if method == "initialize":
                result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "atlas-hoard", "version": "0.1.0"}}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": catalogue()}
            elif method == "tools/call":
                health_code, health, _ = fetch_detailed(base + "/api/health", timeout=5)
                if health_code != 200 or not isinstance(health, dict) or health.get("service") != "atlas-hoard":
                    raise RuntimeError("The configured local port is not Atlas")
                code, body, why = fetch_detailed(base + "/api/agent/call", {"name": params.get("name"), "arguments": params.get("arguments", {}), "caller": "hub"},
                    method="POST", timeout=120, headers={"Authorization": "Bearer " + path.read_text(encoding="utf-8-sig").strip()})
                result = {"content": [{"type": "text", "text": json.dumps(body.get("result", body) if isinstance(body, dict) else {"ok": False, "error": why}, ensure_ascii=False)}],
                          "isError": code != 200}
            else:
                print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "Method not found"}}), flush=True)
                continue
            print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}, ensure_ascii=False), flush=True)
        except json.JSONDecodeError:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}), flush=True)
        except Exception:
            if isinstance(req, dict) and "id" in req:
                print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32603, "message": "Local bridge request failed"}}), flush=True)


if __name__ == "__main__":
    main()
