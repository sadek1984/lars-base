# Feature Specification: Unit Test Coverage for Critical LARS Modules

**Feature Branch**: `001-unit-test-coverage`  
**Created**: 2026-02-20  
**Status**: Draft  
**Input**: User description: "This app does not have any unit test. We need to cover the most important parts of the app."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Entity Mapping & Normalization Tests (Priority: P1)

A developer modifies Arabic↔English pesticide, sample, or neighborhood mappings in `mappings.py`. The test suite immediately catches if any normalization function breaks — ensuring queries continue to resolve entity names correctly.

**Why this priority**: The `mappings.py` module is the single source of truth for all entity lookups. A broken mapping silently corrupts every query in the system. This is the highest-value, lowest-effort test target because its functions are pure, stateless, and deterministic.

**Independent Test**: Can be fully tested by importing `mappings.py` functions and asserting input→output pairs. Delivers confidence that all Arabic pesticide names, sample names, and neighborhoods resolve correctly.

**Acceptance Scenarios**:

1. **Given** the `mappings.py` module is loaded, **When** `translate_pesticide("ابامكتين")` is called, **Then** it returns `"abamectin"`.
2. **Given** a misspelled sample name `"طماطه"`, **When** `normalize_sample_name` is called, **Then** it returns the canonical `"طماطم"`.
3. **Given** a pesticide with known DB typos (e.g., `"buprofezin"`), **When** `get_pesticide_variants` is called, **Then** it returns all known variants including `"buprofuzin"`.
4. **Given** an Arabic numeral string `"٣"`, **When** `normalize_arabic_query` is called, **Then** it returns `"3"`.
5. **Given** raw STT text with common speech-to-text errors, **When** `correct_stt_text` is called, **Then** it corrects known errors to canonical forms.

---

### User Story 2 - Intent Router Classification Tests (Priority: P2)

A developer adds or modifies intent classification rules in `intent_router.py`. The test suite verifies that user queries are correctly parsed into the right `Intent` enum and that all entities (samples, neighborhoods, pesticides, categories) are properly extracted.

**Why this priority**: The intent router is the critical dispatch layer — a misclassification sends queries to the wrong handler, producing wrong answers. Testing classification logic is high-value and the module's `analyze()` method has clear input→output behavior.

**Independent Test**: Can be tested by constructing `IntentRouter` with default dialect synonyms and asserting that sample Arabic queries produce the correct `(Intent, QueryEntities)` pairs.

**Acceptance Scenarios**:

1. **Given** the query `"كم عدد عينات الطماطم"`, **When** `IntentRouter.analyze()` is called, **Then** intent is `Intent.COUNT_SAMPLES` and `entities.samples` contains `"طماطم"`.
2. **Given** the query `"ابحث عن ابامكتين في الطماطم"`, **When** analyzed, **Then** intent is `Intent.FIND_PESTICIDE` with the correct pesticide and sample extracted.
3. **Given** a multi-entity query naming two neighborhoods, **When** analyzed, **Then** `entities.neighborhoods` contains both names.
4. **Given** the query `"تحليل شامل للطماطم"`, **When** analyzed, **Then** intent is `Intent.COMPREHENSIVE_ANALYSIS`.

---

### User Story 3 - Risk Assessment Calculation Tests (Priority: P3)

A developer changes the EDI/HQc/HIc calculation logic in `risk_assessment_service.py` or modifies configuration values in `risk_assessment_config.py`. The test suite ensures that all dietary risk formulas produce mathematically correct results.

**Why this priority**: Risk assessment calculations directly impact public health reporting. Incorrect EDI or Hazard Quotient values could lead to wrong safety conclusions. These calculations are deterministic and testable with known input/output pairs.

**Independent Test**: Can be tested by instantiating `RiskAssessmentConfig` and `ChemicalClassifier`, and verifying calculations with known concentration, ADI, body weight, and ingestion rate values.

**Acceptance Scenarios**:

1. **Given** a pesticide concentration of 0.05 mg/kg and ingestion rate of 0.045 kg/day and body weight of 60 kg, **When** EDI is calculated, **Then** the result matches the expected value `(concentration × IR) / BW`.
2. **Given** an EDI value and an ADI value, **When** HQc is calculated, **Then** `HQc = EDI / ADI`.
3. **Given** a commodity name `"Tomato"` and population `"saudi_adults"`, **When** `RiskAssessmentConfig.get_ingestion_rate()` is called, **Then** it returns the configured rate.
4. **Given** a pesticide name `"cypermethrin"`, **When** `ChemicalClassifier.get_group()` is called, **Then** it returns `"pyrethroid"`.

---

### User Story 4 - Database Helper Tests (Priority: P4)

A developer modifies database query logic or schema prompting in `db_helper.py`. The test suite verifies that connection management, query execution, and SQL prompt generation work correctly.

**Why this priority**: The database layer underpins all query functionality. Ensuring connection lifecycle (open/close/context manager), query execution, and schema info generation are correct prevents silent data access failures.

**Independent Test**: Can be tested with a temporary in-memory DuckDB database seeded with minimal sample data, verifying CRUD operations and prompt generation.

**Acceptance Scenarios**:

1. **Given** a valid DuckDB path, **When** `LARSDatabase` is initialized, **Then** it connects successfully and `get_schema_info()` returns a non-empty schema string.
2. **Given** sample data inserted via `insert_sample()`, **When** `query("SELECT * FROM ...")` is called, **Then** it returns a DataFrame containing the inserted data.
3. **Given** a `LARSDatabase` used as a context manager, **When** the `with` block ends, **Then** the connection is closed.
4. **Given** a user query string, **When** `get_sql_prompt()` is called, **Then** the returned prompt contains schema information and the user query.

---

### User Story 5 - Query Processing Integration Tests (Priority: P5)

A developer modifies query routing or pattern matching in `core_query_engine.py` or `unified_query_processor.py`. Lightweight integration tests verify that specific query patterns route to the correct handler and produce structurally valid responses.

**Why this priority**: While full integration tests require a populated database, lightweight tests can verify pattern matching, query normalization, and handler routing for common queries. This provides a safety net for the most complex module in the system.

**Independent Test**: Can be tested with a test DuckDB database containing minimal representative data (a few samples, pesticides, neighborhoods), verifying that common query patterns return the expected response structure.

**Acceptance Scenarios**:

1. **Given** a test database with known sample data, **When** `CoreQueryEngine.process("كم عدد عينات الطماطم")` is called, **Then** the response contains a count and a non-None DataFrame.
2. **Given** a query about samples above MRL, **When** processed, **Then** the response text includes relevant statistics and the DataFrame contains the correct columns.
3. **Given** a query that matches no known pattern, **When** processed, **Then** the engine falls back gracefully without crashing.

---

### Edge Cases

- What happens when a pesticide name is not found in any mapping dictionary?
- How does the system handle empty or whitespace-only queries?
- What happens when the database file is missing or corrupted?
- How does the intent router handle mixed Arabic/English queries?
- What happens when risk assessment calculates with zero or negative body weight?
- How does the system handle Unicode normalization differences in Arabic text?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Test suite MUST cover all public functions in `mappings.py` including `translate_pesticide`, `normalize_sample_name`, `normalize_neighborhood`, `normalize_arabic_query`, `correct_stt_text`, and `get_pesticide_variants`.
- **FR-002**: Test suite MUST cover `IntentRouter.analyze()` with representative queries for each `Intent` enum value.
- **FR-003**: Test suite MUST verify EDI, HQc, and HIc calculation formulas in `risk_assessment_service.py` with known input/output pairs.
- **FR-004**: Test suite MUST cover `RiskAssessmentConfig` methods: `get_ingestion_rate`, `get_population_bw`, `has_detailed_rates`, and `get_pesticide_adi`.
- **FR-005**: Test suite MUST cover `ChemicalClassifier` methods: `get_group`, `classify_pesticides`, and `get_all_groups`.
- **FR-006**: Test suite MUST cover `LARSDatabase` CRUD operations and connection lifecycle using in-memory DuckDB.
- **FR-007**: Test suite MUST include at least one integration-level test for `CoreQueryEngine.process()` verifying end-to-end query handling.
- **FR-008**: All tests MUST run without requiring external services (Ollama, APIs) — mock LLM dependencies where needed.
- **FR-009**: Test suite MUST use `pytest` as the test framework.
- **FR-010**: Each test file MUST be independently runnable (`pytest tests/test_<module>.py`).

### Key Entities

- **Test Fixture Data**: Minimal DuckDB database with representative pesticide analysis records for integration tests.
- **Mapping Dictionaries**: PESTICIDE_AR_TO_EN, SAMPLE_CORRECTIONS, NEIGHBORHOOD_CORRECTIONS, PESTICIDE_VARIANTS — tested for completeness and correctness.
- **Intent Enum**: All values in `Intent` enum must have at least one test query that triggers them.
- **Risk Parameters**: ADI values, ingestion rates, body weights — tested for correct lookup and calculation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 80% of public functions across the 5 target modules are covered by at least one test.
- **SC-002**: All tests pass when run via `pytest` from the project root with zero failures.
- **SC-003**: Test suite completes execution in under 30 seconds (no slow external calls).
- **SC-004**: Each `Intent` enum variant has at least 1 query that correctly classifies to it.
- **SC-005**: Risk assessment calculations match hand-verified expected values within 0.001 tolerance.
- **SC-006**: No test depends on external services (Ollama, EU MRL API, internet connectivity).

## Assumptions

- pytest is the test framework (standard Python testing).
- Tests will be placed in `tests/` directory at the project root or under `src/tests/`.
- DuckDB can be used in-memory for database tests, avoiding the need for the production database file.
- LLM-dependent code paths will be mocked to avoid requiring Ollama or other model servers.
- Arabic text handling (bidirectional, normalization) will be tested with known correct pairs.
