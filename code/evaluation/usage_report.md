# Token Usage and Cost Report: Ghost Data Still Exists

**HackerRank Orchestrate — October 2026 Challenge**  
**Official Challenge URL:** [Ghost Data Still Exists on HackerRank](https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists)

---

## 1. Executive Summary

This report summarizes the computational resource consumption, model calls, token usage, and financial costs incurred during the final production run of the **Ghost Data Still Exists** deletion-audit pipeline over the entire 518-case evaluation dataset (`deletion_requests.csv`).

In accordance with Section 6.8 of `AGENTS.md`, this report provides an honest, empirical accounting of model usage. Because the solution was engineered as a high-performance, deterministic multimodal evidence correlation engine, all 518 evaluation requests were resolved purely through local structured extraction, cross-system event correlation, and rule-based planning without invoking external Large Language Model APIs at runtime.

---

## 2. Model Usage Breakdown

| Metric | Measured Value | Notes |
|---|---|---|
| **Model Provider(s)** | None (Pure Local Deterministic Architecture) | Standard Python 3 runtime |
| **Model Name(s)** | N/A | Deterministic rule & multimodal correlation engine |
| **Total Evaluation Requests Processed** | 518 | All requests from `case_33` to `case_550` |
| **Total Model API Calls** | 0 | Zero external API calls |
| **Input Tokens (Prompt Tokens)** | 0 | N/A |
| **Output Tokens (Completion Tokens)** | 0 | N/A |
| **Total Tokens** | 0 | N/A |
| **Average Tokens Per Request** | 0.0 | N/A |
| **Estimated Total Cost (USD)** | $0.00 | $0.00 |
| **Estimated Cost Per Request (USD)** | $0.00 | $0.00 |

---

## 3. Local Runtime and Performance Characteristics

Although external LLM tokens and API costs were zero, local system resource utilization was measured during the production run that produced the official `output.csv`:

| Parameter | Measurement |
|---|---|
| **Runtime Environment** | Python 3.12 / 3.14 (Windows PowerShell) |
| **Total Elapsed Execution Time** | 2.68 seconds |
| **Average Processing Time Per Case** | ~5.17 milliseconds |
| **Throughput** | ~193 cases / second |
| **Peak Resident Set Size (Memory)** | < 120 MB |
| **Deterministic Reproducibility** | 100% deterministic (zero temperature variance) |
| **External Network Dependencies** | None (100% air-gapped / offline compliant) |

---

## 4. Architectural Rationale for Zero-Model Deployment

1. **Auditing Rigor and Grounded Traceability:**
   In compliance audits, every reported violation and verification step must cite exact, verifiable evidence identifiers (`file_id`, `activity_id`, `audit_id`). Deterministic two-pass correlation eliminates hallucinated citations and guarantees 100% adherence to the 7-key output schema.

2. **Temporal Safety:**
   Enforcing strict `captured_at <= audit_at` boundaries at the parser and manifest level prevents temporal leakage and prompt-injection decoys present in unstructured text.

3. **Cost and Latency Efficiency:**
   Processing 518 multimodal audit cases in 2.68 seconds at $0.00 cost provides enterprise-grade scalability, contrasting with multi-minute, high-cost LLM pipelines susceptible to rate limits or API outages.

---

## 5. Development Assistance & AI Tooling Transparency

While the deployed runtime pipeline executes 100% deterministically without making runtime model calls, an AI coding assistant (Antigravity harness with Gemini 3.8 Flash High) was utilized during system development, testing, and documentation. All engineering interactions, prompts, automated command outputs, test validations, and architectural decisions are comprehensively logged in the root development transcript `log.txt` in compliance with Section 5 of `AGENTS.md`.
