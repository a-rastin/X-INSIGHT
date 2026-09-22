"""S21 slices 1-4: structural XMLBIF validation (XSD only, never executable)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

MAX_XML_BYTES = 1_048_576


class XmlInputError(ValueError):
    """Bounded rejection for oversize or undecodable XML input."""

    def __init__(
        self, message: str, line: int | None = None, column: int | None = None
    ) -> None:
        super().__init__(message[:500])
        self.line = line
        self.column = column


SCHEMA_PATH = Path(__file__).resolve().parents[4] / "BNs" / "schema.xml"

_schema: etree.XMLSchema | None = None


def _safe_parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        recover=False,
    )


def _get_schema() -> etree.XMLSchema:
    global _schema
    if _schema is None:
        tree = etree.parse(str(SCHEMA_PATH), _safe_parser())
        _schema = etree.XMLSchema(tree)
    return _schema


def export_source(data: bytes | dict[str, Any]) -> bytes:
    """Return a byte-identical copy of the validated source document.

    Validation preserves ``source_sha256``/``byte_count``; export is the
    identity function and never re-serializes (which could lose document
    order or metadata). ``bytes`` input returns ``bytes(data)`` with no
    size/parser side effects. A validation-result ``dict`` returns its
    stored ``source_bytes`` copy.
    """
    if isinstance(data, dict):
        stored = data.get("source_bytes")
        if isinstance(stored, (bytes, bytearray)):
            return bytes(stored)
        raise ValueError("validation result has no stored source_bytes for export")
    return bytes(data)


def validate_xmlbif(data: bytes) -> dict[str, Any]:
    """Validate raw XMLBIF bytes against the versioned XSD and inspect structure.

    v1 inspection flattening: flat keys (``nodes``/``states``/``edges``/
    ``network_properties``/``proposed_parents_ignored``/``missing_definitions``)
    derive from the FIRST network for backward compatibility; the authoritative
    ordered data is the ``networks`` list in document order. Validation preserves
    ``source_sha256``/``byte_count`` and export via :func:`export_source`
    returns the exact input bytes.
    """
    if len(data) > MAX_XML_BYTES:
        raise XmlInputError(f"XML input exceeds {MAX_XML_BYTES} bytes")
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise XmlInputError("rejected DTD/entity declaration; DTDs are not allowed")
    try:
        parsed = etree.fromstring(data, _safe_parser())
    except etree.XMLSyntaxError as exc:
        raw = str(exc).splitlines()
        truncated = (raw[0] if raw else str(exc))[:200]
        exc_lineno: object = exc.lineno
        line_no = exc_lineno if isinstance(exc_lineno, int) else 0
        pos: object = exc.position
        col_no = 0
        if isinstance(pos, tuple) and len(pos) >= 2 and isinstance(pos[1], int):
            col_no = pos[1]
        raise XmlInputError(
            f"malformed XML at line {line_no}, column {col_no}: {truncated}",
            line=line_no,
            column=col_no,
        ) from exc
    if parsed.tag != "BIF":
        raise XmlInputError(f"unsupported root <{str(parsed.tag)[:100]}>; expected BIF")
    schema = _get_schema()
    try:
        is_valid = schema.validate(parsed)
    except etree.Error as exc:
        raise XmlInputError(f"schema validation failed: {str(exc)[:200]}") from exc
    if is_valid:
        xsd_report: dict[str, Any] = {"valid": True, "errors": []}
    else:
        errors: list[dict[str, Any]] = []
        for entry in list(schema.error_log)[:10]:
            errors.append(
                {
                    "line": entry.line if isinstance(entry.line, int) else None,
                    "column": entry.column if isinstance(entry.column, int) else None,
                    "message": str(entry.message)[:500],
                }
            )
        xsd_report = {"valid": False, "errors": errors}

    networks = parsed.findall("NETWORK")
    networks_to_process = networks if networks else [parsed]

    # Ordered per-network view in document order. Edges derive ONLY from
    # GIVEN, never PROPERTY. Each network keeps ordered properties,
    # variables (name, kind, states, properties) and definitions
    # (for, parents in GIVEN order, stripped TABLE text or None,
    # properties).
    networks_data: list[dict[str, Any]] = []
    for net in networks_to_process:
        name_el = net.find("NAME")
        net_name = str(name_el.text) if name_el is not None and name_el.text else ""
        net_properties: list[str] = [
            str(p.text) for p in net.findall("PROPERTY") if p.text is not None
        ]
        var_infos: list[dict[str, Any]] = []
        for variable in net.findall("VARIABLE"):
            v_name_el = variable.find("NAME")
            if v_name_el is None or v_name_el.text is None:
                continue
            var_name = str(v_name_el.text)
            kind = variable.get("TYPE") or "nature"
            var_states = [
                str(o.text) for o in variable.findall("OUTCOME") if o.text is not None
            ]
            var_props = [
                str(p.text) for p in variable.findall("PROPERTY") if p.text is not None
            ]
            var_infos.append(
                {
                    "name": var_name,
                    "kind": kind,
                    "states": var_states,
                    "properties": var_props,
                }
            )
        def_infos: list[dict[str, Any]] = []
        for definition in net.findall("DEFINITION"):
            for_el = definition.find("FOR")
            if for_el is None or for_el.text is None:
                continue
            for_name = str(for_el.text)
            parents = [
                str(g.text) for g in definition.findall("GIVEN") if g.text is not None
            ]
            table_el = definition.find("TABLE")
            table_text: str | None = None
            if table_el is not None and table_el.text is not None:
                table_text = str(table_el.text).strip()
            def_props = [
                str(p.text)
                for p in definition.findall("PROPERTY")
                if p.text is not None
            ]
            def_infos.append(
                {
                    "for": for_name,
                    "for_profile": for_name,
                    "parents": parents,
                    "given": list(parents),
                    "table_text": table_text,
                    "properties": def_props,
                }
            )
        networks_data.append(
            {
                "name": net_name,
                "properties": net_properties,
                "variables": var_infos,
                "definitions": def_infos,
            }
        )

    # v1 flattening: flat keys derive from FIRST network only.
    first = networks_data[0]
    first_vars: list[dict[str, Any]] = first["variables"]
    first_defs: list[dict[str, Any]] = first["definitions"]
    nodes: list[str] = [str(v["name"]) for v in first_vars]
    states: dict[str, list[str]] = {
        str(v["name"]): list(v["states"]) for v in first_vars
    }
    edges: list[tuple[str, str]] = []
    for definition in first_defs:
        child = str(definition["for"])
        for parent in definition["parents"]:
            edges.append((str(parent), child))
    network_properties: list[str] = list(first["properties"])

    proposed_parents_ignored: list[dict[str, str]] = []
    for v in first_vars:
        vname = str(v["name"])
        for prop_text in v["properties"]:
            if isinstance(prop_text, str) and prop_text.startswith("proposed_parent="):
                proposed_parents_ignored.append(
                    {
                        "variable": vname,
                        "proposed_parent": prop_text.split("=", 1)[1].strip(),
                    }
                )
    defined: set[str] = {str(d["for"]) for d in first_defs}
    missing_definitions: list[str] = [
        str(v["name"])
        for v in first_vars
        if v["kind"] == "nature" and str(v["name"]) not in defined
    ]

    kinds_ordered: list[str] = []
    for net_data in networks_data:
        net_vars: list[dict[str, Any]] = net_data["variables"]
        for v in net_vars:
            k = str(v["kind"])
            if k not in kinds_ordered:
                kinds_ordered.append(k)
    unsupported_kinds: list[str] = [
        k for k in kinds_ordered if k in ("decision", "utility")
    ]

    reasons: list[str] = [
        "structural validity only; executability requires S22 semantic/admission checks"
    ]
    if missing_definitions:
        preview = ", ".join(missing_definitions[:5])
        reasons.append(
            f"draft: {len(missing_definitions)} nature variable(s) missing "
            f"definitions are inspectable but not executable: {preview}"
        )
    if proposed_parents_ignored:
        reasons.append(
            f"graph display ignores {len(proposed_parents_ignored)} "
            "proposed_parent metadata entries; "
            "authoritative edges derive only from GIVEN"
        )
    if len(networks_data) != 1:
        reasons.append(
            f"multiple networks ({len(networks_data)}) in one document are "
            "nonactivatable under v1; inspect each separately, "
            "none selected automatically"
        )
    if unsupported_kinds:
        reasons.append(
            "unsupported variable kind(s) under v1 execution profile "
            f"(discrete nature only): {', '.join(unsupported_kinds)}; "
            "drafts inspectable but nonactivatable"
        )

    return {
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "byte_count": len(data),
        "source_bytes": bytes(data),
        "nodes": nodes,
        "states": states,
        "edges": edges,
        "xsd_report": xsd_report,
        "inspection": {
            "activatable": False,
            "reasons": reasons,
        },
        "network_properties": network_properties,
        "proposed_parents_ignored": proposed_parents_ignored,
        "missing_definitions": missing_definitions,
        "networks": networks_data,
        "unsupported_kinds": unsupported_kinds,
    }
