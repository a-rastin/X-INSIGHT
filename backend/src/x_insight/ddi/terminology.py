"""S17 slice-1 controlled terminology: exact normalized resolution only.

No fuzzy matching, no external terminology, no salt/strength stripping,
no combination splitting. An alias claimed by two concepts never resolves
silently: it stays unresolved.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TERMINOLOGY_VERSION = "ddi-terminology-1"

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize(name: str) -> str:
    """Exact normalization: strip, collapse whitespace runs, casefold."""
    return _WHITESPACE_RUN.sub(" ", name.strip()).casefold()


def canonical_pair_key(a: str, b: str) -> str:
    """Unordered pair identity: normalized, sorted, joined as "min:max"."""
    n_a = normalize(a)
    n_b = normalize(b)
    return f"{min(n_a, n_b)}:{max(n_a, n_b)}"


@dataclass(frozen=True)
class Terminology:
    """Controlled concept/alias table with precomputed collision set."""

    version: str
    concepts: dict[str, dict[str, str]]
    index: dict[str, tuple[str, ...]]
    collisions: tuple[str, ...]


def _alias_text(entry: Any, concept_id: str) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        alias = entry.get("alias")
        if isinstance(alias, str):
            return alias
    raise ValueError(f"concept {concept_id!r}: invalid alias entry {entry!r}")


def load_terminology(path: Path) -> Terminology:
    """Load the controlled concept/alias table from a JSON file path."""
    raw: Any = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    if not isinstance(raw, dict) or not isinstance(raw.get("concepts"), list):
        raise ValueError(f"{path}: terminology requires a 'concepts' list")
    concepts: dict[str, dict[str, str]] = {}
    index: dict[str, list[str]] = {}
    for position, item in enumerate(raw["concepts"]):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: concept #{position} is not an object")
        concept_id = item.get("id")
        canonical = item.get("canonical_name")
        concept_type = item.get("concept_type")
        if not isinstance(concept_id, str) or not concept_id:
            raise ValueError(f"{path}: concept #{position} needs a string 'id'")
        if not isinstance(canonical, str) or not canonical:
            raise ValueError(f"{path}: concept #{position} needs 'canonical_name'")
        if not isinstance(concept_type, str) or not concept_type:
            raise ValueError(f"{path}: concept #{position} needs 'concept_type'")
        if concept_id in concepts:
            raise ValueError(f"{path}: duplicate concept id {concept_id!r}")
        concepts[concept_id] = {
            "canonical_name": canonical,
            "concept_type": concept_type,
        }
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError(f"{path}: concept {concept_id!r} needs an 'aliases' list")
        for name in [canonical] + [_alias_text(a, concept_id) for a in aliases]:
            key = normalize(name)
            if not key:
                raise ValueError(f"{path}: concept {concept_id!r} has an empty name")
            bucket = index.setdefault(key, [])
            if concept_id not in bucket:
                bucket.append(concept_id)
    collisions = tuple(sorted(key for key, ids in index.items() if len(ids) >= 2))
    version = raw.get("terminology_version", TERMINOLOGY_VERSION)
    if not isinstance(version, str) or not version:
        raise ValueError(f"{path}: needs a string 'terminology_version'")
    return Terminology(
        version=version,
        concepts=concepts,
        index={key: tuple(ids) for key, ids in index.items()},
        collisions=collisions,
    )


def resolve(name: str, terminology: Terminology) -> dict[str, str]:
    """Exact normalized match only; collisions never resolve silently."""
    candidates = terminology.index.get(normalize(name), ())
    if len(candidates) == 1:
        concept_id = candidates[0]
        return {
            "status": "resolved",
            "concept_id": concept_id,
            "canonical_name": terminology.concepts[concept_id]["canonical_name"],
            "concept_type": terminology.concepts[concept_id]["concept_type"],
        }
    if len(candidates) >= 2:
        return {"status": "unresolved", "reason": "ambiguous", "input": name}
    return {"status": "unresolved", "reason": "unknown", "input": name}
