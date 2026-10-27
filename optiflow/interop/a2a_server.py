"""Serves the ADK Verification Reviewer over the A2A protocol.

    python -m optiflow.interop.a2a_server --port 8790

The agent card is published at /.well-known/agent-card.json; any A2A
client (here: the CrewAI pipeline, see a2a_client.py) can discover and
call it. In docker-compose this runs as its own service.
"""

from __future__ import annotations

import argparse
import os
import warnings

from dotenv import load_dotenv


def build_app(host: str = "127.0.0.1", port: int = 8790):
    # ADK marks its A2A bridge experimental; the warning is noise here.
    warnings.filterwarnings("ignore", message=r"\[EXPERIMENTAL\]")
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    from optiflow.interop.adk_reviewer import build_agent

    import contextlib

    @contextlib.asynccontextmanager
    async def warm_up(_app):
        # The first request otherwise pays ~30 s of lazy imports and client
        # setup (genai client, chromadb + embedding model for the tool);
        # do it at startup so request latency is comparable to in-process.
        import asyncio

        def _load():
            from google import genai

            from optiflow.interop.adk_reviewer import ensure_google_api_key
            from optiflow.knowledge.retriever import retrieve_text

            ensure_google_api_key()
            genai.Client()
            retrieve_text("loop tiling", k=1)

        await asyncio.to_thread(_load)
        yield

    public_host = os.getenv("A2A_PUBLIC_HOST", host)
    return to_a2a(build_agent(), host=public_host, port=port, lifespan=warm_up)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(build_app(args.host, args.port), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
