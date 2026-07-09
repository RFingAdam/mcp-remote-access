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


def test_ssh_connect_keeps_explicit_empty_password():
    """An explicitly empty password must reach paramiko, not get dropped.

    ssh_connect used to build its paramiko kwargs with `if password:`, which
    treats "" the same as "not supplied" and silently omits the password
    argument entirely. That breaks auth against any host configured for
    empty-password login (PermitEmptyPasswords yes), since paramiko never
    even attempts password auth.
    """
    import ast
    import inspect

    from mcp_remote_access import server

    source = inspect.getsource(server.handle_ssh_connect)
    tree = ast.parse(source)

    found_guard = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "password":
            found_guard = True

    assert not found_guard, (
        "handle_ssh_connect still guards password with a bare `if password:` "
        "check, which drops an explicitly empty password."
    )


def test_is_port_alive_detects_dead_handle():
    """A pooled handle whose is_open is stale (True after external invalidation)
    must not be trusted -- is_port_alive should probe real I/O instead.
    """
    from mcp_remote_access.server import is_port_alive

    class DeadHandle:
        is_open = True

        @property
        def in_waiting(self):
            raise OSError("simulated dead handle after external invalidation")

    class AliveHandle:
        is_open = True
        in_waiting = 0

    assert is_port_alive(DeadHandle()) is False
    assert is_port_alive(AliveHandle()) is True
