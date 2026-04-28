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

## Adversarial sets (v1.3.0)

Located under `Adversarial_v1.3.0/`.

These bundles are designed to **stress the analysis system**, not just
the human reader. They deliberately defeat lexical-match heuristics
(`fail` / `blocker` / `unresolved` / `production is still using` etc.)
and require cross-document, chronological or traceability reasoning to
reach the correct verdict.

- **Adversarial_v1.3.0/SET_ADV_GO_FALSE_ALARM_v1.3.0** — atteso **GO**. Le prime email del
  thread contengono parole trigger (`FAIL`, `blocker`, `unresolved`,
  `would not consider ready`) ma si riferiscono a un falso positivo
  causato da cache stale del bench, successivamente diagnosticato come
  TEA (test environment artifact) e archiviato. Il verdetto finale è
  PASS 50/50. Stress test: chronological reasoning sul thread.
- **Adversarial_v1.3.0/SET_ADV_HOLD_SILENT_DRIFT_v1.3.0** — atteso **HOLD**. Linguaggio
  uniformemente positivo, nessuna parola trigger. La tabella MVI
  dichiara `match` su tutti i moduli, ma una sezione "Runtime
  observations" della stessa MVI (e una mail Operations) documenta che
  un nodo backend riporta hash `a91f3c2` invece di `b4f2e91`. In più
  45/47 PASS senza deroga PM e ticket CM-2026-073 OPEN. Stress test:
  cross-document numeric/hash comparison.
- **Adversarial_v1.3.0/SET_ADV_HOLD_UNRESOLVED_CONFLICT_v1.3.0** — atteso **HOLD**.
  Regression 47/47 PASS. Niente defects funzionali. HOLD emerge solo
  dalla matrice di stakeholder: Operations ha emesso obiezione
  formale (rischio memoria +38%) non ritirata e il PM non ha emesso
  autorizzazione. Stress test: matrice di authorization, regola
  REQ-APCS-502, semantica del silenzio del PM.
- **Adversarial_v1.3.0/SET_ADV_HOLD_FAKE_CLOSURE_v1.3.0** — atteso **HOLD**. Regression
  47/47 PASS. La prima email dichiara `BLK-2026-017` chiuso con
  `CLOSURE-EVID-2026-031`. In realtà l'ID appartiene a `OPS-2026-031`
  (memory leak metrics-agent), ticket diverso. QA Lead rileva il
  mismatch, l'autore si auto-corregge. Stress test: traceability
  evidence↔ticket, riconoscimento di sign-off ritirato.

Punti chiave delle adversarial:
- Niente dipendenza da match lessicale per arrivare al verdetto.
- Mix IT/EN, sigle interne (`PV`, `RE-EX`, `TEA`).
- Email con autorizzazione finale del PM presente solo nei GO; nei
  HOLD il PM tace o l'autorizzazione è esplicitamente "NON EMESSA".
- Ogni HOLD è raggiungibile solo combinando informazioni da almeno
  due documenti diversi.

General pipeline note:
- Agent 4 APCS adapter supports document bundles (TXT/DOCX names above).
- Agent 5 primary pipeline uses structured CSV datasets under synthetic_data/phase5/v1 and v2.
