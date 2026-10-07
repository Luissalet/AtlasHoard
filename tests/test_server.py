import json
import threading
import urllib.error
import urllib.request
import pytest

from atlas_hoard.store import Workspace
from atlas_hoard.server import make_server
from atlas_hoard.hoard_link import family


def http(base, path, body=None, headers=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers or {})
    try:
        response = opener.open(request, timeout=3)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        return response.status, raw, response.headers


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setitem(family._state, "enabled", False)
    store = Workspace(tmp_path / "private", tmp_path / "disk")
    server = make_server(store, "operator-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", store
    server.shutdown()
    server.server_close()
    thread.join(3)
    store.close()


def test_health_is_public_catalogue_and_calls_are_authenticated(app):
    base, store = app
    health = json.loads(http(base, "/api/health")[1])
    assert health["service"] == "atlas-hoard" and health["version"] == "0.1.0"
    assert http(base, "/api/agent/tools")[0] == 401
    assert http(base, "/api/agent/call", {"name": "atlas_projects"})[0] == 401
    code, body, _ = http(base, "/api/agent/tools", headers={"Authorization": "Bearer operator-token"})
    tools = json.loads(body)["tools"]
    assert code == 200 and len(tools) == 12
    linked = next(tool for tool in tools if tool["name"] == "atlas_file_link_source")
    assert linked["inputSchema"]["required"] == ["project_id", "source_path"]


def test_external_file_link_and_resolve_are_available_through_agent_mcp_endpoint(app, tmp_path):
    base, store = app
    project = store.dispatch("atlas_project_create", {"name": "External refs", "owner": "writer"})["project"]
    source = tmp_path / "outside-reference.pdf"
    source.write_bytes(b"fixture pdf")
    headers = {"Authorization": "Bearer operator-token"}
    create = {"name": "atlas_file_link_source", "caller": "hub", "arguments": {
        "project_id": project["id"], "source_path": str(source)}}
    code, raw, _ = http(base, "/api/agent/call", create, headers)
    assert code == 200, raw
    result = json.loads(raw)["result"]
    assert result["input_readonly"] is True and result["file"]["external"] is True
    file_id = result["file"]["id"]
    code, raw, _ = http(base, "/api/agent/call", {"name": "atlas_file_resolve", "caller": "writer",
        "arguments": {"file_id": file_id}}, headers)
    assert code == 200 and json.loads(raw)["result"]["file"]["path"] == str(source.resolve())
    assert source.read_bytes() == b"fixture pdf"


def test_browser_session_uses_same_origin_and_cannot_choose_another_caller(app):
    base, store = app
    code, html, headers = http(base, "/")
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    assert code == 200 and b"Atlas's Hoard" in html
    assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]
    body = {"name": "atlas_project_create", "caller": "outsider", "arguments": {"name": "Synthetic", "owner": "writer"}}
    assert http(base, "/api/agent/call", body, {"Cookie": cookie})[0] == 200
    assert http(base, "/api/agent/call", body, {"Cookie": cookie, "Origin": "https://untrusted.example"})[0] == 403
    assert http(base, "/api/status", headers={"Cookie": cookie})[0] == 200


def test_shared_contract_carries_attested_caller_and_enforces_membership(app):
    base, store = app
    project = store.dispatch("atlas_project_create", {"name": "Private", "owner": "writer"})["project"]
    headers = {"Authorization": "Bearer operator-token"}
    code, raw, _ = http(base, "/api/agent/call", {"name": "atlas_project", "arguments": {"project_id": project["id"]}, "caller": "lumiere"}, headers)
    assert code == 403 and "not a member" in json.loads(raw)["error"]
    # An old Hub must fail closed rather than silently elevating a sibling to
    # the Atlas operator when it omits the authenticated caller's identity.
    assert http(base, "/api/agent/call", {"name": "atlas_projects"}, headers)[0] == 400
