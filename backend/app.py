from __future__ import annotations

import base64
import binascii
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_CORE_ROOT = REPO_ROOT.parent / "challange_hitachi"

# Make the repo root importable so copied core packages can be imported directly.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent4.lc_pipeline import (  # noqa: E402
    Agent4LCError,
    LCPipelineConfig as Agent4PipelineConfig,
    LangChainAgent4Pipeline,
)
from agent5.lc_pipeline import (  # noqa: E402
    Agent5LCError,
    LCPipelineConfig as Agent5PipelineConfig,
    LangChainAgent5Pipeline,
)
from brain import (  # noqa: E402
    BrainOrchestrator,
    BrainOrchestratorError,
    BrainRunRequest,
    DependencyPolicy,
    StageDependency,
    StageRegistry,
    build_agent4_stage,
    build_agent5_stage,
    build_default_stage_order,
)

AgentKind = Literal["agent4", "agent5"]
SourceAdapterKind = Literal["auto", "structured_dataset", "apcs_doc_bundle"]

CUSTOM_SET_ROOT = REPO_ROOT / "Dataset" / "Test_Sets"
CUSTOM_SET_MANIFEST_NAME = "custom_set.json"
ENV_PATH = REPO_ROOT / ".env"

AGENT4_STRUCTURED_REQUIRED = {
    "requirements_master.csv",
    "release_calendar.csv",
}
AGENT4_STRUCTURED_OPTIONAL = {
    "phase4_modules_versions.csv",
    "modules_versions.csv",
}
AGENT5_REQUIRED = {
    "requirements_master.csv",
    "test_cases_master.csv",
    "traceability_matrix.csv",
    "test_execution_results.csv",
    "defect_register.csv",
}
AGENT5_CALENDAR_CANDIDATES = {
    "phase5_release_calendar.csv",
    "release_calendar.csv",
}

AGENT_METADATA: Dict[str, Dict[str, str]] = {
    "agent4": {
        "id": "agent4",
        "slug": "release_readiness_analyst",
        "display_name": "Release Readiness Analyst",
        "legacy_name": "Agent 4",
        "phase": "Phase 4",
        "description": (
            "Assesses DEV-to-TEST promotion readiness from APCS operational "
            "and documentary evidence."
        ),
    },
    "agent5": {
        "id": "agent5",
        "slug": "test_evidence_analyst",
        "display_name": "Test Evidence Analyst",
        "legacy_name": "Agent 5",
        "phase": "Phase 5",
        "description": (
            "Assesses Phase 5 test readiness, defects, and continuity closure "
            "after Phase 4."
        ),
    },
}

AGENT_KIND_ALIASES = {
    "agent4": "agent4",
    "agent_4": "agent4",
    "release_readiness_analyst": "agent4",
    "release_readiness": "agent4",
    "release_analyst": "agent4",
    "agent5": "agent5",
    "agent_5": "agent5",
    "test_evidence_analyst": "agent5",
    "test_evidence": "agent5",
    "evidence_analyst": "agent5",
}

AGENT_RUNTIME_CONFIG: Dict[str, Dict[str, Any]] = {
    "agent4": {
        "error_label": "Agent4",
        "response_agent": "agent4_langchain_backend",
        "labels_file": "phase4_decision_labels.csv",
    },
    "agent5": {
        "error_label": "Agent5",
        "response_agent": "agent5_langchain_backend",
        "labels_file": "phase5_decision_labels.csv",
    },
}


def _strip_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        env_key = key.strip()
        if not env_key or env_key in os.environ:
            continue
        os.environ[env_key] = _strip_env_value(value)


def _optional_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or default


def _openrouter_headers(api_key: str) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    referer = _optional_env("OPENROUTER_HTTP_REFERER")
    title = _optional_env("OPENROUTER_APP_TITLE")
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers


def _build_llm_generate() -> Optional[Any]:
    api_key = _optional_env("OPENROUTER_API_KEY")
    if not api_key:
        return None

    base_url = _optional_env(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions"
    )
    model = _optional_env("OPENROUTER_MODEL", "openai/gpt-oss-20b:free")
    timeout_seconds = float(_optional_env("OPENROUTER_TIMEOUT_SECONDS", "45") or "45")
    max_tokens = int(_optional_env("OPENROUTER_MAX_TOKENS", "700") or "700")
    temperature = float(_optional_env("OPENROUTER_TEMPERATURE", "0.2") or "0.2")
    headers = _openrouter_headers(api_key)

    def _generate(prompt: str) -> str:
        body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are refining deterministic release-readiness explanations. "
                        "Return only valid JSON matching the requested schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = urllib_request.Request(
            base_url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                "OpenRouter request failed with status "
                f"{exc.code}: {detail[:400]}"
            ) from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"OpenRouter connection failed: {exc.reason}") from exc

        choices = payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenRouter returned no choices.")

        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            joined = "".join(text_parts).strip()
            if joined:
                return joined

        raise RuntimeError("OpenRouter returned an unsupported response format.")

    return _generate


_load_dotenv(ENV_PATH)
LLM_GENERATE = _build_llm_generate()


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _normalize_agent_kind(value: Any) -> AgentKind:
    normalized = _normalize_identifier(str(value or ""))
    canonical = AGENT_KIND_ALIASES.get(normalized)
    if canonical not in AGENT_METADATA:
        valid = ", ".join(sorted(AGENT_KIND_ALIASES))
        raise ValueError(f"Unsupported agent identifier: {value!r}. Valid values: {valid}")
    return canonical  # type: ignore[return-value]


class CustomSetDocument(BaseModel):
    name: str
    text: Optional[str] = None
    content_base64: Optional[str] = None
    content_type: Optional[str] = None

    @model_validator(mode="after")
    def validate_content(self) -> "CustomSetDocument":
        if self.text is None and not self.content_base64:
            raise ValueError("Each document must include text or content_base64")
        return self


class CustomSetCreateRequest(BaseModel):
    label: str
    documents: List[CustomSetDocument]


class CustomSetDeleteResponse(BaseModel):
    ok: bool
    id: str


class AgentInspectRequest(BaseModel):
    agent: AgentKind
    dataset_root: str = Field(
        ..., description="Dataset root, absolute path or path relative to the repo root."
    )
    source_adapter_kind: Optional[SourceAdapterKind] = "auto"

    @field_validator("agent", mode="before")
    @classmethod
    def normalize_agent(cls, value: Any) -> AgentKind:
        return _normalize_agent_kind(value)


class AgentRunRequest(BaseModel):
    agent: AgentKind
    dataset_root: str = Field(
        ..., description="Dataset root, absolute path or path relative to the repo root."
    )
    documents: Optional[List[CustomSetDocument]] = None
    custom_set_label: Optional[str] = None
    scenario_id: Optional[str] = None
    release_id: Optional[str] = None
    evaluate_all: bool = False
    check_label: bool = False
    labels_path: Optional[str] = None
    fail_on_label_mismatch: bool = False
    strict_schema: bool = False
    no_llm: bool = True
    source_adapter_kind: Optional[SourceAdapterKind] = "auto"

    @field_validator("agent", mode="before")
    @classmethod
    def normalize_agent(cls, value: Any) -> AgentKind:
        return _normalize_agent_kind(value)

    @model_validator(mode="after")
    def validate_mode(self) -> "AgentRunRequest":
        if (
            not self.evaluate_all
            and not (self.scenario_id and self.scenario_id.strip())
            and not self.documents
        ):
            raise ValueError(
                "scenario_id is required when evaluate_all is false, unless documents are provided"
            )
        return self


class AgentRunResponse(BaseModel):
    ok: bool
    mode: Literal["single", "evaluate_all"]
    payload: Dict[str, Any]
    diagnostics: Dict[str, Any]


class BrainRunRequestModel(BaseModel):
    scenario_id: str
    release_id: Optional[str] = None

    agent4_scenario_id: Optional[str] = None
    agent5_scenario_id: Optional[str] = None
    agent4_release_id: Optional[str] = None
    agent5_release_id: Optional[str] = None

    agent4_dataset_root: str = "synthetic_data/v1"
    agent5_dataset_root: str = "synthetic_data/phase5/v1"
    agent4_source_adapter_kind: Optional[SourceAdapterKind] = None

    agent4_use_llm_summary: bool = False
    agent5_use_llm_summary: bool = False
    agent4_strict_schema: bool = False
    agent5_strict_schema: bool = False

    allow_agent5_after_agent4_hold: bool = False

    @model_validator(mode="after")
    def validate_scenario_id(self) -> "BrainRunRequestModel":
        if not self.scenario_id.strip():
            raise ValueError("scenario_id cannot be empty")
        return self


class BrainRunResponse(BaseModel):
    ok: bool
    payload: Dict[str, Any]


def _candidate_roots() -> List[Path]:
    roots = [REPO_ROOT]
    if LEGACY_CORE_ROOT.exists():
        roots.append(LEGACY_CORE_ROOT)
    roots.append(REPO_ROOT.parent)
    unique: List[Path] = []
    seen = set()
    for root in roots:
        resolved = root.resolve()
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def _root_aliases() -> Dict[str, Path]:
    aliases = {
        REPO_ROOT.name.lower(): REPO_ROOT,
        "challenge-app": REPO_ROOT,
        "challenge_app": REPO_ROOT,
    }
    if LEGACY_CORE_ROOT.exists():
        aliases[LEGACY_CORE_ROOT.name.lower()] = LEGACY_CORE_ROOT
        aliases["challange_hitachi"] = LEGACY_CORE_ROOT
    return aliases


def _resolve_repo_path(path_value: str) -> Path:
    raw = str(path_value or "").strip()
    if not raw:
        return REPO_ROOT

    path = Path(raw)
    if path.is_absolute():
        return path.resolve()

    aliases = _root_aliases()
    parts = list(path.parts)
    if parts:
        alias_root = aliases.get(parts[0].lower())
        if alias_root is not None:
            relative = Path(*parts[1:]) if len(parts) > 1 else Path(".")
            return (alias_root / relative).resolve()

    for root in _candidate_roots():
        candidate = (root / path).resolve()
        if candidate.exists():
            return candidate

    return (REPO_ROOT / path).resolve()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "custom_set"


def _custom_set_folder_name(label: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"SET_CUSTOM_{_slugify(label)}_{timestamp}"


def _custom_set_manifest_path(folder: Path) -> Path:
    return folder / CUSTOM_SET_MANIFEST_NAME


def _normalize_uploaded_filename(name: str, index: int) -> str:
    filename = Path(name).name.strip()
    if not filename:
        filename = f"document-{index + 1}.txt"
    return filename


def _write_document_content(file_path: Path, document: CustomSetDocument) -> bool:
    if document.content_base64:
        try:
            payload = base64.b64decode(document.content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid base64 payload for document: {document.name}",
            ) from exc
        file_path.write_bytes(payload)
        return True

    file_path.write_text(document.text or "", encoding="utf-8")
    return False


def _materialize_documents(documents: Sequence[CustomSetDocument], label: str) -> Path:
    temp_dir = Path(
        tempfile.mkdtemp(prefix=f"hitachi-{_slugify(label or 'custom-set')}-", dir=str(REPO_ROOT))
    )
    for index, document in enumerate(documents):
        file_name = _normalize_uploaded_filename(document.name, index)
        _write_document_content(temp_dir / file_name, document)
    return temp_dir


def _infer_custom_set_backend(folder_name: str, file_names: Sequence[str]) -> Dict[str, Any]:
    normalized_names = {Path(name).name for name in file_names}
    backend: Dict[str, Any] = {}

    if AGENT4_STRUCTURED_REQUIRED.issubset(normalized_names) and (
        normalized_names & AGENT4_STRUCTURED_OPTIONAL
    ):
        backend["agent4"] = {
            "datasetRoot": f"challenge-app/Dataset/Test_Sets/{folder_name}",
            "sourceAdapterKind": "structured_dataset",
        }
    elif any(name.startswith("APCS_") for name in normalized_names):
        backend["agent4"] = {
            "datasetRoot": f"challenge-app/Dataset/Test_Sets/{folder_name}",
            "sourceAdapterKind": "apcs_doc_bundle",
        }

    if AGENT5_REQUIRED.issubset(normalized_names) and (
        normalized_names & AGENT5_CALENDAR_CANDIDATES
    ):
        backend["agent5"] = {
            "datasetRoot": f"challenge-app/Dataset/Test_Sets/{folder_name}",
        }

    return backend


def _read_custom_set(folder: Path) -> Optional[Dict[str, Any]]:
    manifest_path = _custom_set_manifest_path(folder)
    if not manifest_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    documents: List[Dict[str, Any]] = []
    for item in manifest.get("documents", []):
        if not isinstance(item, dict):
            continue
        file_name = str(item.get("fileName") or item.get("name") or "").strip()
        if not file_name:
            continue
        file_path = folder / file_name
        if not file_path.exists():
            continue
        is_binary = bool(item.get("binary"))
        text = ""
        if not is_binary:
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                is_binary = True

        documents.append(
            {
                "name": str(item.get("name") or file_name),
                "filePath": f"Dataset/Test_Sets/{folder.name}/{file_name}",
                "text": text,
                "isBinary": is_binary,
                "contentType": item.get("contentType"),
                "contentBase64": (
                    base64.b64encode(file_path.read_bytes()).decode("ascii")
                    if is_binary
                    else None
                ),
            }
        )

    return {
        "id": folder.name,
        "label": str(manifest.get("label") or folder.name),
        "source": "custom",
        "persisted": True,
        "createdAtUtc": manifest.get("createdAtUtc"),
        "documents": documents,
        "backend": manifest.get("backend"),
    }


def _list_custom_sets() -> List[Dict[str, Any]]:
    sets_by_id: Dict[str, Dict[str, Any]] = {}
    if CUSTOM_SET_ROOT.exists():
        for folder in sorted(CUSTOM_SET_ROOT.iterdir()):
            if not folder.is_dir():
                continue
            loaded = _read_custom_set(folder)
            if loaded:
                sets_by_id[loaded["id"]] = loaded

    return [sets_by_id[key] for key in sorted(sets_by_id)]


def _create_custom_set(req: CustomSetCreateRequest) -> Dict[str, Any]:
    label = req.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Set label is required")
    if not req.documents:
        raise HTTPException(status_code=400, detail="At least one document is required")

    CUSTOM_SET_ROOT.mkdir(parents=True, exist_ok=True)
    folder = CUSTOM_SET_ROOT / _custom_set_folder_name(label)
    folder.mkdir(parents=True, exist_ok=False)

    manifest_documents: List[Dict[str, Any]] = []
    file_names: List[str] = []
    for index, document in enumerate(req.documents):
        file_name = _normalize_uploaded_filename(document.name, index)
        file_path = folder / file_name
        is_binary = _write_document_content(file_path, document)
        file_names.append(file_name)
        manifest_documents.append(
            {
                "name": document.name,
                "fileName": file_name,
                "binary": is_binary,
                "contentType": document.content_type,
            }
        )

    manifest = {
        "id": folder.name,
        "label": label,
        "source": "custom",
        "createdAtUtc": datetime.now(timezone.utc).isoformat(),
        "documents": manifest_documents,
        "backend": _infer_custom_set_backend(folder.name, file_names),
    }
    _custom_set_manifest_path(folder).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = _read_custom_set(folder)
    if not loaded:
        raise HTTPException(status_code=500, detail="Unable to persist custom set")
    return loaded


def _find_custom_set_folder(set_id: str) -> Optional[Path]:
    candidate = CUSTOM_SET_ROOT / set_id
    return candidate if candidate.exists() and candidate.is_dir() else None


def _delete_custom_set(set_id: str) -> None:
    folder = _find_custom_set_folder(set_id)
    if folder is None:
        raise HTTPException(status_code=404, detail=f"Custom set not found: {set_id}")
    shutil.rmtree(folder)


def _labels_path(
    dataset_root: Path,
    custom_labels_path: Optional[str],
    default_file_name: str,
) -> Path:
    if custom_labels_path:
        custom = _resolve_repo_path(custom_labels_path)
        if custom.is_dir():
            return custom / default_file_name
        return custom
    return dataset_root / default_file_name


def _safe_schema_valid(payload: Dict[str, Any]) -> bool:
    return bool(payload.get("schema_validation", {}).get("valid", False))


def _label_mismatch_exists(payload: Dict[str, Any], evaluate_all: bool) -> bool:
    if evaluate_all:
        rows = payload.get("rows", [])
        return any(isinstance(row, dict) and row.get("match") is False for row in rows)

    evaluation = payload.get("evaluation", {})
    if not isinstance(evaluation, dict):
        return False
    return bool(evaluation.get("label_check_performed") and evaluation.get("match") is False)


def _schema_error_exists(payload: Dict[str, Any], evaluate_all: bool) -> bool:
    if evaluate_all:
        predictions = payload.get("predictions", [])
        return any(
            isinstance(item, dict)
            and not bool(item.get("schema_validation", {}).get("valid", False))
            for item in predictions
        )
    return not _safe_schema_valid(payload)


def _resolve_agent4_source_adapter_kind(value: Optional[str]) -> Optional[str]:
    if value in (None, "", "auto"):
        return None
    return value


def _resolve_single_scenario(
    scenarios: Sequence[Dict[str, Any]],
    requested_scenario_id: Optional[str],
    requested_release_id: Optional[str],
    *,
    agent_name: str,
) -> Tuple[str, Optional[str]]:
    if requested_scenario_id and requested_scenario_id.strip():
        return requested_scenario_id.strip(), requested_release_id

    if len(scenarios) == 1:
        row = scenarios[0]
        scenario_id = str(row.get("scenario_id") or "").strip()
        if not scenario_id:
            raise HTTPException(
                status_code=400,
                detail=f"{agent_name} dataset exposes one scenario but it has no scenario_id",
            )
        release_id = requested_release_id
        if release_id is None:
            candidate = str(row.get("release_id") or "").strip()
            release_id = candidate or None
        return scenario_id, release_id

    if not scenarios:
        raise HTTPException(
            status_code=400,
            detail=f"scenario_id is required for {agent_name}: dataset exposes no discoverable scenarios",
        )

    raise HTTPException(
        status_code=400,
        detail=(
            f"scenario_id is required for {agent_name}: "
            f"dataset exposes {len(scenarios)} scenarios"
        ),
    )


def _pipeline_dataset_error(agent_name: str, dataset_root: Path, missing_required: Sequence[str]) -> None:
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{agent_name} dataset missing required files: "
                + ", ".join(str(item) for item in missing_required)
            ),
        )
    if not dataset_root.exists():
        raise HTTPException(status_code=400, detail=f"Dataset root not found: {dataset_root}")


def _build_agent_pipeline(
    *,
    agent: AgentKind,
    dataset_root: Path,
    use_llm_summary: bool,
    strict_schema: bool,
    source_adapter_kind: Optional[SourceAdapterKind],
    llm_generate: Optional[Any],
) -> Any:
    if agent == "agent4":
        return LangChainAgent4Pipeline(
            config=Agent4PipelineConfig(
                dataset_root=str(dataset_root),
                source_adapter_kind=_resolve_agent4_source_adapter_kind(source_adapter_kind),
                use_llm_summary=use_llm_summary,
                strict_schema=strict_schema,
            ),
            llm_generate=llm_generate,
        )

    return LangChainAgent5Pipeline(
        config=Agent5PipelineConfig(
            dataset_root=str(dataset_root),
            use_llm_summary=use_llm_summary,
            strict_schema=strict_schema,
        ),
        llm_generate=llm_generate,
    )


def _run_agent(req: AgentRunRequest) -> Dict[str, Any]:
    temp_dataset_root: Optional[Path] = None
    dataset_root = _resolve_repo_path(req.dataset_root)
    if req.documents:
        temp_dataset_root = _materialize_documents(
            req.documents,
            req.custom_set_label or req.dataset_root,
        )
        dataset_root = temp_dataset_root

    try:
        runtime = AGENT_RUNTIME_CONFIG[req.agent]
        pipeline = _build_agent_pipeline(
            agent=req.agent,
            dataset_root=dataset_root,
            use_llm_summary=not req.no_llm,
            strict_schema=bool(req.strict_schema),
            source_adapter_kind=req.source_adapter_kind,
            llm_generate=LLM_GENERATE,
        )
        validation = pipeline.validate_dataset()
        missing_required = validation.get("missing_required", [])
        if not validation.get("exists", False) or missing_required:
            _pipeline_dataset_error(runtime["error_label"], dataset_root, missing_required)

        scenarios = pipeline.list_scenarios()

        if req.evaluate_all:
            predictions = pipeline.assess_all_scenarios()
            total = len(predictions)
            schema_valid_count = sum(1 for p in predictions if _safe_schema_valid(p))
            schema_validity_rate = (schema_valid_count / total) if total else 0.0

            payload: Dict[str, Any] = {
                "agent": runtime["response_agent"],
                "dataset_root": req.dataset_root or str(dataset_root),
                "mode": "evaluate_all",
                "available_scenarios": scenarios,
                "summary": {
                    "total_scenarios": total,
                    "schema_validity_rate": round(schema_validity_rate, 4),
                },
                "predictions": predictions,
            }

            if req.check_label:
                labels_path = _labels_path(
                    dataset_root,
                    req.labels_path,
                    runtime["labels_file"],
                )
                evaluation = pipeline.evaluate_against_labels(
                    predictions=predictions,
                    labels_csv_path=str(labels_path),
                )
                payload["evaluation"] = evaluation
                payload["rows"] = evaluation.get("rows", [])
                payload["summary"].update(
                    {
                        "evaluated_scenarios": evaluation.get("evaluated_scenarios", 0),
                        "missing_predictions": evaluation.get("missing_predictions", 0),
                        "matched": evaluation.get("matched", 0),
                        "accuracy": evaluation.get("accuracy", 0.0),
                        "false_go": evaluation.get("false_go", 0),
                        "false_hold": evaluation.get("false_hold", 0),
                        "false_go_rate": evaluation.get("false_go_rate", 0.0),
                        "false_hold_rate": evaluation.get("false_hold_rate", 0.0),
                    }
                )

            return payload

        scenario_id, release_id = _resolve_single_scenario(
            scenarios,
            req.scenario_id,
            req.release_id,
            agent_name=req.agent,
        )
        payload = pipeline.assess_scenario(scenario_id=scenario_id, release_id=release_id)
        payload["dataset_root"] = req.dataset_root or str(dataset_root)

        if req.check_label:
            labels_path = _labels_path(
                dataset_root,
                req.labels_path,
                runtime["labels_file"],
            )
            evaluation = pipeline.evaluate_against_labels(
                predictions=[payload],
                labels_csv_path=str(labels_path),
            )
            row = evaluation.get("rows", [{}])[0] if evaluation.get("rows") else {}
            payload["evaluation"] = {
                "label_check_performed": True,
                "expected_decision": row.get("expected_decision"),
                "actual_decision": row.get("predicted_decision"),
                "match": row.get("match"),
            }

        return payload
    finally:
        if temp_dataset_root is not None:
            shutil.rmtree(temp_dataset_root, ignore_errors=True)


def _validate_agent(req: AgentInspectRequest) -> Dict[str, Any]:
    dataset_root = _resolve_repo_path(req.dataset_root)

    pipeline = _build_agent_pipeline(
        agent=req.agent,
        dataset_root=dataset_root,
        use_llm_summary=False,
        strict_schema=False,
        source_adapter_kind=req.source_adapter_kind,
        llm_generate=None,
    )

    payload = pipeline.validate_dataset()
    payload["resolved_dataset_root"] = str(dataset_root)
    payload["requested_dataset_root"] = req.dataset_root
    return payload


def _list_agent_scenarios(req: AgentInspectRequest) -> Dict[str, Any]:
    dataset_root = _resolve_repo_path(req.dataset_root)

    pipeline = _build_agent_pipeline(
        agent=req.agent,
        dataset_root=dataset_root,
        use_llm_summary=False,
        strict_schema=False,
        source_adapter_kind=req.source_adapter_kind,
        llm_generate=None,
    )

    validation = pipeline.validate_dataset()
    if not validation.get("exists", False):
        raise HTTPException(status_code=400, detail=f"Dataset root not found: {dataset_root}")

    missing_required = validation.get("missing_required", [])
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail="Dataset missing required files: {0}".format(
                ", ".join(str(item) for item in missing_required)
            ),
        )

    return {
        "agent": req.agent,
        "requested_dataset_root": req.dataset_root,
        "resolved_dataset_root": str(dataset_root),
        "items": pipeline.list_scenarios(),
    }


def _brain_registry(req: BrainRunRequestModel) -> Tuple[StageRegistry, Tuple[str, ...]]:
    registry = StageRegistry()

    agent4_dataset_root = str(_resolve_repo_path(req.agent4_dataset_root))
    agent5_dataset_root = str(_resolve_repo_path(req.agent5_dataset_root))

    agent4_stage = build_agent4_stage(
        dataset_root=agent4_dataset_root,
        source_adapter_kind=_resolve_agent4_source_adapter_kind(req.agent4_source_adapter_kind),
        use_llm_summary=bool(req.agent4_use_llm_summary),
        strict_schema=bool(req.agent4_strict_schema),
        stage_name="agent4",
        depends_on=(),
        enabled=True,
        metadata={"managed_by": "challenge_app_backend"},
        llm_generate=LLM_GENERATE,
    )

    agent5_stage = build_agent5_stage(
        dataset_root=agent5_dataset_root,
        use_llm_summary=bool(req.agent5_use_llm_summary),
        strict_schema=bool(req.agent5_strict_schema),
        stage_name="agent5",
        depends_on=(
            StageDependency(
                stage_name="agent4",
                required=True,
                policy=DependencyPolicy.REQUIRE_GO,
            ),
        ),
        enabled=True,
        metadata={"managed_by": "challenge_app_backend"},
        require_agent4_handoff=True,
        expected_agent4_stage_name="agent4",
        llm_generate=LLM_GENERATE,
    )

    registry.register(agent4_stage)
    registry.register(agent5_stage)
    return registry, build_default_stage_order()


def _brain_stage_inputs(req: BrainRunRequestModel) -> Dict[str, Dict[str, Any]]:
    stage_inputs: Dict[str, Dict[str, Any]] = {
        "agent4": {},
        "agent5": {"require_agent4_handoff": True},
    }

    if req.agent4_scenario_id:
        stage_inputs["agent4"]["scenario_id"] = req.agent4_scenario_id.strip()
    if req.agent5_scenario_id:
        stage_inputs["agent5"]["scenario_id"] = req.agent5_scenario_id.strip()

    if req.agent4_release_id is not None:
        value = req.agent4_release_id.strip()
        stage_inputs["agent4"]["release_id"] = value or None
    if req.agent5_release_id is not None:
        value = req.agent5_release_id.strip()
        stage_inputs["agent5"]["release_id"] = value or None

    return stage_inputs


def _run_brain(req: BrainRunRequestModel) -> Dict[str, Any]:
    registry, stage_order = _brain_registry(req)
    orchestrator = BrainOrchestrator(registry=registry, stage_order=stage_order)
    request = BrainRunRequest(
        scenario_id=req.scenario_id.strip(),
        release_id=req.release_id.strip() if req.release_id else None,
        stage_inputs=_brain_stage_inputs(req),
        options={
            "allow_agent5_after_agent4_hold": bool(req.allow_agent5_after_agent4_hold),
        },
        metadata={
            "runner": "challenge-app/backend/app.py",
            "agent4_dataset_root": str(_resolve_repo_path(req.agent4_dataset_root)),
            "agent5_dataset_root": str(_resolve_repo_path(req.agent5_dataset_root)),
        },
    )
    report = orchestrator.run(request)
    return report.to_dict()


app = FastAPI(title="Challenge App Core Backend", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "repo_root": str(REPO_ROOT),
        "legacy_core_root": str(LEGACY_CORE_ROOT) if LEGACY_CORE_ROOT.exists() else None,
        "capabilities": ["agent4", "agent5", "brain", "custom-sets"],
        "llm": {
            "provider": "openrouter",
            "configured": LLM_GENERATE is not None,
            "model": _optional_env("OPENROUTER_MODEL", "openai/gpt-oss-20b:free"),
        },
        "analysts": list(AGENT_METADATA.values()),
    }


@app.get("/datasets/custom-sets")
def list_custom_sets() -> Dict[str, Any]:
    return {"items": _list_custom_sets()}


@app.post("/datasets/custom-sets")
def create_custom_set(req: CustomSetCreateRequest) -> Dict[str, Any]:
    return _create_custom_set(req)


@app.delete("/datasets/custom-sets/{set_id}", response_model=CustomSetDeleteResponse)
def delete_custom_set(set_id: str) -> CustomSetDeleteResponse:
    _delete_custom_set(set_id)
    return CustomSetDeleteResponse(ok=True, id=set_id)


@app.post("/agents/validate")
def validate_agent_dataset(req: AgentInspectRequest) -> Dict[str, Any]:
    try:
        return _validate_agent(req)
    except (Agent4LCError, Agent5LCError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/agents/scenarios")
def list_agent_scenarios(req: AgentInspectRequest) -> Dict[str, Any]:
    try:
        return _list_agent_scenarios(req)
    except (Agent4LCError, Agent5LCError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/agents/options")
def agent_options() -> Dict[str, Any]:
    return {
        "agent4": {
            **AGENT_METADATA["agent4"],
            "supports": [
                "scenario-id",
                "dataset-root",
                "release-id",
                "evaluate-all",
                "check-label",
                "labels-path",
                "fail-on-label-mismatch",
                "strict-schema",
                "no-llm",
                "source-adapter-kind",
                "validate-dataset",
                "list-scenarios",
            ],
            "source_adapter_kinds": ["auto", "structured_dataset", "apcs_doc_bundle"],
            "aliases": ["agent4", "Agent 4", "Release Readiness Analyst"],
            "examples": [
                "synthetic_data/v1",
                "synthetic_data/v2",
                "challenge-app/Dataset/Test_Sets/SET_GO_STABLE_v1.1.2",
            ],
        },
        "agent5": {
            **AGENT_METADATA["agent5"],
            "supports": [
                "scenario-id",
                "dataset-root",
                "release-id",
                "evaluate-all",
                "check-label",
                "labels-path",
                "fail-on-label-mismatch",
                "strict-schema",
                "no-llm",
                "validate-dataset",
                "list-scenarios",
            ],
            "aliases": ["agent5", "Agent 5", "Test Evidence Analyst"],
            "examples": [
                "synthetic_data/phase5/v1",
                "synthetic_data/phase5/v2",
            ],
        },
    }


@app.post("/agents/run", response_model=AgentRunResponse)
def run_agent(req: AgentRunRequest) -> AgentRunResponse:
    try:
        payload = _run_agent(req)
    except HTTPException:
        raise
    except (Agent4LCError, Agent5LCError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    mode: Literal["single", "evaluate_all"] = "evaluate_all" if req.evaluate_all else "single"

    diagnostics = {
        "strict_schema_enabled": req.strict_schema,
        "check_label_enabled": req.check_label,
        "fail_on_label_mismatch_enabled": req.fail_on_label_mismatch,
        "schema_error_detected": _schema_error_exists(payload, req.evaluate_all),
        "label_mismatch_detected": _label_mismatch_exists(payload, req.evaluate_all),
    }

    if req.strict_schema and diagnostics["schema_error_detected"]:
        raise HTTPException(status_code=422, detail="Schema validation failed")

    if req.fail_on_label_mismatch and diagnostics["label_mismatch_detected"]:
        raise HTTPException(status_code=409, detail="Label mismatch detected")

    return AgentRunResponse(ok=True, mode=mode, payload=payload, diagnostics=diagnostics)


@app.get("/brain/options")
def brain_options() -> Dict[str, Any]:
    return {
        "stage_order": list(build_default_stage_order()),
        "stages": {
            "agent4": AGENT_METADATA["agent4"],
            "agent5": AGENT_METADATA["agent5"],
        },
        "supports": [
            "scenario-id",
            "release-id",
            "agent4-scenario-id",
            "agent5-scenario-id",
            "agent4-release-id",
            "agent5-release-id",
            "agent4-dataset-root",
            "agent5-dataset-root",
            "agent4-source-adapter-kind",
            "agent4-use-llm-summary",
            "agent5-use-llm-summary",
            "agent4-strict-schema",
            "agent5-strict-schema",
            "allow-agent5-after-agent4-hold",
        ],
        "default_policy": {
            "agent5_dependency": (
                "Test Evidence Analyst runs only after Release Readiness Analyst "
                "finishes with decision GO"
            ),
            "override_option": "allow_agent5_after_agent4_hold",
        },
    }


@app.post("/brain/run", response_model=BrainRunResponse)
def run_brain(req: BrainRunRequestModel) -> BrainRunResponse:
    try:
        payload = _run_brain(req)
    except HTTPException:
        raise
    except BrainOrchestratorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return BrainRunResponse(ok=True, payload=payload)
