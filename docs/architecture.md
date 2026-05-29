# Architecture

## Abstract

This document records the architecture of the AutoTestDesign system.
Six visual representations are provided: the two-layer testing model,
the internal architecture of the tool, the nine-step user-interface
workflow, the white-box state machine, an end-to-end runtime trace for
one requirement, and the module dependency graph. The repository
layout is recorded as a final reference. Every diagram is authored in
Mermaid and renders natively in the principal Markdown viewers.

---

## 1. Two-Layer Testing Model

The architecture is organised around a strict separation between the
*tool that designs the tests* and the *tests that exercise the target
application*. The separation is summarised in Figure 1.

```mermaid
flowchart TB
    classDef toolBox  fill:#dbeafe,stroke:#1d4ed8,color:#0c1e3f,stroke-width:1.5px
    classDef testBox  fill:#fef9c3,stroke:#a16207,color:#3a2a06,stroke-width:1.5px
    classDef sutBox   fill:#fee2e2,stroke:#b91c1c,color:#450a0a,stroke-width:1.5px
    classDef artifact fill:#ecfdf5,stroke:#047857,color:#022c22,stroke-width:1px

    subgraph layerA [Layer A — AutoTestDesign Tool]
        direction TB
        UI["Streamlit UI<br/>app.py · 9 steps"]
        Core["Pipeline engine<br/>core/*"]
        Artifacts[("test_cases_*.json<br/>+ CSV + Excel")]
        UI --> Core --> Artifacts
    end

    subgraph layerB [Layer B — Execution against the target]
        direction TB
        Pytest["PyTest data-driven harness<br/>tests/integration/test_data_driven_orders.py"]
        SUT[("Mini-E-Commerce backend<br/>Django REST")]
        Report["pytest report<br/>(table in UI Step 8)"]
        Pytest -- HTTP --> SUT
        SUT -- "status + body" --> Pytest
        Pytest --> Report
    end

    Artifacts -- "feeds" --> Pytest
    Report -- "renders inside" --> UI

    class UI,Core,Artifacts toolBox
    class Pytest,Report testBox
    class SUT sutBox
```

*Figure 1.* The two-layer testing model.

Layer A is responsible for producing evidence in the form of
structured test artefacts. Layer B is responsible for translating
that evidence into verdicts. Step 8 of the user interface closes the
loop by triggering the PyTest run from within the same browser
session that produced the artefacts.

---

## 2. Tool Internal Architecture

The internal organisation of the tool is summarised in Figure 2. The
user interface is a thin scheduler; the substantive functionality is
distributed among the modules of `core/`.

```mermaid
flowchart LR
    classDef llm   fill:#dbeafe,stroke:#1d4ed8,color:#0c1e3f
    classDef rule  fill:#dcfce7,stroke:#15803d,color:#052e1d
    classDef ui    fill:#fde68a,stroke:#b45309,color:#3a2a06
    classDef out   fill:#ecfdf5,stroke:#047857,color:#022c22
    classDef ext   fill:#f3e8ff,stroke:#7e22ce,color:#2c0d52

    Input[/"requirement text<br/>(form / CSV / .json)"/]
    Env[/".env<br/>API_KEY · BASE_URL · MODEL"/]

    subgraph uiLayer ["UI layer · app.py"]
        Scheduler["scheduler functions<br/>parse_with_fallback · ..."]
        Editor["st.data_editor × 5<br/>interactive review"]
    end

    subgraph engine ["core/ pipeline engine"]
        Parser["parser.py<br/>LLM parser"]
        Risk["risk_analysis.py<br/>LLM risk analyser"]
        Fallback["pipeline_fallback.py<br/>deterministic fallback"]
        Coverage["coverage_analysis.py<br/>constraint → coverage items"]
        TestGen["testcase_generator.py<br/>EP · BVA · DT"]
        Oracle["oracle.py<br/>structured oracle (FR 5.0)"]
        StateModel["state_model.py<br/>state transition (FR 4.0)"]
        Optimizer["optimizer.py<br/>prioritise · minimise"]
        Exporter["exporter.py<br/>CSV · JSON · Excel"]
        Runner["test_runner.py<br/>subprocess pytest"]
    end

    Outputs[("outputs/<br/>test_cases_*.json<br/>+ CSV + xlsx")]
    Backend[/"Mini-E-Commerce backend"/]

    Input --> Scheduler
    Env -.-> Parser
    Env -.-> Risk

    Scheduler --> Parser
    Scheduler --> Risk
    Parser -. "API failure" .-> Fallback
    Risk   -. "API failure" .-> Fallback
    Parser --> Coverage
    Fallback --> Coverage
    Coverage --> TestGen
    Risk --> TestGen
    TestGen --> Oracle
    StateModel --> TestGen
    Oracle --> Optimizer
    Optimizer --> Exporter
    Scheduler --> Runner
    Editor -. "edits invalidate downstream" .- Scheduler

    Exporter --> Outputs
    Runner --> Backend
    Runner --> Outputs

    class Parser,Risk llm
    class Coverage,TestGen,Oracle,StateModel,Optimizer,Exporter,Runner,Fallback rule
    class Scheduler,Editor ui
    class Outputs out
    class Backend,Input,Env ext
```

*Figure 2.* Internal architecture of the tool. Legend below.

**Table 1.** Legend for Figure 2.

| Colour | Meaning |
|---|---|
| Blue | LLM-driven node (with deterministic fallback) |
| Green | Deterministic rule engine |
| Yellow | User interface / orchestration |
| Mint | Persistent output artefact |
| Purple | External boundary (input / backend) |

---

## 3. Nine-Step Workflow

The Streamlit user interface exposes the pipeline as a guided nine-
step workflow, summarised in Figure 3. The dotted edges indicate the
interactive-review behaviour: an upstream edit invalidates the cached
downstream artefacts.

```mermaid
flowchart LR
    classDef step fill:#dbeafe,stroke:#1d4ed8,color:#0c1e3f
    classDef sink fill:#ecfdf5,stroke:#047857,color:#022c22

    s1["1 · Requirement<br/>Input"]
    s2["2 · Requirement<br/>Structuring"]
    s3["3 · Risk Analysis<br/>FR 2.0"]
    s4["4 · Coverage<br/>Items"]
    s5["5 · Test Cases<br/>FR 3.0 · FR 4.0 · FR 5.0"]
    s6["6 · Optimisation<br/>FR 7.0"]
    s7["7 · Export<br/>FR 6.0"]
    s8["8 · Run Tests<br/>end-to-end"]
    s9["9 · Evidence<br/>Checklist"]

    s1 --> s2 --> s3 --> s4 --> s5 --> s6 --> s7 --> s8 --> s9

    s2 -. edit .-> s2
    s3 -. edit .-> s3
    s4 -. "edit invalidates" .-> s5
    s5 -. "edit invalidates" .-> s6
    s8 -. "reads current<br/>session" .-> s5

    class s1,s2,s3,s4,s5,s6,s7,s8,s9 step
```

*Figure 3.* Nine-step workflow exposed by the user interface.

Dotted edges represent interactive review: an upstream edit
invalidates the cached downstream artefacts, which are regenerated on
the next visit. Step 8 reads the current session's test cases
directly, so editing a coverage item in Step 4 changes what is sent
to the backend in Step 8 without leaving the browser.

---

## 4. White-Box State Machine (FR 4.0)

The Order status machine in
[target_app/Mini-E-Commerce-System/Backend/store/models.py](../target_app/Mini-E-Commerce-System/Backend/store/models.py)
is encoded in
[data/order_state_model.json](../data/order_state_model.json) and
exposed by the test-case generation step in the UI. The model declares
two valid transitions and two guard edges that the implementation must
reject.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> pending
    pending --> completed : complete
    pending --> cancelled : cancel
    completed --> cancelled : cancel (guarded)
    cancelled --> completed : complete (guarded)
    completed --> [*]
    cancelled --> [*]
```

*Figure 4.* Order status state machine encoded for FR 4.0.

Each coverage criterion produces a deterministic number of test
cases, recorded in Table 2.

**Table 2.** Cases produced under each criterion.

| Criterion | Cases |
|---|---:|
| All states | 2 |
| All valid transitions | 2 |
| All transitions + invalid guards | 4 (2 valid + 2 negative) |

The generated cases share the JSON shape of the black-box engine and
therefore flow through the optimiser, exporter, and in-UI runner
without adaptation.

---

## 5. End-to-End Runtime Trace

To make the runtime behaviour concrete, Figure 5 records the sequence
of interactions that follow REQ-009 (*reject an order whose quantity
exceeds stock*) through the entire system.

```mermaid
sequenceDiagram
    autonumber
    actor U as Designer
    participant App as Streamlit · app.py
    participant Engine as core/* engine
    participant Json as outputs/<br/>test_cases.json
    participant Pytest as PyTest harness
    participant Be as Mini-E-Commerce backend

    U->>App: paste 12 requirements
    App->>Engine: parse_requirements()
    Engine-->>App: 12 structured requirements
    App->>Engine: analyze_risk(REQ-009)
    Engine-->>App: risk_level=High · risk_score=9
    App->>Engine: generate_coverage(REQ-009)
    Engine-->>App: 3 items<br/>(positive · boundary · negative)
    App->>Engine: generate_test_cases() + attach_oracles()
    Engine-->>App: 4 cases — TC-REQ-009-001..004
    U->>App: edit TC-REQ-009-002 expected result
    App->>Engine: optimize_test_suite()
    Engine-->>App: prioritised suite
    U->>App: Step 8 — Run Data-Driven Tests
    App->>Json: write current session test cases
    App->>Pytest: subprocess pytest, env=BACKEND_BASE_URL
    Pytest->>Be: POST /api/orders/create/<br/>quantity=0
    Be-->>Pytest: 400 "Quantity must be > 0"
    Pytest-->>App: TC-REQ-009-002 PASSED
    App-->>U: results table · failed rows expandable
```

*Figure 5.* End-to-end runtime trace for REQ-009.

The trace records the canonical closed loop: the tool produces
evidence, the tester reviews and edits it, the harness executes it
against the running backend, and the verdicts return to the same
interface.

---

## 6. Module Dependency Graph

Figure 6 presents the import graph of the modules. It distinguishes
the user-interface layer, the deterministic core engine, the external
dependencies, and the test infrastructure.

```mermaid
flowchart TD
    classDef ui     fill:#fde68a,stroke:#b45309,color:#3a2a06
    classDef core   fill:#dcfce7,stroke:#15803d,color:#052e1d
    classDef ext    fill:#f3e8ff,stroke:#7e22ce,color:#2c0d52
    classDef test   fill:#fce7f3,stroke:#be185d,color:#3a0a25

    app[app.py]
    parser[parser.py]
    risk[risk_analysis.py]
    fallback[pipeline_fallback.py]
    coverage[coverage_analysis.py]
    testgen[testcase_generator.py]
    oracle[oracle.py]
    state[state_model.py]
    optimizer[optimizer.py]
    exporter[exporter.py]
    runner[test_runner.py]

    openai((openai))
    pandas((pandas))
    requests((requests))

    conftest[tests/integration/conftest.py]
    ddt[tests/integration/test_data_driven_orders.py]
    mec[tests/integration/mec_request_builder.py]

    app --> parser
    app --> risk
    app --> fallback
    app --> coverage
    app --> testgen
    app --> oracle
    app --> state
    app --> optimizer
    app --> exporter
    app --> runner

    parser --> openai
    risk --> openai
    fallback --> pandas
    exporter --> pandas
    coverage --> testgen
    state --> testgen
    optimizer --> testgen
    oracle --> testgen

    runner --> requests
    runner --> ddt

    ddt --> conftest
    ddt --> mec
    mec --> requests

    class app ui
    class parser,risk,fallback,coverage,testgen,oracle,state,optimizer,exporter,runner core
    class openai,pandas,requests ext
    class conftest,ddt,mec test
```

---

## 7. Repository Layout

The on-disk organisation of the project is summarised below.

```
.
├── app.py                                # Streamlit UI (9 steps)
├── core/
│   ├── parser.py                         # LLM parser
│   ├── risk_analysis.py                  # LLM risk analyser
│   ├── pipeline_fallback.py              # deterministic rule pipeline
│   ├── coverage_analysis.py              # constraint → coverage items
│   ├── testcase_generator.py             # EP / BVA / DT engine
│   ├── state_model.py                    # white-box state coverage (FR 4.0)
│   ├── oracle.py                         # structured oracle (FR 5.0)
│   ├── optimizer.py                      # prioritise + minimise (FR 7.0)
│   ├── exporter.py                       # CSV / JSON / Excel writers
│   ├── test_runner.py                    # in-UI pytest subprocess
│   └── utils.py                          # loaders, JSON helpers
├── prompts/                              # LLM system prompts
├── schema/                               # JSON schema files
├── data/
│   ├── mini_ecommerce_requirements.json  # canonical dataset
│   ├── order_state_model.json            # FR 4.0 state machine
│   ├── baseline/                         # reproducible pipeline output
│   └── sample_*.json                     # unit-test fixtures
├── target_app/Mini-E-Commerce-System/    # target backend (Django REST)
├── tests/
│   ├── conftest.py                       # shared fixtures
│   ├── mec_request_builder.py            # test case → HTTP template
│   ├── test_data_driven_orders.py        # generated cases → backend
│   ├── test_mini_ecommerce_api.py        # product CRUD checks
│   ├── test_order_api.py                 # order create/read checks
│   ├── test_order_status_api.py          # order status transitions
│   └── *_test.py                         # engine / exporter / etc unit tests
├── scripts/
│   └── build_traceability.py             # regenerates traceability_matrix.md
├── docs/                                 # this folder
├── outputs/                              # timestamped run artefacts
└── screenshots/                          # workflow screenshots
```
