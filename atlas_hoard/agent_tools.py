"""Tools exposed to the assistant. One catalogue drives /api/agent/*, mcp_server.py and the UI routes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field

from . import ach as ach_mod
from . import cases as cases_mod
from . import enrich as enrich_mod
from . import entities as entities_mod
from . import history as history_mod
from . import reports as reports_mod
from . import relations as relations_mod
from . import sources as sources_mod
from . import timeline as timeline_mod
from .errors import AtlasError
from .services import Services

AGENT_INSTRUCTIONS = """Atlas's Hoard is a research-case workspace: sources, entities, evidence-backed relations, a timeline, a map and
competing-hypotheses analysis. Work in this order: case_create -> source_add (capture or paste what you may use; grade it) ->
entity_upsert -> relation_add (evidence is mandatory: source_id plus a verbatim quote or a locator) -> timeline / map_layers / graph ->
hypothesis_add + ach_rate -> case_report.
Rules: cite sources as [S<id>] in anything you write from a case. Relations are claimed until two independent sources back them
(corroborated); only a person confirms or retracts. Retracting a source never deletes: relations it alone supported become unsupported.
Similar names are suggestions (duplicates_suggest), never merges: entity_merge is explicit. Pass as_of to see facts as they were.
A person-type entity is a private person unless public_figure=true: enrichers and family_search skip private persons; do not add
personal-data lookups or social-network pages (URL capture refuses them; paste text you may use as a text source instead).
The least-contradicted hypothesis in ach_matrix is never 'proven'. Deletes need action=delete and confirm=true; ask the user first."""

Id = Optional[int]


class Empty(BaseModel):
    pass


class CaseCreateArgs(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    question: str = Field("", max_length=2000, description="The research question the case tries to answer.")
    tags: Optional[list[str]] = None
    summary: str = Field("", max_length=4000)
    open_questions: Optional[list[str]] = None


class CaseListArgs(BaseModel):
    status: Optional[Literal["open", "paused", "closed"]] = None
    query: Optional[str] = Field(None, max_length=200)
    limit: int = Field(30, ge=1, le=100)
    cursor: Optional[str] = None


class CaseGetArgs(BaseModel):
    case_id: int


class CaseUpdateArgs(BaseModel):
    case_id: int
    action: Literal["update", "delete"] = "update"
    confirm: bool = Field(False, description="Required with action=delete: removes the whole case.")
    title: Optional[str] = Field(None, max_length=200)
    question: Optional[str] = Field(None, max_length=2000)
    status: Optional[Literal["open", "paused", "closed"]] = None
    tags: Optional[list[str]] = None
    summary: Optional[str] = Field(None, max_length=4000)
    open_questions: Optional[list[str]] = None


class SourceAddArgs(BaseModel):
    case_id: Optional[int] = Field(None, description="Case to add to (not needed when updating with source_id).")
    source_id: Optional[int] = Field(None, description="Update this source's grades/metadata instead of adding one.")
    kind: Optional[Literal["url", "file", "text", "family_ref", "note"]] = None
    title: str = Field("", max_length=300)
    url: str = Field("", max_length=2000, description="kind=url: page to capture (public web only). With kind=text it is just a reference.")
    path: str = Field("", max_length=1000, description="kind=file: local txt/md/pdf/csv/json/html file.")
    text: str = Field("", max_length=400_000, description="kind=text/note: the text to keep as the snapshot.")
    ref: str = Field("", max_length=300, description="kind=family_ref: hoard://<app>/<kind>/<id>.")
    revision: str = Field("", max_length=200, description="kind=family_ref: revision of the referenced item (sha256:...).")
    reliability: Optional[str] = Field(None, max_length=1, description="Source reliability A (completely) to F (cannot be judged).")
    credibility: Optional[str] = Field(None, max_length=1, description="Information credibility 1 (confirmed) to 6 (cannot be judged).")
    published_at: Optional[str] = Field(None, max_length=10, description="YYYY, YYYY-MM or YYYY-MM-DD.")
    origin: str = Field("", max_length=200, description="Who is behind it; sources with the same origin do not corroborate each other.")
    note: str = Field("", max_length=2000)


class SourceGetArgs(BaseModel):
    source_id: int
    max_chars: int = Field(4000, ge=200, le=12000)
    offset: int = Field(0, ge=0)


class SourceRetractArgs(BaseModel):
    source_id: int
    action: Literal["retract", "restore", "delete"] = "retract"
    reason: str = Field("", max_length=500)
    confirm: bool = Field(False, description="Required with action=delete (only for sources nothing cites).")


class SourcesSearchArgs(BaseModel):
    case_id: int
    query: str = Field(..., min_length=1, max_length=300)
    kind: Optional[str] = Field(None, max_length=20)
    include_retracted: bool = False
    limit: int = Field(10, ge=1, le=50)
    cursor: Optional[str] = None


class EntityUpsertArgs(BaseModel):
    case_id: int
    action: Literal["upsert", "delete"] = "upsert"
    confirm: bool = False
    entity_id: Optional[int] = Field(None, description="Edit this entity; otherwise matched by name+type or created.")
    type: Optional[Literal["person", "organization", "place", "event", "document", "object", "domain", "concept"]] = None
    name: Optional[str] = Field(None, max_length=300)
    aliases: Optional[list[str]] = None
    remove_aliases: Optional[list[str]] = None
    description: Optional[str] = Field(None, max_length=4000)
    attributes: Optional[dict[str, Any]] = Field(None, description="name -> value, or name -> {value, source_id, quote, locator, valid_from, valid_to}.")
    remove_attributes: Optional[list[str]] = None
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    geo_precision: Optional[str] = Field(None, max_length=40)
    date_start: Optional[str] = Field(None, max_length=10)
    date_end: Optional[str] = Field(None, max_length=10)
    wikidata_qid: Optional[str] = Field(None, max_length=20)
    public_figure: Optional[bool] = Field(None, description="Top-level parameter (not an attribute): a person is private unless this is true; it lifts the private-person guard for enrichers.")
    private_person: Optional[bool] = None


class EntityGetArgs(BaseModel):
    entity_id: int
    as_of: Optional[str] = Field(None, max_length=10)
    include_retracted: bool = False


class EntitySearchArgs(BaseModel):
    query: Optional[str] = Field(None, max_length=200)
    case_id: Optional[int] = None
    type: Optional[Literal["person", "organization", "place", "event", "document", "object", "domain", "concept"]] = None
    limit: int = Field(20, ge=1, le=100)
    cursor: Optional[str] = None


class EntityMergeArgs(BaseModel):
    keep_id: int
    merge_id: int
    confirm: bool = Field(False, description="Without it the call only previews what would move.")


class DuplicatesArgs(BaseModel):
    case_id: int
    min_score: float = Field(0.5, ge=0, le=1)
    limit: int = Field(20, ge=1, le=100)


class EvidenceItem(BaseModel):
    source_id: int
    quote: str = Field("", max_length=2000, description="Verbatim passage of the source.")
    locator: str = Field("", max_length=200, description="Page, section, timestamp.")
    observed_at: Optional[str] = Field(None, max_length=10)


class RelationAddArgs(BaseModel):
    case_id: int
    subject: int | str = Field(..., description="Entity id or exact name/alias.")
    predicate: str = Field(..., min_length=1, max_length=60, description="e.g. works_for, headquartered_in, founded (free text allowed).")
    object: int | str = Field(..., description="Entity id or exact name/alias.")
    evidence: list[EvidenceItem] = Field(..., min_length=1, description="At least one {source_id, quote|locator}.")
    valid_from: Optional[str] = Field(None, max_length=10)
    valid_to: Optional[str] = Field(None, max_length=10)
    observed_at: Optional[str] = Field(None, max_length=10)
    confidence: Optional[float] = Field(None, ge=0, le=1)
    notes: str = Field("", max_length=2000)
    derived_from: Optional[list[int]] = Field(None, description="Relation ids this one was inferred from.")


class RelationUpdateArgs(BaseModel):
    relation_id: int
    action: Literal["update", "delete"] = "update"
    confirm: bool = False
    subject: Optional[int | str] = None
    predicate: Optional[str] = Field(None, max_length=60)
    object: Optional[int | str] = None
    valid_from: Optional[str] = Field(None, max_length=10)
    valid_to: Optional[str] = Field(None, max_length=10)
    observed_at: Optional[str] = Field(None, max_length=10)
    clear_dates: Optional[list[str]] = Field(None, description="Any of valid_from, valid_to, observed_at to empty.")
    confidence: Optional[float] = Field(None, ge=0, le=1)
    notes: Optional[str] = Field(None, max_length=2000)
    status: Optional[Literal["disputed", "confirmed", "clear"]] = Field(None, description="Person's judgement; confirmed needs 2 independent sources.")
    reason: str = Field("", max_length=500)
    add_evidence: Optional[list[EvidenceItem]] = None
    remove_evidence: Optional[list[int]] = None
    derived_from: Optional[list[int]] = None


class RelationRetractArgs(BaseModel):
    relation_id: int
    reason: str = Field("", max_length=500)
    action: Literal["retract", "restore"] = "retract"


class RelationGetArgs(BaseModel):
    relation_id: Optional[int] = Field(None, description="One relation with all its evidence.")
    case_id: Optional[int] = Field(None, description="Or list a case's relations (paginated, with 3 quotes each).")
    subject: Optional[int | str] = None
    object: Optional[int | str] = None
    predicate: Optional[str] = Field(None, max_length=60)
    statuses: Optional[list[Literal["claimed", "corroborated", "confirmed", "disputed", "retracted", "unsupported"]]] = None
    as_of: Optional[str] = Field(None, max_length=10)
    include_retracted: bool = True
    limit: int = Field(30, ge=1, le=100)
    cursor: Optional[str] = None


class TimelineArgs(BaseModel):
    case_id: int
    entity_id: Optional[int] = None
    types: Optional[list[str]] = None
    as_of: Optional[str] = Field(None, max_length=10)
    date_from: Optional[str] = Field(None, max_length=10)
    date_to: Optional[str] = Field(None, max_length=10)
    gap_days: int = Field(365, ge=1, le=36500)
    include_retracted: bool = False
    limit: int = Field(60, ge=1, le=1000)


class MapArgs(BaseModel):
    case_id: int
    as_of: Optional[str] = Field(None, max_length=10)
    date_from: Optional[str] = Field(None, max_length=10)
    date_to: Optional[str] = Field(None, max_length=10)
    types: Optional[list[str]] = None


class GraphArgs(BaseModel):
    case_id: int
    entity_id: Optional[int] = Field(None, description="Neighbourhood of this entity instead of the whole case.")
    depth: int = Field(1, ge=1, le=4)
    statuses: Optional[list[Literal["claimed", "corroborated", "confirmed", "disputed", "retracted", "unsupported"]]] = None
    as_of: Optional[str] = Field(None, max_length=10)
    date_from: Optional[str] = Field(None, max_length=10)
    date_to: Optional[str] = Field(None, max_length=10)
    include_retracted: bool = False
    max_nodes: int = Field(60, ge=5, le=600)


class HypothesisAddArgs(BaseModel):
    case_id: Optional[int] = None
    hypothesis_id: Optional[int] = Field(None, description="Edit or delete this hypothesis.")
    statement: Optional[str] = Field(None, max_length=1000)
    status: Optional[Literal["open", "discarded"]] = None
    action: Literal["upsert", "delete"] = "upsert"
    confirm: bool = False


class AchRateArgs(BaseModel):
    hypothesis_id: int
    evidence_id: Optional[int] = Field(None, description="An evidence item of the case (see ach_matrix with include_unrated).")
    evidence: Optional[EvidenceItem] = Field(None, description="Or create a case-level evidence item {source_id, quote|locator}.")
    rating: Optional[Literal["CC", "C", "N", "I", "II", "NA"]] = None
    note: str = Field("", max_length=500)
    action: Literal["rate", "delete"] = "rate"


class AchMatrixArgs(BaseModel):
    case_id: int
    include_unrated: bool = Field(False, description="List every evidence item, not only the rated ones.")


class EnrichArgs(BaseModel):
    enricher: Literal["wikidata", "geocode", "url_capture", "family_search"]
    case_id: Optional[int] = None
    entity_id: Optional[int] = None
    qid: Optional[str] = Field(None, max_length=20)
    language: Optional[str] = Field(None, max_length=5)
    query: Optional[str] = Field(None, max_length=300)
    url: Optional[str] = Field(None, max_length=2000)
    title: Optional[str] = Field(None, max_length=300)
    note: Optional[str] = Field(None, max_length=1000)
    reliability: Optional[str] = Field(None, max_length=1)
    credibility: Optional[str] = Field(None, max_length=1)
    overwrite: bool = False
    dry_run: bool = False
    apps: Optional[list[str]] = None
    limit: Optional[int] = Field(None, ge=1, le=20)
    include_private: bool = False


class EnrichmentUndoArgs(BaseModel):
    run_id: int


class CaseReportArgs(BaseModel):
    case_id: int
    format: Literal["markdown", "json"] = "markdown"
    lang: Literal["es", "en"] = "en"
    use_model: bool = True
    section: Optional[Literal["summary", "entities", "relations", "timeline", "ach", "open_questions", "sources"]] = None
    offset: int = Field(0, ge=0)
    max_chars: int = Field(14000, ge=1000, le=10_000_000)


class HistoryArgs(BaseModel):
    case_id: Optional[int] = None
    target_type: Optional[str] = Field(None, max_length=20)
    target_id: Optional[int] = None
    action: Optional[str] = Field(None, max_length=40)
    limit: int = Field(30, ge=1, le=100)
    cursor: Optional[str] = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    annotations: dict[str, bool]
    run: Callable[[Services, Any], Any]


def _ann(read_only: bool, destructive: bool = False, idempotent: bool | None = None, open_world: bool = False) -> dict[str, bool]:
    return {"readOnlyHint": read_only, "destructiveHint": destructive,
            "idempotentHint": read_only if idempotent is None else idempotent, "openWorldHint": open_world}


def _kw(args: BaseModel, *drop: str) -> dict[str, Any]:
    data = args.model_dump(exclude_none=True)
    for k in drop:
        data.pop(k, None)
    return data


def _ev(items) -> list[dict]:
    return [i.model_dump() if hasattr(i, "model_dump") else i for i in (items or [])]


# ---------------- runners ----------------

def run_status(svc: Services, args: Empty) -> dict:
    return svc.status()


def run_case_create(svc: Services, a: CaseCreateArgs) -> dict:
    return cases_mod.create(svc, **_kw(a))


def run_case_list(svc: Services, a: CaseListArgs) -> dict:
    return cases_mod.list_cases(svc, **_kw(a))


def run_case_get(svc: Services, a: CaseGetArgs) -> dict:
    return cases_mod.get(svc, a.case_id)


def run_case_update(svc: Services, a: CaseUpdateArgs) -> dict:
    if a.action == "delete":
        return cases_mod.delete(svc, a.case_id, a.confirm)
    return cases_mod.update(svc, a.case_id, **_kw(a, "case_id", "action", "confirm"))


def run_source_add(svc: Services, a: SourceAddArgs) -> dict:
    return sources_mod.add(svc, **_kw(a))


def run_source_get(svc: Services, a: SourceGetArgs) -> dict:
    return sources_mod.get(svc, a.source_id, max_chars=a.max_chars, offset=a.offset)


def run_source_retract(svc: Services, a: SourceRetractArgs) -> dict:
    return sources_mod.retract(svc, a.source_id, action=a.action, reason=a.reason, confirm=a.confirm)


def run_sources_search(svc: Services, a: SourcesSearchArgs) -> dict:
    return sources_mod.search(svc, a.case_id, a.query, kind=a.kind, include_retracted=a.include_retracted, limit=a.limit, cursor=a.cursor)


def run_entity_upsert(svc: Services, a: EntityUpsertArgs) -> dict:
    if a.action == "delete":
        if a.entity_id is None:
            raise AtlasError("entity_id is required to delete an entity.")
        return entities_mod.delete(svc, a.entity_id, a.confirm)
    return entities_mod.upsert(svc, **_kw(a, "action", "confirm"))


def run_entity_get(svc: Services, a: EntityGetArgs) -> dict:
    return entities_mod.get(svc, a.entity_id, as_of=a.as_of, include_retracted=a.include_retracted)


def run_entity_search(svc: Services, a: EntitySearchArgs) -> dict:
    return entities_mod.search(svc, **_kw(a))


def run_entity_merge(svc: Services, a: EntityMergeArgs) -> dict:
    return entities_mod.merge(svc, a.keep_id, a.merge_id, confirm=a.confirm)


def run_duplicates(svc: Services, a: DuplicatesArgs) -> dict:
    return entities_mod.suggest_duplicates(svc, a.case_id, min_score=a.min_score, limit=a.limit)


def run_relation_add(svc: Services, a: RelationAddArgs) -> dict:
    data = _kw(a, "evidence")
    return relations_mod.add(svc, evidence=_ev(a.evidence), **data)


def run_relation_update(svc: Services, a: RelationUpdateArgs) -> dict:
    if a.action == "delete":
        return relations_mod.delete(svc, a.relation_id, a.confirm)
    data = _kw(a, "action", "confirm", "relation_id", "add_evidence")
    return relations_mod.update(svc, a.relation_id, add_evidence=_ev(a.add_evidence) or None, **data)


def run_relation_retract(svc: Services, a: RelationRetractArgs) -> dict:
    return relations_mod.retract(svc, a.relation_id, reason=a.reason, action=a.action)


def run_relation_get(svc: Services, a: RelationGetArgs) -> dict:
    if a.relation_id is not None:
        return relations_mod.get(svc, a.relation_id)
    if a.case_id is None:
        raise AtlasError("Give relation_id (one relation) or case_id (a list).")
    return relations_mod.list_page(svc, a.case_id, subject=a.subject, object=a.object, predicate=a.predicate, statuses=a.statuses,
                                   as_of=a.as_of, include_retracted=a.include_retracted, limit=a.limit, cursor=a.cursor)


def run_timeline(svc: Services, a: TimelineArgs) -> dict:
    return timeline_mod.timeline(svc, **_kw(a))


def run_map_layers(svc: Services, a: MapArgs) -> dict:
    return timeline_mod.map_layers(svc, **_kw(a))


def run_graph(svc: Services, a: GraphArgs) -> dict:
    return timeline_mod.graph(svc, **_kw(a))


def run_hypothesis_add(svc: Services, a: HypothesisAddArgs) -> dict:
    return ach_mod.hypothesis(svc, **_kw(a))


def run_ach_rate(svc: Services, a: AchRateArgs) -> dict:
    return ach_mod.rate(svc, hypothesis_id=a.hypothesis_id, evidence_id=a.evidence_id,
                        evidence=a.evidence.model_dump() if a.evidence else None, rating=a.rating, note=a.note, action=a.action)


def run_ach_matrix(svc: Services, a: AchMatrixArgs) -> dict:
    return ach_mod.matrix(svc, a.case_id, include_unrated=a.include_unrated)


def run_enrich(svc: Services, a: EnrichArgs) -> dict:
    return enrich_mod.run(svc, **_kw(a))


def run_enrichment_undo(svc: Services, a: EnrichmentUndoArgs) -> dict:
    return enrich_mod.undo(svc, a.run_id)


def run_case_report(svc: Services, a: CaseReportArgs) -> dict:
    return reports_mod.report(svc, a.case_id, format=a.format, lang=a.lang, use_model=a.use_model, offset=a.offset,
                              max_chars=a.max_chars, section=a.section)


def run_history(svc: Services, a: HistoryArgs) -> dict:
    return history_mod.list_history(svc, a.case_id, target_type=a.target_type, target_id=a.target_id, action=a.action,
                                    limit=a.limit, cursor=a.cursor)


TOOLS: list[Tool] = [
    Tool("atlas_status",
        "Health and counts: cases, sources, entities, relations, model and geocoding status. Estado de Atlas.\n"
        "Sinónimos: estado, salud, ¿funciona?, modelos disponibles, geocodificación.\nKeywords: status, health, counts.",
        Empty, _ann(True), run_status),
    Tool("case_create",
        "Open a research case with a question: title, tags, open questions. Crear un caso de investigación.\n"
        "A case holds sources, entities, relations, hypotheses and its own history.\n"
        "Sinónimos: nuevo caso, investigación, expediente, abrir caso.\nKeywords: new case, investigation, dossier.",
        CaseCreateArgs, _ann(False, False, False), run_case_create),
    Tool("case_list",
        "List research cases with counts, newest first. Listar casos de investigación.\n"
        "Sinónimos: casos, investigaciones, expedientes, buscar caso.\nKeywords: cases, list, search.",
        CaseListArgs, _ann(True), run_case_list),
    Tool("case_get",
        "One case with its dashboard: counts, unsupported/stale/disputed relations, open questions. Ver caso.\n"
        "Sinónimos: panel del caso, resumen, pendientes, qué falta.\nKeywords: dashboard, overview, attention.",
        CaseGetArgs, _ann(True), run_case_get),
    Tool("case_update",
        "Edit a case (title, question, status, tags, summary, open questions) or delete it with confirm. Editar caso.\n"
        "action=delete needs confirm=true and removes everything in the case: only when the user asks.\n"
        "Sinónimos: actualizar caso, cerrar caso, pausar, borrar caso.\nKeywords: edit, close, delete case.",
        CaseUpdateArgs, _ann(False, True, True), run_case_update),
    Tool("source_add",
        "Add a source to a case: capture a URL, paste text, read a file, reference a family doc. Añadir fuente.\n"
        "Grades: reliability A-F, credibility 1-6. URL capture never runs JavaScript and refuses social networks. "
        "With source_id it edits grades/metadata instead.\nSinónimos: fuente, capturar web, pegar texto, documento, graduar fuente.\n"
        "Keywords: source, url capture, grade, admiralty.",
        SourceAddArgs, _ann(False, False, True, True), run_source_add),
    Tool("source_get",
        "Read a source: grades, dates, hash, snapshot text (paged) and the evidence that cites it. Leer una fuente.\n"
        "Sinónimos: ver fuente, texto de la fuente, snapshot, dónde se cita.\nKeywords: source, snapshot, citations.",
        SourceGetArgs, _ann(True), run_source_get),
    Tool("source_retract",
        "Retract a source (or restore it): relations that only it supported become unsupported. Retractar fuente.\n"
        "Nothing is deleted; the cascade is reported. action=delete (confirm) only for sources nothing cites.\n"
        "Sinónimos: retirar fuente, desmentir, fuente falsa, rectificación.\nKeywords: retract, withdraw, debunk, restore.",
        SourceRetractArgs, _ann(False, True, True), run_source_retract),
    Tool("sources_search",
        "Full-text search over a case's sources (title, text, url, notes) with snippets. Buscar en las fuentes.\n"
        "Sinónimos: buscar fuentes, búsqueda de texto, qué dice la fuente, FTS.\nKeywords: search sources, full text.",
        SourcesSearchArgs, _ann(True), run_sources_search),
    Tool("entity_upsert",
        "Create or edit an entity (person, organization, place, event...) with aliases, geo, dates. Entidad.\n"
        "Matched by name+type, so repeated calls do not duplicate; persons are private unless the parameter public_figure=true is passed "
        "(a top-level parameter, never an attribute; it lifts the guard that blocks enrichers). "
        "action=delete needs confirm. Returns possible duplicates.\nSinónimos: crear entidad, persona, organización, lugar, evento, alias, coordenadas.\n"
        "Keywords: entity, upsert, person, organisation, place, event, aliases.",
        EntityUpsertArgs, _ann(False, True, True), run_entity_upsert),
    Tool("entity_get",
        "One entity with attributes (and their support), relations (as_of), evidence and history. Ver entidad.\n"
        "Sinónimos: ficha de entidad, relaciones de, qué sabemos de, vigente en una fecha.\nKeywords: entity, profile, as of date.",
        EntityGetArgs, _ann(True), run_entity_get),
    Tool("entity_search",
        "Search entities by name, alias or description, filter by type or case. Buscar entidades.\n"
        "Sinónimos: buscar persona, organización, lugar, alias, quién es.\nKeywords: find entity, lookup, alias.",
        EntitySearchArgs, _ann(True), run_entity_search),
    Tool("entity_merge",
        "Merge two entities of a case (explicit; preview without confirm). Fusionar entidades duplicadas.\n"
        "Moves relations, evidence, aliases and attributes into keep_id and records history. Similar names are never merged on their own.\n"
        "Sinónimos: fusionar, unir duplicados, misma entidad.\nKeywords: merge, dedupe, same entity.",
        EntityMergeArgs, _ann(False, True, False), run_entity_merge),
    Tool("duplicates_suggest",
        "Suggest possible duplicate entities with reasons (name, alias, QID, coordinates). Duplicados.\n"
        "Suggestions only: coincidence is not identity. Sinónimos: duplicados, posibles iguales, mismo nombre.\nKeywords: duplicates, similar.",
        DuplicatesArgs, _ann(True), run_duplicates),
    Tool("relation_add",
        "Add a relation subject-predicate-object; evidence (source + quote/locator) is required. Añadir relación.\n"
        "Status is derived: claimed, corroborated with 2 independent sources. Same triple+dates adds evidence to the existing one. "
        "Dates are YYYY[-MM[-DD]].\nSinónimos: relación, vínculo, trabaja para, sede en, fundó, con evidencia, cita.\n"
        "Keywords: relation, edge, link, evidence, valid from/to.",
        RelationAddArgs, _ann(False, False, False), run_relation_add),
    Tool("relation_update",
        "Edit a relation: dates, predicate, evidence, disputed/confirmed; or delete with confirm. Editar relación.\n"
        "confirmed needs 2 independent sources; the last evidence item cannot be removed. Sinónimos: corregir relación, disputar, confirmar, "
        "añadir evidencia, borrar relación.\nKeywords: edit relation, dispute, confirm, evidence.",
        RelationUpdateArgs, _ann(False, True, True), run_relation_update),
    Tool("relation_retract",
        "Retract a relation with a reason (or restore it); history and evidence are kept. Retractar relación.\n"
        "Anything derived from it is flagged. Sinónimos: retirar relación, era falsa, descartar vínculo.\nKeywords: retract relation, withdraw.",
        RelationRetractArgs, _ann(False, True, True), run_relation_retract),
    Tool("relation_get",
        "Read one relation with its quotes, or list a case's relations by status/entity/as_of. Ver relaciones.\n"
        "Sinónimos: relaciones del caso, evidencia de una relación, citas, filtrar por estado.\nKeywords: relations, evidence quotes, list.",
        RelationGetArgs, _ann(True), run_relation_get),
    Tool("timeline",
        "Case timeline: events and dated relations, gaps and contradictions; filter by entity, type, as_of. Cronología.\n"
        "Sinónimos: línea de tiempo, fechas, huecos, contradicciones, en una fecha.\nKeywords: timeline, gaps, contradictions, as of.",
        TimelineArgs, _ann(True), run_timeline),
    Tool("map_layers",
        "Map data: layers by entity type with coordinates, source count and date coverage. Capas del mapa.\n"
        "Sinónimos: mapa, lugares, eventos geolocalizados, cobertura, sin coordenadas.\nKeywords: map, layers, geo, coordinates.",
        MapArgs, _ann(True), run_map_layers),
    Tool("graph",
        "Relation graph of a case or an entity's neighbourhood (depth), edges coloured by status. Grafo de relaciones.\n"
        "Sinónimos: red, vecindario, conexiones, quién se relaciona con, grafo.\nKeywords: graph, network, neighbourhood, depth.",
        GraphArgs, _ann(True), run_graph),
    Tool("hypothesis_add",
        "Add, edit, discard or delete a competing hypothesis of a case. Añadir hipótesis.\n"
        "Sinónimos: hipótesis, explicación alternativa, descartar hipótesis.\nKeywords: hypothesis, ACH, alternative explanation.",
        HypothesisAddArgs, _ann(False, True, True), run_hypothesis_add),
    Tool("ach_rate",
        "Rate evidence against a hypothesis: CC, C, N, I, II, NA (ACH cell). Valorar evidencia e hipótesis.\n"
        "Can create a case-level evidence item inline. Sinónimos: valorar, consistente, inconsistente, matriz de hipótesis.\n"
        "Keywords: ACH, rate, consistent, inconsistent.",
        AchRateArgs, _ann(False, False, True), run_ach_rate),
    Tool("ach_matrix",
        "ACH matrix: scores, diagnosticity, sensitivity; the least contradicted hypothesis, never 'proven'. Matriz ACH.\n"
        "Sinónimos: análisis de hipótesis competidoras, cuál es la menos contradicha, sensibilidad, diagnosticidad.\nKeywords: ACH matrix, ranking.",
        AchMatrixArgs, _ann(True), run_ach_matrix),
    Tool("enrich",
        "Enrich a case: wikidata, geocode (Nominatim), url_capture, family_search (Borges, Links). Enriquecer.\n"
        "Traceable run, undoable, never on private persons; results are claimed. dry_run previews. Sinónimos: wikidata, geocodificar, "
        "capturar url, buscar en la biblioteca, QID.\nKeywords: enrich, wikidata, geocode, capture, family search.",
        EnrichArgs, _ann(False, False, False, True), run_enrich),
    Tool("enrichment_undo",
        "Undo one enrichment run: removes what it created, restores what it changed. Deshacer enriquecimiento.\n"
        "Sinónimos: deshacer, revertir, quitar lo añadido por el enriquecedor.\nKeywords: undo, revert enrichment.",
        EnrichmentUndoArgs, _ann(False, True, True), run_enrichment_undo),
    Tool("case_report",
        "Case report in Markdown or JSON with [S12] citations, status groups, timeline, ACH, sources. Informe del caso.\n"
        "Summary by a model when available (citation-checked: uncited sentences are flagged) else deterministic; paged by offset.\n"
        "Sinónimos: informe, resumen, exportar, citas, memoria del caso.\nKeywords: report, markdown, citations, summary.",
        CaseReportArgs, _ann(True), run_case_report),
    Tool("history",
        "Change history of a case: who (caller), what, when, with before/after. Historial de cambios.\n"
        "Sinónimos: auditoría, qué cambió, quién cambió, registro de cambios.\nKeywords: history, audit, changes, log.",
        HistoryArgs, _ann(True), run_history),
]

TOOLS_BY_NAME = {t.name: t for t in TOOLS}
RESULT_CAP = 20_000


def tool_catalog() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "annotations": t.annotations,
         "inputSchema": t.input_model.model_json_schema(by_alias=True)}
        for t in TOOLS
    ]


def cap_result(result: Any, limit: int = RESULT_CAP) -> Any:
    """Keep an agent-facing result under ~20 KB: halve the biggest list until it fits and say so."""
    if not isinstance(result, dict) or len(json.dumps(result, ensure_ascii=False)) <= limit:
        return result
    cut: list[str] = []
    for _ in range(40):
        size = len(json.dumps(result, ensure_ascii=False))
        if size <= limit:
            break
        best: tuple[int, Any, str] | None = None
        for key, value in result.items():
            if isinstance(value, list) and len(value) > 1:
                n = len(json.dumps(value, ensure_ascii=False))
                if best is None or n > best[0]:
                    best = (n, result, key)
            elif isinstance(value, dict):
                for k2, v2 in value.items():
                    if isinstance(v2, list) and len(v2) > 1:
                        n = len(json.dumps(v2, ensure_ascii=False))
                        if best is None or n > best[0]:
                            best = (n, value, k2)
        if best is None:
            text_key = max((k for k, v in result.items() if isinstance(v, str)), key=lambda k: len(result[k]), default=None)
            if text_key and len(result[text_key]) > 1000:
                result[text_key] = result[text_key][: len(result[text_key]) // 2] + "…"
                cut.append(text_key)
                continue
            break
        _, holder, key = best
        holder[key] = holder[key][: max(1, len(holder[key]) // 2)]
        cut.append(key)
    if cut:
        result["truncated"] = True
        result["truncated_fields"] = sorted(set(cut))
        result["hint"] = "The result was trimmed to fit ~20 KB: narrow the filters, lower limit, or page with cursor/offset."
    return result


def call_tool(svc: Services, name: str, arguments: dict | None, *, caller: str | None = None, cap: bool = False) -> Any:
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    args = tool.input_model.model_validate(arguments or {})
    token = history_mod.set_caller(caller)
    try:
        result = tool.run(svc, args)
    finally:
        history_mod.CALLER.reset(token)
    return cap_result(result) if cap else result
