"""
OpenRouter API client for LLM-based agents.

Wraps the OpenRouter chat completions endpoint (OpenAI-compatible).
Any agent that needs an LLM call should import this module rather than
calling the API directly, so that auth, retries, and model selection
stay in one place.

Configuration (environment variables):
    OPENROUTER_API_KEY   — required; without it the client returns None
    OPENROUTER_MODEL     — model identifier (default: free tier Llama)
    OPENROUTER_BASE_URL  — override base URL (default: https://openrouter.ai/api/v1)
    OPENROUTER_TIMEOUT   — HTTP timeout in seconds (default: 30)

Usage:
    client = OpenRouterClient.from_env()
    if client:
        text = client.complete([{"role": "user", "content": "Hello"}])
        data = client.complete_json([{"role": "user", "content": "Return JSON..."}])
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_TIMEOUT = 30


class LLMError(Exception):
    """Raised when the LLM call fails after retries."""


class OpenRouterClient:
    """Thin wrapper around the OpenRouter chat completions endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> Optional["OpenRouterClient"]:
        """Build a client from env vars. Returns None if OPENROUTER_API_KEY is missing."""
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            return None
        return cls(
            api_key=api_key,
            model=os.environ.get("OPENROUTER_MODEL", "").strip() or _DEFAULT_MODEL,
            base_url=os.environ.get("OPENROUTER_BASE_URL", "").strip() or _DEFAULT_BASE_URL,
            timeout=int(os.environ.get("OPENROUTER_TIMEOUT", str(_DEFAULT_TIMEOUT))),
        )

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        """Send a chat completion request and return the assistant message text."""
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "reasoning": {"enabled": False},
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/federicomameli1/challenge-app",
                "X-Title": "challenge-app",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
            message = data["choices"][0]["message"]
            text = message.get("content") or message.get("reasoning") or ""
            if not text.strip():
                raise LLMError(
                    f"empty content in response (finish_reason={data['choices'][0].get('finish_reason')!r})"
                )
            return text
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            raise LLMError(f"HTTP {exc.code}: {body_text[:300]}") from exc
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(str(exc)) from exc

    def complete_json(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request and parse the response as JSON.

        Tries to extract a JSON object from the response even if the model
        wraps it in markdown code fences or adds extra text.
        Raises LLMError if the response cannot be parsed as JSON.
        """
        text = self.complete(messages, max_tokens=max_tokens, temperature=0.1)
        return _extract_json(text)

    def truncate_to_tokens(self, text: str, max_chars: int = 6000) -> str:
        """Hard-truncate text to stay within a token budget (1 token ≈ 4 chars)."""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n[...truncated...]"


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract the first JSON object from a string, stripping markdown fences."""
    # Strip ```json ... ``` fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)

    # Find first { ... } block
    start = text.find("{")
    if start == -1:
        raise LLMError(f"No JSON object found in response: {text[:200]!r}")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError as exc:
                    raise LLMError(f"JSON parse error: {exc}") from exc
    raise LLMError(f"Unbalanced JSON in response: {text[:200]!r}")
