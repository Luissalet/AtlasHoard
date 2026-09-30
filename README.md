# Atlas's Hoard

A local workspace for research cases. Each case gathers sources with a stated reliability, entities, and relations
that cannot exist without evidence. The app keeps a timeline, a map, a relation graph and a competing-hypotheses
matrix, and writes reports in which every sentence cites a source. It is meant for a person and for an assistant
working together: everything is available as a REST API for the bundled UI and as MCP tools, built from the same code,
so the two cannot disagree.

## What it does

- **Cases**: a question, tags, open questions, a dashboard of what needs attention (unsupported relations, disputed
  ones, stale facts, contradictions, entities with no relations, hypotheses with no ratings).
- **Sources**: capture a URL (readable text is extracted and a snapshot with its hash is stored), paste text, read a
  local text/HTML/PDF file, or reference a document that lives in another app of the family. Each source carries a
  reliability grade (A-F) and a credibility grade (1-6), an origin, a publication date and full-text search.
- **Entities**: people, organizations, places, events, documents, objects, domains, concepts, with aliases, attributes
  (each with its own source), coordinates and dates. Possible duplicates are suggested with reasons; merging is always
  explicit and previewed first.
- **Relations**: subject, predicate, object, optional validity dates, and evidence (a source plus a verbatim quote or
  a locator). A relation cannot be created without evidence. Quotes are checked against the stored source text.
- **Derived status**, never typed by hand:

  | status | meaning |
  | --- | --- |
  | `claimed` | backed by one origin |
  | `corroborated` | backed by at least two independent origins |
  | `confirmed` | marked by a person and backed by at least two independent origins |
  | `disputed` | marked by a person |
  | `unsupported` | every source behind it was retracted |
  | `retracted` | retracted by a person, until restored |

  An origin is a domain or a reference. Two sources from the same origin, or with identical content, count once.
- **Retraction cascade**: retracting a source never deletes anything. Relations are recomputed, relations derived from
  an unsupported one are flagged, and the affected attributes and ACH hypotheses are listed.
- **Timeline with `as_of`**: partial dates (`2024`, `2024-03`, `2024-03-05`) are treated as ranges of days; `as_of`
  shows what was valid on a date. A fact whose validity ended in the past is history (`ended`), not stale; `stale` is
  reserved for facts that should still be current but were last observed more than `ATLAS_STALE_DAYS` ago. Gaps and conflicting values of one-value predicates (for example two
  headquarters at the same time) are reported.
- **Map** (Leaflet, OpenStreetMap tiles): one layer per entity type, with the number of sources behind it and a time
  slider. **Graph** (d3-force): edges coloured by status, neighbourhood by depth.
- **Competing hypotheses (ACH)**: rate each evidence item against each hypothesis (`CC`, `C`, `N`, `I`, `II`, `NA`).
  The score counts inconsistencies (I = 1, II = 2). Diagnosticity shows which evidence discriminates, and the
  sensitivity note names the evidence the ranking hinges on. The top hypothesis is always described as "least
  contradicted so far", never as proven.
- **Enrichers**, each undoable as a whole with `enrichment_undo`: `wikidata` (public facts for organizations, places,
  events and public figures), `geocode` (Nominatim), `url_capture`, `family_search` (other apps of the family).
  Everything an enricher adds is `claimed` and cites its source.
- **Reports**: Markdown or JSON with `[S12]` citations, relations grouped by status, timeline, ACH table and a source
  list with grades. A model-written summary (when a model is configured) passes a citation check: every sentence that
  states a fact must cite a source that exists in the case; uncited sentences are flagged and invalid or retracted
  citations are listed. Without a model the summary is built deterministically.
- **History**: every change records who made it (the UI or the named assistant), what changed and before/after values.

## Responsible use

- **Private persons.** A person entity is treated as a private person unless it is marked `public_figure`. Enrichers
  never run on a private person, `family_search` removes their names and aliases from queries unless
  `include_private` is set, and reports mark them. Marking someone as a public figure is a deliberate, recorded act;
  use it only for people with a documented public role.
- **Social networks.** URL capture refuses social-network hosts. If you are entitled to use a post, add its text by
  hand as a text source and put the address in the reference.
- **Local addresses.** URL capture refuses private, loopback and link-local addresses unless
  `ATLAS_ALLOW_PRIVATE_URLS=1` is set. Local files must be text, Markdown, HTML or PDF and can be limited to folders
  with `ATLAS_FILE_ROOTS`.
- **Claims and certainty.** Status is derived from evidence. ACH ranks hypotheses by how little evidence contradicts
  them and never declares one proven. Model text is checked for citations, not for truth: a person reviews it.
- **Undo.** Enrichment runs are stamped and can be undone exactly; a failed run undoes itself.
- **External services.** Only the data providers listed under Credits are called. Place names go to Nominatim only
  when geocoding is enabled (Settings, or `ATLAS_GEOCODE=0` to turn it off).

## Install

Requirements: Python 3.11+ (Windows target 3.13), Node.js 22+ to build the client.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
npm install
npm run build
python -m atlas_hoard             # http://127.0.0.1:5193
```

The built client is committed under `atlas_hoard/static`, so `npm` is only needed to change the UI. During UI work,
`python scripts/dev.py` starts the API and the Vite dev server together.

| variable | default | meaning |
| --- | --- | --- |
| `ATLAS_PORT` / `PORT` | `5193` | port; with `PORT_STRICT=1` the app fails instead of moving to another port |
| `ATLAS_DATA_DIR` | `./data` | database, `mcp-token`, `url` |
| `ATLAS_GEOCODE` | `1` | `0` disables geocoding entirely |
| `ATLAS_ALLOW_PRIVATE_URLS` | `0` | `1` lets URL capture reach private addresses |
| `ATLAS_FILE_ROOTS` | empty | list of folders file sources may be read from |
| `ATLAS_STALE_DAYS` | `730` | age after which an undated fact is flagged as possibly outdated |
| `ATLAS_ALLOWED_HOSTS` | local only | extra host names the server accepts |

## MCP

`mcp_server.py` is a stdio bridge. It never opens the database: it reads `data/mcp-token`, fetches the tool list
from the running app and forwards each call. When the app is not running it starts it. Register it in any MCP client:

```json
{"mcpServers": {"atlas": {"command": "python", "args": ["/path/to/atlas/mcp_server.py"],
  "env": {"ATLAS_URL": "http://127.0.0.1:5193", "ATLAS_TOKEN_FILE": "/path/to/atlas/data/mcp-token"}}}}
```

`faustus-plugin.json` describes the same setup for the Faustus workspace.

### Tools

| tool | what it does |
| --- | --- |
| `atlas_status` | health and counts; the model probe is cached for 60 s and never blocks |
| `case_create`, `case_list`, `case_get`, `case_update` | cases and their dashboard; delete with `action=delete` and `confirm=true` |
| `source_add`, `source_get`, `source_retract`, `sources_search` | capture, read, retract/restore and search sources |
| `entity_upsert`, `entity_get`, `entity_search`, `entity_merge`, `duplicates_suggest` | entities, duplicates and explicit merges; `public_figure: true` (a parameter, not an attribute) lifts the private-person guard |
| `relation_add`, `relation_update`, `relation_retract`, `relation_get` | relations with mandatory evidence; list by status, entity or `as_of` |
| `timeline`, `map_layers`, `graph` | dated view, map layers, relation graph |
| `hypothesis_add`, `ach_rate`, `ach_matrix` | competing hypotheses |
| `enrich`, `enrichment_undo` | enrichers and their undo |
| `case_report` | Markdown or JSON report with citations |
| `history` | change history |

Results sent to an assistant are trimmed to about 20 KB with a hint to narrow or page.

## Family

Atlas works alone. When the other apps of the family run, `family_search` looks up the Borges library
(`library_search`) and Links (`search_links`) through the hub or directly, and keeps each hit as a `family_ref` source
(`hoard://<app>/<kind>/<id>` with a short excerpt); an app that does not answer is skipped. The tool names are
configurable in Settings. Atlas emits `atlas.case.created`, `atlas.relation.added`, `atlas.relation.status_changed`
and `atlas.source.retracted`, and its cases are addressable as `hoard://atlas/case/<id>`.

## Development

```bash
pip install -r requirements.txt
python -m pytest -q      # no network: fetching, Wikidata, geocoding, the model and other apps are faked
npm run build
```

The UI is in Spanish by default and English when the browser language is English.

## Limits

- Wikidata is read through its web API (search and entity data), not SPARQL.
- The address check happens before the request; a host that changes its DNS answer between the check and the
  request is not caught.
- PDF extraction is text only; scanned PDFs need OCR elsewhere.
- Relations with the same triple but different dates are kept apart on purpose; merge them by hand if they describe
  the same fact.
- The map needs internet access for its tiles.

## Credits

Map data © OpenStreetMap contributors (ODbL); tiles from openstreetmap.org; place lookup by Nominatim; entity data
from Wikidata (CC0). Leaflet and d3-force draw the map and the graph.

## License

See `LICENSE`.
