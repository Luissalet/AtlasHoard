# Multimodal anchors

An anchor is a stable identifier for a precise place inside one revision of a
registered file (internal or external read-only reference). It extends Atlas's
existing files and revisions; there is no separate store and Atlas still never
modifies, copies or executes anything. The anchor stores a small snapshot of
what was there (a quote with context, cell values, a symbol body hash, PDF text
chunks, mesh fingerprint) so it can be re-found later without keeping old file
copies.

## Tools (HTTP `POST /api/agent/call`, and MCP)

| Tool | Purpose |
| --- | --- |
| `atlas_anchor_create` | `file_id`, `kind`, `selector`, optional `label`, `comment`, `request_id`. Made on the current revision (refreshed first). |
| `atlas_anchor_get` | One anchor with per-revision history and comments. Metadata only. |
| `atlas_anchor_list` | By `file_id` or `project_id`; optional `revision` (sequence number or sha256, with `file_id`), `kind`, `status`, `limit`, `offset`. Returns a status summary and the revisions Atlas has seen. |
| `atlas_anchor_resolve` | Refreshes the file, re-locates the place and returns an `open` block for clients. |
| `atlas_anchor_comment` | Adds a comment pinned to the revision current at that moment. |

`hoard://atlas/anchor/<id>` identifies an anchor; `hoard://atlas/file/<id>` the file.

## Selectors

| kind | selector | files |
| --- | --- | --- |
| `text` | `{quote, prefix?, suffix?}` or `{start, end}` (character offsets) or `{line_start, line_end?, char_start?, char_end?}` (1-based lines) | any text (UTF-8; line endings normalised to `\n`) |
| `cell` | `{ref: "Sheet1!A1:B3"}` or `{sheet, range}` | `.csv`/`.tsv` (sheet `csv`), `.xlsx`/`.xlsm` |
| `pdf` | `{page, rect: [x0, y0, x1, y1]}` page fractions 0..1, origin top-left | `.pdf` (text positions need `pypdf`) |
| `image` | `{rect}` or `{x, y, w, h}` fractions 0..1 | any image (PNG/JPEG/GIF/BMP sizes are read) |
| `time` | `{start, end, duration?}` seconds | any audio/video (WAV and MP4/MOV/M4A durations are read) |
| `mesh` | `{node}` name or `{node_index}`, optional `faces: [triangle indices]` | `.glb`, `.gltf`, `.obj` (`o`/`g`), `.stl` |
| `code` | `{symbol, line_start?}` (`Class.method`) or `{line_start}` (Python) | Python via `ast`; other languages by heuristic |

## Status per revision

When a new revision of the file is registered or refreshed, every older anchor is
re-resolved against the new content and the outcome is stored for that revision:

* `intact`: same place, same content.
* `moved`: same content at a new location (text/quote and context, cell block, code symbol lines, PDF text shifted or on another page, mesh part index).
* `changed`: the place exists but its content differs (similar text found by fuzzy match, other cell values, other symbol body, other geometry, image size or media duration changed).
* `lost`: not found (quote gone, sheet/symbol/part missing or renamed, page missing, time range after the new end).

Each re-resolution starts from the anchor's original selector, so a reverted file
goes back to `intact`. History is never rewritten: the anchor keeps its creation
revision (`origin`), every observed revision keeps its own status row, and a
comment made on revision 1 stays on revision 1 and reports what happened later
(`comments[].status_at_revision`, `history`). Atlas only knows revisions it has
seen, i.e. every time a file is registered, resolved or used in a context.

## Resolution result

`atlas_anchor_resolve` returns `status`, `detail`, `location`, `origin`, `history`,
`comments`, `file` and an `open` object: `path`, `file_uri`, `anchor_uri`,
`revision`, `revision_seq`, `current_revision_seq`, `viewable`, plus the
kind-specific keys (`line_start`/`line_end`, `char_start`/`char_end`, `page`,
`rect`, `time_start`/`time_end`, `sheet`/`range`/`ref`, `symbol`, `node`/`faces`)
and a `fragment` (`page=3`, `t=2.5,4.0`, `L12-L14`, `Sheet1!A1:B3`). With
`revision` it returns the place on an earlier observed revision; then `viewable`
is false because the file on disk is no longer that content.

## Limits

* The content of old revisions is not stored, so anchors are created on the current revision and statuses of unobserved intermediate revisions do not exist.
* Files over 64 MiB cannot hold text, cell, PDF, mesh or code anchors; image and time anchors are accepted without size/duration checks.
* PDF text matching needs `pypdf`; without it a PDF anchor only checks that the page exists. Scanned PDFs have no text to compare.
* Renamed 3D nodes and renamed symbols are reported `lost`; there is no rename detection. Non-Python code symbols and block ends use heuristics.
* Membership rules apply as for files; this is API access control, not an OS sandbox.
