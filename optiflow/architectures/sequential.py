"""Sequential architecture: a fixed pipeline, looped in plain Python.

analyze -> profile -> [plan -> transform -> build/test -> benchmark ->
judge] x up to max_attempts, stopping on the Critic's rule-based stop
signal. Lowest coordination overhead of the three architectures: no
manager tokens, no event dispatch, nothing runs in parallel.
"""

from __future__ import annotations

from optiflow.agents.mcp_tools import McpToolClient
from optiflow.architectures.base import Architecture
from optiflow.architectures.pipeline import Pipeline
from optiflow.core.schemas import RunState


class Sequential(Architecture):
    name = "sequential"

    def run(self, program_id: str) -> RunState:
        tools_cm = self._tools or McpToolClient()
        with tools_cm as tools:
            p = Pipeline(self.cfg, self.channel, tools, program_id, self.name, emit=self.emit)
            try:
                with p.tracer.start_as_current_span("run", attributes={"program": program_id, "architecture": self.name}):
                    p.start()
                    p.analyze()
                    p.profile()
                    stop_reason = ""
                    for attempt in range(1, self.cfg.max_attempts + 1):
                        verdict = p.attempt(attempt)
                        if verdict is None:
                            stop_reason = "no_more_strategies"
                            break
                        if verdict.stop:
                            stop_reason = verdict.stop_reason
                            break
                # Finish after the run span closes, so the saved row can
                # compute the critical path from the complete trace.
                return p.finish(stop_reason)
            except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised
                p.fail(exc)
                raise
