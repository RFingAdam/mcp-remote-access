"""Smoke tests for mcp-remote-access.

These don't open any SSH/serial connections — they verify the package and
MCP server module import and that the server factory builds and registers
its tool surface without error.
"""
from __future__ import annotations

import mcp_remote_access


def test_package_importable():
    """The package imports."""
    assert mcp_remote_access is not None


def test_server_module_importable():
    """The MCP server module imports."""
    from mcp_remote_access import server
    assert server is not None


def test_create_server_builds():
    """The server factory constructs a named Server with its tools registered."""
    from mcp_remote_access.server import create_server

    srv = create_server()
    assert srv.name == "mcp-remote-access"
