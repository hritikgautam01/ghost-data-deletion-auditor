# Ghost Data Still Exists — Solution Codebase

**HackerRank Orchestrate — October 2026 Challenge**  
Official Challenge URL: [Ghost Data Still Exists on HackerRank](https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists)

---

## 1. Overview

This directory contains the runnable source code, policy engine, multimodal evidence extractors, evaluation harness, and documentation for the **Ghost Data Still Exists** deletion-audit agent.

The agent investigates customer deletion requests against primary databases, read replicas, search indexes, analytics platforms, support archives, and system activity logs. It resolves historical identities, enforces temporal boundaries (`captured_at <= audit_at`), checks the 15 organizational deletion rules, and outputs a strictly verified remediation plan.

---

## 2. Directory Layout

```text
code/
├── main.py                  # Primary solution CLI entry point
├── README.md                # Solution setup and execution guide
├── evaluation/
│   ├── main.py              # Public sample evaluation harness
│   ├── evaluation_report.md # Formal accuracy & case analysis report
│   └── usage_report.md      # Model calls, token usage, and cost report
└── src/
    ├── data/                # Dataset loader, models, and path resolver
    ├── identity/            # Identity resolution & historical graph
    ├── nlp/                 # Multilingual intent classification
    ├── evidence/            # JSON, log, SQL, PDF/screenshot extractors & correlator
    ├── policy/              # 15 organizational deletion rules & tombstones
    ├── planner/             # Remediation & verification step planner
    └── pipeline.py          # End-to-end orchestration pipeline
```

---

## 3. Setup and Prerequisites

- **Python Version:** Python 3.10+ (Standard library only; zero external third-party dependencies required).
- **Environment:** Compatible with Linux, macOS, and Windows.

---

## 4. Execution Commands

### 4.1 Run the Full Audit Pipeline on All 518 Requests

From the repository root or the `code/` directory, run:

```bash
python code/main.py --all --output-file output.csv
```

This generates `output.csv` at the repository root containing exactly 518 evaluation rows (`case_33` through `case_550`) in standard CSV format:
```text
case_id,deletion_status,steps_json
```

*Note: The dataset location is auto-discovered. If your dataset is located in a custom path, use `--dataset-dir <path>` or set the `ORCHESTRATE_DATASET_DIR` environment variable.*

### 4.2 Run an Individual Audit Case

To run a single case and view its JSON-formatted findings and plan:

```bash
python code/main.py --case case_33
```

### 4.3 Run Evaluation Against Public Ground Truth (32 Samples)

To benchmark the solution against `dataset/sample_output.csv`:

```bash
python code/evaluation/main.py --run-sample
```

### 4.4 Run Independent Schema and Invariant Validation

To validate the generated `output.csv` against all 10 challenge invariant rules:

```bash
python scripts/validate_output.py output.csv
```

---

## 5. Automated Tests

Run the complete unit and integration test suite:

```bash
python -m unittest discover tests -v
```

All 97 unit and integration tests execute in ~2.1 seconds with 100% pass rate.
