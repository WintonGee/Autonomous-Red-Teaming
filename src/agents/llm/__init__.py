"""LLM (Claude) integration for the agents — the non-deterministic brains.

Activates automatically when ANTHROPIC_API_KEY is set; otherwise the agents fall
back to their deterministic reasoners. The LLM proposes; code still gates.
"""
from .client import ClaudeClient, LlmError
from .reasoners import ClaudeEvaluator, ClaudeLearner, ClaudePlanner

__all__ = [
    "ClaudeClient",
    "LlmError",
    "ClaudePlanner",
    "ClaudeEvaluator",
    "ClaudeLearner",
]
