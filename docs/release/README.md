# Release Documentation Bundle

This folder contains the APCS-style release documentation that Agent 4 ingests
during CI runs. The CI workflow (`.github/workflows/ci.yml`) calls
`scripts/eval/run_ci_analysis.py`, which merges this content with the diff /
commit evidence collected from the runner before producing a recommendation.

The bundle here is **the bundle that describes `challenge-app` itself**: the
agents, the backend, the frontend, the CI bridge and the deployment chart.
Agent 4 evaluates release readiness of the same project that produced the
pipeline run.

## Files

- `APCS_Requirements.txt` — requirement master list (REQ-CHA-*). Hard,
  recommended and nice-to-have requirements covering agents, CI integration,
  dashboard, deployment and traceability.
- `APCS_Test_Procedure.txt` — pre-promotion test cases (TC-CHA-*). Each test
  case traces back to one or more requirements.
- `APCS_Module_Version_Inventory.txt` — module/version inventory for the
  candidate build, plus a short rationale for each version bump.
- `APCS_Emails.txt` — narrative correspondence (release announcements,
  retest outcomes, DevOps notes) used to detect open issues and informal
  approvals/holds.
- `APCS_VDD.txt` — Version Description Document stub (filled in fully only
  at release time).

## Traceability

The traceability between REQ-CHA-* and TC-CHA-* is also encoded in the
`traceability_matrix.csv` consumed by Agent 5, alongside the
`requirements_master.csv`, `test_cases_master.csv`, `test_execution_results.csv`
and `defect_register.csv` files. Agent 5 raises HOLD when a requirement has no
linked test case, when a test case has no execution evidence, or when a defect
linked to the candidate is still open.

## How to update for a new release

1. Bump the candidate version inside every `APCS_*.txt` header.
2. Append the new requirements/test cases (or update existing ones).
3. Update `APCS_Module_Version_Inventory.txt` with the new module versions.
4. Refresh `APCS_Emails.txt` with the latest correspondence.
5. Sync the Phase 5 CSVs in `datasets/apcs_bundles/.../phase5/` so that the
   traceability matrix matches the new REQ/TC pair set.
6. Commit. The next CI run reads the new content automatically.

The CI script tolerates missing files — only those present are merged into the
Agent 4 evidence bundle.
