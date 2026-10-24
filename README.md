# Atlas's Hoard

**Register file** accepts an optional descriptive title for a newly registered
internal file. It keeps the physical filename and path unchanged; an empty
title uses the filename. Registering an existing path preserves its ID, title
and application while reading the original bytes to refresh its revision.
The receipt shows the title and path actually returned. Path/title drafts stay
with their project and folder through navigation, cancellation and retries;
pending responses preserve later edits. Existing API/MCP14 remain unchanged.

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

**Find registered files:** each project has a title/path search that ignores case
and accents, with shared/native folder and current file-presence filters. Search
results keep the original paths and include external read-only references in the
whole-project view. Use `atlas_files_search` through MCP or the normal
`POST /api/agent/call` API with `project_id`, optional `query`, `area` (`all`,
`shared` or a member application ID), `availability` (`all`, `present`, `missing`),
`limit` (1–200) and `offset`. All query words must match the title or path. Results
include the total and pagination. This searches registered metadata, not file
contents or unregistered folders, and checks existence without refreshing hashes.

**Find projects:** the projects sidebar filters names and goals by all query words,
ignoring case and accents, alongside state (active/archived) and sphere. It shows
the matching count, a clear action and an explicit notice when the open project
is outside the filter. Filtering keeps the project and its unsaved forms open;
refreshes retain the filters, and obsolete responses cannot replace newer results.
Errors keep the preceding list and identify it as such, with Retry. The existing
`atlas_projects` HTTP/MCP operation accepts optional `query`, `state` and `sphere`;
its `projects` response remains compatible with unfiltered callers. It reads all
accessible project metadata, including projects older than the former global1000
row cutoff, without reading file contents, checking hashes or changing any paths.

Register project files normally with `atlas_file_register`. For a file that
must stay in another folder, the operator can use `atlas_file_link_source` to
add an explicit read-only reference; Atlas records its absolute path, size and
SHA-256 revision without copying it. `atlas_file_resolve` refreshes the source
revision after edits, and project context marks the reference as read-only.
Linked sources cannot be published as derived outputs. `atlas_file_import`
remains the explicit one-time copy operation. Existing applications' native
databases and copying importers remain unchanged.
In **Archivos**, **Añadir referencia externa** takes an explicit absolute source
path, optional title and project member. The project-wide references section
shows original paths, read-only status, current presence and recorded revisions,
independently of the selected shared/native folder. **Comprobar** uses the native
resolver to refresh hashes and metadata; **Copiar ruta original** copies the path.
Registration and checks read source bytes for hashing, but never execute, display,
copy or modify the original. The form retains drafts across view changes, errors
and copilot refresh; the existing derived-results view can use references as
inputs, while excluding them as outputs. Duplicate handling follows the native
tool response; this UI adds no policy or backend operation.
See [external source references](docs/EXTERNAL-SOURCES.md) for the MCP contract
and its filesystem limits.

**Reusable results:** open a project's **Resultados reutilizables** view to see
saved outputs, source revisions and the full recipe. **Comprobar ahora** calls
`atlas_derived_lookup` against current file hashes; a list entry alone never
claims freshness. Register an already generated, registered output with its
sources, operation/version and optional model revision/JSON options. Publishing
declares that the output was produced from those current source revisions; Atlas
does not run the operation. Regenerate externally first if the sources changed.
`atlas_derived_results` takes `project_id` through HTTP/MCP and returns `results`
with the saved recipe, source/output revisions, file metadata and recorded state;
`freshness: "unchecked"` means it has not refreshed hashes. Form drafts survive
view switches and in-place refreshes and are exposed to the assistant as unsaved
fields, alongside the active project tab.

Membership restricts the API, not OS filesystem access. No automatic migration,
continuous watcher or cloud dependency. BookHoard and WatchHoard are independent.

**Edit a project:** **Editar proyecto** opens the current name, optional goal,
other participating Hoard IDs and active/archived state. Only fields actually
changed are sent to the existing `atlas_project_update`; an empty goal clears it.
Opening again or an assistant refresh reads current data while preserving the
unsaved fields, focus and cursor. Closing the editor keeps its draft; **Descartar
cambios** discards it. Draft fields are included in the existing assistant context.
Renaming does not move its folder; owner, sphere, file IDs/paths/revisions stay
stable. The owner remains a member. Removing another Hoard keeps its folders and
files, and an open removed folder falls back to Compartidos after save. Archived
projects stay listed with a label and can be reactivated from the same editor.
This UI adds no new backend operation or permission model.

See [the Spanish operating guide](README.es.md) for examples, backup behavior,
resource coordination and practical limits. Vendored HoardLink keeps its license
and attribution. This application is MIT licensed.

## Faustus assistant

Once the shared Hoard Link launcher is installed, the app shows the family's Faustus panel (a floating button). The conversation, the model and the tools live in Faustus; this app only tells the panel what is open.

- **Context per view.** An open project is sent as kind `project` with its real id, name, sphere, owner, goal, state, members, path and shared path, and as the panel's external project. The files of the current area (`shared` or one app's folder) follow as kind `file`, up to 50: title, relative path, app, revision, state, whether it exists, and path. Only metadata is sent, never file contents. With no project open the view is `home` and gives no object.
- **Unsaved fields.** The panel asks for them with the `atlas:context-request` window event. The open forms answer with the fields that differ from their defaults: `project_create` (new project) and `file_register` (relative path).
- **Refresh.** When the assistant finishes a turn the open project reloads in place (`hoard:copilot-turn-end` / `window.hoardCopilot.onTurnEnd`, merged into one reload). The relative path being typed keeps its text, focus and cursor.
- **Saving.** `atlas_project_update` merges only the fields it receives, so an edit by the assistant and one by hand both survive (archiving touches only `state`). No endpoint changed; the page script is served at `/copilot-context.js`. The server mounts the relay under `/api/copilot/*` (session or token required, except the launcher script), injects the launcher into the page. The content security policy stays strict: the launcher styles itself with constructed stylesheets, so no inline styles are allowed.
- **Tests.** `node --test tests/copilot-context.test.mjs` and `python -m pytest tests/test_copilot_ui.py tests/test_server.py tests/test_store.py`.
