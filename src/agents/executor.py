"""Executor agent: runs an approved action via the appropriate tool.

Deterministic by design (no LLM). The orchestrator gates the action before this
runs; the tool layer enforces target scope again as defense in depth.
"""
from __future__ import annotations

from .contracts import ExecutionResult, ProposedAction
from src.skills.registry import SkillRegistry
from src.tools.http_client import HttpClient


class Executor:
    def __init__(self, http_client: HttpClient, skill_registry: SkillRegistry) -> None:
        self.http = http_client
        self.skills = skill_registry

    def execute(self, action: ProposedAction) -> ExecutionResult:
        skill = self.skills.get(action.skill_id)
        if skill is None:
            return ExecutionResult(action, ok=False, error=f"unknown skill {action.skill_id!r}")
        if skill.tool != "http-client":
            return ExecutionResult(action, ok=False, error=f"unsupported tool {skill.tool!r}")
        try:
            response = self.http.get(action.target_url)
        except Exception as exc:  # tool-layer refusal, network error, timeout
            return ExecutionResult(action, ok=False, error=f"{type(exc).__name__}: {exc}")
        return ExecutionResult(action, ok=True, observations=skill.detect(response))
