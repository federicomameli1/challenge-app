"""
Agent 4 orchestrator: end-to-end Phase 4 readiness pipeline.

Pipeline:
1) Ingestion of raw scenario artifacts
2) Normalization into canonical evidence bundle
3) Deterministic policy/rule evaluation (GO/HOLD)
4) Deterministic or optional LLM-assisted explanation
5) Output schema validation
6) Optional benchmark evaluation against expected labels
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from .evidence import build_traceable_reasons_and_evidence, evidence_coverage_ratio
    from .explanation import ExplanationContext, build_explanation_with_optional_llm
    from .ingestion import IngestionError, Phase4Ingestion, RawInputBundle
    from .models import validate_output_schema
    from .normalization import NormalizedEvidenceBundle, normalize_evidence_bundle
    from .policy import Phase4PolicyEngine, PolicyConfig
except ImportError:
    # Allow running this file directly (python agent4/agent.py)
    from evidence import build_traceable_reasons_and_evidence, evidence_coverage_ratio
    from explanation import ExplanationContext, build_explanation_with_optional_llm
    from ingestion import IngestionError, Phase4Ingestion, RawInputBundle
    from models import validate_output_schema
    from normalization import NormalizedEvidenceBundle, normalize_evidence_bundle
    from policy import Phase4PolicyEngine, PolicyConfig


class Agent4Error(Exception):
    """Raised for orchestrator-level execution failures."""


@dataclass(frozen=True)
class Agent4Config:
    dataset_root: str = "synthetic_data/v1"
    policy_version: str = "phase4-policy-v1"
    use_llm_summary: bool = True
    evidence_limit_per_reason: int = 5
    total_evidence_limit: int = 20


class Agent4Orchestrator:
    """
    End-to-end Agent 4 orchestration.
    """

    def __init__(
        self,
        config: Optional[Agent4Config] = None,
        llm_generate: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.config = config or Agent4Config()
        self.ingestion = Phase4Ingestion(self.config.dataset_root)
        self.policy_engine = Phase4PolicyEngine(
            config=PolicyConfig(target_environment="DEV")
        )
        self.llm_generate = llm_generate

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def validate_dataset(self) -> Dict[str, Any]:
        return self.ingestion.validate_dataset()

    def list_scenarios(self) -> List[Dict[str, str]]:
        return self.ingestion.list_scenarios()

    def assess_scenario(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
        llm_generate: Optional[Callable[[str], str]] = None,
    ) -> Dict[str, Any]:
        """
        Run full Agent 4 pipeline for one scenario and return validated output JSON.
        """
        raw = self._ingest(scenario_id=scenario_id, release_id=release_id)
        normalized = self._normalize(raw)
        findings = self.policy_engine.evaluate(normalized, environment=raw.environment)

        context = ExplanationContext(
            scenario_id=raw.scenario_id,
            release_id=raw.release_id,
            environment=raw.environment,
            findings=findings,
            non_blocking_warning=self._has_non_blocking_warning(normalized),
            evidence_conflict=self._has_evidence_conflict(normalized),
            evidence_incomplete=self._has_evidence_incomplete(raw, normalized),
            policy_version=self.config.policy_version,
        )

        llm_callable = llm_generate if llm_generate is not None else self.llm_generate
        if not self.config.use_llm_summary:
            llm_callable = None

        output_obj = build_explanation_with_optional_llm(
            context=context,
            llm_generate=llm_callable,
        )
        payload = output_obj.to_dict()

        # Strengthen traceability contract with deterministic reason/evidence mapping.
        trace_reasons, trace_evidence = build_traceable_reasons_and_evidence(
            findings=findings,
            evidence_limit_per_reason=self.config.evidence_limit_per_reason,
            total_evidence_limit=self.config.total_evidence_limit,
        )
        payload = self._merge_traceability(payload, trace_reasons, trace_evidence)

        valid, errors = validate_output_schema(payload)
        if not valid:
            raise Agent4Error(
                f"Invalid Agent 4 output schema for scenario {scenario_id}: {errors}"
            )

        return payload

    def assess_all_scenarios(
        self,
        llm_generate: Optional[Callable[[str], str]] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        scenarios = self.list_scenarios()
        for row in scenarios:
            scenario_id = row.get("scenario_id", "").strip()
            release_id = row.get("release_id", "").strip() or None
            if not scenario_id:
                continue
            result = self.assess_scenario(
                scenario_id=scenario_id,
                release_id=release_id,
                llm_generate=llm_generate,
            )
            results.append(result)
        return results

    def evaluate_against_labels(
        self,
        predictions: Optional[Sequence[Dict[str, Any]]] = None,
        labels_csv_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate Agent 4 outputs against expected GO/HOLD labels.
        """
        if predictions is None:
            predictions = self.assess_all_scenarios()

        labels_path = (
            Path(labels_csv_path)
            if labels_csv_path
            else Path(self.config.dataset_root) / "phase4_decision_labels.csv"
        )
        labels = self._read_labels(labels_path)

        pred_by_scenario: Dict[str, Dict[str, Any]] = {
            str(p.get("scenario_id", "")).strip(): p for p in predictions
        }

        total = 0
        matched = 0
        false_go = 0
        false_hold = 0
        missing_predictions = 0
        rows: List[Dict[str, Any]] = []

        for label in labels:
            scenario_id = label["scenario_id"]
            expected = label["expected_decision"]
            pred = pred_by_scenario.get(scenario_id)
            total += 1

            if pred is None:
                missing_predictions += 1
                rows.append(
                    {
                        "scenario_id": scenario_id,
                        "release_id": label["release_id"],
                        "expected_decision": expected,
                        "predicted_decision": None,
                        "match": False,
                        "note": "missing prediction",
                    }
                )
                continue

            predicted = str(pred.get("decision", "")).strip().upper()
            is_match = predicted == expected
            if is_match:
                matched += 1
            else:
                if predicted == "GO" and expected == "HOLD":
                    false_go += 1
                elif predicted == "HOLD" and expected == "GO":
                    false_hold += 1

            rows.append(
                {
                    "scenario_id": scenario_id,
                    "release_id": label["release_id"],
                    "expected_decision": expected,
                    "predicted_decision": predicted,
                    "match": is_match,
                }
            )

        accuracy = (matched / total) if total else 0.0
        evaluated = total - missing_predictions
        false_go_rate = (false_go / evaluated) if evaluated else 0.0
        false_hold_rate = (false_hold / evaluated) if evaluated else 0.0

        return {
            "dataset_root": self.config.dataset_root,
            "labels_path": str(labels_path),
            "total_scenarios": total,
            "evaluated_scenarios": evaluated,
            "missing_predictions": missing_predictions,
            "matched": matched,
            "accuracy": round(accuracy, 4),
            "false_go": false_go,
            "false_hold": false_hold,
            "false_go_rate": round(false_go_rate, 4),
            "false_hold_rate": round(false_hold_rate, 4),
            "rows": rows,
        }

    # -------------------------------------------------------------------------
    # Internal orchestration helpers
    # -------------------------------------------------------------------------

    def _ingest(self, scenario_id: str, release_id: Optional[str]) -> RawInputBundle:
        try:
            return self.ingestion.ingest(scenario_id=scenario_id, release_id=release_id)
        except IngestionError as exc:
            raise Agent4Error(f"Ingestion failed for {scenario_id}: {exc}") from exc

    def _normalize(self, raw: RawInputBundle) -> NormalizedEvidenceBundle:
        refs = raw.source_references
        requirements_source = self._source_path(
            refs, "requirements", "requirements_master.csv"
        )
        versions_source = self._source_path(
            refs, "module_versions", "phase4_modules_versions.csv"
        )
        log_source = self._source_path(
            refs, "deploy_log", f"dev_deploy_logs/{raw.scenario_id}.log"
        )
        health_source = self._source_path(
            refs,
            "service_health_report",
            f"service_health_reports/{raw.scenario_id}.json",
        )
        email_source = self._source_path(
            refs, "blocker_email_thread", f"dev_blockers_emails/{raw.scenario_id}.txt"
        )

        return normalize_evidence_bundle(
            requirements_rows=raw.requirements,
            version_rows=raw.module_versions,
            deploy_log_text=raw.deploy_log,
            health_report=raw.service_health_report,
            email_thread_text=raw.blocker_email_thread,
            requirements_source=requirements_source,
            versions_source=versions_source,
            deploy_log_source=log_source,
            health_source=health_source,
            email_source=email_source,
        )

    @staticmethod
    def _source_path(
        refs: Dict[str, Any],
        key: str,
        default_value: str,
    ) -> str:
        ref = refs.get(key)
        if ref is None:
            return default_value
        value = getattr(ref, "path", None)
        if not value:
            return default_value
        return str(value)

    @staticmethod
    def _has_non_blocking_warning(normalized: NormalizedEvidenceBundle) -> bool:
        for event in normalized.deploy_logs:
            if event.severity.upper() == "WARN" and not event.is_error_like:
                return True
        return False

    @staticmethod
    def _has_evidence_incomplete(
        raw: RawInputBundle,
        normalized: NormalizedEvidenceBundle,
    ) -> bool:
        if not raw.requirements:
            return True
        if not raw.module_versions:
            return True
        if not normalized.deploy_logs:
            return True
        if normalized.health_report is None:
            return True
        if normalized.email_thread is None:
            return True
        return False

    @staticmethod
    def _has_evidence_conflict(normalized: NormalizedEvidenceBundle) -> bool:
        """
        Lightweight conflict heuristic:
        - health report says overall healthy while any critical service is unhealthy
        - email reports OPEN and RESOLVED in contradictory way at thread level
        """
        conflict = False

        report = normalized.health_report
        if report is not None:
            critical_unhealthy = any(
                svc.critical and svc.status.strip().lower() != "healthy"
                for svc in report.services
            )
            if (
                report.overall_status.strip().lower() == "healthy"
                and critical_unhealthy
            ):
                conflict = True

        thread = normalized.email_thread
        if thread is not None:
            status = (thread.thread_status or "").upper()
            if status == "UNKNOWN" and thread.open_blocker_detected:
                conflict = True

        return conflict

    @staticmethod
    def _merge_traceability(
        payload: Dict[str, Any],
        trace_reasons: Sequence[Any],
        trace_evidence: Sequence[Any],
    ) -> Dict[str, Any]:
        """
        Ensure payload has robust evidence references without weakening LLM phrasing.
        """
        current_reasons = payload.get("reasons")
        if not isinstance(current_reasons, list) or len(current_reasons) == 0:
            payload["reasons"] = [r.to_dict() for r in trace_reasons]

        current_evidence = payload.get("evidence")
        if not isinstance(current_evidence, list) or len(current_evidence) == 0:
            payload["evidence"] = [e.to_dict() for e in trace_evidence]

        # Coverage metric is attached as auxiliary diagnostics.
        reasons_for_coverage = []
        if isinstance(payload.get("reasons"), list):
            for r in payload["reasons"]:
                ev = r.get("evidence", []) if isinstance(r, dict) else []
                reasons_for_coverage.append(type("TmpReason", (), {"evidence": ev})())

        if reasons_for_coverage:
            covered = sum(
                1 for r in reasons_for_coverage if len(getattr(r, "evidence", [])) > 0
            )
            payload["diagnostics"] = {
                "reason_evidence_coverage": round(
                    covered / len(reasons_for_coverage), 4
                )
            }

        return payload

    @staticmethod
    def _read_labels(path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            raise Agent4Error(f"Labels file not found: {path}")

        rows: List[Dict[str, str]] = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise Agent4Error(f"Labels CSV has no header row: {path}")

            required = {"scenario_id", "release_id", "expected_decision"}
            missing = required - set(reader.fieldnames)
            if missing:
                raise Agent4Error(
                    f"Labels CSV missing required columns: {', '.join(sorted(missing))}"
                )

            for row in reader:
                rows.append(
                    {
                        "scenario_id": str(row.get("scenario_id", "")).strip(),
                        "release_id": str(row.get("release_id", "")).strip(),
                        "expected_decision": str(row.get("expected_decision", ""))
                        .strip()
                        .upper(),
                    }
                )
        return rows


# -----------------------------------------------------------------------------
# CLI entry point
# -----------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Agent 4 readiness assessment.")
    parser.add_argument(
        "--dataset-root",
        default="synthetic_data/v1",
        help="Path to Phase 4 dataset root",
    )
    parser.add_argument(
        "--scenario-id",
        default=None,
        help="Scenario ID to assess (e.g., S4-001). If omitted, all scenarios are assessed.",
    )
    parser.add_argument(
        "--release-id",
        default=None,
        help="Optional release_id filter when running single scenario",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM summary layer (deterministic summary only)",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run benchmark evaluation against phase4_decision_labels.csv",
    )
    parser.add_argument(
        "--output-json", default=None, help="Optional output JSON file path"
    )
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON output"
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    config = Agent4Config(
        dataset_root=args.dataset_root,
        use_llm_summary=not args.no_llm,
    )
    agent = Agent4Orchestrator(config=config, llm_generate=None)

    if args.scenario_id:
        result = agent.assess_scenario(
            scenario_id=args.scenario_id,
            release_id=args.release_id,
        )
    else:
        predictions = agent.assess_all_scenarios()
        if args.evaluate:
            result = {
                "predictions": predictions,
                "evaluation": agent.evaluate_against_labels(predictions=predictions),
            }
        else:
            result = {"predictions": predictions}

    text = json.dumps(result, indent=2 if args.pretty else None)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        print(f"Wrote Agent 4 output to {output_path}")
    else:
        print(text)


if __name__ == "__main__":
    main()
