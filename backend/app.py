from __future__ import annotations

import json
import re
import shutil
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

# Keep the original repo parent importable for compatibility modules,
# while using the actual app root for files owned by this backend.
SUPPORT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = Path(__file__).resolve().parents[1]
if str(SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(SUPPORT_ROOT))

from .agent4.lc_pipeline import (  # noqa: E402
    Agent4LCError,
    LCPipelineConfig as Agent4PipelineConfig,
    LangChainAgent4Pipeline,
)
from .agent5.lc_pipeline import (  # noqa: E402
    Agent5LCError,
    LCPipelineConfig as Agent5PipelineConfig,
    LangChainAgent5Pipeline,
)


class AgentRunRequest(BaseModel):
    agent: Literal["agent4", "agent5"]
    dataset_root: str = Field(
        ..., description="Dataset root, absolute path or path relative to repository root."
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
    source_adapter_kind: Optional[Literal["auto", "structured_dataset", "apcs_doc_bundle"]] = "auto"

    @model_validator(mode="after")
    def validate_mode(self) -> "AgentRunRequest":
        if (
            not self.evaluate_all
            and not (self.scenario_id and self.scenario_id.strip())
            and not self.documents
        ):
            raise ValueError("scenario_id is required when evaluate_all is false")
        return self


class AgentRunResponse(BaseModel):
    ok: bool
    mode: Literal["single", "evaluate_all"]
    payload: Dict[str, Any]
    diagnostics: Dict[str, Any]


class CustomSetDocument(BaseModel):
    name: str
    text: str


class CustomSetCreateRequest(BaseModel):
    label: str
    documents: List[CustomSetDocument]


class CustomSetDeleteResponse(BaseModel):
    ok: bool
    id: str


CUSTOM_SET_ROOT = APP_ROOT / "Dataset" / "Test_Sets"
CUSTOM_SET_MANIFEST_NAME = "custom_set.json"


def _resolve_repo_path(path_value: str) -> Path:
    p = Path(path_value)
    if not p.is_absolute():
        p = (SUPPORT_ROOT / p).resolve()
    return p


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


def _materialize_documents(documents: List[CustomSetDocument], label: str) -> Path:
    temp_dir = Path(
        tempfile.mkdtemp(prefix=f"hitachi-{_slugify(label or 'custom-set')}-", dir=str(SUPPORT_ROOT))
    )
    for index, document in enumerate(documents):
        file_name = _normalize_uploaded_filename(document.name, index)
        (temp_dir / file_name).write_text(document.text, encoding="utf-8")
    return temp_dir


def _read_custom_set(folder: Path) -> Optional[Dict[str, Any]]:
    manifest_path = _custom_set_manifest_path(folder)
    if not manifest_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    documents: List[Dict[str, Any]] = []
    for index, item in enumerate(manifest.get("documents", [])):
        if not isinstance(item, dict):
            continue
        file_name = str(item.get("fileName") or item.get("name") or "").strip()
        if not file_name:
            continue
        file_path = folder / file_name
        if not file_path.exists():
            continue
        documents.append(
            {
                "name": str(item.get("name") or file_name),
                "filePath": f"Dataset/Test_Sets/{folder.name}/{file_name}",
                "text": file_path.read_text(encoding="utf-8"),
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
    for index, document in enumerate(req.documents):
        file_name = _normalize_uploaded_filename(document.name, index)
        file_path = folder / file_name
        file_path.write_text(document.text, encoding="utf-8")
        manifest_documents.append(
            {
                "name": document.name,
                "fileName": file_name,
            }
        )

    manifest = {
        "id": folder.name,
        "label": label,
        "source": "custom",
        "createdAtUtc": datetime.now(timezone.utc).isoformat(),
        "documents": manifest_documents,
        "backend": {
            "agent4": {
                "datasetRoot": f"challenge-app/Dataset/Test_Sets/{folder.name}",
                "sourceAdapterKind": "apcs_doc_bundle",
            }
        },
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


def _run_agent4(req: AgentRunRequest) -> Dict[str, Any]:
    if req.documents:
        dataset_root = _materialize_documents(req.documents, req.custom_set_label or req.dataset_root)
    else:
        dataset_root = _resolve_repo_path(req.dataset_root)

    pipeline = LangChainAgent4Pipeline(
        config=Agent4PipelineConfig(
            dataset_root=str(dataset_root),
            source_adapter_kind=(
                None if req.source_adapter_kind in (None, "auto") else req.source_adapter_kind
            ),
            use_llm_summary=not req.no_llm,
            strict_schema=False,
        ),
        llm_generate=None,
    )

    validation = pipeline.validate_dataset()
    if not validation.get("exists", False):
        raise HTTPException(status_code=400, detail=f"Dataset root not found: {dataset_root}")
    missing_required = validation.get("missing_required", [])
    if missing_required and not req.documents:
        raise HTTPException(
            status_code=400,
            detail=f"Dataset missing required files: {', '.join(missing_required)}",
        )

    if req.evaluate_all:
        predictions = pipeline.assess_all_scenarios()
        total = len(predictions)
        schema_valid_count = sum(1 for p in predictions if _safe_schema_valid(p))
        schema_validity_rate = (schema_valid_count / total) if total else 0.0

        payload: Dict[str, Any] = {
            "agent": "agent4_langchain_backend",
            "dataset_root": str(dataset_root),
            "mode": "evaluate_all",
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
                "phase4_decision_labels.csv",
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
                    "matched": evaluation.get("matched", 0),
                    "accuracy": evaluation.get("accuracy", 0.0),
                    "false_go": evaluation.get("false_go", 0),
                    "false_hold": evaluation.get("false_hold", 0),
                }
            )

        return payload

    payload = pipeline.assess_scenario(
        scenario_id=str(req.scenario_id).strip(),
        release_id=req.release_id,
    )

    if req.check_label:
        labels_path = _labels_path(
            dataset_root,
            req.labels_path,
            "phase4_decision_labels.csv",
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


def _run_agent5(req: AgentRunRequest) -> Dict[str, Any]:
    if req.documents:
        dataset_root = _materialize_documents(req.documents, req.custom_set_label or req.dataset_root)
    else:
        dataset_root = _resolve_repo_path(req.dataset_root)

    pipeline = LangChainAgent5Pipeline(
        config=Agent5PipelineConfig(
            dataset_root=str(dataset_root),
            use_llm_summary=not req.no_llm,
            strict_schema=False,
        ),
        llm_generate=None,
    )

    validation = pipeline.validate_dataset()
    if not validation.get("exists", False):
        raise HTTPException(status_code=400, detail=f"Dataset root not found: {dataset_root}")
    missing_required = validation.get("missing_required", [])
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=f"Dataset missing required files: {', '.join(missing_required)}",
        )

    if req.evaluate_all:
        predictions = pipeline.assess_all_scenarios()
        total = len(predictions)
        schema_valid_count = sum(1 for p in predictions if _safe_schema_valid(p))
        schema_validity_rate = (schema_valid_count / total) if total else 0.0

        payload: Dict[str, Any] = {
            "agent": "agent5_langchain_backend",
            "dataset_root": str(dataset_root),
            "mode": "evaluate_all",
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
                "phase5_decision_labels.csv",
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
                    "matched": evaluation.get("matched", 0),
                    "accuracy": evaluation.get("accuracy", 0.0),
                    "false_go": evaluation.get("false_go", 0),
                    "false_hold": evaluation.get("false_hold", 0),
                }
            )

        return payload

    payload = pipeline.assess_scenario(
        scenario_id=str(req.scenario_id).strip(),
        release_id=req.release_id,
    )

    if req.check_label:
        labels_path = _labels_path(
            dataset_root,
            req.labels_path,
            "phase5_decision_labels.csv",
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


app = FastAPI(title="Challenge App Agent Backend", version="0.1.0")

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
def health() -> Dict[str, str]:
    return {"status": "ok"}


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


@app.get("/agents/options")
def agent_options() -> Dict[str, Any]:
    return {
        "agent4": {
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
            ]
        },
        "agent5": {
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
            ]
        },
    }


@app.post("/agents/run", response_model=AgentRunResponse)
def run_agent(req: AgentRunRequest) -> AgentRunResponse:
    try:
        payload = _run_agent4(req) if req.agent == "agent4" else _run_agent5(req)
    except (Agent4LCError, Agent5LCError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

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
