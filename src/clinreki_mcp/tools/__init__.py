"""Регистрация всех инструментов MCP."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import clinrecs, mkb, refs


def register_tools(mcp: FastMCP) -> None:
    clinrecs.register(mcp)
    mkb.register(mcp)
    refs.register(mcp)
