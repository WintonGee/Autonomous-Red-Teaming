"""Thin wrapper around the Anthropic SDK for structured agent reasoning.

Best-practice choices (per the claude-api skill):
- Official Anthropic SDK, model `claude-opus-4-7` by default (override via
  ART_LLM_MODEL).
- **Structured output via forced tool-use.** For a known output schema this is
  the correct mode — not a compromise. Do NOT "fix" this by adding
  `thinking: {type: "adaptive"}`: adaptive thinking is for open-ended generation
  and combines awkwardly with a forced `tool_choice`. If you later want the model
  to reason first, add a separate free-text call before the structured one
  (the seam is here); don't force thinking into the forced tool call.
- `cache_control` on the stable system prompt for prompt caching.
- Typed error handling; the SDK already does retry/backoff — we don't reimplement.

The client never gates anything. It returns structured proposals; the
deterministic Guard/RiskEngine still enforce every action.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional


class LlmError(RuntimeError):
    """Raised when a structured LLM call cannot be completed."""


DEFAULT_MODEL = "claude-opus-4-7"


class ClaudeClient:
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        max_tokens: int = 1024,
        create_message: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.model = model or os.environ.get("ART_LLM_MODEL") or DEFAULT_MODEL
        self.max_tokens = max_tokens
        self._audit: list[dict] = []
        if create_message is not None:
            # Injected (tests / custom transport).
            self._create = create_message
            return
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            self._create = None
            return
        try:
            import anthropic
        except ImportError:
            self._create = None
            return
        self._create = anthropic.Anthropic(api_key=key).messages.create

    def available(self) -> bool:
        return self._create is not None

    def drain_audit(self) -> list[dict]:
        """Return and clear the buffered LLM-call audit records."""
        records, self._audit = self._audit, []
        return records

    def structured(
        self,
        *,
        system: str,
        user: str,
        tool: dict,
        tool_name: str,
        audit_meta: Optional[dict] = None,
    ) -> dict:
        """Run one forced-tool-use call and return the tool input dict."""
        if not self.available():
            raise LlmError("Claude client is not available (no API key / SDK)")
        meta = audit_meta or {}
        try:
            response = self._create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
            )
        except Exception as exc:  # SDK already retried; record the failure, then surface it
            # Audit failures too, so a silent fallback to deterministic is visible.
            self._audit.append({
                "model": self.model, "agent_role": meta.get("agent_role", ""),
                "error": f"{type(exc).__name__}: {exc}",
            })
            raise LlmError(f"{type(exc).__name__}: {exc}") from exc

        self._record_audit(response, meta)

        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
                return dict(block.input)
        raise LlmError("model did not return the expected tool_use block")

    def _record_audit(self, response: Any, meta: dict) -> None:
        usage = getattr(response, "usage", None)
        self._audit.append({
            "model": self.model,
            "agent_role": meta.get("agent_role", ""),
            "redacted_secrets": meta.get("redacted_secrets", 0),
            "chars_sent": meta.get("chars_sent", 0),
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        })
