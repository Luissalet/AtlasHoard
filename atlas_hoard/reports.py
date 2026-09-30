"""Case reports: Markdown and JSON with citations, plus the citation check that keeps model text honest.

The summary is written by a model through Hoard Link when one is available and by a deterministic template
otherwise. Either way every factual sentence must cite a source of the case (``[S12]``); sentences that do not
are flagged, never silently kept as if they were supported.
"""

from __future__ import annotations

import re
from typing import Any

from . import ach as ach_mod
from . import cases as cases_mod
from . import dates
from . import relations as relations_mod
from . import timeline as timeline_mod
from .util import clip, iso_day, iso_stamp

STATUS_ORDER = ("confirmed", "corroborated", "claimed", "disputed", "unsupported", "retracted")
T = {
    "en": {
        "question": "Question", "status": "Status", "summary": "Summary", "overview": "Overview", "entities": "Key entities",
        "relations": "Relations by status", "timeline": "Timeline", "gaps": "Gaps", "contradictions": "Contradictions",
        "ach": "Competing hypotheses", "open": "Open questions", "sources": "Sources", "private": "private person",
        "uncited": "uncited", "none": "None.", "valid": "valid", "confidence": "confidence", "stale": "stale", "evidence": "evidence",
        "model": "model-written summary, citation-checked", "det": "deterministic summary", "generated": "Generated",
        "retracted": "RETRACTED", "hyp": "Hypothesis", "score": "inconsistency", "least": "least contradicted so far",
        "no_support": "No supported relations yet.", "cite_problem": "Citation check", "counts": "{s} active sources, {e} entities, {r} relations",
        "unsupported_q": "Relation without support", "disputed_q": "Disputed relation", "stale_q": "Stale fact",
        "no_ratings_q": "Hypothesis without ratings", "conflict_q": "Conflict",
    },
    "es": {
        "question": "Pregunta", "status": "Estado", "summary": "Resumen", "overview": "Panorama", "entities": "Entidades clave",
        "relations": "Relaciones por estado", "timeline": "Cronología", "gaps": "Huecos", "contradictions": "Contradicciones",
        "ach": "Hipótesis en competencia", "open": "Preguntas abiertas", "sources": "Fuentes", "private": "persona privada",
        "uncited": "sin cita", "none": "Ninguna.", "valid": "vigente", "confidence": "confianza", "stale": "desactualizado", "evidence": "evidencia",
        "model": "resumen redactado por un modelo, con citas comprobadas", "det": "resumen determinista", "generated": "Generado",
        "retracted": "RETRACTADA", "hyp": "Hipótesis", "score": "inconsistencia", "least": "la menos contradicha hasta ahora",
        "no_support": "Todavía no hay relaciones con respaldo.", "cite_problem": "Comprobación de citas",
        "counts": "{s} fuentes activas, {e} entidades, {r} relaciones",
        "unsupported_q": "Relación sin respaldo", "disputed_q": "Relación en disputa", "stale_q": "Dato desactualizado",
        "no_ratings_q": "Hipótesis sin valorar", "conflict_q": "Conflicto",
    },
}
STATUS_LABEL = {
    "en": {"confirmed": "Confirmed", "corroborated": "Corroborated", "claimed": "Claimed", "disputed": "Disputed",
           "unsupported": "Unsupported", "retracted": "Retracted"},
    "es": {"confirmed": "Confirmadas", "corroborated": "Corroboradas", "claimed": "Afirmadas", "disputed": "En disputa",
           "unsupported": "Sin respaldo", "retracted": "Retractadas"},
}

_CITE_GROUP = re.compile(r"\[(S\d+(?:\s*[,;]\s*S?\d+)*)\]")


# ---------------- citation check ----------------

def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\[\"“(0-9-])", (text or "").replace("\n", " ").strip())
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if out and _CITE_GROUP.fullmatch(p.rstrip(".")):
            out[-1] += " " + p  # a citation that ended up alone after the full stop belongs to the sentence before
        else:
            out.append(p)
    return out


def cited_ids(sentence: str) -> list[int]:
    ids: list[int] = []
    for group in _CITE_GROUP.findall(sentence):
        ids += [int(n) for n in re.findall(r"\d+", group)]
    return ids


def is_claim(sentence: str) -> bool:
    """Heuristic: a sentence asserts something checkable when it has a number, a proper noun after its first word,
    or is long enough to carry content. Questions and very short connective sentences are not claims."""
    bare = _CITE_GROUP.sub("", sentence).strip()
    if not bare or bare.endswith("?"):
        return False
    words = re.findall(r"[\wÁÉÍÓÚÑáéíóúñü'-]+", bare)
    if any(ch.isdigit() for ch in bare):
        return True
    if any(w[:1].isupper() for w in words[1:]):
        return True
    return len(words) >= 8


def check_citations(svc, case_id: int, text: str) -> dict[str, Any]:
    known = {r["id"]: bool(r["retracted"]) for r in svc.db.query("SELECT id, retracted FROM sources WHERE case_id = ?", (case_id,))}
    sentences = split_sentences(text)
    uncited, invalid, retracted = [], set(), set()
    claims = cited = 0
    for s in sentences:
        ids = cited_ids(s)
        bad = [i for i in ids if i not in known]
        invalid |= set(bad)
        retracted |= {i for i in ids if known.get(i)}
        if not is_claim(s):
            continue
        claims += 1
        if ids and len(bad) < len(ids):
            cited += 1
        else:
            uncited.append(s)
    return {"ok": not uncited and not invalid, "sentences": len(sentences), "claims": claims, "cited": cited, "uncited": uncited,
            "invalid_citations": sorted(invalid), "retracted_citations": sorted(retracted)}


def mark_uncited(text: str, check: dict, label: str) -> str:
    out = text
    for s in check["uncited"]:
        out = out.replace(s, f"{s} ⚠[{label}]", 1)
    return out


# ---------------- material ----------------

def _valid_text(v: dict) -> str:
    if v["valid_from"] or v["valid_to"]:
        return f"{v['valid_from'] or '?'}–{v['valid_to'] or 'now'}"
    return ""


def gather(svc, case_id: int, lang: str) -> dict[str, Any]:
    case = cases_mod.get_row(svc, case_id)
    t = T[lang]
    rels = relations_mod.list_views(svc, case_id, include_retracted=True, with_evidence=True)
    by_status: dict[str, list] = {s: [] for s in STATUS_ORDER}
    for v in rels:
        by_status[v["status"]].append(v)
    ents = svc.db.query("SELECT * FROM entities WHERE case_id = ? AND merged_into IS NULL", (case_id,))
    from . import entities as entities_mod
    ent_views = sorted((entities_mod.view(svc, e) for e in ents), key=lambda e: (-e["relation_count"], -e["source_count"], e["name"].lower()))
    sources = [dict(id=s["id"], cite=f"[S{s['id']}]", title=s["title"], kind=s["kind"], grade=f"{s['reliability']}{s['credibility']}",
                    origin=s["origin"], url=s["url"], ref=s["ref"], published_at=s["published_at"], captured_at=s["captured_at"],
                    retracted=bool(s["retracted"]), retract_reason=s["retract_reason"])
               for s in svc.db.query("SELECT * FROM sources WHERE case_id = ? ORDER BY id", (case_id,))]
    tl = timeline_mod.timeline(svc, case_id, limit=60)
    matrix = ach_mod.matrix(svc, case_id)
    dash = cases_mod.get(svc, case_id)
    counts = dash["counts"]
    return {"case": cases_mod.view(case), "relations_by_status": by_status, "entities": ent_views, "sources": sources, "timeline": tl,
            "ach": matrix, "dashboard": dash["dashboard"], "counts": counts,
            "overview": t["counts"].format(s=counts["sources"], e=counts["entities"], r=counts["relations"])}


def deterministic_summary(data: dict, lang: str) -> str:
    t = T[lang]
    sentences = []
    for status in ("confirmed", "corroborated", "claimed"):
        for v in data["relations_by_status"][status]:
            if len(sentences) >= 10:
                break
            valid = f" ({_valid_text(v)})" if _valid_text(v) else ""
            sentences.append(f"{v['label']}{valid} {v['cite']}.")
    return " ".join(sentences) if sentences else t["no_support"]


def _material_text(data: dict) -> str:
    lines = []
    for status in ("confirmed", "corroborated", "claimed", "disputed"):
        for v in data["relations_by_status"][status]:
            flag = " (private person involved)" if v["subject_private"] or v["object_private"] else ""
            lines.append(f"- {v['label']} [{status}] {v['cite']} {_valid_text(v)}{flag}")
    return "\n".join(lines[:60])


def model_summary(svc, data: dict, lang: str) -> tuple[str | None, str]:
    """(text, note). text None means no model answer; the caller falls back to the deterministic summary."""
    material = _material_text(data)
    if not material:
        return None, "no supported relations to summarise"
    language = "Spanish (Spain)" if lang == "es" else "English"
    prompt = (
        f"You are summarising a research case. Question: {data['case']['question'] or data['case']['title']}\n"
        f"Facts (each with its source ids):\n{material}\n\n"
        f"Write a summary of at most 150 words in {language}. Use only these facts. Every sentence that states a fact must end "
        "with its citation in the form [S12] (only ids listed above). Mention where facts are only claimed or disputed. "
        "Do not add details about private persons beyond the facts listed.")
    try:
        result = svc.link_sync.chat([{"role": "user", "content": prompt}], effort="medium", max_tokens=700)
        text = (getattr(result, "text", "") or "").strip()
    except Exception as error:  # noqa: BLE001 - any backend failure degrades to the deterministic summary
        return None, f"no model available ({type(error).__name__}: {str(error)[:120]})"
    return (text or None), ("" if text else "the model returned an empty answer")


def build(svc, case_id: int, *, lang: str = "en", use_model: bool = True) -> dict[str, Any]:
    if lang not in T:
        lang = "en"
    data = gather(svc, case_id, lang)
    det = deterministic_summary(data, lang)
    text, note, source = det, "", "deterministic"
    if use_model:
        mtext, note = model_summary(svc, data, lang)
        if mtext:
            text, source = mtext, "model"
    check = check_citations(svc, case_id, text)
    data["summary"] = {"text": text, "source": source, "note": note, "deterministic": det, "citation_check": check}
    data["lang"] = lang
    data["generated_at"] = iso_stamp(svc.clock())
    data["material"] = _material_text(data)
    return data


# ---------------- markdown ----------------

def _md_relation(v: dict, t: dict) -> list[str]:
    bits = [f"- {v['label']} {v['cite']}"]
    meta = []
    if _valid_text(v):
        meta.append(f"{t['valid']} {_valid_text(v)}")
    meta.append(f"{t['confidence']} {v['confidence']:g}")
    if v["stale"]:
        meta.append(f"⚑ {t['stale']}: {v['stale_reason']}")
    for f in v["flags"]:
        meta.append(f"⚑ {f}")
    if v["subject_private"] or v["object_private"]:
        meta.append(f"({t['private']})")
    lines = [bits[0] + " — " + "; ".join(meta)]
    for e in v.get("evidence", [])[:3]:
        quote = e["quote"] or e["locator"]
        suffix = f" — {e['cite']}" + (f", {e['locator']}" if e["locator"] and e["quote"] else "")
        lines.append(f"  > {clip(quote, 220)}{suffix}" + (f" ({t['retracted']})" if e["source_retracted"] else ""))
    return lines


def to_markdown(data: dict, *, full_quotes: bool = False) -> str:
    t = T[data["lang"]]
    c = data["case"]
    out = [f"# {c['title']}", ""]
    out.append(f"**{t['question']}:** {c['question'] or '—'}  ")
    out.append(f"**{t['status']}:** {c['status']} · {data['overview']} · {c['ref']}")
    out += ["", f"## {t['summary']}", ""]
    s = data["summary"]
    summary_text = mark_uncited(s["text"], s["citation_check"], t["uncited"]) if s["citation_check"]["uncited"] else s["text"]
    out.append(summary_text)
    out.append("")
    out.append(f"_{t['model'] if s['source'] == 'model' else t['det']}_" + (f" · {t['cite_problem']}: {len(s['citation_check']['uncited'])} {t['uncited']}" if s["citation_check"]["uncited"] else ""))
    if s["citation_check"]["invalid_citations"] or s["citation_check"]["retracted_citations"]:
        out.append(f"_{t['cite_problem']}: invalid {s['citation_check']['invalid_citations']}, retracted {s['citation_check']['retracted_citations']}_")
    out += ["", f"## {t['entities']}", ""]
    for e in data["entities"][:15]:
        tag = f" ({t['private']})" if e["private_person"] else ""
        aliases = f" — {', '.join(e['aliases'][:3])}" if e["aliases"] else ""
        out.append(f"- **{e['name']}**{tag} · {e['type']} · {e['relation_count']} rel · {e['source_count']} src{aliases}")
    if not data["entities"]:
        out.append(t["none"])
    out += ["", f"## {t['relations']}", ""]
    for status in STATUS_ORDER:
        rels = data["relations_by_status"][status]
        if not rels:
            continue
        out += [f"### {STATUS_LABEL[data['lang']][status]} ({len(rels)})", ""]
        for v in rels:
            out += _md_relation(v, t)
        out.append("")
    if not any(data["relations_by_status"].values()):
        out += [t["none"], ""]
    tl = data["timeline"]
    out += [f"## {t['timeline']}", ""]
    for x in tl["entries"][:40]:
        label = x.get("name") or x.get("label")
        kind = {"event": "●", "relation_start": "▶", "relation_end": "■"}[x["kind"]]
        out.append(f"- {x['date']} {kind} {label}" + (f" [{x['status']}]" if x.get("status") else "") + (f" {x['cite']}" if x.get("cite") else ""))
    if not tl["entries"]:
        out.append(t["none"])
    if tl["gaps"]:
        out += ["", f"**{t['gaps']}:** " + "; ".join(f"{g['from']} → {g['to']} ({g['days']} d)" for g in tl["gaps"][:8])]
    if tl["contradictions"]:
        out += ["", f"**{t['contradictions']}:**"]
        for k in tl["contradictions"]:
            out.append(f"- {k.get('note') or k.get('label')}")
    m = data["ach"]
    out += ["", f"## {t['ach']}", ""]
    if m["hypotheses"]:
        heads = [h for h in m["hypotheses"] if h["status"] == "open"]
        out.append("| E | " + " | ".join(f"H{h['id']}" for h in heads) + " |")
        out.append("|---|" + "---|" * len(heads))
        rt = {(r["hypothesis_id"], r["evidence_id"]): r["rating"] + ("*" if r["inactive"] else "") for r in m["ratings"]}
        for e in m["evidence"]:
            out.append(f"| E{e['id']} {e['cite']} {clip(e['context'], 40)} | " + " | ".join(rt.get((h["id"], e["id"]), "") for h in heads) + " |")
        out.append("")
        for h in m["hypotheses"]:
            mark = f" ← {t['least']}" if h["least_contradicted"] else ""
            out.append(f"- H{h['id']}: {h['statement']} — {t['score']} {h['score'] if h['score'] is not None else '—'}{mark}")
        out += ["", m["note"], "", f"_{m['disclaimer']}_"]
    else:
        out.append(t["none"])
    out += ["", f"## {t['open']}", ""]
    items = [*c["open_questions"]]
    d = data["dashboard"]
    items += [f"{t['unsupported_q']}: {x['label']}" for x in d["unsupported_relations"]]
    items += [f"{t['disputed_q']}: {x['label']}" for x in d["disputed_relations"]]
    items += [f"{t['stale_q']}: {x['label']} ({x['reason']})" for x in d["stale_facts"]]
    items += [f"{t['no_ratings_q']}: H{i}" for i in d["hypotheses_without_ratings"]]
    items += [f"{t['conflict_q']}: {x.get('note') or x.get('label')}" for x in d["contradictions"]]
    out += [f"- {i}" for i in items] if items else [t["none"]]
    out += ["", f"## {t['sources']}", ""]
    for s_ in data["sources"]:
        ref = s_["url"] or s_["ref"] or s_["kind"]
        pub = f", {s_['published_at']}" if s_["published_at"] else ""
        line = f"- {s_['cite']} {s_['title']} — {s_['grade']}, {s_['kind']}{pub}, {ref}"
        if s_["retracted"]:
            line += f" — {t['retracted']}" + (f": {s_['retract_reason']}" if s_["retract_reason"] else "")
        out.append(line)
    if not data["sources"]:
        out.append(t["none"])
    out += ["", f"_{t['generated']}: {data['generated_at']}_", ""]
    return "\n".join(out)


SECTIONS = ("summary", "entities", "relations", "timeline", "ach", "open_questions", "sources")


def report(svc, case_id: int, *, format: str = "markdown", lang: str = "en", use_model: bool = True,  # noqa: A002
           offset: int = 0, max_chars: int = 14000, section: str | None = None) -> dict:
    data = build(svc, case_id, lang=lang, use_model=use_model)
    base = {"case_id": case_id, "lang": data["lang"], "summary_source": data["summary"]["source"], "model_note": data["summary"]["note"],
            "citation_check": data["summary"]["citation_check"]}
    if format == "markdown":
        md = to_markdown(data)
        chunk = md[offset: offset + max_chars]
        nxt = offset + max_chars if offset + max_chars < len(md) else None
        return {**base, "format": "markdown", "markdown": chunk, "offset": offset, "next_offset": nxt, "total_chars": len(md)}
    if section:
        if section not in SECTIONS:
            raise ValueError(f"section must be one of {', '.join(SECTIONS)}.")
        key = {"summary": "summary", "entities": "entities", "relations": "relations_by_status", "timeline": "timeline", "ach": "ach",
               "open_questions": "dashboard", "sources": "sources"}[section]
        return {**base, "format": "json", "section": section, section: data[key]}
    slim = {k: v for k, v in data.items() if k != "material"}
    return {**base, "format": "json", "report": slim}
