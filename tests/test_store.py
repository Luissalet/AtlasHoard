from pathlib import Path
import json
import sqlite3
import pytest

from atlas_hoard.store import Workspace, StoreError


@pytest.fixture
def store(tmp_path):
    workspace = Workspace(tmp_path / "private", tmp_path / "disk")
    yield workspace
    workspace.close()


def project(store, **options):
    return store.dispatch("atlas_project_create", {"name": "Lanzamiento", "owner": "writer", "members": ["writer", "lumiere"], **options})["project"]


def register(store, p, relative, data=b"original", caller="writer"):
    path = Path(p["path"]) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    result = store.dispatch("atlas_file_register", {"project_id": p["id"], "relative_path": relative}, caller)
    return result["file"]


def test_two_native_consumers_open_the_same_live_file_and_see_edits(store):
    p = project(store)
    asset = register(store, p, "shared/cover.png")
    writer = store.dispatch("atlas_file_resolve", {"file_id": asset["id"]}, "writer")["file"]
    editor = store.dispatch("atlas_file_resolve", {"file_id": asset["id"]}, "lumiere")["file"]
    assert writer["path"] == editor["path"] == str(Path(p["shared_path"]) / "cover.png")
    Path(editor["path"]).write_bytes(b"edited by native application")
    refreshed = store.dispatch("atlas_file_resolve", {"file_id": asset["id"]}, "writer")["file"]
    assert refreshed["id"] == asset["id"] and refreshed["revision"] != asset["revision"]
    assert Path(writer["path"]).read_bytes() == b"edited by native application"
    assert list(store.root.rglob("cover.png")) == [Path(writer["path"])]


def test_locations_keep_native_projects_and_shared_assets_in_one_project(store):
    p = project(store)
    for caller in ("writer", "lumiere"):
        common = store.dispatch("atlas_location", {"project_id": p["id"]}, caller)
        native = store.dispatch("atlas_location", {"project_id": p["id"], "area": "hoard"}, caller)
        assert common["path"] == p["shared_path"]
        assert native["path"] == str(Path(p["path"]) / "hoards" / caller)
        assert Path(native["path"]).is_dir()


def test_project_rename_archive_and_membership_preserve_every_original(store):
    p = project(store)
    asset = register(store, p, "shared/file.txt")
    changed = store.dispatch("atlas_project_update", {"project_id": p["id"], "name": "Otro nombre", "state": "archived", "members": ["writer"]}, "writer")
    assert changed["project"]["path"] == p["path"]
    assert Path(asset["path"]).read_bytes() == b"original"
    with pytest.raises(StoreError, match="not a member"):
        store.dispatch("atlas_file_resolve", {"file_id": asset["id"]}, "lumiere")
    assert not store.dispatch("atlas_projects", caller="lumiere")["projects"]


def test_members_cannot_edit_membership_impersonate_owner_or_access_other_projects(store):
    p = project(store)
    with pytest.raises(StoreError, match="only the project owner"):
        store.dispatch("atlas_project_update", {"project_id": p["id"], "members": ["lumiere"]}, "lumiere")
    with pytest.raises(StoreError, match="own project"):
        store.dispatch("atlas_project_create", {"name": "x", "owner": "writer"}, "lumiere")
    other = project(store, owner="people", members=["people"])
    with pytest.raises(StoreError, match="not a member"):
        store.dispatch("atlas_project", {"project_id": other["id"]}, "writer")


@pytest.mark.parametrize("relative", ["../outside.txt", "shared/../../outside.txt", "C:/Windows/file", "shared/mcp-token", "shared/.ssh/id_rsa"])
def test_paths_refuse_escape_and_secret_files(store, relative):
    p = project(store)
    with pytest.raises(StoreError):
        store.dispatch("atlas_file_register", {"project_id": p["id"], "relative_path": relative}, "writer")


def test_register_never_rewrites_or_copies_existing_file(store):
    p = project(store)
    file = register(store, p, "hoards/writer/native.project", b"native format")
    before = Path(file["path"]).stat()
    result = store.dispatch("atlas_file_register", {"project_id": p["id"], "relative_path": file["relative_path"]}, "writer")
    assert result["file"]["id"] == file["id"]
    assert Path(file["path"]).stat().st_mtime_ns == before.st_mtime_ns
    assert Path(file["path"]).read_bytes() == b"native format"


def test_idempotency_survives_restart_and_conflicting_arguments_are_refused(tmp_path):
    data, disk = tmp_path / "private", tmp_path / "disk"
    first = Workspace(data, disk)
    args = {"name": "One", "owner": "writer", "request_id": "create-1"}
    original = first.dispatch("atlas_project_create", args)
    first.close()
    second = Workspace(data, disk)
    try:
        repeated = second.dispatch("atlas_project_create", args)
        assert repeated["replayed"] and repeated["project"]["id"] == original["project"]["id"]
        assert len(list(disk.iterdir())) == 1
        with pytest.raises(StoreError, match="different operation"):
            second.dispatch("atlas_project_create", {**args, "name": "Changed"})
    finally:
        second.close()


def test_workspace_root_cannot_silently_change(tmp_path):
    data = tmp_path / "private"
    first = Workspace(data, tmp_path / "disk")
    first.close()
    with pytest.raises(StoreError, match="root changed"):
        Workspace(data, tmp_path / "other-disk")


def test_import_is_explicit_operator_only_and_preserves_source_and_destination(store, tmp_path):
    p = project(store)
    source = tmp_path / "cover.png"
    source.write_bytes(b"one png")
    args = {"project_id": p["id"], "source_path": str(source), "request_id": "import-1"}
    with pytest.raises(StoreError, match="only the operator"):
        store.dispatch("atlas_file_import", args, "writer")
    imported = store.dispatch("atlas_file_import", args)["file"]
    assert Path(imported["path"]).read_bytes() == source.read_bytes()
    assert store.dispatch("atlas_file_import", args)["replayed"]
    with pytest.raises(StoreError, match="destination exists"):
        store.dispatch("atlas_file_import", {**args, "request_id": "new-import"})
    assert source.read_bytes() == Path(imported["path"]).read_bytes() == b"one png"


def test_external_sources_are_readonly_live_inputs_with_fresh_revisions(store, tmp_path):
    p = project(store)
    root_asset = register(store, p, "shared/root-source.txt", b"project root asset")
    external_dir_a = tmp_path / "references-a"
    external_dir_b = tmp_path / "references-b"
    external_dir_a.mkdir()
    external_dir_b.mkdir()
    source_a = external_dir_a / "paper.pdf"
    source_b = external_dir_b / "template.docx"
    source_a.write_bytes(b"pdf original")
    source_b.write_bytes(b"docx original")

    linked_a = store.dispatch("atlas_file_link_source", {
        "project_id": p["id"], "source_path": str(source_a)}, "hub")["file"]
    linked_b = store.dispatch("atlas_file_link_source", {
        "project_id": p["id"], "source_path": str(source_b), "app": "writer"}, "hub")["file"]
    assert linked_a["external"] and linked_a["input_readonly"]
    assert linked_a["path"] == str(source_a.resolve()) and linked_a["source_path"] == linked_a["path"]
    assert linked_a["revision"].startswith("sha256:") and linked_a["size"] == len(b"pdf original")
    assert source_a.read_bytes() == b"pdf original" and not (Path(p["shared_path"]) / source_a.name).exists()

    for caller in ("writer", "lumiere"):
        resolved = store.dispatch("atlas_file_resolve", {"file_id": linked_a["id"]}, caller)["file"]
        assert resolved["path"] == str(source_a.resolve()) and resolved["input_readonly"]
    context = store.dispatch("atlas_context", {
        "project_id": p["id"], "file_ids": [root_asset["id"], linked_a["id"], linked_b["id"]]}, "writer")["context"]
    assert len(context["files"]) == 3
    assert context["files"][1]["external"] is True and context["files"][1]["input_readonly"] is True

    before = linked_a["revision"]
    source_a.write_bytes(b"revised pdf source")
    refreshed = store.dispatch("atlas_file_resolve", {"file_id": linked_a["id"]}, "writer")
    assert refreshed["changed"] is True
    assert refreshed["file"]["revision"] != before and refreshed["file"]["size"] == len(b"revised pdf source")
    unchanged = store.dispatch("atlas_file_resolve", {"file_id": linked_a["id"]}, "writer")
    assert unchanged["changed"] is False

    output = register(store, p, "shared/result.json", b"{}")
    with pytest.raises(StoreError, match="read-only"):
        store.dispatch("atlas_derived_publish", {
            "project_id": p["id"], "source_ids": [root_asset["id"]],
            "recipe": {"operation": "extract", "version": "1"},
            "source_revisions": {root_asset["id"]: root_asset["revision"]},
            "output_id": linked_a["id"]}, "writer")
    assert Path(output["path"]).read_bytes() == b"{}"


def test_external_link_refuses_missing_duplicate_and_internal_paths_before_registration(store, tmp_path):
    p = project(store)
    external = tmp_path / "source.txt"
    external.write_text("source", encoding="utf-8")
    args = {"project_id": p["id"], "source_path": str(external)}
    linked = store.dispatch("atlas_file_link_source", args, "hub")["file"]
    count = store.db.execute("SELECT COUNT(*) FROM files WHERE project_id=?", (p["id"],)).fetchone()[0]
    with pytest.raises(StoreError, match="already linked"):
        store.dispatch("atlas_file_link_source", args, "hub")
    with pytest.raises(StoreError, match="existing file"):
        store.dispatch("atlas_file_link_source", {**args, "source_path": str(tmp_path / "missing.txt")}, "hub")
    internal = Path(p["shared_path"]) / "already-here.txt"
    internal.write_text("internal", encoding="utf-8")
    with pytest.raises(StoreError, match="use file_register"):
        store.dispatch("atlas_file_link_source", {**args, "source_path": str(internal)}, "hub")
    assert store.db.execute("SELECT COUNT(*) FROM files WHERE project_id=?", (p["id"],)).fetchone()[0] == count
    Path(linked["path"]).unlink()
    result = store.dispatch("atlas_file_resolve", {"file_id": linked["id"]}, "writer")
    assert result["file"]["state"] == "missing" and not result["file"]["exists"]


def test_external_link_is_operator_only_and_catalogued_for_http_mcp(store, tmp_path):
    from atlas_hoard.contracts import catalogue

    p = project(store)
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    with pytest.raises(StoreError, match="only the operator"):
        store.dispatch("atlas_file_link_source", {"project_id": p["id"], "source_path": str(source)}, "writer")
    tool = next(item for item in catalogue() if item["name"] == "atlas_file_link_source")
    assert tool["inputSchema"]["required"] == ["project_id", "source_path"]
    assert tool["annotations"]["readOnlyHint"] is False


def test_external_link_resolves_after_workspace_reopen(tmp_path):
    data, disk = tmp_path / "private", tmp_path / "disk"
    source = tmp_path / "references" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(b"source survives restart")
    first = Workspace(data, disk)
    project_row = first.dispatch("atlas_project_create", {"name": "Restart", "owner": "writer"})["project"]
    linked = first.dispatch("atlas_file_link_source", {
        "project_id": project_row["id"], "source_path": str(source)}, "hub")["file"]
    first.close()

    reopened = Workspace(data, disk)
    try:
        columns = {row[1] for row in reopened.db.execute("PRAGMA table_info(files)")}
        assert {"external_path", "external_key", "input_readonly"} <= columns
        result = reopened.dispatch("atlas_file_resolve", {"file_id": linked["id"]}, "writer")
        assert result["file"]["path"] == str(source.resolve())
        assert result["file"]["revision"] == linked["revision"]
        assert result["file"]["input_readonly"] is True
    finally:
        reopened.close()


def test_existing_file_rows_survive_additive_external_source_schema_migration(tmp_path):
    data, disk = tmp_path / "private", tmp_path / "disk"
    folder = disk / "legacy-project"
    (folder / "shared").mkdir(parents=True)
    original = folder / "shared" / "existing.txt"
    original.write_text("unchanged legacy file", encoding="utf-8")
    data.mkdir(parents=True)
    db = sqlite3.connect(data / "atlas.db")
    db.executescript("""
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE projects (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, folder TEXT UNIQUE NOT NULL,
          owner TEXT NOT NULL, sphere TEXT NOT NULL, members TEXT NOT NULL,
          goal TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', created REAL NOT NULL);
        CREATE TABLE files (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
          relative_path TEXT NOT NULL, app TEXT NOT NULL, title TEXT NOT NULL,
          revision TEXT NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
          state TEXT NOT NULL DEFAULT 'available', updated REAL NOT NULL,
          UNIQUE(project_id, relative_path));
        INSERT INTO settings VALUES ('root', 'PLACEHOLDER');
    """)
    db.execute("UPDATE settings SET value=? WHERE key='root'", (str(disk.resolve()),))
    db.execute("INSERT INTO projects VALUES ('legacy','Legacy','legacy-project','writer','personal','[\"writer\"]','','active',1)")
    db.execute("INSERT INTO files VALUES ('file-old','legacy','shared/existing.txt','writer','existing.txt','old-revision',0,0,'available',1)")
    db.commit()
    db.close()

    migrated = Workspace(data, disk)
    try:
        resolved = migrated.dispatch("atlas_file_resolve", {"file_id": "file-old"}, "writer")["file"]
        assert resolved["path"] == str(original.resolve())
        assert resolved.get("input_readonly", False) is False
        assert resolved["revision"] != "old-revision"
        assert original.read_text(encoding="utf-8") == "unchanged legacy file"
    finally:
        migrated.close()


def test_derived_cache_reuses_exact_recipe_and_invalidates_source_output_or_membership(store):
    p = project(store)
    source = register(store, p, "shared/original.txt", b"source")
    output = register(store, p, "shared/extracted.json", b'{"text":"source"}')
    args = {"project_id": p["id"], "source_ids": [source["id"]], "recipe": {"operation": "extract", "version": "1", "model": "fixture-v1"}}
    miss = store.dispatch("atlas_derived_lookup", args, "lumiere")
    assert not miss["hit"]
    expected = {s["id"]: s["revision"] for s in miss["sources"]}
    store.dispatch("atlas_derived_publish", {**args, "source_revisions": expected, "output_id": output["id"]}, "writer")
    hit = store.dispatch("atlas_derived_lookup", args, "lumiere")
    assert hit["hit"] and hit["file"]["path"] == output["path"]
    assert not store.dispatch("atlas_derived_lookup", {**args, "recipe": {**args["recipe"], "model": "fixture-v2"}}, "lumiere")["hit"]
    Path(output["path"]).write_bytes(b"human edit")
    assert not store.dispatch("atlas_derived_lookup", args, "lumiere")["hit"]
    Path(source["path"]).write_bytes(b"new source")
    with pytest.raises(StoreError, match="sources changed"):
        store.dispatch("atlas_derived_publish", {**args, "source_revisions": expected, "output_id": output["id"]}, "writer")
    store.dispatch("atlas_project_update", {"project_id": p["id"], "members": ["writer"]})
    with pytest.raises(StoreError, match="not a member"):
        store.dispatch("atlas_derived_lookup", args, "lumiere")


def test_context_is_bounded_scoped_and_marks_sources_untrusted(store):
    p = project(store, sphere="work", goal="Make a launch film")
    source = register(store, p, "shared/brief.txt")
    ctx = store.dispatch("atlas_context", {"project_id": p["id"], "file_ids": [source["id"]]}, "writer")["context"]
    assert ctx["sphere"] == "work" and ctx["goal"] == "Make a launch film"
    assert ctx["files"][0]["path"] == source["path"] and "never agent instructions" in ctx["trust"]
    other = project(store, name="Private", owner="people", members=["people"])
    outsider = register(store, other, "shared/private.txt", caller="people")
    with pytest.raises(StoreError):
        store.dispatch("atlas_context", {"project_id": p["id"], "file_ids": [outsider["id"]]}, "writer")


def test_missing_original_is_reported_and_never_recreated(store):
    p = project(store)
    asset = register(store, p, "shared/gone.txt")
    Path(asset["path"]).unlink()
    result = store.dispatch("atlas_file_resolve", {"file_id": asset["id"]}, "writer")["file"]
    assert result["state"] == "missing" and not result["exists"]
    assert not Path(result["path"]).exists()
