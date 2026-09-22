"""S21 slice 1 (RED tracer) through the model-validation seam (T5).

Public interface under test (not yet implemented):
    x_insight.models.validation.validate_xmlbif(data: bytes) -> dict

Fixture is a synthetic two-node format check (Format_Test with variables A, B,
mirroring BNs/test_schema.py base plus ordered network PROPERTY entries) —
not clinical content, never patient data, never an existing BN as oracle.
"""

from __future__ import annotations

import hashlib

from x_insight.models.validation import validate_xmlbif

_INPUT = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>Format_Test</NAME>'
    b"<PROPERTY>label=format check</PROPERTY>"
    b"<PROPERTY>source=test</PROPERTY>"
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b'<VARIABLE TYPE="nature"><NAME>B</NAME><OUTCOME>no</OUTCOME>'
    b"<OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
    b"<TABLE>0.8 0.2 0.1 0.9</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)


def test_validate_synthetic_two_node_format_fixture() -> None:
    result = validate_xmlbif(_INPUT)

    assert result["source_sha256"] == hashlib.sha256(_INPUT).hexdigest()
    assert result["byte_count"] == len(_INPUT)
    assert result["nodes"] == ["A", "B"]
    assert result["states"] == {"A": ["no", "yes"], "B": ["no", "yes"]}
    assert result["edges"] == [("A", "B")]
    assert result["xsd_report"]["valid"] is True
    assert result["xsd_report"]["errors"] == []
    assert result["inspection"]["activatable"] is False
    assert result["network_properties"] == [
        "label=format check",
        "source=test",
    ]


def test_rejects_doctype_entity_safely() -> None:
    """Slice 2: DOCTYPE/ENTITY must fail safe with no expansion, no network."""
    import pytest

    from x_insight.models.validation import XmlInputError, validate_xmlbif

    payload = (
        b'<!DOCTYPE BIF [<!ENTITY xxe "boom">]>'
        b'<BIF VERSION="0.3"><NETWORK><NAME>XXE_Test</NAME>'
        b"<PROPERTY>&xxe;</PROPERTY>"
        b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>A</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    with pytest.raises(XmlInputError) as exc_info:
        validate_xmlbif(payload)
    msg = str(exc_info.value)
    assert len(msg) <= 500
    assert "boom" not in msg


def test_rejects_remote_resolution_safely() -> None:
    """Slice 2: remote SYSTEM DTD must fail fast with no fetch."""
    import time

    import pytest

    from x_insight.models.validation import XmlInputError, validate_xmlbif

    payload = (
        b'<!DOCTYPE BIF SYSTEM "http://example.invalid/evil.dtd">'
        b'<BIF VERSION="0.3"><NETWORK><NAME>Remote_Test</NAME>'
        b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>A</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    start = time.monotonic()
    with pytest.raises(XmlInputError) as exc_info:
        validate_xmlbif(payload)
    elapsed = time.monotonic() - start
    assert elapsed < 5
    assert len(str(exc_info.value)) <= 500


def test_rejects_oversize_input() -> None:
    """Slice 2: oversize bytes must be rejected before parsing."""
    import pytest

    from x_insight.models.validation import (
        MAX_XML_BYTES,
        XmlInputError,
        validate_xmlbif,
    )

    payload = b"A" * (MAX_XML_BYTES + 1)
    with pytest.raises(XmlInputError) as exc_info:
        validate_xmlbif(payload)
    msg = str(exc_info.value)
    assert len(msg) <= 500
    lowered = msg.lower()
    assert "exceed" in lowered or "limit" in lowered or "size" in lowered
    assert "byte" in lowered or str(MAX_XML_BYTES) in msg


def test_malformed_xml_bounded_location() -> None:
    """Slice 2: truncated XML must raise with bounded line/column location."""
    import pytest

    from x_insight.models.validation import XmlInputError, validate_xmlbif

    with pytest.raises(XmlInputError) as exc_info:
        validate_xmlbif(b'<BIF VERSION="0.3"><NETWORK>')
    exc = exc_info.value
    msg = str(exc)
    assert len(msg) <= 500
    line = getattr(exc, "line", None)
    column = getattr(exc, "column", None)
    errors = getattr(exc, "errors", None)
    ok = False
    if isinstance(line, int) and isinstance(column, int):
        ok = True
    elif isinstance(errors, list) and errors:
        first = errors[0]
        if (
            isinstance(first, dict)
            and isinstance(first.get("line"), int)
            and isinstance(first.get("column"), int)
        ):
            ok = True
    elif "line" in msg.lower():
        ok = True
    assert ok, "expected bounded line/column location"


def test_unsupported_root_fails_safely() -> None:
    """Slice 2: well-formed non-XMLBIF root must raise, not return valid."""
    import pytest

    from x_insight.models.validation import XmlInputError, validate_xmlbif

    with pytest.raises(XmlInputError) as exc_info:
        validate_xmlbif(b"<FOO/>")
    msg = str(exc_info.value)
    assert len(msg) <= 500
    lowered = msg.lower()
    assert "unsupported" in lowered or "root" in lowered or "bif" in lowered


def test_draft_bn04_inspectable_proposed_parents_not_edges() -> None:
    """Slice 3 RED: BN-04 draft inspectable; proposed_parent PROPERTYs are not edges."""
    from pathlib import Path

    from lxml import etree

    path = Path("/root/X-INSIGHT/BNs/BN-04.xml")
    data = path.read_bytes()
    result = validate_xmlbif(data)

    assert result["source_sha256"] == hashlib.sha256(data).hexdigest()
    assert result["byte_count"] == len(data)
    assert result["xsd_report"]["valid"] is True

    reasons = result["inspection"]["reasons"]
    assert result["inspection"]["activatable"] is False
    assert isinstance(reasons, list) and len(reasons) > 0
    assert any(
        marker in r.lower()
        for r in reasons
        for marker in ("draft", "incomplete", "missing", "s22", "executable")
    )

    # Independent reader: same safe parser flags, GIVEN-derived edges in order.
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        recover=False,
    )
    root = etree.fromstring(data, parser)
    networks = root.findall("NETWORK")
    network = networks[0] if networks else root
    expected_edges: list[tuple[str, str]] = []
    for definition in network.findall("DEFINITION"):
        for_el = definition.find("FOR")
        if for_el is None or for_el.text is None:
            continue
        child = str(for_el.text)
        for given in definition.findall("GIVEN"):
            if given.text is not None:
                expected_edges.append((str(given.text), child))
    assert result["edges"] == expected_edges

    # Proposed parents are VARIABLE PROPERTY metadata, never authoritative edges.
    proposed: list[tuple[str, str]] = []
    for variable in network.findall("VARIABLE"):
        name_el = variable.find("NAME")
        if name_el is None or name_el.text is None:
            continue
        child_name = str(name_el.text)
        for prop in variable.findall("PROPERTY"):
            if prop.text is not None and prop.text.startswith("proposed_parent="):
                proposed.append((str(prop.text.split("=", 1)[1]), child_name))
    assert len(proposed) >= 1
    expected_set = set(expected_edges)
    proposed_only = [p for p in proposed if p not in expected_set]
    assert len(proposed_only) >= 1
    assert ("PreferenceBarrier", "AdherenceDifficulty") not in result["edges"]
    assert ("PriorTreatmentDifficulty", "AdherenceDifficulty") not in result["edges"]
    assert not any(p in result["edges"] for p in proposed_only)

    # RED: implementation must record that proposed parents were ignored.
    assert "proposed_parents_ignored" in result or any(
        "proposed_parent" in r.lower() for r in reasons
    )


def test_draft_bn08_inspectable_despite_missing_definitions() -> None:
    """Slice 3 RED: BN-08 draft inspectable despite missing DEFINITIONs."""
    from pathlib import Path

    data = Path("/root/X-INSIGHT/BNs/BN-08.xml").read_bytes()
    result = validate_xmlbif(data)

    assert result["xsd_report"]["valid"] is True
    assert result["inspection"]["activatable"] is False
    assert "SchizophreniaEstablished" in result["nodes"]
    assert "ClozapineSuicideRiskIndication" in result["nodes"]
    assert ("SchizophreniaEstablished", "ClozapineSuicideRiskIndication") in result[
        "edges"
    ]

    # RED: per-draft missing-definition reporting for a known undefined variable.
    reasons = result["inspection"]["reasons"]
    has_field = isinstance(result.get("missing_definitions"), list) and (
        "ClozapineTreatmentStatus" in result["missing_definitions"]
    )
    has_reason = any(
        "ClozapineTreatmentStatus" in r or "missing" in r.lower() for r in reasons
    )
    assert has_field or has_reason


def test_order_and_metadata_preserved() -> None:
    """Slice 4 RED: document order and network metadata preserved, bytes round-trip."""
    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Order_Test</NAME>'
        b"<PROPERTY>b=2</PROPERTY>"
        b"<PROPERTY>a=1</PROPERTY>"
        b"<VARIABLE><NAME>Zed</NAME><OUTCOME>c</OUTCOME>"
        b"<OUTCOME>a</OUTCOME><OUTCOME>b</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>Alpha</NAME><OUTCOME>yes</OUTCOME>"
        b"<OUTCOME>no</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>Beta</NAME><OUTCOME>yes</OUTCOME>"
        b"<OUTCOME>no</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>Child</NAME><OUTCOME>yes</OUTCOME>"
        b"<OUTCOME>no</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>Zed</FOR><TABLE>0.2 0.3 0.5</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>Alpha</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>Beta</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>Child</FOR><GIVEN>Beta</GIVEN><GIVEN>Alpha</GIVEN>"
        b"<TABLE>0.5 0.5 0.5 0.5 0.5 0.5 0.5 0.5</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    result = validate_xmlbif(payload)

    assert result["nodes"] == ["Zed", "Alpha", "Beta", "Child"]
    assert result["states"]["Zed"] == ["c", "a", "b"]
    child_edges = [e for e in result["edges"] if e[1] == "Child"]
    assert child_edges == [("Beta", "Child"), ("Alpha", "Child")]

    # RED: flat-only impl has no ordered multi-field networks view.
    assert "networks" in result
    networks = result["networks"]
    assert networks[0]["variables"][0]["states"] == ["c", "a", "b"]
    assert networks[0]["properties"] == ["b=2", "a=1"]
    defs = networks[0].get("definitions", [])
    child = next(
        d
        for d in defs
        if d.get("for") == "Child"
        or d.get("for_profile") == "Child"
        or d.get("child") == "Child"
        or d.get("FOR") == "Child"
    )
    parents = child.get("parents", child.get("given", child.get("GIVEN", [])))
    assert list(parents) == ["Beta", "Alpha"]

    # RED: byte-preserving export must return identical bytes.
    try:
        from x_insight.models.validation import export_source  # type: ignore
    except ImportError as exc:
        assert False, f"export_source missing for byte-preservation: {exc}"
    else:
        assert export_source(result) == payload


def test_multi_network_reported_nonactivatable() -> None:
    """Slice 4 RED: two NETWORKs reported, not silently flattened, non-activatable."""
    payload = (
        b'<BIF VERSION="0.3">'
        b"<NETWORK><NAME>First</NAME>"
        b"<VARIABLE><NAME>A</NAME><OUTCOME>yes</OUTCOME>"
        b"<OUTCOME>no</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>A</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"</NETWORK>"
        b"<NETWORK><NAME>Second</NAME>"
        b"<VARIABLE><NAME>B</NAME><OUTCOME>yes</OUTCOME>"
        b"<OUTCOME>no</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>B</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    result = validate_xmlbif(payload)

    assert "networks" in result
    assert len(result["networks"]) == 2
    assert [n.get("name", n.get("NAME")) for n in result["networks"]] == [
        "First",
        "Second",
    ]
    assert result["inspection"]["activatable"] is False
    reasons = " ".join(result["inspection"]["reasons"]).lower()
    assert ("multiple" in reasons or "two" in reasons) and "network" in reasons


def test_unsupported_kinds_nonactivatable() -> None:
    """Slice 4 RED: decision/utility kinds parsed per XSD but non-activatable."""
    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Kinds_Test</NAME>'
        b'<VARIABLE TYPE="decision"><NAME>D</NAME><OUTCOME>yes</OUTCOME>'
        b"<OUTCOME>no</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME>"
        b"<OUTCOME>yes</OUTCOME></VARIABLE>"
        b'<VARIABLE TYPE="utility"><NAME>U</NAME></VARIABLE>'
        b"<DEFINITION><FOR>B</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>U</FOR><GIVEN>B</GIVEN><GIVEN>D</GIVEN>"
        b"<TABLE>1 2 3 4</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    result = validate_xmlbif(payload)

    assert result["xsd_report"]["valid"] is True
    assert result["inspection"]["activatable"] is False
    reasons = result["inspection"]["reasons"]
    joined = " ".join(reasons).lower()
    assert "decision" in joined or "utility" in joined or "unsupported" in joined
    assert "unsupported" in joined or "unsupported_kinds" in result
