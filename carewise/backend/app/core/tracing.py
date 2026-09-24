"""Per-turn tracing: what happened while answering one chat message.

A Trace is opened for each chat request and held in a context variable, so every model call made
while handling that request (by the router or any agent) is recorded against it without passing
a trace object through every function. It captures routing, agents, each model call's latency and
token usage, and total time. It never records message text, so it is safe to log.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from app.core.config import get_settings

_current_trace: ContextVar["Trace | None"] = ContextVar("carewise_trace", default=None)
_current_step: ContextVar[str] = ContextVar("carewise_trace_step", default="unknown")


@dataclass
class ModelCall:
    step: str  # "router" or the agent that made the call
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    ok: bool = True


@dataclass
class Trace:
    started: float = field(default_factory=time.perf_counter)
    route: str | None = None  # which agent the router picked first
    route_method: str | None = None  # shortcut | follow-up | model | demo-fallback | safety
    agents: list[str] = field(default_factory=list)
    calls: list[ModelCall] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)  # e.g. retrieval mode and hits
    total_ms: int | None = None

    def finish(self) -> None:
        self.total_ms = round((time.perf_counter() - self.started) * 1000)

    def summary(self) -> dict[str, Any]:
        tokens_in = sum(c.input_tokens or 0 for c in self.calls)
        tokens_out = sum(c.output_tokens or 0 for c in self.calls)
        tokens_thinking = sum(c.thinking_tokens or 0 for c in self.calls)
        return {
            "route": self.route,
            "route_method": self.route_method,
            "agents": self.agents,
            "model_calls": [c.__dict__ for c in self.calls],
            "model_ms": sum(c.latency_ms for c in self.calls),
            "total_ms": self.total_ms,
            "tokens": {"input": tokens_in, "output": tokens_out, "thinking": tokens_thinking},
            "cost_usd": estimate_cost(tokens_in, tokens_out + tokens_thinking),
            **self.extra,
        }


def estimate_cost(input_tokens: int, output_tokens: int) -> float | None:
    """Only when prices are configured (LLM_PRICE_INPUT_PER_MTOK / LLM_PRICE_OUTPUT_PER_MTOK, USD
    per million tokens). Prices change and differ by plan, so none are assumed."""
    s = get_settings()
    if s.llm_price_input_per_mtok is None or s.llm_price_output_per_mtok is None:
        return None
    return round((input_tokens * s.llm_price_input_per_mtok + output_tokens * s.llm_price_output_per_mtok) / 1e6, 6)


@contextmanager
def start_trace() -> Iterator[Trace]:
    trace = Trace()
    token = _current_trace.set(trace)
    try:
        yield trace
    finally:
        trace.finish()
        _current_trace.reset(token)


def current_trace() -> Trace | None:
    return _current_trace.get()


@contextmanager
def step(name: str) -> Iterator[None]:
    """Label model calls made inside this block (e.g. with step("symptom_tracker"))."""
    token = _current_step.set(name)
    try:
        yield
    finally:
        _current_step.reset(token)


def record_call(**kwargs: Any) -> None:
    trace = _current_trace.get()
    if trace is not None:
        trace.calls.append(ModelCall(step=_current_step.get(), **kwargs))
