
---
name: evidence-forensics
description: Investigate deletion-audit datasets and local evidence files. Use when tracing customer identities, historical identifiers, surviving personal data, synchronization or restoration paths, policy requirements, and evidence-backed deletion conclusions.
---

# Evidence Forensics

## Purpose

Investigate the supplied evidence for the Northstar Shop deletion-audit challenge. Build a defensible, evidence-backed account of what happened to a person's data and what remains to be done.

## When to use this skill

Use this skill when:
- Investigating a deletion request.
- Discovering how a person is identified across systems.
- Tracing historical identifiers or account changes.
- Examining CSV, JSON, SQL, log, PDF, image, or other supplied evidence.
- Identifying data copies and processes that could recreate deleted data.
- Determining which policy rules apply to a record.

## Required workflow

### 1. Inspect before concluding

- Read the problem statement and the repository's instructions.
- Identify the supplied dataset, evidence manifest, deletion requests, and deletion rules.
- Inspect the actual schemas and available file types before designing parsers.
- Discover the expected output schema before deciding what the investigation must produce.
- Do not assume a file, field, identifier, or evidence source exists until verified.

### 2. Establish the subject's identity

- Begin with the identifiers supplied in the deletion request.
- Search the evidence for current and historical identifiers, aliases, email addresses, account IDs, and relevant mappings.
- Link records only when supported by evidence.
- Distinguish confirmed identity matches from ambiguous or possible matches.
- Do not merge two people solely because they share a name or another weak identifier.

### 3. Build an evidence inventory

For every relevant finding, capture:
- The evidence ID or other traceable source reference.
- The system or storage location.
- The record or object identifier, when available.
- The relevant subject identifier.
- The observed state and timestamp, when available.
- The policy rule that applies.
- Whether the finding is confirmed, uncertain, or contradicted by other evidence.

Use only source references that actually exist in the supplied corpus.

### 4. Reconstruct the deletion timeline

- Establish the sequence of the deletion request, processing events, synchronization, imports, exports, backups, and restoration events.
- Respect the request's audit timestamp and the timestamps of individual records.
- Distinguish historical existence from data that still exists at the audit time.
- Do not treat an old log entry as proof that data currently exists.
- Do not treat a dashboard's "Complete" status as proof that every relevant copy was handled.

### 5. Trace data copies and resurrection paths

Investigate relevant locations such as:
- Primary and secondary databases.
- Support tickets and attachments.
- Search indexes and caches.
- Analytics exports and logs.
- Archives and backups.
- Synchronization, import, and restoration pipelines.

For each suspected surviving copy, determine the required treatment under the supplied deletion rules.

For each process that might recreate data, establish whether it is active or otherwise capable of causing resurrection, and identify the evidence supporting that conclusion.

Do not claim that all copies or resurrection paths have been checked unless the available evidence supports that claim.

### 6. Apply policy and retention requirements

- Read and follow the actual deletion rules.
- Distinguish deletion, redaction, and anonymization.
- Preserve records that must be retained.
- Remove or transform identifiers in retained records only as required by policy.
- Do not recommend deleting legally or operationally required records without checking the applicable rule.
- If a rule is ambiguous, explain the ambiguity rather than inventing a policy.

### 7. Produce actionable findings

For each relevant record or process, describe:
- What was found.
- Why it matters.
- The evidence supporting it.
- The required treatment or verification.
- Any dependency that determines the order of remediation.

Order remediation so that data cannot simply be recreated by an active synchronization, import, or restore process.

### 8. Report uncertainty honestly

- Separate observed facts, inferences, and assumptions.
- Identify missing or conflicting evidence.
- Never invent evidence IDs, record contents, timestamps, or system states.
- Never claim a deletion is complete merely because no matching record was found in a limited search.
- Return findings in a structured form that the main application can process.

## Constraints

- Do not hardcode answers for particular request IDs or filenames.
- Do not modify the supplied evidence corpus.
- Do not execute destructive deletion operations against real systems.
- Do not use external services to transmit customer data.
- Do not treat the output of another AI model as verified evidence.
- Follow the repository's output schema and existing architecture.

## Definition of success

A successful investigation provides traceable evidence, justified identity matches, a time-aware reconstruction, policy-compliant treatment of retained records, identified resurrection risks, and ordered remediation or verification steps.
