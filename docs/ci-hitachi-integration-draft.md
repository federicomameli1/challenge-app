# Hitachi CI Integration

The real workflow in `.github/workflows/ci.yml` now calls Agent 4 and Agent 5 during CI.
The draft workflow under `.github/workflows/drafts/` remains as a compact reference version of the target design.

## Goal

Embed the release-readiness solution directly into GitHub Actions so the pipeline can:

- collect CI-native evidence from code, workflow, charts, and documents,
- generate a structured report before the TEST gate,
- generate a second structured report before the PROD gate,
- keep the final promotion decision in human hands between phases.

## Recommended Flow

1. `analyze-pre-test`
   Agent target: `agent4`
   Purpose: assess DEV-to-TEST readiness from the current change set.

2. `approve-test`
   Human gate implemented with a protected GitHub Environment and required reviewers.

3. `test-and-build`
   Existing test/build logic continues here.

4. `analyze-pre-prod`
   Agent target: `agent5`
   Purpose: assess readiness after tests/build and before PROD promotion.

5. `approve-prod`
   Human gate implemented with a protected GitHub Environment and required reviewers.

6. `deploy-prod`
   Existing GitOps handoff happens only after human approval.

## Evidence To Collect

### Pre-test / Agent 4

- changed source files under `src/` and `backend/`
- git diff and diff stat
- workflow files under `.github/workflows/`
- deployment/chart files under `chart/`
- `README.md`
- `WORKLOG_SUMMARY.md`
- `Dockerfile`
- dependency manifests such as `package.json` and `backend/requirements.txt`

### Pre-prod / Agent 5

- everything from pre-test that is still relevant
- test execution output
- build output
- image metadata
- the artifact emitted by pre-test analysis
- final chart/manifests that will be promoted
- optional future additions such as JUnit, coverage, lint, and deployment smoke checks

## Output Recommendation

Use three channels:

- `GITHUB_STEP_SUMMARY` as the primary user-facing report
- JSON and Markdown artifacts for audit trail
- PR comments later, only if needed

This keeps the first version simple and visible without adding too much automation noise.

## Files Used By The Integration

- `scripts/run_ci_analysis.py`
  CI runner that:
  - collects CI evidence,
  - synthesizes a temporary structured dataset for the target gate,
  - invokes Agent 4 for `pre-test`,
  - invokes Agent 5 for `pre-prod`,
  - writes:
  - `ci_report.json`
  - `ci_report.md`
  - `agent_payload.json`
  - `changed_files.txt`
  - `diff_stat.txt`

- `.github/workflows/ci.yml`
  Active workflow that now:
  - runs Agent 4 before the TEST gate,
  - pauses for human approval before the TEST stage on push/release events,
  - captures test/build outcomes as CI evidence,
  - runs Agent 5 before the PROD gate on release events,
  - pauses for human approval before PROD promotion,
  - performs the GitOps prod handoff only after approval.

- `.github/workflows/drafts/ci-hitachi-analysis-draft.yml`
  Non-active reference workflow that keeps the same overall job shape in a smaller file.

## Current Limitation

The current implementation does call the real agents, but it still uses a synthesized CI dataset.
That means the deterministic decision is real, while the CI-to-dataset mapping remains heuristic.

Right now the script is useful for:

- validating the shape of the workflow,
- validating the human approval sequence,
- validating artifact/report generation,
- validating real Agent 4 / Agent 5 execution in CI,
- validating optional LLM narration in CI.

## Configuration Checklist

1. Configure GitHub Environments:
   - `hitachi-test-approval`
   - `hitachi-prod-approval`
2. Add secrets/variables:
   - `OPENROUTER_API_KEY`
   - `OPENROUTER_MODEL` (optional)
3. Ensure GitOps settings already used by the workflow exist:
   - `GITOPS_REPO`
   - `APP_NAME`
   - `GITOPS_TOKEN`
4. Replace the synthesized CI dataset builder in `scripts/run_ci_analysis.py` with a richer CI-native adapter when you want better evidence fidelity.

## Suggested Next Implementation Step

Improve the CI adapter so it maps:

- workflow/config/code/document evidence to Agent 4 style readiness evidence,
- test/build results plus Agent 4 handoff to Agent 5 style verification evidence.

The current version already proves that the agents can be called during CI with:

- deterministic outputs,
- optional LLM summary layer,
- artifact handoff between phases,
- human approval remaining outside the agent decision.
