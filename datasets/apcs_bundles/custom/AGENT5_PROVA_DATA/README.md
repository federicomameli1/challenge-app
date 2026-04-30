# Agent 5 Test Data for Custom Set "prova"

Questa cartella contiene dati strutturati CSV per testare **Agent 5** (LangChain structured dataset analyzer).

## File disponibili

### `test_scenarios.csv`
Contiene 10 scenari di test con le seguenti colonne:
- **scenario_id**: Identificativo univoco dello scenario
- **release_id**: Versione del rilascio (v2.x.x)
- **test_procedure_status**: Stato della procedura di test (PASSED, FAILED, IN_PROGRESS)
- **requirements_status**: Stato dei requirements (COMPLETE, INCOMPLETE, REVIEW)
- **version_consistency**: Coerenza versione (CONSISTENT, INCONSISTENT)
- **critical_issues**: Numero di issue critiche
- **minor_issues**: Numero di issue minori
- **test_coverage**: Percentuale di copertura test (0-100)
- **environment_ready**: Ambiente pronto (TRUE, FALSE)

### `phase5_decision_labels.csv`
Contiene le **decisioni attese** per ogni scenario (GO o HOLD) - usato da Agent 5 per validare le predizioni.

## Come caricare questi dati nel custom set

1. Quando crei un nuovo custom set nel dashboard
2. Carica i documenti text (emails, requirements, ecc.)
3. **Inoltre**, carica questi file CSV:
   - `test_scenarios.csv`
   - `phase5_decision_labels.csv`
4. Il backend aggiungerà automaticamente i dati strutturati al custom set
5. Ora puoi eseguire sia **Agent 4** (analisi documenti) che **Agent 5** (analisi dati strutturati)

## Nota

- Questa cartella è un **template** di dati strutturati
- Puoi modificare il file `test_scenarios.csv` aggiungendo più scenari se vuoi
- I scenari riportati (PROVA_001-PROVA_010) hanno decisioni realistiche basate sui parametri
