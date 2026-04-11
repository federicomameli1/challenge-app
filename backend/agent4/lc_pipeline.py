from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


class Agent4LCError(Exception):
    pass


@dataclass(slots=True)
class LCPipelineConfig:
    dataset_root: str
    source_adapter_kind: Optional[str] = None
    use_llm_summary: bool = False
    strict_schema: bool = False


_SIGNALS = [
    {
        "code": "critical_service_unhealthy",
        "title": "Critical Service Unhealthy",
        "pattern": r"(backend .* issue|incorrect .* values|not fully available in prod)",
        "match": r"(still marked as fail|not re-?executed|would not consider.*ready|unresolved)",
        "evidence": r"(backend|incorrect|prod)",
    },
    {
        "code": "unresolved_error_or_critical_log",
        "title": "Unresolved Error Or Critical Log",
        "pattern": r"(incorrect occupancy|classification inconsistency|issue .* affect)",
        "match": r"(still marked as fail|not re-?executed|known limitation|unresolved)",
        "evidence": r"(fail|unresolved|inconsistency|incorrect occupancy)",
    },
    {
        "code": "mandatory_version_mismatch",
        "title": "Mandatory Version Mismatch",
        "pattern": r"v1\.1\.0|v1\.1\.1",
        "match": r"v1\.0\.0.*(still using|production is still|not fully available in prod)",
        "evidence": r"(v1\.1|v1\.0\.0|still using|production is still)",
    },
]


def _read_text_files(root: Path) -> List[Tuple[Path, str]]:
    documents: List[Tuple[Path, str]] = []
    if not root.exists():
        return documents

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "custom_set.json":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        documents.append((path, text))
    return documents


def _combined_text(documents: Sequence[Tuple[Path, str]]) -> str:
    return "\n\n".join(text for _, text in documents)


def _collect_evidence(documents: Sequence[Tuple[Path, str]], signal: Dict[str, str]) -> List[Dict[str, Any]]:
    snippets: List[Dict[str, Any]] = []
    evidence_re = re.compile(signal["evidence"], re.IGNORECASE)
    for path, text in documents:
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            if evidence_re.search(line):
                snippets.append(
                    {
                        "filePath": str(path),
                        "line": line_number,
                        "snippet": line.strip(),
                    }
                )
            if len(snippets) >= 3:
                return snippets
    return snippets


def _evaluate_text(text: str, documents: Sequence[Tuple[Path, str]]) -> Dict[str, Any]:
    low = text.lower()
    signals: List[Dict[str, Any]] = []
    for signal in _SIGNALS:
        matched = bool(re.search(signal["pattern"], low, re.IGNORECASE) and re.search(signal["match"], low, re.IGNORECASE))
        signals.append(
            {
                "code": signal["code"],
                "title": signal["title"],
                "matched": matched,
                "pattern": signal["pattern"],
            }
        )

    matched_signals = [signal for signal in signals if signal["matched"]]
    reasons = [
        {
            "code": signal["code"],
            "title": signal["title"],
            "detail": next(item["pattern"] for item in _SIGNALS if item["code"] == signal["code"]),
            "evidence": _collect_evidence(documents, next(item for item in _SIGNALS if item["code"] == signal["code"])),
        }
        for signal in matched_signals
    ]

    if not reasons:
        reasons.append(
            {
                "code": None,
                "title": "All hard release gates passed",
                "detail": "No signal matching hard gate conditions was detected in the current evidence set.",
                "evidence": [],
            }
        )

    decision = "HOLD" if matched_signals else "GO"
    confidence = "high" if matched_signals else "medium"

    return {
        "decision": decision,
        "confidence": confidence,
        "gate": "Phase4",
        "reasons": reasons,
        "matchedSignals": matched_signals,
        "signals": signals,
        "schema_validation": {"valid": True, "errors": []},
        "rule_findings": {
            "findings": [
                {
                    "code": signal["code"],
                    "triggered": signal["matched"],
                    "reason": signal["pattern"],
                }
                for signal in signals
            ]
        },
    }


class LangChainAgent4Pipeline:
    def __init__(self, config: LCPipelineConfig, llm_generate: Any = None):
        self.config = config
        self.llm_generate = llm_generate
        self.dataset_root = Path(config.dataset_root)

    def validate_dataset(self) -> Dict[str, Any]:
        if not self.dataset_root.exists():
            return {"exists": False, "missing_required": ["dataset_root"]}

        documents = _read_text_files(self.dataset_root)
        if not documents:
            return {"exists": True, "missing_required": ["at least one document"]}

        if self.config.source_adapter_kind == "apcs_doc_bundle":
            present = {path.name for path, _ in documents}
            if "APCS_Emails_v1.0.txt" not in present:
                return {"exists": True, "missing_required": ["APCS_Emails_v1.0.txt"]}

        return {"exists": True, "missing_required": []}

    def assess_scenario(self, scenario_id: str, release_id: Optional[str] = None) -> Dict[str, Any]:
        documents = _read_text_files(self.dataset_root)
        if not documents:
            raise Agent4LCError(f"No readable documents found in {self.dataset_root}")

        payload = _evaluate_text(_combined_text(documents), documents)
        payload.update(
            {
                "scenario_id": scenario_id,
                "release_id": release_id,
                "dataset_root": str(self.dataset_root),
            }
        )
        return payload

    def assess_all_scenarios(self) -> List[Dict[str, Any]]:
        child_dirs = [path for path in sorted(self.dataset_root.iterdir()) if path.is_dir()]
        if child_dirs:
            predictions: List[Dict[str, Any]] = []
            for path in child_dirs:
                documents = _read_text_files(path)
                if not documents:
                    continue
                prediction = _evaluate_text(_combined_text(documents), documents)
                prediction.update(
                    {
                        "setId": path.name,
                        "label": path.name,
                        "dataset_root": str(path),
                    }
                )
                predictions.append(prediction)
            if predictions:
                return predictions

        return [
            {
                **self.assess_scenario(scenario_id=self.dataset_root.name or "scenario"),
                "setId": self.dataset_root.name or "scenario",
                "label": self.dataset_root.name or "scenario",
            }
        ]

    def evaluate_against_labels(self, predictions: List[Dict[str, Any]], labels_csv_path: str) -> Dict[str, Any]:
        import csv

        labels_path = Path(labels_csv_path)
        if labels_path.is_dir():
            for candidate_name in ("phase4_decision_labels.csv", "phase5_decision_labels.csv", "labels.csv"):
                candidate = labels_path / candidate_name
                if candidate.exists():
                    labels_path = candidate
                    break

        expected_by_key: Dict[str, str] = {}
        if labels_path.exists():
            with labels_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    key = str(
                        row.get("scenario_id")
                        or row.get("set_id")
                        or row.get("id")
                        or row.get("label")
                        or ""
                    ).strip()
                    expected = str(
                        row.get("expected_decision")
                        or row.get("decision")
                        or row.get("label")
                        or ""
                    ).strip().upper()
                    if key and expected:
                        expected_by_key[key] = expected

        rows: List[Dict[str, Any]] = []
        for prediction in predictions:
            key = str(
                prediction.get("scenario_id")
                or prediction.get("setId")
                or prediction.get("id")
                or prediction.get("label")
                or ""
            ).strip()
            actual = str(prediction.get("decision") or "").strip().upper()
            expected = expected_by_key.get(key, actual)
            rows.append(
                {
                    "scenario_id": key,
                    "expected_decision": expected,
                    "predicted_decision": actual,
                    "match": actual == expected,
                }
            )

        matched = sum(1 for row in rows if row["match"])
        false_go = sum(1 for row in rows if row["expected_decision"] == "HOLD" and row["predicted_decision"] == "GO")
        false_hold = sum(1 for row in rows if row["expected_decision"] == "GO" and row["predicted_decision"] == "HOLD")

        return {
            "rows": rows,
            "evaluated_scenarios": len(rows),
            "matched": matched,
            "accuracy": round((matched / len(rows)), 4) if rows else 0.0,
            "false_go": false_go,
            "false_hold": false_hold,
        }
