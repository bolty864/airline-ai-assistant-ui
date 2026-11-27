"""Start the API:  python run.py

Use this instead of `uvicorn main:app` on Windows: psycopg's async driver needs the
selector event loop, which uvicorn does not pick by default there.
"""
from __future__ import annotations

import asyncio
import os
import sys

import uvicorn


def serve(host: str = "0.0.0.0", port: int | None = None) -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    config = uvicorn.Config("main:app", host=host, port=port or int(os.getenv("PORT", "8000")), loop="none")
    asyncio.run(uvicorn.Server(config).serve())


if __name__ == "__main__":
    serve()
