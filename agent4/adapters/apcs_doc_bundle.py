"""
APCS colleague-style document bundle adapter.

This adapter converts a document-oriented APCS evidence bundle into the
`RawInputBundle` contract already used by Agent 4, so policy/explanation logic
can remain unchanged.

Supported source layout (single folder):
- APCS_Emails_v1.0.txt                      (optional)
- APCS_Requirements_v1.0.docx or .txt       (optional but recommended)
- APCS_Module_Version_Inventory_v1.0.docx or .txt (optional but recommended)
- APCS_Inconsistencies_map_v1.0.docx/.txt   (optional)

Design goals:
- Minimal integration impact with existing Agent 4
- Deterministic adaptation
- Graceful handling of partial/missing fields
- Keep output in canonical schema for normalization/policy layers
"""

from __future__ import annotations

import html
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..ingestion import IngestionError, RawInputBundle, SourceRef


@dataclass(frozen=True)
class APCSAdapterConfig:
    source_root: str | Path
    scenario_id: str = "APCS-S4-001"
    release_id: str = "APCS-REL-1.1.0"
    environment: str = "DEV"
    strict_mode: bool = False


class APCSDocBundleAdapter:
    """
    Adapter for APCS colleague-style document bundles.

    Public API mirrors the ingestion shape used by Agent 4:
    - validate_source()
    - list_scenarios()
    - ingest(...)

    Initialization supports either:
    - APCSAdapterConfig instance
    - source root path (str | Path), which uses default config values
    """

    EMAIL_FILE = "APCS_Emails_v1.0.txt"
    REQUIREMENTS_CANDIDATES = (
        "APCS_Requirements_v1.0.docx",
        "APCS_Requirements_v1.0.txt",
    )
    VERSIONS_CANDIDATES = (
        "APCS_Module_Version_Inventory_v1.0.docx",
        "APCS_Module_Version_Inventory_v1.0.txt",
    )
    TEST_PROCEDURE_CANDIDATES = (
        "APCS_Test_Procedure_v1.0.docx",
        "APCS_Test_Procedure_v1.0.txt",
    )
    VDD_CANDIDATES = (
        "APCS_VDD_v1.0.docx",
        "APCS_VDD_v1.0.txt",
    )
    INCONSISTENCIES_CANDIDATES = (
        "APCS_Inconsistencies_map_v1.0.docx",
        "APCS_Inconsistencies_map_v1.0.txt",
    )

    def __init__(self, config: APCSAdapterConfig | str | Path) -> None:
        if isinstance(config, APCSAdapterConfig):
            resolved_config = config
        else:
            resolved_config = APCSAdapterConfig(source_root=config)

        self.config = resolved_config
        self.source_root = Path(resolved_config.source_root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_source(self) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "source_root": str(self.source_root),
            "exists": self.source_root.exists(),
            "missing_required": [],
            "missing_optional": [],
            "present_optional": [],
            "notes": [],
        }

        if not self.source_root.exists():
            report["missing_optional"].extend(
                [self.EMAIL_FILE]
                + list(self.REQUIREMENTS_CANDIDATES)
                + list(self.VERSIONS_CANDIDATES)
                + list(self.TEST_PROCEDURE_CANDIDATES)
                + list(self.VDD_CANDIDATES)
                + list(self.INCONSISTENCIES_CANDIDATES)
            )
            return report

        email_path = self.source_root / self.EMAIL_FILE
        if not email_path.exists():
            report["missing_optional"].append(self.EMAIL_FILE)
            report["notes"].append(
                "email thread not found; adapter will run with non-email evidence only"
            )

        for candidate in (
            list(self.REQUIREMENTS_CANDIDATES)
            + list(self.VERSIONS_CANDIDATES)
            + list(self.TEST_PROCEDURE_CANDIDATES)
            + list(self.VDD_CANDIDATES)
            + list(self.INCONSISTENCIES_CANDIDATES)
        ):
            p = self.source_root / candidate
            if p.exists():
                report["present_optional"].append(candidate)
            else:
                report["missing_optional"].append(candidate)

        if not any(
            (self.source_root / c).exists() for c in self.REQUIREMENTS_CANDIDATES
        ):
            report["notes"].append(
                "requirements document not found; fallback inferred requirements will be used"
            )
        if not any((self.source_root / c).exists() for c in self.VERSIONS_CANDIDATES):
            report["notes"].append(
                "module version inventory not found; fallback inferred versions will be used"
            )
        if not any(
            (self.source_root / c).exists() for c in self.TEST_PROCEDURE_CANDIDATES
        ):
            report["notes"].append(
                "test procedure document not found; test-flow evidence may be reduced"
            )
        if not any((self.source_root / c).exists() for c in self.VDD_CANDIDATES):
            report["notes"].append(
                "VDD document not found; validation summary evidence may be reduced"
            )

        return report

    def list_scenarios(self) -> List[Dict[str, str]]:
        # APCS bundle is currently treated as one aggregated scenario.
        sid, rid, env = self._resolve_identity(
            scenario_id=None,
            release_id=None,
        )
        return [
            {
                "scenario_id": sid,
                "release_id": rid,
                "environment": env,
                "target_test_promotion": "",
            }
        ]

    def _infer_identity_from_filenames(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Infer scenario and release identity from available APCS file names.

        Example:
            APCS_Requirements_v1.0.docx -> scenario_id=APCS-S4-001, release_id=APCS-REL-1.0.0
        """
        files = sorted(p.name for p in self.source_root.glob("APCS_*.*"))
        if not files:
            return None, None

        first = files[0]
        prefix_match = re.match(r"^([A-Za-z0-9]+)_", first)
        prefix = prefix_match.group(1).upper() if prefix_match else "APCS"

        version_match = re.search(
            r"_v(\d+)(?:\.(\d+))?(?:\.(\d+))?", first, re.IGNORECASE
        )
        if version_match:
            major = version_match.group(1) or "1"
            minor = version_match.group(2) or "0"
            patch = version_match.group(3) or "0"
            inferred_release = f"{prefix}-REL-{major}.{minor}.{patch}"
        else:
            inferred_release = None

        inferred_scenario = f"{prefix}-S4-001"
        return inferred_scenario, inferred_release

    def _resolve_identity(
        self,
        scenario_id: Optional[str],
        release_id: Optional[str],
    ) -> Tuple[str, str, str]:
        inferred_sid, inferred_rid = self._infer_identity_from_filenames()

        default_sid = (self.config.scenario_id or "").strip() or "APCS-S4-001"
        default_rid = (self.config.release_id or "").strip() or "APCS-REL-1.1.0"

        sid = (scenario_id or "").strip() or default_sid
        rid = (release_id or "").strip() or default_rid

        # In partial-source mode, default identity is replaced by file-derived identity
        # when available.
        if sid == default_sid and inferred_sid:
            sid = inferred_sid
        if rid == default_rid and inferred_rid:
            rid = inferred_rid

        env = self.config.environment.strip().upper() or "DEV"
        return sid, rid, env

    def ingest(
        self, scenario_id: Optional[str] = None, release_id: Optional[str] = None
    ) -> RawInputBundle:
        report = self.validate_source()
        if not report["exists"]:
            raise IngestionError(f"APCS source root not found: {self.source_root}")

        sid, rid, env = self._resolve_identity(
            scenario_id=scenario_id,
            release_id=release_id,
        )

        email_path = self.source_root / self.EMAIL_FILE
        req_path = self._first_existing(self.REQUIREMENTS_CANDIDATES)
        ver_path = self._first_existing(self.VERSIONS_CANDIDATES)
        test_path = self._first_existing(self.TEST_PROCEDURE_CANDIDATES)
        vdd_path = self._first_existing(self.VDD_CANDIDATES)
        inc_path = self._first_existing(self.INCONSISTENCIES_CANDIDATES)

        if (
            not email_path.exists()
            and req_path is None
            and ver_path is None
            and test_path is None
            and vdd_path is None
            and inc_path is None
        ):
            raise IngestionError(
                "APCS source does not contain ingestible evidence files "
                "(email, requirements, versions, test procedure, VDD, or inconsistencies)."
            )

        email_text = self._read_text(email_path) if email_path.exists() else ""
        req_text = self._read_maybe_docx(req_path) if req_path is not None else ""
        ver_text = self._read_maybe_docx(ver_path) if ver_path is not None else ""
        test_text = self._read_maybe_docx(test_path) if test_path is not None else ""
        vdd_text = self._read_maybe_docx(vdd_path) if vdd_path is not None else ""
        inc_text = self._read_maybe_docx(inc_path) if inc_path is not None else ""

        source_markers = {
            "has_email_source": bool(email_path.exists()),
            "has_requirements_source": bool(req_path is not None),
            "has_versions_source": bool(ver_path is not None),
            "has_test_procedure_source": bool(test_path is not None),
            "has_vdd_source": bool(vdd_path is not None),
            "has_inconsistencies_source": bool(inc_path is not None),
        }

        combined_text = "\n".join(
            [email_text, req_text, ver_text, test_text, vdd_text, inc_text]
        )
        signals = self._extract_signals(combined_text, source_markers=source_markers)

        requirements = self._build_requirements(
            req_text=req_text,
            email_text=email_text,
            test_text=test_text,
            vdd_text=vdd_text,
        )
        module_versions = self._build_module_versions(
            sid=sid,
            rid=rid,
            env=env,
            version_text=ver_text,
            email_text=email_text,
            signals=signals,
        )
        release_metadata = self._build_release_metadata(sid=sid, rid=rid, env=env)
        deploy_log = self._build_synthetic_deploy_log(rid=rid, sid=sid, signals=signals)
        health_report = self._build_synthetic_health_report(
            sid=sid, rid=rid, env=env, signals=signals
        )

        refs = {
            "requirements": SourceRef(
                source_type="docx_or_text",
                path=str(req_path) if req_path else "inferred:requirements",
            ),
            "release_metadata": SourceRef(
                source_type="inferred",
                path=f"inferred:release_metadata:{sid}",
            ),
            "module_versions": SourceRef(
                source_type="docx_or_text",
                path=str(ver_path) if ver_path else "inferred:module_versions",
            ),
            "test_procedure": SourceRef(
                source_type="docx_or_text",
                path=str(test_path) if test_path else "inferred:no_test_procedure",
            ),
            "vdd_summary": SourceRef(
                source_type="docx_or_text",
                path=str(vdd_path) if vdd_path else "inferred:no_vdd",
            ),
            "deploy_log": SourceRef(
                source_type="inferred_log",
                path=f"inferred:deploy_log:{sid}",
            ),
            "service_health_report": SourceRef(
                source_type="inferred_json",
                path=f"inferred:service_health:{sid}",
            ),
            "blocker_email_thread": SourceRef(
                source_type="txt_or_inferred",
                path=str(email_path) if email_path.exists() else "inferred:no_email",
            ),
        }

        return RawInputBundle(
            scenario_id=sid,
            release_id=rid,
            environment=env,
            requirements=requirements,
            module_versions=module_versions,
            release_metadata=release_metadata,
            deploy_log=deploy_log,
            service_health_report=health_report,
            blocker_email_thread=email_text,
            source_references=refs,
        )

    # ------------------------------------------------------------------
    # Internal helpers - filesystem/readers
    # ------------------------------------------------------------------

    def _first_existing(self, candidates: Tuple[str, ...]) -> Optional[Path]:
        for name in candidates:
            p = self.source_root / name
            if p.exists():
                return p
        return None

    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")

    def _read_maybe_docx(self, path: Path) -> str:
        if path.suffix.lower() != ".docx":
            return self._read_text(path)
        return self._extract_docx_text(path)

    def _extract_docx_text(self, path: Path) -> str:
        """
        Lightweight DOCX text extraction without external dependencies.
        """
        try:
            with zipfile.ZipFile(path, "r") as zf:
                xml_bytes = zf.read("word/document.xml")
            xml_text = xml_bytes.decode("utf-8", errors="replace")
        except Exception as exc:  # pragma: no cover - defensive path
            if self.config.strict_mode:
                raise IngestionError(f"Failed to read DOCX {path}: {exc}") from exc
            return ""

        # Convert Word paragraph/table boundaries into newlines then strip tags.
        text = xml_text
        text = re.sub(r"</w:p>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</w:tr>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<w:tab[^>]*/>", "\t", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text

    # ------------------------------------------------------------------
    # Internal helpers - signal extraction
    # ------------------------------------------------------------------

    def _extract_signals(
        self,
        text: str,
        source_markers: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, bool]:
        low = text.lower()
        source_markers = source_markers or {}

        has_email_source = bool(source_markers.get("has_email_source", False))
        has_requirements_source = bool(
            source_markers.get("has_requirements_source", False)
        )
        has_versions_source = bool(source_markers.get("has_versions_source", False))
        has_test_procedure_source = bool(
            source_markers.get("has_test_procedure_source", False)
        )
        has_vdd_source = bool(source_markers.get("has_vdd_source", False))
        has_inconsistencies_source = bool(
            source_markers.get("has_inconsistencies_source", False)
        )

        fail_mentions = bool(re.search(r"\bfail(?:ed|ure)?\b", low))
        unresolved_phrases = bool(
            re.search(
                r"(not re-?executed|still marked as fail|not fully ready|not consider(?:ed)? .* ready|known limitation|did not yet generate a new official version)",
                low,
            )
        )
        blocker_phrases = bool(
            re.search(
                r"(blocking|blocker|issue still|unresolved|would not consider.*ready)",
                low,
            )
        )

        open_blocker = fail_mentions and (unresolved_phrases or blocker_phrases)
        unmet_conditional = bool(
            re.search(
                r"(confirm when .* new version|re-?executed .* yet|pending validation|for validation)",
                low,
            )
        )

        # Heuristic mismatch: evidence references v1.1.0 and v1.0.0 simultaneously.
        version_mismatch = bool(
            re.search(r"\bv1\.1\.0\b", low)
            and re.search(r"\bv1\.0\.0\b", low)
            and re.search(
                r"(production is still|still using|not fully available in prod)", low
            )
        )

        # Runtime severity synthesis from strong fail/unresolved signals.
        unresolved_runtime = bool(
            re.search(
                r"(incorrect occupancy|classification inconsistency|fail .* test|issue .* affect)",
                low,
            )
            and open_blocker
        )

        unhealthy_service = bool(
            re.search(
                r"(backend .* issue|not fully available in prod|incorrect .* values)",
                low,
            )
            and open_blocker
        )

        return {
            "has_open_blocker_email": open_blocker,
            "has_unmet_conditional": unmet_conditional,
            "has_version_mismatch": version_mismatch,
            "has_unresolved_runtime": unresolved_runtime,
            "has_unhealthy_service": unhealthy_service,
            "has_email_source": has_email_source,
            "has_requirements_source": has_requirements_source,
            "has_versions_source": has_versions_source,
            "has_test_procedure_source": has_test_procedure_source,
            "has_vdd_source": has_vdd_source,
            "has_inconsistencies_source": has_inconsistencies_source,
            "has_requirement_like_source": (
                has_requirements_source or has_test_procedure_source or has_vdd_source
            ),
            "inferred_from_partial_sources": not (
                has_email_source
                and has_requirements_source
                and has_versions_source
                and has_test_procedure_source
                and has_vdd_source
                and has_inconsistencies_source
            ),
            "missing_primary_source_email": not has_email_source,
        }

    # ------------------------------------------------------------------
    # Internal helpers - canonical artifact builders
    # ------------------------------------------------------------------

    def _build_release_metadata(self, sid: str, rid: str, env: str) -> Dict[str, str]:
        return {
            "release_id": rid,
            "scenario_id": sid,
            "environment": env,
            "dev_window_start": "",
            "dev_window_end": "",
            "target_test_promotion": "",
        }

    def _build_requirements(
        self,
        req_text: str,
        email_text: str,
        test_text: str = "",
        vdd_text: str = "",
    ) -> List[Dict[str, str]]:
        """
        Build normalized requirement rows from available doc texts, with deterministic fallback.
        """
        rows: List[Dict[str, str]] = []

        source_text = "\n".join(
            part for part in [req_text, test_text, vdd_text] if part and part.strip()
        )
        lines = [ln.strip() for ln in source_text.splitlines() if ln.strip()]
        id_pattern = re.compile(r"\b((?:REQ|FR|R)-?\s*\d+(?:\.\d+)?)\b", re.IGNORECASE)

        inferred_count = 0
        for ln in lines:
            m = id_pattern.search(ln)
            if not m:
                continue

            req_id = m.group(1).upper().replace(" ", "")
            desc = self._clean_sentence(ln)
            module = self._module_from_text(desc)
            priority = "HIGH" if self._looks_critical(desc) else "MEDIUM"

            rows.append(
                {
                    "requirement_id": req_id,
                    "description": desc,
                    "priority": priority,
                    "module": module,
                    "mandatory_for_phase4": "true",
                }
            )
            inferred_count += 1
            if inferred_count >= 25:
                break

        # Fallback requirements if extraction was sparse.
        if len(rows) < 3:
            rows = self._fallback_requirements(
                email_text=email_text,
                req_text=req_text,
                test_text=test_text,
                vdd_text=vdd_text,
            )

        return rows

    def _fallback_requirements(
        self,
        email_text: str,
        req_text: str = "",
        test_text: str = "",
        vdd_text: str = "",
    ) -> List[Dict[str, str]]:
        context_text = "\n".join(
            part
            for part in [email_text, req_text, test_text, vdd_text]
            if part and part.strip()
        )
        low = context_text.lower()

        base = [
            {
                "requirement_id": "REQ-APCS-001",
                "description": "Backend shall compute occupancy percentage correctly under rapid passenger count updates.",
                "priority": "HIGH",
                "module": "backend",
                "mandatory_for_phase4": "true",
            },
            {
                "requirement_id": "REQ-APCS-002",
                "description": "Backend shall classify occupancy levels correctly around Light/Medium threshold boundaries.",
                "priority": "HIGH",
                "module": "backend",
                "mandatory_for_phase4": "true",
            },
            {
                "requirement_id": "REQ-APCS-003",
                "description": "Integration layer publishing shall complete within acceptable latency bounds.",
                "priority": "MEDIUM",
                "module": "integration-layer",
                "mandatory_for_phase4": "true",
            },
            {
                "requirement_id": "REQ-APCS-004",
                "description": "HMI statistics feature shall be available only when dependent backend API version is aligned.",
                "priority": "MEDIUM",
                "module": "hmi",
                "mandatory_for_phase4": "true",
            },
        ]

        # If text context indicates mocked/non-blocking integration latency,
        # lower strictness signal for integration.
        if "mocked integration layer" in low:
            base[2]["priority"] = "LOW"

        # When email is missing, adapt fallback priorities using requirement text cues.
        if not email_text.strip() and req_text.strip():
            if "threshold" not in low and "classification" not in low:
                base[1]["priority"] = "MEDIUM"
            if "integration" not in low:
                base[2]["priority"] = "LOW"
            if "hmi" not in low and "statistics" not in low:
                base[3]["mandatory_for_phase4"] = "false"

        return base

    def _build_module_versions(
        self,
        sid: str,
        rid: str,
        env: str,
        version_text: str,
        email_text: str,
        signals: Dict[str, bool],
    ) -> List[Dict[str, str]]:
        """
        Build canonical module version rows expected by Agent 4.
        """
        planned_backend = self._extract_first_version(
            version_text + "\n" + email_text, "1.1.0"
        )
        deployed_backend = (
            "1.0.0" if signals["has_version_mismatch"] else planned_backend
        )

        # Other modules keep aligned defaults unless inferred otherwise.
        planned_integration = "1.1.0"
        deployed_integration = "1.1.0"
        planned_hmi = "1.1.0"
        deployed_hmi = "1.1.0"

        rows = [
            self._version_row(
                sid=sid,
                rid=rid,
                env=env,
                module="backend",
                planned=planned_backend,
                deployed=deployed_backend,
                mandatory=True,
            ),
            self._version_row(
                sid=sid,
                rid=rid,
                env=env,
                module="integration-layer",
                planned=planned_integration,
                deployed=deployed_integration,
                mandatory=True,
            ),
            self._version_row(
                sid=sid,
                rid=rid,
                env=env,
                module="hmi",
                planned=planned_hmi,
                deployed=deployed_hmi,
                mandatory=True,
            ),
        ]
        return rows

    def _version_row(
        self,
        sid: str,
        rid: str,
        env: str,
        module: str,
        planned: str,
        deployed: str,
        mandatory: bool,
    ) -> Dict[str, str]:
        return {
            "scenario_id": sid,
            "release_id": rid,
            "environment": env,
            "module": module,
            "planned_version": planned,
            "deployed_version": deployed,
            "mandatory_for_phase4": str(mandatory).lower(),
            "version_match": str(planned == deployed).lower(),
        }

    def _build_synthetic_deploy_log(
        self, rid: str, sid: str, signals: Dict[str, bool]
    ) -> str:
        lines: List[str] = []
        lines.append(
            f"2026-03-26T10:00:00+00:00 INFO  [orchestrator] Starting deployment for {rid} ({sid})"
        )
        lines.append("2026-03-26T10:01:00+00:00 INFO  [orchestrator] Environment=DEV")
        lines.append("2026-03-26T10:02:00+00:00 INFO  [backend] Container started")
        lines.append(
            "2026-03-26T10:03:00+00:00 INFO  [integration-layer] Container started"
        )
        lines.append("2026-03-26T10:04:00+00:00 INFO  [hmi] Container started")

        has_unresolved_runtime = bool(signals.get("has_unresolved_runtime", False))
        missing_email_source = bool(signals.get("missing_primary_source_email", False))
        has_versions_source = bool(signals.get("has_versions_source", False))
        has_requirement_like_source = bool(
            signals.get("has_requirement_like_source", False)
        )
        inferred_from_partial_sources = bool(
            signals.get("inferred_from_partial_sources", False)
        )

        # Conservative policy:
        # - Missing email or version inventory means blocker/runtime state cannot be
        #   confidently closed, so emit unresolved error-like evidence.
        if has_unresolved_runtime or missing_email_source or not has_versions_source:
            if has_unresolved_runtime:
                lines.append(
                    "2026-03-26T10:05:00+00:00 ERROR [backend] Occupancy calculation inconsistency detected under rapid updates"
                )
                lines.append(
                    "2026-03-26T10:06:00+00:00 CRITICAL [backend] Validation scenario failed; unresolved test-linked runtime defect"
                )
            else:
                lines.append(
                    "2026-03-26T10:05:00+00:00 ERROR [orchestrator] Incomplete evidence set: cannot verify runtime blocker closure"
                )
                if missing_email_source:
                    lines.append(
                        "2026-03-26T10:06:00+00:00 CRITICAL [orchestrator] Missing blocker email source; unresolved communication risk"
                    )
                if not has_versions_source:
                    lines.append(
                        "2026-03-26T10:07:00+00:00 CRITICAL [backend] Missing version inventory; deployment consistency cannot be verified"
                    )

            lines.append(
                "2026-03-26T10:08:00+00:00 ERROR [orchestrator] Candidate marked unstable pending complete evidence validation"
            )
        else:
            if inferred_from_partial_sources and not has_requirement_like_source:
                lines.append(
                    "2026-03-26T10:05:00+00:00 WARN  [orchestrator] Requirement-like sources missing; proceeding with inferred baseline only"
                )
            else:
                lines.append(
                    "2026-03-26T10:05:00+00:00 WARN  [integration-layer] Intermittent delay observed in mocked environment"
                )
            lines.append(
                "2026-03-26T10:06:00+00:00 INFO  [orchestrator] Deployment completed successfully"
            )

        return "\n".join(lines) + "\n"

    def _build_synthetic_health_report(
        self, sid: str, rid: str, env: str, signals: Dict[str, bool]
    ) -> Dict[str, Any]:
        has_unhealthy_service = bool(signals.get("has_unhealthy_service", False))
        missing_email_source = bool(signals.get("missing_primary_source_email", False))
        has_versions_source = bool(signals.get("has_versions_source", False))
        has_requirement_like_source = bool(
            signals.get("has_requirement_like_source", False)
        )

        backend_status = "healthy"
        backend_reason = "ok"

        if has_unhealthy_service:
            backend_status = "unhealthy"
            backend_reason = "functional reliability concern inferred from unresolved failure evidence"
        elif missing_email_source:
            backend_status = "unhealthy"
            backend_reason = "primary blocker communication source is missing; closure state cannot be confirmed"
        elif not has_versions_source:
            backend_status = "unhealthy"
            backend_reason = "version inventory source missing; runtime compatibility cannot be verified"

        integration_status = "healthy"
        integration_reason = "ok"
        if not has_requirement_like_source:
            integration_status = "degraded"
            integration_reason = "requirement-like sources missing; functional coverage confidence reduced"

        services = [
            {
                "service": "backend",
                "status": backend_status,
                "critical": True,
                "reason": backend_reason,
            },
            {
                "service": "integration-layer",
                "status": integration_status,
                "critical": False,
                "reason": integration_reason,
            },
            {
                "service": "hmi",
                "status": "healthy",
                "critical": False,
                "reason": "ok",
            },
        ]

        overall = "healthy"
        if any(s["critical"] and s["status"] != "healthy" for s in services):
            overall = "degraded"
        elif not has_requirement_like_source:
            overall = "degraded"

        return {
            "scenario_id": sid,
            "release_id": rid,
            "environment": env,
            "generated_at": "2026-03-26T10:20:00+00:00",
            "overall_status": overall,
            "services": services,
        }

    # ------------------------------------------------------------------
    # Small parsing helpers
    # ------------------------------------------------------------------

    def _extract_first_version(self, text: str, default_value: str) -> str:
        m = re.search(r"\bv(\d+\.\d+\.\d+)\b", text, flags=re.IGNORECASE)
        if not m:
            return default_value
        return m.group(1)

    def _clean_sentence(self, value: str) -> str:
        text = re.sub(r"\s+", " ", value.strip())
        return text

    def _module_from_text(self, text: str) -> str:
        low = text.lower()
        if "backend" in low:
            return "backend"
        if "integration" in low:
            return "integration-layer"
        if "hmi" in low or "ui" in low:
            return "hmi"
        return "backend"

    def _looks_critical(self, text: str) -> bool:
        low = text.lower()
        return bool(
            re.search(
                r"(shall|must|critical|fail|error|blocking|occupancy|classification)",
                low,
            )
        )


def ingest_apcs_doc_bundle(
    source_root: str | Path,
    scenario_id: str = "APCS-S4-001",
    release_id: str = "APCS-REL-1.1.0",
    environment: str = "DEV",
    strict_mode: bool = False,
) -> RawInputBundle:
    """
    Convenience functional API.
    """
    adapter = APCSDocBundleAdapter(
        APCSAdapterConfig(
            source_root=source_root,
            scenario_id=scenario_id,
            release_id=release_id,
            environment=environment,
            strict_mode=strict_mode,
        )
    )
    return adapter.ingest(scenario_id=scenario_id, release_id=release_id)
