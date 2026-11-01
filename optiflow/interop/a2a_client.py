"""A2A client used by the CrewAI pipeline to reach the ADK reviewer.

`ReviewerClient(url).review(prompt)` sends one A2A message, collects the
streamed reply, and returns (text, TokenUsage). Token counts come from
the `adk_usage_metadata` ADK attaches to every A2A event, so the remote
agent's cost is billed to the run exactly like a local LLM call.

`local_reviewer()` gives a reviewer for the current process: it uses
OPTIFLOW_A2A_URL when set (e.g. the docker-compose `reviewer` service),
otherwise it starts `python -m optiflow.interop.a2a_server` as a child
process on a free port and shuts it down at exit. Either way the CrewAI
side and the ADK side talk only over HTTP + the A2A protocol.
"""

from __future__ import annotations

import asyncio
import atexit
import os
import socket
import subprocess
import sys
import threading
import time

import httpx

from optiflow.core.config import price
from optiflow.core.schemas import TokenUsage


class A2AError(RuntimeError):
    pass


FAILED_STATES = frozenset({"TASK_STATE_FAILED", "TASK_STATE_REJECTED", "TASK_STATE_CANCELED"})


class ReviewerClient:
    transport = "a2a-jsonrpc"

    def __init__(self, url: str, timeout_s: float = 120) -> None:
        self.url = url.rstrip("/")
        self.timeout_s = timeout_s
        self.card: dict | None = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="a2a-client", daemon=True)
        self._thread.start()
        self._client = None
        self._lock = threading.Lock()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(self.timeout_s + 10)

    async def _connect(self):
        from a2a.client import ClientConfig, ClientFactory

        http = httpx.AsyncClient(timeout=self.timeout_s)
        client = await ClientFactory(ClientConfig(httpx_client=http)).create_from_url(self.url)
        card = (await http.get(f"{self.url}/.well-known/agent-card.json")).json()
        return client, card

    def connect(self) -> dict:
        with self._lock:
            if self._client is None:
                try:
                    self._client, self.card = self._run(self._connect())
                except Exception as exc:  # noqa: BLE001
                    raise A2AError(f"cannot reach A2A agent at {self.url}: {exc}") from exc
        return self.card or {}

    async def _send(self, text: str):
        from a2a.helpers.proto_helpers import get_stream_response_text, new_text_message
        from a2a.types import a2a_pb2
        from google.protobuf.json_format import MessageToDict

        request = a2a_pb2.SendMessageRequest(message=new_text_message(text))
        chunks: list[str] = []
        usage: dict = {}
        final_state = ""
        async for response in self._client.send_message(request):
            as_dict = MessageToDict(response)
            piece = get_stream_response_text(response)
            if piece:
                chunks.append(piece)
            found = _find_key(as_dict, "adk_usage_metadata")
            if found:
                usage = found
            state = _find_key(as_dict, "state")
            if isinstance(state, str):
                final_state = state
        # A failed remote task still streams its error message as ordinary
        # text. Without this check a "429 RESOURCE_EXHAUSTED ..." from the ADK
        # agent would be returned as a *review* and fed to the Strategist.
        if final_state in FAILED_STATES:
            raise A2AError(f"remote agent task ended {final_state}: {(chunks[-1] if chunks else '')[:300]}")
        return chunks, usage

    def review(self, prompt: str) -> tuple[str, TokenUsage, dict]:
        """Returns (reply text, usage, info). Raises A2AError on transport failure."""
        self.connect()
        t0 = time.time()
        try:
            chunks, usage = self._run(self._send(prompt))
        except Exception as exc:  # noqa: BLE001
            raise A2AError(f"A2A call failed: {type(exc).__name__}: {exc}") from exc
        # ADK streams the reply incrementally and repeats the final text in
        # the completed task; the last non-empty chunk is the full answer.
        text = chunks[-1] if chunks else ""
        prompt_tokens = int(usage.get("promptTokenCount", 0) or 0)
        completion_tokens = int(usage.get("candidatesTokenCount", 0) or 0)
        from optiflow.interop.adk_reviewer import adk_model_name

        model = f"gemini/{adk_model_name()}"
        token_usage = TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, calls=1,
                                 cost_usd=price(model, prompt_tokens, completion_tokens))
        info = {"transport": self.transport, "url": self.url, "latency_ms": (time.time() - t0) * 1000,
                "agent": (self.card or {}).get("name", "verification_reviewer"), "model": model}
        return text.strip(), token_usage, info


def _find_key(obj, key: str):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                return v
            found = _find_key(v, key)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_key(v, key)
            if found:
                return found
    return None


# ------------------------------------------------------------ local server

_local: ReviewerClient | None = None
_proc: subprocess.Popen | None = None
_local_lock = threading.Lock()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _stop_local_server() -> None:
    global _proc
    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(10)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None


def local_reviewer(startup_timeout_s: float = 60) -> ReviewerClient:
    """A connected reviewer client (shared per process)."""
    global _local, _proc
    with _local_lock:
        if _local is not None:
            return _local
        url = os.getenv("OPTIFLOW_A2A_URL")
        if not url:
            port = _free_port()
            _proc = subprocess.Popen(
                [sys.executable, "-m", "optiflow.interop.a2a_server", "--port", str(port)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            atexit.register(_stop_local_server)
            url = f"http://127.0.0.1:{port}"
            deadline = time.time() + startup_timeout_s
            while time.time() < deadline:
                if _proc.poll() is not None:
                    raise A2AError("A2A reviewer server exited during startup")
                try:
                    if httpx.get(f"{url}/.well-known/agent-card.json", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            else:
                _stop_local_server()
                raise A2AError("A2A reviewer server did not start in time")
        client = ReviewerClient(url)
        client.connect()
        _local = client
        return client
