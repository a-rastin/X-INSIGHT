# Model Xml Validation Tests

> 21 nodes · cohesion 0.10

## Key Concepts

- **test_xml_validation.py** (14 connections) — `backend/tests/models/test_xml_validation.py`
- **test_malformed_xml_bounded_location()** (4 connections) — `backend/tests/models/test_xml_validation.py`
- **test_rejects_doctype_entity_safely()** (4 connections) — `backend/tests/models/test_xml_validation.py`
- **test_rejects_oversize_input()** (4 connections) — `backend/tests/models/test_xml_validation.py`
- **test_rejects_remote_resolution_safely()** (4 connections) — `backend/tests/models/test_xml_validation.py`
- **test_unsupported_root_fails_safely()** (4 connections) — `backend/tests/models/test_xml_validation.py`
- **test_draft_bn04_inspectable_proposed_parents_not_edges()** (3 connections) — `backend/tests/models/test_xml_validation.py`
- **test_draft_bn08_inspectable_despite_missing_definitions()** (3 connections) — `backend/tests/models/test_xml_validation.py`
- **test_multi_network_reported_nonactivatable()** (3 connections) — `backend/tests/models/test_xml_validation.py`
- **test_unsupported_kinds_nonactivatable()** (3 connections) — `backend/tests/models/test_xml_validation.py`
- **test_validate_synthetic_two_node_format_fixture()** (2 connections) — `backend/tests/models/test_xml_validation.py`
- **S21 slice 1 (RED tracer) through the model-validation seam (T5). Public…** (1 connections) — `backend/tests/models/test_xml_validation.py`
- **Slice 2: truncated XML must raise with bounded line/column location.** (1 connections) — `backend/tests/models/test_xml_validation.py`
- **Slice 2: well-formed non-XMLBIF root must raise, not return valid.** (1 connections) — `backend/tests/models/test_xml_validation.py`
- **Slice 3 RED: BN-04 draft inspectable; proposed_parent PROPERTYs are not edges.** (1 connections) — `backend/tests/models/test_xml_validation.py`
- **Slice 3 RED: BN-08 draft inspectable despite missing DEFINITIONs.** (1 connections) — `backend/tests/models/test_xml_validation.py`
- **Slice 4 RED: two NETWORKs reported, not silently flattened, non-activatable.** (1 connections) — `backend/tests/models/test_xml_validation.py`
- **Slice 4 RED: decision/utility kinds parsed per XSD but non-activatable.** (1 connections) — `backend/tests/models/test_xml_validation.py`
- **Slice 2: DOCTYPE/ENTITY must fail safe with no expansion, no network.** (1 connections) — `backend/tests/models/test_xml_validation.py`
- **Slice 2: remote SYSTEM DTD must fail fast with no fetch.** (1 connections) — `backend/tests/models/test_xml_validation.py`
- **Slice 2: oversize bytes must be rejected before parsing.** (1 connections) — `backend/tests/models/test_xml_validation.py`

## Relationships

- [Model CPT Inference Tests Validation](Model_CPT_Inference_Tests_Validation.md) (10 shared connections)
- [Models Validation 2](Models_Validation_2.md) (5 shared connections)
- [Models Validation Xml](Models_Validation_Xml.md) (2 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)

## Source Files

- `backend/tests/models/test_xml_validation.py`

## Audit Trail

- EXTRACTED: 33 (87%)
- INFERRED: 5 (13%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*