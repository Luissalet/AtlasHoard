# Atlas's Hoard

Local shared storage for the Hoard family: ordinary project folders containing
shared live files and each application's native files. All project members
resolve the same original path; registering a PNG never copies or edits it.

Run `python -m atlas_hoard` (Python 3.11+, standard library only), then open
`http://127.0.0.1:5203`. `--root PATH` selects the shared disk on first launch.
Metadata lives separately in `data/`. Windows includes a launcher.

The Hub discovers its manifest; Python and Node clients, HTTP tools and a stdio
MCP bridge expose projects, live paths, revisions, scoped context and reusable
derived results. Cache reuse requires exact source/output hashes and recipes.
Lumiere's `media_shared` opens live files without copying them and refreshes
changed originals while preserving timeline references.

Register project files normally with `atlas_file_register`. For a file that
must stay in another folder, the operator can use `atlas_file_link_source` to
add an explicit read-only reference; Atlas records its absolute path, size and
SHA-256 revision without copying it. `atlas_file_resolve` refreshes the source
revision after edits, and project context marks the reference as read-only.
Linked sources cannot be published as derived outputs. `atlas_file_import`
remains the explicit one-time copy operation. Existing applications' native
databases and copying importers remain unchanged.
See [external source references](docs/EXTERNAL-SOURCES.md) for the MCP contract
and its filesystem limits.
Membership restricts the API, not OS filesystem access. No automatic migration,
continuous watcher or cloud dependency. BookHoard and WatchHoard are independent.

See [the Spanish operating guide](README.es.md) for examples, backup behavior,
resource coordination and practical limits. Vendored HoardLink keeps its license
and attribution. This application is MIT licensed.

## Faustus assistant

Once the shared Hoard Link launcher is installed, the app shows the family's Faustus panel (a floating button). The conversation, the model and the tools live in Faustus; this app only tells the panel what is open.

- **Context per view.** An open project is sent as kind `project` with its real id, name, sphere, owner, goal, state, members, path and shared path, and as the panel's external project. The files of the current area (`shared` or one app's folder) follow as kind `file`, up to 50: title, relative path, app, revision, state, whether it exists, and path. Only metadata is sent, never file contents. With no project open the view is `home` and gives no object.
- **Unsaved fields.** The panel asks for them with the `atlas:context-request` window event. The open forms answer with the fields that differ from their defaults: `project_create` (new project) and `file_register` (relative path).
- **Refresh.** When the assistant finishes a turn the open project reloads in place (`hoard:copilot-turn-end` / `window.hoardCopilot.onTurnEnd`, merged into one reload). The relative path being typed keeps its text, focus and cursor.
- **Saving.** `atlas_project_update` merges only the fields it receives, so an edit by the assistant and one by hand both survive (archiving touches only `state`). No endpoint changed; the page script is served at `/copilot-context.js`.
- **Tests.** `node --test tests/copilot-context.test.mjs` and `python -m pytest tests/test_copilot_ui.py tests/test_server.py tests/test_store.py`.
