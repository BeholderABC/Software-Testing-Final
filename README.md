# AutoTestDesign

## Abstract

AutoTestDesign is the final-project deliverable of the *Software
Testing* course (2026 Spring). The system is an artificial-
intelligence-assisted test-design tool that converts natural-language
software requirements into structured, traceable, and risk-prioritised
test cases. The tool is paired with an executable target application —
a Django REST mini e-commerce backend bundled at
[target_app/Mini-E-Commerce-System/Backend/](target_app/Mini-E-Commerce-System/Backend/) —
so that the generated suite is exercised end-to-end from inside a
single Streamlit user interface. The tool implements the assignment's
functional requirements FR 1.0, FR 1.1, FR 2.0, FR 3.0, FR 4.0,
FR 5.0, FR 6.0, and FR 7.0, together with the mandatory interactive-
review capability.

---

## 1. The Two-Layer Testing Model

The repository contains two distinct testing layers; preserving the
separation between them is the most important conceptual model for
evaluating the project. Their division of responsibility is recorded
in Table 1.

**Table 1.** Two-layer testing model.

| Layer | Role | Location |
|---|---|---|
| A — Tool | AutoTestDesign produces structured test artefacts from natural-language requirements. | [app.py](app.py) and [core/](core/) |
| B — Execution | PyTest consumes those artefacts and exercises the target backend. | [tests/](tests/) and [target_app/](target_app/) |

Step 8 of the user interface closes the loop by triggering Layer B
from inside Layer A, so that the complete end-to-end demonstration is
observed within one browser session. The full set of architectural
diagrams is recorded in [docs/architecture.md](docs/architecture.md).

---

## 2. Capabilities

The capabilities of the tool and the modules that realise them are
recorded in Table 2.

**Table 2.** Capabilities and their host modules.

| Capability | Module |
|---|---|
| Parse free-text requirements into structured JSON | [core/parser.py](core/parser.py) (LLM) with rule fallback |
| Risk analysis (`risk_level` / `risk_score` / factors) | [core/risk_analysis.py](core/risk_analysis.py) (LLM) with rule fallback |
| Coverage-item generation across nine constraint types | [core/coverage_analysis.py](core/coverage_analysis.py) |
| Black-box test-case generation — EP, BVA, DT | [core/testcase_generator.py](core/testcase_generator.py) |
| White-box state-transition coverage (FR 4.0) | [core/state_model.py](core/state_model.py) with [data/order_state_model.json](data/order_state_model.json) |
| Structured test-oracle synthesis (FR 5.0) | [core/oracle.py](core/oracle.py) |
| Risk-based prioritisation and minimisation (FR 7.0) | [core/optimizer.py](core/optimizer.py) |
| Export to CSV, JSON, and multi-sheet Excel (FR 6.0) | [core/exporter.py](core/exporter.py) |
| In-UI subprocess PyTest runner with parsed report | [core/test_runner.py](core/test_runner.py) |
| Interactive review (edit, then regenerate downstream artefacts) | Streamlit UI ([app.py](app.py)) |
| Data-driven execution against the target backend | [tests/integration/test_data_driven_orders.py](tests/integration/test_data_driven_orders.py) |
| Auto-generation of the three IEEE 829 deliverable reports (LLM-first, rule fallback) | [core/report_pipeline.py](core/report_pipeline.py), [core/report_llm.py](core/report_llm.py), [core/report_generator.py](core/report_generator.py) |

The mapping from each functional requirement of the assignment to its
implementation is recorded in Table 3.

**Table 3.** Functional requirement to implementation.

| Requirement | Implementation |
|---|---|
| FR 1.0 — Input and parse | Text area, CSV upload, and `.txt` / `.json` loaders in [core/utils.py](core/utils.py). |
| FR 1.1 — Structuring | LLM parser plus rule fallback; output normalised to schema v1 ([docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md) §3.1). |
| FR 2.0 — Risk and priority | `risk_score ∈ [1, 10]` mapped onto `priority ∈ {High, Medium, Low}`. |
| FR 3.0 — Black-box generation | EP, BVA, and DT in [core/testcase_generator.py](core/testcase_generator.py). |
| FR 4.0 — White-box modelling | All states, all transitions, and guards in [core/state_model.py](core/state_model.py). |
| FR 5.0 — Test oracle | Structured oracle (HTTP status range and must-contain keywords) in [core/oracle.py](core/oracle.py). |
| FR 6.0 — Export | CSV, JSON, and Excel via [core/exporter.py](core/exporter.py). |
| FR 7.0 — Suite optimisation | Prioritisation and risk-based minimisation in [core/optimizer.py](core/optimizer.py). |
| Interactive review | `st.data_editor` on every pipeline step with automatic downstream invalidation. |

---

## 3. Repository Layout

```
.
├── app.py                                # Streamlit UI (nine-step workflow)
├── core/                                 # Pipeline modules
│   ├── parser.py                         # LLM requirement parser
│   ├── risk_analysis.py                  # LLM risk analyser
│   ├── pipeline_fallback.py              # Deterministic rule pipeline
│   ├── coverage_analysis.py              # Constraint → coverage items
│   ├── testcase_generator.py             # EP / BVA / DT engine
│   ├── state_model.py                    # White-box state coverage (FR 4.0)
│   ├── oracle.py                         # Structured test oracle (FR 5.0)
│   ├── optimizer.py                      # Prioritise + minimise (FR 7.0)
│   ├── exporter.py                       # CSV / JSON / Excel writers
│   ├── test_runner.py                    # In-UI subprocess PyTest runner
│   ├── report_pipeline.py                # Orchestrates deliverable-doc generation
│   ├── report_llm.py                     # LLM-first report writer (per-doc prompt)
│   ├── report_generator.py               # Deterministic report fallback (IEEE 829)
│   ├── run_context.py                    # Per-run outputs/run_<ts>/ directories
│   └── utils.py                          # Loaders and JSON helpers
├── prompts/                              # System prompts for the LLM stages
├── schema/                               # JSON schema files
├── data/
│   ├── mini_ecommerce_requirements.json  # Canonical dataset for the target app
│   ├── order_state_model.json            # FR 4.0 state machine
│   ├── baseline/                         # Reproducible pipeline output
│   └── sample_*.json                     # Smaller fixtures used by unit tests
├── docs/
│   ├── STYLE_GUIDE.md                    # Terminology, IDs, JSON schema
│   ├── architecture.md                   # System / workflow / dependency diagrams
│   ├── test_design.md                    # Test-design engine reference
│   ├── coverage_strategy.md              # Coverage strategy reference
│   ├── constraint_schema.md              # Constraint schema reference
│   ├── coverage_item_schema.md           # Coverage-item schema reference
│   ├── traceability_matrix.md            # Project-wide traceability matrix
│   └── test_result_analysis.md           # Target-app execution analysis
├── target_app/Mini-E-Commerce-System/    # Django REST target application
├── tests/
│   ├── unit/                             # Tests of the tool itself (no backend needed)
│   │   ├── coverage_test.py              # Coverage engine
│   │   ├── exporter_test.py              # Exporter (11 cases)
│   │   ├── optimizer_test.py             # Optimiser (8 cases)
│   │   ├── oracle_test.py                # Oracle synthesis (9 cases)
│   │   ├── parser_test.py                # LLM parser smoke (requires API)
│   │   ├── risk_test.py                  # LLM risk smoke (requires API)
│   │   ├── state_model_test.py           # State model (8 cases)
│   │   └── testcase_generator_test.py    # Engine (11 cases)
│   └── integration/                      # Tests against the target backend
│       ├── conftest.py                   # Shared fixtures (backend probe, case loader)
│       ├── mec_request_builder.py        # Test case → HTTP template adapter
│       ├── test_data_driven_orders.py    # Generated cases → backend execution
│       ├── test_mini_ecommerce_api.py    # Product CRUD checks      (REQ-001 … REQ-005)
│       ├── test_order_api.py             # Order create / read       (REQ-006 … REQ-011)
│       └── test_order_status_api.py      # Order status transitions  (REQ-012)
├── scripts/
│   ├── benchmark.py                      # Measures latency + LLM token cost → benchmark_report.md
│   ├── build_traceability.py             # Regenerates the traceability matrix
│   └── run_offline_tests.py              # Runs the offline unit suite → outputs/offline_tests_*
├── outputs/                              # Per-run artefacts: run_<ts>/docs (reports) + data (exports)
├── screenshots/                          # Workflow screenshots for the report
└── requirements.txt                      # Python dependencies
```

---

## 4. Setup

### 4.1 Prerequisites

The environment is required to provide Python ≥ 3.10 (the OpenAI SDK
and recent Streamlit releases no longer support Python 3.8 or 3.9),
`pip`, and SQLite (bundled with Python; used by the target backend).

### 4.2 Installing the Dependencies

```bash
git clone https://github.com/BeholderABC/Software-Testing-Final.git
cd Software-Testing-Final
python3 -m venv .venv
source .venv/bin/activate            # macOS / Linux
# .venv\Scripts\activate             # Windows
pip install --upgrade pip
pip install -r requirements.txt
```

The target backend ships its own `requirements.txt` at
[target_app/Mini-E-Commerce-System/Backend/requirements.txt](target_app/Mini-E-Commerce-System/Backend/requirements.txt);
its dependencies are installed into the same virtual environment.

### 4.3 Configuring the Language Model (Optional)

A `.env` file in the project root supplies the language-model
credentials, as illustrated below.

```dotenv
API_KEY=sk-your-key-here
BASE_URL=https://api.openai.com/v1   # or the chosen provider's endpoint
MODEL=gpt-4o-mini
```

When no key is configured the tool nevertheless runs end-to-end: the
three LLM-backed stages — the parser, the risk analyser, and the
deliverable-report writer — fall back to their deterministic rule
engines. The active path is displayed in the sidebar, so the
demonstration remains robust when the network or the API quota is
unavailable.

---

## 5. Running the Tool

### 5.1 Starting the Target Backend

```bash
cd target_app/Mini-E-Commerce-System/Backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The backend listens on `http://127.0.0.1:8000`.

### 5.2 Starting the Streamlit User Interface

The user interface is launched via the **virtual environment's**
Streamlit binary by full path so that the process is guaranteed to use
the interpreter that carries `openai`, `python-dotenv`, and the other
project dependencies.

```bash
.venv/bin/streamlit run app.py
# macOS hosts behind a corporate proxy:
NO_PROXY='*' .venv/bin/streamlit run app.py
```

A bare `streamlit run app.py` may resolve to a globally installed
`streamlit` (for example a Homebrew installation) even inside an
activated virtual environment, depending on the order of `PATH`
entries. The global interpreter does not carry the project
dependencies, so the sidebar would then report *LLM SDK: not
installed*. Invoking `.venv/bin/streamlit` removes this ambiguity.

The sidebar reports the API-key and LLM-SDK status and the target
backend URL with a live reachability indicator. The URL field is
edited in place to redirect the test runner to a different host or
port without restarting Streamlit.

### 5.3 The Nine-Step Workflow

The user interface presents a Welcome page followed by eight pipeline
steps, summarised below.

0. **Welcome** — the entry page. From here a reviewer can either
   execute the persisted baseline (`data/baseline/test_cases.json`
   or its optimised counterpart) against the live backend without
   running the design pipeline, or press *Start the full pipeline →*
   to advance to Step 1.
1. **Requirement input** — paste text or upload a CSV.
2. **Requirement structuring** — parsed JSON, editable.
3. **Risk analysis** — `risk_level`, `risk_score`, and factors,
   editable.
4. **Coverage items** — EP, BVA, and DT items per requirement,
   editable.
5. **Test cases** — generated cases with traceability and an attached
   oracle; the page also hosts a state-transition coverage subsection
   that appends white-box cases for the Order status machine
   (FR 4.0 + FR 5.0).
6. **Optimisation** — prioritisation and risk-based minimisation
   (FR 7.0).
7. **Export** — CSV, JSON, and Excel into `outputs/` (FR 6.0).
8. **Run tests** — execute pytest against the target backend; a
   coloured table records per-case PASS, FAIL, or SKIPPED with
   expandable error stacks. A *"Run every case individually"*
   checkbox toggles between the default representative-per-key
   execution and the diagnostic mode that issues every case as its
   own HTTP request (see [test_result_analysis.md](docs/test_result_analysis.md) §2.1).
   Once a run has been recorded, a gated *Generate deliverable
   documents* control renders the three IEEE 829 reports (risk
   analysis, test plan, detailed design and execution) into
   `outputs/run_<timestamp>/docs/`, embedding the run results;
   generation is LLM-first with a deterministic rule fallback.

Every editable step employs `st.data_editor`. When the tester modifies
a table, the cached downstream artefacts are invalidated automatically
and visiting the next step recomputes them. This realises the
assignment's interactive-review requirement.

### 5.4 Demonstration Walkthrough

The intended demonstration sequence is recorded below.

1. Welcome — *Start the full pipeline →*.
2. Steps 1 to 5 — the requirements are entered and the tool produces
   sixty-five structured test cases (sixty-one black-box and four
   white-box state-transition) with full traceability and an attached
   oracle.
3. Step 6 — *Minimise (risk-based)* demonstrates FR 7.0; the
   before-and-after grouped bar chart shows the suite reducing from
   sixty-five to sixty-one cases while every requirement and every
   decision-table or state-transition case is retained.
4. Step 8 — *Run Data-Driven Tests* fires pytest at the live backend;
   the per-case table reports the outcome.
5. Step 4 — a coverage item is edited (for example, tightening an
   expected behaviour).
6. Step 8 is revisited — the results change in place, evidencing that
   interactive review reaches all the way through execution.

A reviewer who only wishes to inspect the persisted baseline can
remain on the Welcome page (Step 0), select *Baseline — raw* or
*Baseline — optimised* and click *Run Data-Driven Tests* directly,
without entering the design pipeline.

### 5.5 Running the Tests from the Command Line

The suite is partitioned by purpose. The unit suite at
[tests/unit/](tests/unit/) exercises the tool itself (engines,
optimiser, exporter, oracle, state model) and does not depend on the
backend. The integration suite at
[tests/integration/](tests/integration/) exercises the target backend
(data-driven harness and hand-written API checks) and assumes that the
backend is running on `127.0.0.1:8000`.

```bash
# All Tests
.venv/bin/python -m pytest tests/

# Offline: tool unit tests, omitting the two LLM smoke tests by default
.venv/bin/python -m pytest tests/unit/ -v \
  --ignore=tests/unit/parser_test.py \
  --ignore=tests/unit/risk_test.py

# Integration: data-driven harness (generated cases → backend)
NO_PROXY='*' .venv/bin/python -m pytest tests/integration/test_data_driven_orders.py -v

# Integration: hand-written backend checks
NO_PROXY='*' .venv/bin/python -m pytest \
    tests/integration/test_mini_ecommerce_api.py \
    tests/integration/test_order_api.py \
    tests/integration/test_order_status_api.py -v

# Full suite (the backend is running)
NO_PROXY='*' .venv/bin/python -m pytest tests/ -v \
  --ignore=tests/unit/parser_test.py --ignore=tests/unit/risk_test.py
```

The data-driven harness defaults to
[data/baseline/test_cases.json](data/baseline/test_cases.json), so it
runs without any prior Streamlit session. The harness is redirected at
a fresh export by the environment override shown below.

```bash
GENERATED_TEST_CASES=outputs/test_cases_<timestamp>.json \
  NO_PROXY='*' python3 -m pytest tests/integration/test_data_driven_orders.py -v
```

The environment variable `BACKEND_BASE_URL` overrides the default
backend URL and is read by the hand-written tests, the data-driven
harness, and the in-UI runner.

### 5.6 Benchmarking the Pipeline

The script [scripts/benchmark.py](scripts/benchmark.py) measures the
performance of the pipeline and the cost of the language-model stages
and writes the results to
[docs/benchmark_report.md](docs/benchmark_report.md). This report is
the single source of truth for every latency and token-cost figure
quoted in [docs/test_plan.md](docs/test_plan.md) and
[docs/cost_estimation.md](docs/cost_estimation.md); it is regenerated
to refresh those numbers.

```bash
# Full run: rule-pipeline latency plus real LLM token usage (issues API calls)
.venv/bin/python scripts/benchmark.py

# Without the LLM stages (no API calls; no key required)
.venv/bin/python scripts/benchmark.py --no-llm

# Adjusting the number of repetitions per rule stage (default 20)
.venv/bin/python scripts/benchmark.py --repeats 50
```

The contents of the regenerated report are summarised in Table 4.

**Table 4.** Sections of `docs/benchmark_report.md`.

| Section | Content |
|---|---|
| Performance verdict | End-to-end rule-pipeline generation time compared with the 2-second target. |
| Rule-stage latency | Mean, minimum, maximum, and standard deviation per stage (parse, structure, risk, coverage, test-case generation, oracle, optimise, export), averaged over `--repeats` repetitions. |
| LLM usage | Exact input and output token counts (from the provider's `usage` field) together with the latency of the parse and risk calls; populated only when an API key is configured. |
| Cost | Cost per full run at standard and batch pricing. |

The full run issues real API calls and therefore requires a valid
`.env`; the LLM token figures appear only when a key is present. The
`--no-llm` invocation produces a report restricted to the performance
and latency sections. Temporary export artefacts created while timing
the export stage are persisted to `outputs/_bench_tmp/` and may be
deleted after each run.

---

## 6. Documents

The project documents are organised by purpose. Project conventions
are recorded in
[docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md),
[docs/architecture.md](docs/architecture.md),
[docs/constraint_schema.md](docs/constraint_schema.md), and
[docs/coverage_item_schema.md](docs/coverage_item_schema.md). 
Engine and strategy references are recorded in
[docs/test_design.md](docs/test_design.md),
[docs/coverage_strategy.md](docs/coverage_strategy.md),
[docs/prompt_design.md](docs/prompt_design.md), and
[docs/benchmark_report.md](docs/benchmark_report.md). 
Submission reports for the Mini-E-Commerce target application are
[docs/risk_analysis_report.md](docs/risk_analysis_report.md),
[docs/test_plan.md](docs/test_plan.md),
[docs/detailed_test_design_execution.md](docs/detailed_test_design_execution.md),
[docs/traceability_matrix.md](docs/traceability_matrix.md),
[docs/test_result_analysis.md](docs/test_result_analysis.md), and
[docs/cost_estimation.md](docs/cost_estimation.md).

---

## 7. Test Status

The current status of the test suites is recorded in Table 5.

**Table 5.** Test status.

| Scope | Result |
|---|---|
| Offline unit and integration (backend off) | 48 passed, 81 skipped |
| Full suite with the backend running | 129 passed (excluding the two LLM-only smoke tests) |
| Hand-written backend coverage | 30 cases across REQ-001 … REQ-012 |
| Data-driven harness against the backend | 51 generated cases on the rule-pipeline baseline (47 black-box + 4 white-box state-transition) |

The two LLM smoke tests in
[tests/unit/parser_test.py](tests/unit/parser_test.py) and
[tests/unit/risk_test.py](tests/unit/risk_test.py) require live API
access and are excluded from the offline suite by design.

---

## 8. Licence and Attribution

This work is an academic project. The Mini-E-Commerce backend bundled
under [target_app/](target_app/) is adapted from a public reference
implementation for educational use only.
