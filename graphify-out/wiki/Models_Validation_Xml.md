# Models Validation Xml

> 16 nodes · cohesion 0.13

## Key Concepts

- **validation.py** (18 connections) — `backend/src/x_insight/models/validation.py`
- **test_schema.py** (6 connections) — `BNs/test_schema.py`
- **export_source()** (4 connections) — `backend/src/x_insight/models/validation.py`
- **_get_schema()** (4 connections) — `backend/src/x_insight/models/validation.py`
- **_safe_parser()** (4 connections) — `backend/src/x_insight/models/validation.py`
- **test_order_and_metadata_preserved()** (4 connections) — `backend/tests/models/test_xml_validation.py`
- **copy** (4 connections)
- **lxml** (4 connections)
- **Any** (2 connections)
- **itertools** (2 connections)
- **S21 slices 1-4: structural XMLBIF validation (XSD only, never executable).** (1 connections) — `backend/src/x_insight/models/validation.py`
- **Return a byte-identical copy of the validated source document. Validation…** (1 connections) — `backend/src/x_insight/models/validation.py`
- **Slice 4 RED: document order and network metadata preserved, bytes round-trip.** (1 connections) — `backend/tests/models/test_xml_validation.py`
- **Run with python3 test_schema.py; requires lxml (already installed here).…** (1 connections) — `BNs/test_schema.py`
- **XMLParser** (1 connections)
- **XMLSchema** (1 connections)

## Relationships

- [Model CPT Inference Tests Validation](Model_CPT_Inference_Tests_Validation.md) (6 shared connections)
- [Models Inference](Models_Inference.md) (3 shared connections)
- [DDI Checker](DDI_Checker.md) (2 shared connections)
- [Model Question Packages Tests](Model_Question_Packages_Tests.md) (2 shared connections)
- [MCP Server](MCP_Server.md) (2 shared connections)
- [Reasoning Coordinator Provider](Reasoning_Coordinator_Provider.md) (2 shared connections)
- [Model Xml Validation Tests](Model_Xml_Validation_Tests.md) (2 shared connections)
- [Assessment PANSS Tests](Assessment_PANSS_Tests.md) (2 shared connections)
- [Models Routes 2](Models_Routes_2.md) (1 shared connections)
- [Model Bundles Tests](Model_Bundles_Tests.md) (1 shared connections)
- [Model Admission Tests](Model_Admission_Tests.md) (1 shared connections)
- [Models Validation 2](Models_Validation_2.md) (1 shared connections)

## Source Files

- `BNs/test_schema.py`
- `backend/src/x_insight/models/validation.py`
- `backend/tests/models/test_xml_validation.py`

## Audit Trail

- EXTRACTED: 42 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*