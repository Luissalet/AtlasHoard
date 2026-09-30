# Atlas's Hoard: REST API

Base URL `http://127.0.0.1:5193` (the resolved port is written to `data/url`). The routes serve the bundled UI and run
the same code as the MCP tools of the same name. Bodies and responses are JSON. Errors are `{"error": "message"}`:
400 invalid input, 403 refused by the ethics guard, 404 not found, 401 missing or wrong agent token.
Deleting needs `confirm=true`.

## Health

| route | notes |
| --- | --- |
| `GET /api/health` | service, version, counts, link status |
| `GET /api/status` | adds model and geocoding status, family sources, uptime |

## Cases

| route | notes |
| --- | --- |
| `GET /api/cases` | `status`, `query`, `limit`, `cursor` |
| `POST /api/cases` | `title`, `question`, `tags`, `summary`, `open_questions` |
| `GET /api/cases/{id}` | case, counts and dashboard |
| `PUT /api/cases/{id}` | any of the create fields plus `status` (`open`, `paused`, `closed`) |
| `DELETE /api/cases/{id}?confirm=true` | removes the case and everything in it |

## Sources

| route | notes |
| --- | --- |
| `GET /api/cases/{id}/sources` | `kind`, `include_retracted`, `limit`, `cursor` |
| `GET /api/cases/{id}/sources/search?q=` | full text with snippets |
| `POST /api/cases/{id}/sources` | `kind` (`url`, `file`, `text`, `family_ref`, `note`), `url`, `path`, `text`, `ref`, `title`, `reliability` (A-F), `credibility` (1-6), `origin`, `published_at` |
| `GET /api/sources/{id}` | `max_chars`, `offset` page the snapshot text |
| `PUT /api/sources/{id}` | grades and metadata |
| `POST /api/sources/{id}/retract` | `action` (`retract`, `restore`), `reason`; returns what the retraction affected |
| `DELETE /api/sources/{id}?confirm=true` | only when nothing cites it |

## Entities

| route | notes |
| --- | --- |
| `GET /api/cases/{id}/entities` | `type`, `q`, `limit`, `cursor` |
| `POST /api/cases/{id}/entities` | `type`, `name`, `aliases`, `description`, `attributes`, `lat`, `lon`, `date_start`, `date_end`, `public_figure` |
| `GET /api/entities/{id}` | attributes with support, relations (`as_of`), evidence, history |
| `PUT /api/entities/{id}` | same fields as create |
| `DELETE /api/entities/{id}?confirm=true` | only when it is in no relation |
| `GET /api/cases/{id}/duplicates` | suggestions with reasons |
| `POST /api/entities/merge` | `keep_id`, `merge_id`, `confirm` (without it, a preview) |

## Relations

| route | notes |
| --- | --- |
| `GET /api/cases/{id}/relations` | `status`, `subject`, `object`, `predicate`, `as_of`, `limit`, `cursor` |
| `POST /api/cases/{id}/relations` | `subject`, `predicate`, `object`, `evidence` (`[{source_id, quote or locator}]`, required), `valid_from`, `valid_to`, `confidence`, `derived_from` |
| `GET /api/relations/{id}` | with evidence and quote verification |
| `PUT /api/relations/{id}` | dates, evidence (`add_evidence`, `remove_evidence`), `status` (`disputed`, `confirmed`, `clear`) |
| `POST /api/relations/{id}/retract` | `reason`, `action` (`retract`, `restore`) |
| `DELETE /api/relations/{id}?confirm=true` | |
| `GET /api/predicates`, `PUT /api/predicates`, `DELETE /api/predicates/{name}` | the predicate vocabulary (`functional`, `symmetric`) |

## Analysis

| route | notes |
| --- | --- |
| `GET /api/cases/{id}/timeline` | `as_of`, `date_from`, `date_to`, `types`, `entity_id`, `gap_days`, `limit` |
| `GET /api/cases/{id}/map` | `as_of`, `date_from`, `date_to`, `types` |
| `GET /api/cases/{id}/graph` | `entity_id`, `depth`, `status`, `as_of`, `include_retracted`, `max_nodes` |
| `GET /api/cases/{id}/evidence` | every evidence item, for the ACH matrix |
| `GET /api/cases/{id}/ach` | matrix, scores, diagnosticity, pivotal evidence, note |
| `POST /api/cases/{id}/hypotheses`, `PUT` and `DELETE /api/hypotheses/{id}` | `statement`, `status` (`open`, `discarded`) |
| `PUT /api/ach` | `hypothesis_id`, `evidence_id` or `evidence`, `rating` (`CC`, `C`, `N`, `I`, `II`, `NA`), `action` (`rate`, `delete`) |
| `GET /api/cases/{id}/report` | `format` (`markdown`, `json`), `lang` (`es`, `en`), `use_model`, `section`, `raw=true` downloads the Markdown |
| `GET /api/cases/{id}/history` | `action` prefix, `target_type`, `target_id`, `limit`, `cursor` |

## Enrichment

| route | notes |
| --- | --- |
| `POST /api/cases/{id}/enrich` | `enricher` (`wikidata`, `geocode`, `url_capture`, `family_search`), `entity_id`, `qid`, `query`, `url`, `apps`, `dry_run`, `overwrite`, `include_private` |
| `GET /api/cases/{id}/enrichment` | runs, newest first |
| `POST /api/enrichment/{run_id}/undo` | removes what the run created, restores what it changed |

## Settings

`GET /api/settings`, `PUT /api/settings` with `geocode_enabled`, `family_sources`, `family_tools`.

## Agent bridge

| route | notes |
| --- | --- |
| `GET /api/agent/tools` | instructions and the tool catalogue (public) |
| `POST /api/agent/call` | `{name, arguments, caller}`; needs `Authorization: Bearer <contents of data/mcp-token>` |

## PWA

`GET /manifest.webmanifest`, `GET /sw.js` (caches built assets only; API calls always go to the network).
