"""
Brain adapters package exports.

This package contains stage adapters that wrap concrete agents and expose them
through the Brain stage contract.
"""

from .agent4_stage import Agent4StageAdapter, Agent4StageSettings, build_agent4_stage
from .agent5_stage import Agent5StageAdapter, Agent5StageSettings, build_agent5_stage
from .base import AdapterConfig, BrainStageAdapterBase, StageAdapterError

__all__ = [
    "AdapterConfig",
    "BrainStageAdapterBase",
    "StageAdapterError",
    "Agent4StageSettings",
    "Agent4StageAdapter",
    "build_agent4_stage",
    "Agent5StageSettings",
    "Agent5StageAdapter",
    "build_agent5_stage",
]
