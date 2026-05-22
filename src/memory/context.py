"""Working memory: the token-budgeted view the model actually sees.

This is the "self-clearing short-term memory". It separates three regions:

  pinned   - safety-critical facts (authorization, scope, risk limits, goal).
             NEVER evicted. Rendering without them fails closed.
  summary  - a rolling, compressed summary of older salient items.
  recent   - the most recent items, kept verbatim.

When the token budget is exceeded, compaction runs:
  1. drop ephemeral items (raw tool output / dead-end reasoning),
  2. fold older salient items into the rolling summary,
  3. keep the most recent items verbatim.

Token counting and summarization are injected so production code can pass
Anthropic's real tokenizer and an LLM-backed summarizer, while tests stay
deterministic and offline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

TokenCounter = Callable[[str], int]
Summarizer = Callable[[List[str]], str]

EPHEMERAL = "ephemeral"
SALIENT = "salient"


def heuristic_token_count(text: str) -> int:
    """Cheap, deterministic token estimate (~4 chars/token).

    Replace in production by passing Anthropic's token counter, e.g.
    count_tokens=lambda t: client.messages.count_tokens(...).input_tokens
    """
    return max(1, len(text) // 4)


def make_truncating_summarizer(max_chars: int = 600) -> Summarizer:
    """Default summarizer for tests/offline use: concatenate and truncate.

    In production pass an LLM-backed summarizer that genuinely abstracts the
    older turns instead of truncating them.
    """
    def _summarize(parts: List[str]) -> str:
        joined = " ".join(p for p in parts if p).strip()
        if len(joined) <= max_chars:
            return joined
        return joined[:max_chars].rstrip() + " …"
    return _summarize


class PinnedContextMissing(RuntimeError):
    """Raised when a context is rendered without its pinned safety facts."""


@dataclass
class MemoryItem:
    content: str
    salience: str
    token_cost: int
    seq: int
    turns_remaining: int | None = None  # only set for ephemeral items


@dataclass
class WorkingMemory:
    token_budget: int
    recent_keep: int = 6
    count_tokens: TokenCounter = heuristic_token_count
    summarize: Summarizer = field(default_factory=make_truncating_summarizer)
    ephemeral_ttl_turns: int = 1  # ephemeral scratch is dropped after this many further adds

    pinned: List[str] = field(default_factory=list)
    rolling_summary: str = ""
    items: List[MemoryItem] = field(default_factory=list)
    _seq: int = 0

    # ---- mutation -------------------------------------------------------
    def pin(self, fact: str) -> None:
        """Pin a safety-critical fact that must never be evicted.

        Call only at engagement start (before any items are added). Pinned text
        must not change within an engagement, or it breaks Anthropic prompt
        caching of the preamble — so pinning after items exist is rejected.
        """
        if self.items:
            raise RuntimeError(
                "pin() must be called before any items are added; mutating pinned "
                "text mid-engagement breaks prompt caching of the preamble."
            )
        self.pinned.append(fact)

    def add(self, content: str, *, salience: str = SALIENT, token_cost: int | None = None) -> None:
        # Age out expired ephemeral scratch first, so junk self-clears even when
        # the budget is never breached (it was tagged ephemeral for a reason).
        self._age_ephemeral()
        tc = token_cost if token_cost is not None else self.count_tokens(content)
        ttl = self.ephemeral_ttl_turns if salience == EPHEMERAL else None
        self.items.append(MemoryItem(content, salience, tc, self._seq, ttl))
        self._seq += 1
        if self.total_tokens() > self.token_budget:
            self.compact()

    def _age_ephemeral(self) -> None:
        survivors: List[MemoryItem] = []
        for item in self.items:
            if item.salience == EPHEMERAL and item.turns_remaining is not None:
                item.turns_remaining -= 1
                if item.turns_remaining <= 0:
                    continue  # expired scratch, drop it
            survivors.append(item)
        self.items = survivors

    # ---- accounting -----------------------------------------------------
    def total_tokens(self) -> int:
        total = sum(self.count_tokens(p) for p in self.pinned)
        if self.rolling_summary:
            total += self.count_tokens(self.rolling_summary)
        total += sum(i.token_cost for i in self.items)
        return total

    # ---- compaction (the "self-clearing" step) --------------------------
    def compact(self) -> None:
        # 1. ephemeral items are disposable working junk.
        self.items = [i for i in self.items if i.salience != EPHEMERAL]
        if self.total_tokens() <= self.token_budget:
            return
        # 2. fold everything older than the recent window into the summary.
        if len(self.items) > self.recent_keep:
            old = self.items[: -self.recent_keep]
            self.items = self.items[-self.recent_keep :]
            self.rolling_summary = self.summarize(
                ([self.rolling_summary] if self.rolling_summary else [])
                + [i.content for i in old]
            )
        # 3. still over budget: keep folding the oldest remaining item.
        while self.total_tokens() > self.token_budget and self.items:
            oldest = self.items.pop(0)
            self.rolling_summary = self.summarize(
                ([self.rolling_summary] if self.rolling_summary else []) + [oldest.content]
            )

    # ---- rendering ------------------------------------------------------
    def render(self) -> List[dict]:
        """Render context blocks for a model call.

        Fail-closed safety invariant: a context with no pinned facts (i.e. no
        authorization/scope present) must never be sent to a model. The stable
        preamble (pinned + summary) is marked cacheable so callers can apply
        Anthropic prompt caching.
        """
        if not self.pinned:
            raise PinnedContextMissing(
                "Refusing to render context without pinned safety facts "
                "(authorization/scope). Fail closed."
            )
        blocks: List[dict] = [
            {"region": "pinned", "text": "\n".join(self.pinned), "cacheable": True}
        ]
        if self.rolling_summary:
            blocks.append({"region": "summary", "text": self.rolling_summary, "cacheable": True})
        for item in self.items:
            blocks.append({"region": "recent", "text": item.content, "cacheable": False})
        return blocks
