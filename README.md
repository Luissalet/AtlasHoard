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

Existing applications' native databases and copying importers remain unchanged.
Membership restricts the API, not OS filesystem access. No automatic migration,
continuous watcher or cloud dependency. BookHoard and WatchHoard are independent.

See [the Spanish operating guide](README.es.md) for examples, backup behavior,
resource coordination and practical limits. Vendored HoardLink keeps its license
and attribution. This application is MIT licensed.
