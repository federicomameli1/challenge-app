# Release Documentation Bundle

This folder contains the APCS-style release documentation that Agent 4 ingests
during CI runs. The CI workflow (`.github/workflows/ci.yml`) calls
`scripts/eval/run_ci_analysis.py`, which merges this content with the diff/commit
evidence collected from the runner before producing a recommendation.

## Files

- `APCS_Emails.txt` — narrative correspondence (release announcements, retest
  outcomes, blocker discussions) used to detect open issues and informal
  approvals/holds.
- `APCS_Requirements.txt` — requirements traceability tags. Agent 4 cross-checks
  these against the change set.
- `APCS_Test_Procedure.txt` — pre-promotion test procedure outcomes.
- `APCS_Module_Version_Inventory.txt` — module/version inventory for the
  candidate build.
- `APCS_VDD.txt` — Version Description Document stub (filled in fully only at
  release time).

## How to update for a new release

1. Update `APCS_Emails.txt` with the latest release-readiness emails.
2. Update `APCS_Test_Procedure.txt` with the actual pre-test outcomes.
3. Bump the version inside `APCS_Module_Version_Inventory.txt`.
4. Commit. The next CI run will read the new content automatically.

The CI script tolerates missing files — only those present are merged into the
Agent 4 evidence bundle.
