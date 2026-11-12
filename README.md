# Atlas's Hoard

Local shared storage for the Hoard family: ordinary project folders that hold shared live files and each application's native files.

[Leer en español](README.es.md)

## What it is

Atlas's Hoard gives projects a common place on disk. Every member application of a project resolves the same original path by file ID, so registering a PNG never copies or edits it, and the originals stay openable with their normal paths even when Atlas is stopped. Metadata (projects, file IDs, revisions, anchors, derived results) lives separately in `data/`. Membership governs the API, not Windows permissions: a process with access to the disk can open the files; Atlas is not a sandbox.

```text
HoardStorage/
  autumn-collection-<id>/
    shared/
      cover.png
      references.pdf
    hoards/
      writer/
      lumiere/
      prospero/
```

Applications' internal databases stay where they are; Atlas moves nothing and does not merge them. There is no continuous file watcher and no cloud dependency; BookHoard and WatchHoard are independent of it.

## What it does

**Projects**
- Create a project with a name, optional goal, sphere and the IDs of the participating Hoards; each gets its own folder next to `shared/`.
- **Editar proyecto**: change name, goal, participants and active/archived state; only changed fields are sent, drafts survive closing and refreshes, and renaming or archiving keeps paths, file IDs and revisions stable. Removing a Hoard keeps its folders and files.
- A sidebar search filters projects by name and goal (all words, ignoring case and accents), state and sphere, without losing open forms.

**Files**
- **Register file** takes a relative path such as `shared/cover.png` and an optional descriptive title; registering an existing path keeps its ID and refreshes the revision. Files get an ID, a `hoard://atlas/file/<id>` URI, a SHA-256 revision and a size.
- **Ver detalles** shows the registered ID, URI, path, application, revision and size; **Copiar referencia** copies the URI; **Actualizar metadatos** reads the original and refreshes the recorded metadata (a missing file keeps its last recorded revision, labelled). Hash inspection is limited to 512 MiB per file; larger files can still live in the project folders.
- Search registered files by title or path (all words, ignoring case and accents), by shared or native folder and by presence. This searches registered metadata, not file contents or unregistered folders.
- **External source references** (**Añadir referencia externa**): a file that must stay in another folder is linked read-only; Atlas records its absolute path, size and SHA-256 without copying it. **Comprobar** refreshes the revision, **Copiar ruta original** copies the path. Linked sources can be inputs of derived results but never outputs. `atlas_file_import` is the explicit one-time copy for the operator (it never overwrites and needs a file system with hard links). See [docs/EXTERNAL-SOURCES.md](docs/EXTERNAL-SOURCES.md).

**Reusable results**
- Atlas stores references to results already produced; the owning applications still do the OCR, transcription, indexing and inference. The **Resultados reutilizables** view shows saved outputs, source revisions and the full recipe, and **Comprobar ahora** checks against current file hashes.
- Lookup takes a project, source IDs and a recipe; a cache hit requires exact source and output hashes, operation version, options and model revision. Publishing a registered output declares it was produced from those source revisions and is refused if the sources changed meanwhile. Atlas does not run the operation.

**Multimodal anchors**
- Mark a precise place in a registered file revision: text range, spreadsheet cells, PDF page and rectangle, image region, audio/video time range, 3D part (GLB/OBJ/STL) or code symbol, with comments.
- When a new revision is registered or refreshed, Atlas re-locates every anchor and records it as intact, moved, changed or lost for that revision; anchors and comments stay pinned to the revision they were made on. The project's **Anclas / Anchors** tab lists them per file and revision and creates text, cell, PDF and other anchors from form fields. PDF text positions need the optional `pypdf` package. See [docs/ANCHORS.md](docs/ANCHORS.md).

**Context**
- `atlas_context` builds a bounded context with goal, scope, participants and up to twenty explicit file references. File contents are working material, never instructions for the agent.

**Backups and resources.** The Hub includes the external disk as `atlas-files` besides Atlas's metadata in backups; restoring needs a separate folder for review, and backups are not an atomic snapshot of several applications editing at once. The Hub also offers cooperative CPU, RAM and disk reservations (`hoard_link.fam_resources.claim`) that consumers must adopt and respect.

## How to run it

Open **Iniciar Atlas's Hoard.cmd**, or run:

```powershell
python -m atlas_hoard
```

Requires Python 3.11+ and nothing outside the standard library. The interface is at `http://127.0.0.1:5203`. `--root PATH` selects the shared disk on first launch (default: `HoardStorage` in the development folder on Windows when it exists, else in the home directory). That choice is stored; do not change the root of an installation with projects without an explicit migration.

1. Create a project and type the IDs of the participating Hoards.
2. Copy the **Compartidos** path and save your file there with any editor.
3. Register it by relative path, for example `shared/cover.png`.
4. Participants resolve the same file by ID; nobody receives a copy.

## Connection with Faustus and the Hub

The Hub discovers `faustus-plugin.json`, authenticates the caller and keeps its identity when calling Atlas. Clients: Python `hoard_link.fam_workspace`, Node `hoard-commons/fam-workspace.js`, Hub `hub_workspace`, `GET /api/workspace/projects` and `POST /api/workspace/call`. Atlas serves its catalogue at `/api/agent/tools`, calls at `/api/agent/call`, and a stdio MCP bridge `mcp_server.py`. Responses include `path`, `uri`, `project_id` and the SHA-256 revision.

Tools, by group:
- Projects: `atlas_projects` (optional `query`, `state`, `sphere`), `atlas_project`, `atlas_project_create`, `atlas_project_update` (merges only the fields it receives), `atlas_location`, `atlas_session`, `atlas_context`.
- Files: `atlas_file_register`, `atlas_file_resolve`, `atlas_files_search`, `atlas_file_link_source`, `atlas_file_import`.
- Derived results: `atlas_derived_lookup`, `atlas_derived_publish`, `atlas_derived_results`.
- Anchors: `atlas_anchor_create`, `atlas_anchor_get`, `atlas_anchor_list`, `atlas_anchor_resolve`, `atlas_anchor_comment`.

Mutations take a `request_id` that stores a persistent receipt for retries; this does not make an operation across several services a transaction.

**Lumiere** offers `media_shared(file_id)`: it opens the original within its folder limits without copying it, and repeating it after the original was edited keeps the media ID in timelines, refreshes its measurements and renews caches and analyses. Removing that reference from its library keeps the shared original. Other applications receive the shared clients and contract; their usual importers keep their behaviour and some copy files, so a live reference needs an operation that links files.

**Faustus assistant.** The shared Hoard Link launcher shows the family's Faustus panel (a floating button). Conversation, model and tools live in Faustus; this app only tells the panel what is open.
- Context per view: an open project is sent as kind `project` (id, name, sphere, owner, goal, state, members, path, shared path) and the files of the current area as kind `file`, up to 50 (title, relative path, app, revision, state, presence, path). Only metadata is sent, never file contents.
- Unsaved fields (`project_create`, `file_register`) are returned on the `atlas:context-request` window event. When the assistant finishes a turn the open project reloads in place, keeping the text, focus and cursor of what is being typed.
- The relay is mounted under `/api/copilot/*` (session or token required, except the launcher script) and the page script is served at `/copilot-context.js`. The content security policy stays strict.

**Skills.** The app carries `shared-project-files`, `revision-aware-media` and `verification-loop` from the family's skill library for connecting agents, read with `skills_list` and `skill_read`, assigned on the skills page (`/api/agent/skills/page`) or in the hub's Skills tab.

## Project layout

| Path | Contents |
|---|---|
| `atlas_hoard/` | server, store, anchors, contracts |
| `atlas_hoard/ui/` | web interface |
| `atlas_hoard/hoard_link/` | vendored family library (keeps its licence and attribution) |
| `mcp_server.py` | stdio MCP bridge |
| `faustus-plugin.json` | plugin manifest |
| `docs/` | anchors and external source references (English and Spanish) |
| `tests/` | Python and JS tests |
| `data/` | metadata and token (not tracked) |

## Tests

```powershell
python -m pytest tests
node --test tests/copilot-context.test.mjs tests/anchors-ui.test.mjs tests/external-references.test.mjs
```

Tests use isolated folders and synthetic data.

## Licence

MIT.
