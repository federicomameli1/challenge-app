"""PR review agent: LLM-driven GO/HOLD on a pull request diff vs. project docs.

Standalone module (does not conform to BrainStage) — see audit notes in
memory for the rationale. Add a brain adapter only if/when chaining is
actually needed.
"""

from .models import Highlight, PRReviewInput, PRReviewOutput, Severity, Verdict
from .runner import PRReviewError, PRReviewRunner

__all__ = [
    "Highlight",
    "PRReviewInput",
    "PRReviewOutput",
    "PRReviewError",
    "PRReviewRunner",
    "Severity",
    "Verdict",
]
