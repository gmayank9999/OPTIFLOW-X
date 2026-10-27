"""Event-driven architecture: agents react to events on a bus.

There is no central loop deciding the order. Each handler subscribes to
an event type, does its step, and publishes the event(s) its output
enables:

  program_requested -> [analyze]  -> analyzed ----.
  program_requested -> [measure]  -> measured ----+-> [profile] -> profiled
  profiled | judged(continue)     -> [plan+transform+build+bench+judge] -> judged
  judged(stop)                    -> done

The structural difference from Sequential is loose coupling plus real
concurrency where the dependency graph allows it: profiling the baseline
(perf + benchmark, seconds of sandbox time) needs only the program id, so
it runs *in parallel* with the Analyzer's LLM call instead of after it.
The critical-path metric shows the saving. Fairness rules are unchanged:
same agents, tools, prompts, budget and stop rules.
"""

from __future__ import annotations

import contextvars
import queue
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from optiflow.agents.mcp_tools import McpToolClient
from optiflow.architectures.base import Architecture
from optiflow.architectures.pipeline import Pipeline
from optiflow.core.schemas import RunState


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[dict], None]]] = defaultdict(list)
        self._queue: queue.Queue = queue.Queue()
        self.dispatched: list[str] = []

    def on(self, event: str, handler: Callable[[dict], None]) -> None:
        self._handlers[event].append(handler)

    def publish(self, event: str, payload: dict | None = None) -> None:
        self._queue.put((event, payload or {}))

    def run_until(self, terminal: str, timeout_s: float = 3600) -> dict:
        while True:
            event, payload = self._queue.get(timeout=timeout_s)
            self.dispatched.append(event)
            if event == terminal:
                return payload
            for handler in self._handlers.get(event, []):
                handler(payload)


class EventDriven(Architecture):
    name = "event"

    def run(self, program_id: str) -> RunState:
        tools_cm = self._tools or McpToolClient()
        with tools_cm as tools:
            p = Pipeline(self.cfg, self.channel, tools, program_id, self.name, emit=self.emit)
            try:
                with p.tracer.start_as_current_span("run", attributes={"program": program_id, "architecture": self.name}):
                    p.start()
                    bus = EventBus()
                    self._wire(bus, p)
                    bus.publish("program_requested")
                    result = bus.run_until("done")
                    if result.get("error"):
                        raise result["error"]
                p.extra_stats["events_dispatched"] = len(bus.dispatched)
                return p.finish(result.get("stop_reason", ""))
            except Exception as exc:  # noqa: BLE001
                p.fail(exc)
                raise

    def _wire(self, bus: EventBus, p: Pipeline) -> None:
        pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="optiflow-event")
        joined: dict = {}
        lock = threading.Lock()

        def in_background(fn, done_event: str, key: str) -> None:
            ctx = contextvars.copy_context()  # keep the run span as parent

            def task():
                try:
                    joined[key] = ctx.run(fn)
                    bus.publish(done_event)
                except Exception as exc:  # noqa: BLE001
                    bus.publish("done", {"error": exc})
            pool.submit(task)

        def on_requested(_):
            in_background(p.analyze, "analyzed", "summary")
            in_background(p.measure_profile, "measured", "measured")

        def on_ready(_):
            with lock:
                ready = "summary" in joined and "measured" in joined and not joined.get("_profiled")
                if ready:
                    joined["_profiled"] = True
            if ready:
                p.profile(measured=joined["measured"])
                pool.shutdown(wait=False)
                bus.publish("profiled")

        state = {"attempt": 0}

        def on_attempt_requested(_):
            state["attempt"] += 1
            verdict = p.attempt(state["attempt"])
            bus.publish("judged", {"verdict": verdict})

        def on_judged(payload):
            verdict = payload["verdict"]
            if verdict is None:
                bus.publish("done", {"stop_reason": "no_more_strategies"})
            elif verdict.stop or state["attempt"] >= self.cfg.max_attempts:
                bus.publish("done", {"stop_reason": verdict.stop_reason or "attempt_budget"})
            else:
                bus.publish("attempt_requested")

        bus.on("program_requested", on_requested)
        bus.on("analyzed", on_ready)
        bus.on("measured", on_ready)
        bus.on("profiled", lambda _: bus.publish("attempt_requested"))
        bus.on("attempt_requested", on_attempt_requested)
        bus.on("judged", on_judged)
