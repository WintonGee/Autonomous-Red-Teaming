"""Evaluator agent: judges whether an execution produced real signal."""
from __future__ import annotations

from typing import Optional

from .contracts import EvaluatorReasoner, ExecutionResult, Verdict
from .reasoners import RuleBasedEvaluator


class Evaluator:
    def __init__(self, reasoner: Optional[EvaluatorReasoner] = None) -> None:
        self.reasoner: EvaluatorReasoner = reasoner or RuleBasedEvaluator()

    def evaluate(self, result: ExecutionResult) -> Verdict:
        return self.reasoner.evaluate(result)
