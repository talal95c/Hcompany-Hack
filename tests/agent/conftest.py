import asyncio
import os
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: appels H authentifiés réels")


@asynccontextmanager
async def connect(transport: str, root: Path, state: Path):
    env = {**os.environ, "AGENT_LESSONS_DIR": str(root), "AGENT_STATE_DIR": str(state)}
    if transport == "stdio":
        params = StdioServerParameters(command=sys.executable, args=["-m", "agent.server"], env=env)
        async with (
            stdio_client(params, errlog=sys.__stderr__) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            yield session
    else:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, "-m", "agent.server", "--transport", "http", "--port", str(port)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            async with httpx.AsyncClient() as client:
                for _ in range(100):
                    try:
                        await client.get(f"http://127.0.0.1:{port}/mcp")
                        break
                    except httpx.ConnectError:
                        await asyncio.sleep(0.05)
                else:
                    raise AssertionError("HTTP server did not start")
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        finally:
            process.terminate()
            process.wait(timeout=10)


@pytest.fixture(params=["stdio", "http"])
def transport(request):
    return request.param


async def call(session, name, arguments=None):
    started = time.perf_counter()
    result = await session.call_tool(name, arguments or {})
    print(f"MCP {name} latency_ms={(time.perf_counter() - started) * 1000:.3f}")
    return result
