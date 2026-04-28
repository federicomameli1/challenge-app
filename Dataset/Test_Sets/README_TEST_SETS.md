# APCS Test Sets (New)

This folder contains additional APCS-style document bundles for manual and automated tests.
Each set includes:
- APCS_Emails_v1.0.txt
- APCS_Requirements_v1.0.txt
- APCS_Module_Version_Inventory_v1.0.txt
- APCS_Test_Procedure_v1.0.txt
- APCS_VDD_v1.0.txt

Expected outcomes:
- SET_GO_STABLE_v1.1.2: GO
- SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2: HOLD
- SET_HOLD_A4_CONTINUITY_v1.1.2: HOLD
- SET_RANDOM_APCS_v1.0: HOLD

## Premium / high-complexity sets (v1.2.0)

These bundles are richer than the baseline ones: longer email threads with
multiple stakeholders, traceability between requirements / tests / VDD,
explicit references to ticket IDs and closure records, and the optional
`APCS_Inconsistencies_map_v1.0.txt` file (supported by the Agent 4 adapter
but not present in the baseline sets).

- **SET_GO_PREMIUM_v1.2.0** — GO. Clean release candidate v1.2.0 with full
  47/47 mandatory PASS, explicit closure of the previous-gate blocker
  (BLK-2026-017 → CLOSURE-EVID-2026-017), no version drift across
  DEV/INT/STG, and converging sign-off from PM/QA/CM.
- **SET_HOLD_VERSION_DRIFT_v1.2.0** — HOLD. Backend planned at v1.1.0 but
  deployed at v1.0.0 in the production-equivalent environment. Designed
  to exercise the adapter's `has_version_mismatch` heuristic and to
  invalidate the evidence admissibility (REQ-APCS-202).
- **SET_HOLD_COMPOUND_BLOCKERS_v1.2.0** — HOLD. Four overlapping issues:
  unresolved T-APCS-004 (incorrect occupancy under rapid updates), no
  continuity closure for BLK-2026-017, integration-layer fix existing
  only as a test-bench workaround (no new official build), and
  T-APCS-006 in pending validation. Designed to exercise multiple
  heuristics simultaneously: `has_open_blocker_email`,
  `has_unresolved_runtime`, `has_unhealthy_service`,
  `has_unmet_conditional`.

Each premium set contains:
- APCS_Emails_v1.0.txt (multi-thread, multi-author)
- APCS_Requirements_v1.0.txt (functional + governance + traceability)
- APCS_Module_Version_Inventory_v1.0.txt (per-environment alignment table)
- APCS_Test_Procedure_v1.0.txt (sectioned: pre-conditions / regression /
  governance / summary)
- APCS_VDD_v1.0.txt (executive summary + scope + result + continuity +
  risks + recommendation)
- APCS_Inconsistencies_map_v1.0.txt (cross-document consistency checks)

General pipeline note:
- Agent 4 APCS adapter supports document bundles (TXT/DOCX names above).
- Agent 5 primary pipeline uses structured CSV datasets under synthetic_data/phase5/v1 and v2.
