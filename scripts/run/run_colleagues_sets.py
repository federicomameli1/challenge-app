#!/usr/bin/env python3
"""
Run Agent 4 over the colleague test sets in
Dataset/Test_Sets/TEST_SET_COLLEAGUES.

Each set ships APCS_* documents but uses versioned suffixes
(e.g. v1.3.14) and inconsistent casing for the inconsistencies map,
so the apcs_doc_bundle adapter does not match them as-is. This
runner materializes a temp dir with canonical filenames and runs
the Agent 4 LangChain pipeline on each set.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.agent4.lc_pipeline import LCPipelineConfig, LangChainAgent4Pipeline

COLLEAGUES_ROOT = (
    PROJECT_ROOT / "datasets" / "apcs_bundles" / "colleagues"
)
OUTPUT_PATH = (
    PROJECT_ROOT / "artifacts" / "colleague_sets_agent4_report.json"
)

CANONICAL = {
    "emails": "APCS_Emails_v1.0.txt",
    "requirements": "APCS_Requirements_v1.0.txt",
    "module_versions": "APCS_Module_Version_Inventory_v1.0.txt",
    "test_procedure": "APCS_Test_Procedure_v1.0.txt",
    "vdd": "APCS_VDD_v1.0.txt",
    "inconsistencies": "APCS_Inconsistencies_map_v1.0.txt",
}

PATTERNS = [
    (re.compile(r"^APCS_Emails_", re.IGNORECASE), "emails"),
    (re.compile(r"^APCS_Requirements_", re.IGNORECASE), "requirements"),
    (
        re.compile(r"^APCS_Module_Version_Inventory_", re.IGNORECASE),
        "module_versions",
    ),
    (re.compile(r"^APCS_Test_Procedure_", re.IGNORECASE), "test_procedure"),
    (re.compile(r"^APCS_VDD_", re.IGNORECASE), "vdd"),
    (
        re.compile(r"^APCS_Inconsistencies[_-]?map_", re.IGNORECASE),
        "inconsistencies",
    ),
]


def classify(filename: str) -> Optional[str]:
    for pattern, key in PATTERNS:
        if pattern.match(filename):
            return key
    return None


def materialize_canonical(src: Path) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix=f"apcs-{src.name}-"))
    for child in src.iterdir():
        if not child.is_file():
            continue
        key = classify(child.name)
        if key is None:
            continue
        target = tmp / CANONICAL[key]
        shutil.copyfile(child, target)
    return tmp


def run_one(set_path: Path) -> Dict:
    tmp_root = materialize_canonical(set_path)
    try:
        pipeline = LangChainAgent4Pipeline(
            config=LCPipelineConfig(
                dataset_root=str(tmp_root),
                source_adapter_kind="apcs_doc_bundle",
                use_llm_summary=False,
                strict_schema=False,
            ),
            llm_generate=None,
        )
        validation = pipeline.validate_dataset()
        if not validation.get("exists", False):
            return {
                "set": set_path.name,
                "status": "error",
                "error": "dataset_root_missing",
                "validation": validation,
            }
        scenarios = pipeline.list_scenarios()
        if not scenarios:
            return {
                "set": set_path.name,
                "status": "error",
                "error": "no_scenarios",
            }
        scenario_id = scenarios[0]["scenario_id"]
        release_id = scenarios[0].get("release_id")
        prediction = pipeline.assess_scenario(
            scenario_id=scenario_id, release_id=release_id
        )
        return {
            "set": set_path.name,
            "status": "ok",
            "scenario_id": scenario_id,
            "release_id": release_id,
            "decision": prediction.get("decision"),
            "rationale": prediction.get("rationale"),
            "findings": prediction.get("findings"),
            "missing_optional": validation.get("missing_optional", []),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "set": set_path.name,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def main() -> None:
    if not COLLEAGUES_ROOT.exists():
        print(f"COLLEAGUES_ROOT not found: {COLLEAGUES_ROOT}", file=sys.stderr)
        sys.exit(1)

    sets = sorted(p for p in COLLEAGUES_ROOT.iterdir() if p.is_dir())
    results: List[Dict] = []
    for s in sets:
        print(f"running: {s.name}", file=sys.stderr, flush=True)
        results.append(run_one(s))

    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "errors": sum(1 for r in results if r["status"] != "ok"),
        "go": sum(1 for r in results if r.get("decision") == "GO"),
        "hold": sum(1 for r in results if r.get("decision") == "HOLD"),
    }

    payload = {"summary": summary, "results": results}
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(json.dumps(summary, indent=2))
    for r in results:
        decision = r.get("decision") or r.get("error")
        print(f"  - {r['set']}: {r['status']} -> {decision}")
    print(f"\nFull report: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
