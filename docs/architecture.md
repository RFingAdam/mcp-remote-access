# Architecture

How `mcp-remote-access` is built, and how it composes with the rest of
[eng-mcp-suite](https://github.com/RFingAdam/eng-mcp-suite).

## Internal layout

```
┌──────────────────────────────────────────────────────────────────┐
│  User-facing surface                                             │
│  ┌────────────────┐                                              │
│  │  MCP server    │ stdio (JSON-RPC)                             │
│  │  (Python)      │                                              │
│  └────────┬───────┘                                              │
└───────────┼──────────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────┐
│  Connection registries                                           │
│  • SSHRegistry      — paramiko clients keyed by connection_id    │
│  • SerialRegistry   — pyserial handles keyed by connection_id    │
│  • BackgroundJobs   — async SSH command tracker (job_id)         │
└──────────────────────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────┐
│  Transports                                                      │
│  • paramiko (SSH 2.0, SFTP)                                       │
│  • pyserial (RS-232, USB-CDC, USB-serial bridges)                │
└──────────────────────────────────────────────────────────────────┘
```

The server holds connection state in memory only. Restarting the MCP
server clears all sessions; clients must reconnect. There is no
on-disk session store and no credential cache.

## Source layout

```
mcp-remote-access/
├── src/mcp_remote_access/
│   ├── __init__.py
│   ├── __main__.py
│   └── server.py         ← all 24 tool definitions + dispatch
├── assets/               ← logo-banner.svg, logo.svg
├── docs/                 ← this docs/ directory
├── pyproject.toml
└── LICENSE               ← Apache 2.0
```

The server is intentionally compact — one server module owns all 24
tools because they share connection registries and the surface area is
small enough that splitting would add ceremony without value.

## Position in eng-mcp-suite

`mcp-remote-access` sits in the **transport / lab-automation** layer of
the engineering MCP stack. It does not measure or compute — it gives
the agent shell access and serial access so other tools (or human
muscle memory) can drive a target.

```
       ┌─────────────────────────────────────┐
       │   AI agent (Claude Code / Codex)    │
       └──────┬─────────────────┬────────────┘
              │ via MCP         │ via MCP
       ┌──────▼──────┐   ┌──────▼─────────────┐
       │  lab gear   │   │  mcp-remote-access │ ← transport
       │  SCPI MCPs  │   │  (this MCP)         │
       └─────────────┘   └────────┬────────────┘
                                  │
                         ┌────────▼────────────┐
                         │ embedded target /   │
                         │ Raspberry Pi /      │
                         │ remote build server │
                         └─────────────────────┘
```

### Feeds / consumes

- **Feeds**: nothing in the suite directly — output is arbitrary
  shell / UART data that an agent interprets.
- **Consumes**: nothing in the suite — credentials and ports come from
  the user prompt.

### Workflow bundles

| Bundle              | Role of this MCP                                                   |
| ------------------- | ------------------------------------------------------------------ |
| `lab-automation`    | DUT shell access + USB-serial console for bench scripts             |
| `embedded-bringup`  | Bootloader interaction, AT flows, DTR/RTS reset, SFTP image pull   |

See the [suite manifest](https://github.com/RFingAdam/eng-mcp-suite/blob/main/manifest.yaml)
for full bundle definitions.

---

## Design decisions

- **In-memory credentials, no on-disk store.** Passwords passed to
  `ssh_connect` are held in the paramiko transport, cleared on
  `ssh_disconnect` or server exit. Keys are referenced by path, not
  copied.
- **VID/PID/serial match on `serial_connect_match`.** Embedded
  bring-up cannot tolerate guessing `/dev/ttyUSB0` vs `/dev/ttyUSB1`.
  Matching on USB descriptors makes the connection reproducible across
  reboots and host changes.
- **`serial_expect` instead of polling.** Login prompts and AT flows
  race the user; an expect / send loop avoids the "send before prompt"
  bug class.
- **`ssh_execute_background` for long commands.** A blocking
  `ssh_execute` would stall the MCP channel during a build. Background
  jobs return immediately and clients poll.
- **Apache 2.0.** Compatible with downstream proprietary lab tooling.
