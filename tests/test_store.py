from pathlib import Path
import json
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
