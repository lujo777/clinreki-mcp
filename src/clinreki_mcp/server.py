"""Точка входа MCP-сервера: FastMCP-инстанс, lifespan и регистрация инструментов."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from mcp.server.fastmcp import FastMCP

from .cache import ReferenceCache
from .client import ClinrecApiClient
from .constants import BASE_URL
from .tools import register_tools


@dataclass
class AppContext:
    """Разделяемое состояние на время жизни процесса."""

    api: ClinrecApiClient
    cache: ReferenceCache


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    timeout = httpx.Timeout(60.0, connect=10.0, write=30.0, pool=10.0)
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=timeout,
        limits=limits,
        headers={"User-Agent": "clinreki-mcp", "Accept": "application/json"},
    ) as client:
        api = ClinrecApiClient(client)
        yield AppContext(api=api, cache=ReferenceCache(api))


mcp = FastMCP("clinreki-mcp", lifespan=lifespan)
register_tools(mcp)


def main() -> None:
    """Запуск сервера по транспорту stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
