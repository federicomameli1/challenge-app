"""VDD Drafter agent: produces a full Version Description Document for a
release from the available evidence (release metadata, cumulative diff,
APCS docs, module versions).

Standalone module — does not conform to BrainStage. Same rationale as
agents/pr_review (see D11 in docs/design-decisions.md): the LLM call is
the analysis, there is no deterministic policy to layer in front.
"""

from .models import ModuleVersion, VDDDraftInput, VDDDraftOutput
from .runner import VDDDrafterError, VDDDrafterRunner

__all__ = [
    "ModuleVersion",
    "VDDDraftInput",
    "VDDDraftOutput",
    "VDDDrafterError",
    "VDDDrafterRunner",
]
