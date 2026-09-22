"""S25 slice 1 (RED): workflow bundle completeness/review gate (T-seam bundle).

Public interface under test (not yet implemented):
    from x_insight.models.bundles import validate_bundle, REGISTRATION_ORDER, FOLLOWUP_ORDER
    validate_bundle(bundle: dict, load) -> dict with keys:
        activatable (bool), errors (list of {code, message[, question]}),
        bundle_hash, questions.

Bundle shape:
    {"workflow": "registration" | "followup",
     "questions": [{"question_key": str, "version": str, "network_hash": str}, ...]}

load: callable(question_key) -> (validated, package) where validated is
validate_xmlbif() output on real tiny synthetic XMLBIF bytes and package is a
minimal decide_activation-shaped dict. Synthetic fixtures only (2-node A->B);
never content/questions/ or BNs/.
"""

from __future__ import annotations

from x_insight.models.bundles import (
    FOLLOWUP_ORDER,
    REGISTRATION_ORDER,
    validate_bundle,
)
from x_insight.models.validation import validate_xmlbif

_SYNTHETIC_XML = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>Synthetic_Bundle</NAME>'
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
    b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)


def _approved_package() -> dict:
    return {
        "mappings": [
            {"node_id": "B", "allowed_source_paths": ["assessment.score"]}
        ],
        "prompt": "synthetic prompt",
        "template": "synthetic template",
        "review": {
            "decision": "approved",
            "reviewer": "reviewer",
            "date": "2026-09-22",
        },
        "query_nodes": ["B"],
    }


def test_missing_question_cannot_activate() -> None:
    assert REGISTRATION_ORDER == [
        "hospitalization",
        "pharmacotherapy",
        "involuntary_care",
        "high_suicide_clozapine",
        "lai_indication_choice",
        "aggression_clozapine",
        "established_case_clozapine",
    ]
    assert FOLLOWUP_ORDER == [
        "tardive_dyskinesia",
        "akathisia",
        "parkinsonism",
        "acute_dystonia",
        "no_improvement_clozapine",
        "continue_or_adjust",
    ]
    validated = validate_xmlbif(_SYNTHETIC_XML)
    network_hash = validated["source_sha256"]
    keys = [k for k in REGISTRATION_ORDER if k != "established_case_clozapine"]
    assert len(keys) == 6
    bundle = {
        "workflow": "registration",
        "questions": [
            {"question_key": k, "version": "v1", "network_hash": network_hash}
            for k in keys
        ],
    }

    def load(question_key: str) -> tuple[dict, dict]:
        return (validated, _approved_package())

    result = validate_bundle(bundle, load)
    assert result["activatable"] is False
    assert any(
        isinstance(e, dict) and e.get("code") == "missing_question"
        for e in result["errors"]
    )


def test_unreviewed_package_cannot_activate() -> None:
    validated = validate_xmlbif(_SYNTHETIC_XML)
    network_hash = validated["source_sha256"]
    bundle = {
        "workflow": "registration",
        "questions": [
            {"question_key": k, "version": "v1", "network_hash": network_hash}
            for k in REGISTRATION_ORDER
        ],
    }

    def load(question_key: str) -> tuple[dict, dict]:
        package = _approved_package()
        if question_key == "hospitalization":
            package["review"] = {"decision": "pending", "reviewer": "", "date": ""}
        return (validated, package)

    result = validate_bundle(bundle, load)
    assert result["activatable"] is False
    assert any(
        isinstance(e, dict) and e.get("code") == "unreviewed_package"
        for e in result["errors"]
    )


def test_duplicate_question_cannot_activate() -> None:
    validated = validate_xmlbif(_SYNTHETIC_XML)
    network_hash = validated["source_sha256"]
    base = [k for k in REGISTRATION_ORDER if k != "established_case_clozapine"]
    assert len(base) == 6
    dup_keys = [*base, REGISTRATION_ORDER[0]]
    assert len(dup_keys) == 7
    assert len(set(dup_keys)) == 6
    bundle = {
        "workflow": "registration",
        "questions": [
            {"question_key": k, "version": "v1", "network_hash": network_hash}
            for k in dup_keys
        ],
    }

    def load(question_key: str) -> tuple[dict, dict]:
        return (validated, _approved_package())

    result = validate_bundle(bundle, load)
    assert result["activatable"] is False
    assert any(
        isinstance(e, dict) and e.get("code") == "duplicate_question"
        for e in result["errors"]
    )


def test_wrong_order_cannot_activate() -> None:
    validated = validate_xmlbif(_SYNTHETIC_XML)
    network_hash = validated["source_sha256"]
    reversed_keys = list(reversed(REGISTRATION_ORDER))
    assert len(reversed_keys) == 7
    assert set(reversed_keys) == set(REGISTRATION_ORDER)
    assert reversed_keys != list(REGISTRATION_ORDER)
    bundle = {
        "workflow": "registration",
        "questions": [
            {"question_key": k, "version": "v1", "network_hash": network_hash}
            for k in reversed_keys
        ],
    }

    def load(question_key: str) -> tuple[dict, dict]:
        return (validated, _approved_package())

    result = validate_bundle(bundle, load)
    assert result["activatable"] is False
    assert any(
        isinstance(e, dict) and e.get("code") == "wrong_order"
        for e in result["errors"]
    )


def test_nonexecutable_network_cannot_activate() -> None:
    validated = validate_xmlbif(_SYNTHETIC_XML)
    network_hash = validated["source_sha256"]
    cyclic_xml = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Synthetic_Cyclic</NAME>'
        b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>A</FOR><GIVEN>B</GIVEN>"
        b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
        b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    cyclic_validated = validate_xmlbif(cyclic_xml)
    cyclic_hash = cyclic_validated["source_sha256"]
    assert cyclic_hash != network_hash
    bundle = {
        "workflow": "registration",
        "questions": [
            {
                "question_key": k,
                "version": "v1",
                "network_hash": (
                    cyclic_hash if k == "hospitalization" else network_hash
                ),
            }
            for k in REGISTRATION_ORDER
        ],
    }

    def load(question_key: str) -> tuple[dict, dict]:
        if question_key == "hospitalization":
            return (cyclic_validated, _approved_package())
        return (validated, _approved_package())

    result = validate_bundle(bundle, load)
    assert result["activatable"] is False
    assert any(
        isinstance(e, dict)
        and e.get("code") == "semantic_not_executable"
        and e.get("question") == "hospitalization"
        for e in result["errors"]
    )


def test_hash_mismatch_cannot_activate() -> None:
    validated = validate_xmlbif(_SYNTHETIC_XML)
    network_hash = validated["source_sha256"]
    wrong_hash = "sha256:" + "0" * 64
    assert wrong_hash != network_hash
    assert wrong_hash != "sha256:" + str(network_hash).removeprefix("sha256:")
    bundle = {
        "workflow": "registration",
        "questions": [
            {
                "question_key": k,
                "version": "v1",
                "network_hash": (
                    wrong_hash if k == "hospitalization" else network_hash
                ),
            }
            for k in REGISTRATION_ORDER
        ],
    }

    def load(question_key: str) -> tuple[dict, dict]:
        return (validated, _approved_package())

    result = validate_bundle(bundle, load)
    assert result["activatable"] is False
    assert any(
        isinstance(e, dict)
        and e.get("code") == "content_mismatch"
        and e.get("question") == "hospitalization"
        for e in result["errors"]
    )


def test_complete_synthetic_bundle_activates() -> None:
    validated = validate_xmlbif(_SYNTHETIC_XML)
    assert validated["source_bytes"] == _SYNTHETIC_XML
    network_hash = "sha256:" + str(validated["source_sha256"])
    bundle = {
        "workflow": "registration",
        "questions": [
            {"question_key": k, "version": "v1", "network_hash": network_hash}
            for k in REGISTRATION_ORDER
        ],
    }

    def load(question_key: str) -> tuple[dict, dict]:
        return (validated, _approved_package())

    result = validate_bundle(bundle, load)
    assert result["activatable"] is True
    assert result["errors"] == []
    assert result["questions"] == list(REGISTRATION_ORDER)
    assert isinstance(result["bundle_hash"], str)
    assert result["bundle_hash"].startswith("sha256:")
    again = validate_bundle(bundle, load)
    assert again["bundle_hash"] == result["bundle_hash"]
    admission = result.get("admission")
    assert isinstance(admission, dict)
    for key in REGISTRATION_ORDER:
        entry = admission.get(key)
        assert isinstance(entry, dict)
        assert entry.get("admitted") is True
        meas = (
            entry.get("measurements")
            if isinstance(entry.get("measurements"), dict)
            else entry
        )
        assert isinstance(meas.get("xml_bytes"), int)
        assert isinstance(meas.get("node_count"), int)
        assert isinstance(meas.get("cpt_cells"), int)


def test_chained_result_reference_rejected() -> None:
    validated = validate_xmlbif(_SYNTHETIC_XML)
    network_hash = "sha256:" + str(validated["source_sha256"])
    bundle = {
        "workflow": "registration",
        "questions": [
            {"question_key": k, "version": "v1", "network_hash": network_hash}
            for k in REGISTRATION_ORDER
        ],
    }

    def load(question_key: str) -> tuple[dict, dict]:
        package = _approved_package()
        if question_key == "hospitalization":
            package["mappings"] = list(package["mappings"]) + [
                {
                    "node_id": "B",
                    "allowed_source_paths": [
                        "questions.high_suicide_clozapine.posterior"
                    ],
                }
            ]
        return (validated, package)

    result = validate_bundle(bundle, load)
    assert result["activatable"] is False
    assert any(
        isinstance(e, dict)
        and e.get("code") == "chained_result"
        and e.get("question") == "hospitalization"
        for e in result["errors"]
    )


def test_bundle_hash_pins_versions() -> None:
    validated = validate_xmlbif(_SYNTHETIC_XML)
    network_hash = "sha256:" + str(validated["source_sha256"])
    bundle_v1 = {
        "workflow": "registration",
        "questions": [
            {"question_key": k, "version": "v1", "network_hash": network_hash}
            for k in REGISTRATION_ORDER
        ],
    }
    bundle_v2 = {
        "workflow": "registration",
        "questions": [
            {
                "question_key": k,
                "version": "v2" if k == "hospitalization" else "v1",
                "network_hash": network_hash,
            }
            for k in REGISTRATION_ORDER
        ],
    }

    def load(question_key: str) -> tuple[dict, dict]:
        return (validated, _approved_package())

    result_v1 = validate_bundle(bundle_v1, load)
    result_v2 = validate_bundle(bundle_v2, load)
    assert result_v2["activatable"] is True
    assert isinstance(result_v1["bundle_hash"], str)
    assert isinstance(result_v2["bundle_hash"], str)
    assert result_v1["bundle_hash"] != result_v2["bundle_hash"]
    admission = result_v2.get("admission")
    assert isinstance(admission, dict)
    for key in REGISTRATION_ORDER:
        entry = admission.get(key)
        assert isinstance(entry, dict)
        assert entry.get("admitted") is True
