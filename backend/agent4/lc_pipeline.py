from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_external_module():
    external_path = Path(__file__).resolve().parents[3] / "agent4" / "lc_pipeline.py"
    spec = importlib.util.spec_from_file_location("challenge_external_agent4_lc_pipeline", external_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load agent4 pipeline from {external_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_module = _load_external_module()

Agent4LCError = _module.Agent4LCError
LCPipelineConfig = _module.LCPipelineConfig
LangChainAgent4Pipeline = _module.LangChainAgent4Pipeline
