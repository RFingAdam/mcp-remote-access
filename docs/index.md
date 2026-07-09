# mcp-remote-access

SSH and serial-port control for embedded devices, exposed as MCP tools.

---

## What it is

A thin MCP server that exposes **paramiko** (SSH) and **pyserial**
(UART / serial) as MCP tools. 26 tools total across two transports,
no orchestration language — agent prompts handle higher-level logic.

## Install

```bash
git clone https://github.com/RFingAdam/mcp-remote-access.git
cd mcp-remote-access
uv pip install -e .
```

## First call

=== "MCP"

    Add to your client's config:

    ```json
    {
      "mcpServers": {
        "remote-access": {
          "command": "uv",
          "args": ["run", "--directory", "/path/to/mcp-remote-access", "mcp-remote-access"]
        }
      }
    }
    ```

    Then ask your assistant:

    > *"Connect to my Pi at vpn-ap.local as `pi` (password `raspberry`), run `uname -a`, then `dmesg | tail -20`."*

=== "Codex CLI"

    ```bash
    codex mcp add remote-access -- uv run --directory /path/to/mcp-remote-access mcp-remote-access
    ```

=== "Claude Code"

    ```bash
    claude mcp add remote-access -- uv run --directory /path/to/mcp-remote-access mcp-remote-access
    ```

## Where to next

- [Tool reference](tools.md) — every MCP tool with arguments
- [Usage examples](usage.md) — SSH session and UART AT-flow walkthroughs
- [Architecture](architecture.md) — paramiko + pyserial layout

---

!!! note "Part of eng-mcp-suite"
    This MCP server is part of [eng-mcp-suite](https://github.com/RFingAdam/eng-mcp-suite) —
    an umbrella of engineering MCP servers. `mcp-remote-access` is the
    bench-control / lab-automation transport for the family.
