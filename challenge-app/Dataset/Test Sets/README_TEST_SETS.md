# APCS Test Sets (New)

This folder contains additional APCS-style document bundles for manual and automated tests.
Each set includes the following files in TXT format:
- APCS_Emails_v1.0.txt
- APCS_Requirements_v1.0.txt
- APCS_Module_Version_Inventory_v1.0.txt
- APCS_Test_Procedure_v1.0.txt
- APCS_VDD_v1.0.txt
- APCS_Inconsistencies_map_v1.0.txt

Suggested expected outcomes:
- SET_GO_STABLE_v1.1.2: GO (no unresolved blockers, aligned versions, pass re-tests)
- SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2: HOLD (runtime issue still open, re-test not completed)
- SET_HOLD_A4_CONTINUITY_v1.1.2: HOLD (continuity blocker from Agent 4 not explicitly closed)

General pipeline note:
- Agent 4 APCS adapter supports document bundles (TXT/DOCX names above).
- Agent 5 primary pipeline uses structured CSV datasets under synthetic_data/phase5/v1 and v2.
