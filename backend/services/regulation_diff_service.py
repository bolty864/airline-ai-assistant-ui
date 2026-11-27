"""Deterministic comparison of two versions of a regulation, obligation by obligation. No LLM, no I/O.

Steps: exact matches -> best-pair matching of the rest (wording similarity + embedding similarity + same clause number)
-> classify each pair -> unmatched old = REMOVED, unmatched new = NEW.
"""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

import numpy as np

from services.impact_types import ChangeType, DiffEntry, Domain, ObligationRec

_WORD = re.compile(r"[a-z0-9]+")
_NUM_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
              "nine": "9", "ten": "10", "twelve": "12", "fifteen": "15", "twenty": "20", "thirty": "30"}
_QTY = re.compile(r"\b(\d+(?:\.\d+)?|" + "|".join(_NUM_WORDS) + r")\s*-?\s*(years?|yrs?|months?|weeks?|days?|hours?|hrs?|"
                  r"minutes?|mins?|percent)\b")
_UNIT = {"year": "year", "yr": "year", "month": "month", "week": "week", "day": "day", "hour": "hour", "hr": "hour",
         "minute": "minute", "min": "minute", "percent": "percent"}
_MODALS = ("shall", "must", "required", "should", "may", "prohibited", "mandatory")
_NEGATION = re.compile(r"\b(not|no|never|without|neither|nor)\b")
_DOMAIN_WORDS: dict[str, tuple[str, ...]] = {
    Domain.RETENTION: ("retain", "retention", "retained", "preserve", "preserved", "archive", "archival", "purge",
                       "delete", "deleted", "deletion", "erase", "erasure", "storage period", "kept for", "keep records"),
    Domain.REPORTING: ("report", "reporting", "notify", "notification", "notified", "inform", "submit", "submission",
                       "disclose", "intimate", "within hours", "furnish"),
    Domain.SECURITY: ("encrypt", "encryption", "tls", "cipher", "authentication", "authenticate", "multi factor", "mfa",
                      "password", "firewall", "vulnerability", "penetration", "malware", "intrusion", "security",
                      "access control", "privileged", "cyber", "hardening", "patch"),
}
_TYPE_DOMAIN = {"Data Retention": Domain.RETENTION, "Data Deletion": Domain.RETENTION, "Data Archival": Domain.RETENTION,
                "Record Keeping": Domain.RETENTION, "Incident Management": Domain.REPORTING,
                "Cyber Security": Domain.SECURITY, "Access Control": Domain.SECURITY}
_DOMAIN_ORDER = [Domain.RETENTION, Domain.REPORTING, Domain.SECURITY]
MINOR_SIMILARITY = 0.92


def canon(text: str | None) -> str:
    return " ".join(_WORD.findall((text or "").lower()))


def quantities(text: str) -> dict[str, list[str]]:
    """{'year': ['5'], 'hour': ['6']}: every number with a unit in the text."""
    out: dict[str, list[str]] = {}
    for num, unit in _QTY.findall((text or "").lower().replace("%", " percent ")):
        out.setdefault(_UNIT[unit.rstrip("s") if unit.rstrip("s") in _UNIT else unit], []).append(_NUM_WORDS.get(num, num))
    return {u: sorted(v) for u, v in out.items()}


def modals(text: str) -> list[str]:
    words = set(_WORD.findall((text or "").lower()))
    return [m for m in _MODALS if m in words]


def classify_domain(text: str, obligation_type: str | None) -> str:
    lowered = " " + canon(text) + " "
    scores = {d: sum(1 for w in words if f" {w} " in lowered or (" " in w and w in lowered))
              for d, words in _DOMAIN_WORDS.items()}
    bonus = _TYPE_DOMAIN.get(obligation_type or "")
    if bonus:
        scores[bonus] += 2
    best = max(_DOMAIN_ORDER, key=lambda d: (scores[d], -_DOMAIN_ORDER.index(d)))
    return best if scores[best] > 0 else Domain.OTHER


def impact_key(old: ObligationRec | None, new: ObligationRec | None) -> str:
    """Stable id of a change: the same old/new wording always gives the same key, so task status survives re-runs."""
    raw = f"{canon(old.text) if old else ''}|{canon(new.text) if new else ''}"
    return hashlib.sha1(raw.encode()).hexdigest()[:32]


# ------------------------------------------------------------------ matching
def _lexical(a: str, b: str) -> float:
    return SequenceMatcher(None, a.split(), b.split(), autojunk=False).ratio()


def _cosine(a, b) -> float | None:
    if a is None or b is None:
        return None
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    return float(va @ vb / (na * nb)) if na and nb else None


def pair_score(old: ObligationRec, new: ObligationRec) -> float:
    lex = _lexical(canon(old.text), canon(new.text))
    cos = _cosine(old.embedding, new.embedding)
    score = lex if cos is None else 0.6 * lex + 0.4 * max(0.0, (cos - 0.5) / 0.5)
    if old.clause_ref and old.clause_ref == new.clause_ref:
        score += 0.08
    return min(score, 1.0)


def match(old: list[ObligationRec], new: list[ObligationRec], threshold: float) -> tuple[
        list[tuple[int, int, float]], list[int], list[int]]:
    """(old_idx, new_idx, score) pairs, plus the old indexes left (REMOVED) and new indexes left (NEW)."""
    pairs: list[tuple[int, int, float]] = []
    used_old: set[int] = set()
    used_new: set[int] = set()

    by_text: dict[str, list[int]] = {}
    for j, n in enumerate(new):
        by_text.setdefault(canon(n.text), []).append(j)
    for i, o in enumerate(old):
        candidates = [j for j in by_text.get(canon(o.text), []) if j not in used_new]
        if candidates:
            j = next((c for c in candidates if new[c].clause_ref == o.clause_ref), candidates[0])
            pairs.append((i, j, 1.0))
            used_old.add(i)
            used_new.add(j)

    scored = [(pair_score(o, n), i, j) for i, o in enumerate(old) if i not in used_old
              for j, n in enumerate(new) if j not in used_new]
    for score, i, j in sorted(scored, reverse=True):
        if score < threshold:
            break
        if i in used_old or j in used_new:
            continue
        pairs.append((i, j, round(score, 3)))
        used_old.add(i)
        used_new.add(j)
    return (pairs, [i for i in range(len(old)) if i not in used_old], [j for j in range(len(new)) if j not in used_new])


# ------------------------------------------------------------------ classification
def _classify_pair(old: ObligationRec, new: ObligationRec, score: float) -> DiffEntry | None:
    text_changed = canon(old.text) != canon(new.text)
    sev_changed = bool(old.severity and new.severity and old.severity != new.severity)
    if not text_changed and not sev_changed:
        return None

    domain = classify_domain(new.text, new.obligation_type)
    entry = DiffEntry(change_type=ChangeType.MODIFIED, domain=domain, old=old, new=new, similarity=score,
                      severity_old=old.severity, severity_new=new.severity)
    if sev_changed:
        entry.additional_changes.append(ChangeType.SEVERITY)
    if not text_changed:
        entry.change_type = ChangeType.SEVERITY
        entry.additional_changes = []
        entry.minor = False
        return entry

    qo, qn = quantities(old.text), quantities(new.text)
    for unit in sorted(set(qo) | set(qn)):
        if qo.get(unit) != qn.get(unit):
            entry.quantity_changes.append({"unit": unit, "old": qo.get(unit, []), "new": qn.get(unit, [])})
    mo, mn = modals(old.text), modals(new.text)
    if mo != mn:
        entry.modal_change = (mo, mn)
    negation_changed = len(_NEGATION.findall(old.text.lower())) != len(_NEGATION.findall(new.text.lower()))

    lex = _lexical(canon(old.text), canon(new.text))
    entry.minor = lex >= MINOR_SIMILARITY and not entry.quantity_changes and not entry.modal_change and not negation_changed
    if not entry.minor:
        entry.change_type = {Domain.RETENTION: ChangeType.RETENTION, Domain.REPORTING: ChangeType.REPORTING,
                             Domain.SECURITY: ChangeType.SECURITY}.get(domain, ChangeType.MODIFIED)
    return entry


def diff(old: list[ObligationRec], new: list[ObligationRec], threshold: float = 0.55) -> list[DiffEntry]:
    """All changes between the two versions, in the order of the new document (removed obligations last)."""
    pairs, removed, added = match(old, new, threshold)
    entries: list[DiffEntry] = []
    for i, j, score in pairs:
        entry = _classify_pair(old[i], new[j], score)
        if entry:
            entries.append(entry)
    for j in added:
        n = new[j]
        entries.append(DiffEntry(change_type=ChangeType.NEW, domain=classify_domain(n.text, n.obligation_type),
                                 old=None, new=n, severity_new=n.severity))
    for i in removed:
        o = old[i]
        entries.append(DiffEntry(change_type=ChangeType.REMOVED, domain=classify_domain(o.text, o.obligation_type),
                                 old=o, new=None, severity_old=o.severity))
    for e in entries:
        e.key = impact_key(e.old, e.new)
    order = {id(n): k for k, n in enumerate(new)}
    entries.sort(key=lambda e: (e.new is None, order.get(id(e.new), 0)))
    return entries
