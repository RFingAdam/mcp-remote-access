<p align="center"><img src="docs/logo.svg" alt="RFingAdam — Security Research" width="300"></p>

> ⚠️ **Authorized security testing only.** See [DISCLAIMER.md](./DISCLAIMER.md).

---

<div align="center">

<img src="assets/logo-banner.svg" alt="mcp-remote-access — SSH and serial-port control for embedded devices over MCP" width="100%"/>

<br/>

[![License](https://img.shields.io/badge/License-AGPL--3.0-1E40AF.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-3776AB.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-server-A78BFA.svg)](https://modelcontextprotocol.io)
[![eng-mcp-suite](https://img.shields.io/badge/eng--mcp--suite-member-22D3EE.svg)](https://github.com/RFingAdam/eng-mcp-suite)

**SSH and serial-port control for embedded devices, exposed as MCP tools.** Log into a Raspberry Pi, talk to a UART, drive a USB-CDC console from your assistant.

[Quick start](#quick-start) ·
[Tools](#tools) ·
[Workflows](#workflows) ·
[Documentation](#documentation)

</div>

---

## What is mcp-remote-access?

`mcp-remote-access` is an MCP server that exposes SSH (over paramiko)
and serial / UART (over pyserial) as MCP tools. Once it's running,
an agent can log into a host over SSH, run commands, transfer files,
open a serial console, send AT-style command sequences, and reset a
device over DTR/RTS.

It's deliberately thin: 26 tools, two transports, no orchestration
language. Higher-level workflow logic lives in the agent's prompts,
not in this server.

A few things it handles that are easy to get wrong by hand:

- Connect to a serial port by VID/PID/serial number/description
  instead of guessing `/dev/ttyUSB0` vs `/dev/ttyUSB1`
  (`serial_connect_match`).
- Long-running SSH commands (builds, `tcpdump`, test runs) don't
  block the MCP channel — `ssh_execute_background` returns a task ID,
  `ssh_check_background` polls it.
- `serial_expect`/`serial_wait_for` wait for a real pattern in the
  stream instead of a fixed `sleep()`, which avoids the usual
  "sent before the prompt was ready" race on login prompts and AT
  flows.
- DTR/RTS control for hard-resetting MCUs over USB-serial, plus
  break-signal support.
- SSH passwords are held in memory only and cleared on disconnect;
  no on-disk session store.

---

## Quick start

### Install

```bash
git clone https://github.com/RFingAdam/mcp-remote-access.git
cd mcp-remote-access
uv pip install -e .
```

### Run it

The server speaks MCP over stdio:

```bash
uv run --directory /path/to/mcp-remote-access mcp-remote-access
```

### Add it to an MCP client

Codex CLI:

```bash
codex mcp add remote-access -- \
  uv run --directory /path/to/mcp-remote-access mcp-remote-access
```

Claude Code:

```bash
claude mcp add remote-access -- \
  uv run --directory /path/to/mcp-remote-access mcp-remote-access
```

Or add it to a client config file directly:

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

Then, from the assistant:

> *"Connect to my Pi at vpn-ap.local as `pi` (password `raspberry`), run
> `uname -a`, then `dmesg | tail -20`."*

That's `ssh_connect` followed by two `ssh_execute` calls.

---

## Tools

26 MCP tools across two transports. Full reference in [`docs/tools.md`](docs/tools.md).

### SSH (9)

| Tool                       | Purpose                                                              |
| -------------------------- | -------------------------------------------------------------------- |
| `ssh_connect`              | Connect to a host via SSH (password or key auth)                     |
| `ssh_execute`              | Run a command on a connected host (sync)                             |
| `ssh_execute_background`   | Run a long-running command async, returns `task_id`                   |
| `ssh_check_background`     | Check status / collect output of a background command                |
| `ssh_list_background`      | List all active background commands                                  |
| `ssh_upload`               | Upload a file via SFTP                                               |
| `ssh_download`             | Download a file via SFTP                                             |
| `ssh_disconnect`           | Close an SSH connection                                              |
| `ssh_list_connections`     | Show active SSH connections                                          |

### Serial / UART (17)

| Tool                       | Purpose                                                              |
| -------------------------- | -------------------------------------------------------------------- |
| `serial_list_ports`        | List available serial ports (with VID/PID, description, serial #)    |
| `serial_connect`           | Connect by port name                                                 |
| `serial_connect_match`     | Connect by VID / PID / serial / description match                    |
| `serial_esp32_connect`     | ESP32-aware connect (BOOT/RESET sequence, auto-baud)                 |
| `serial_send`              | Send text data (with optional response read + configurable line ending) |
| `serial_send_bytes`        | Send raw bytes as hex (binary protocols — Nordic DTM, HCI, etc.)      |
| `serial_read`              | Read available data                                                  |
| `serial_read_bytes`        | Read raw bytes back as hex                                           |
| `serial_wait_for`          | Wait for a pattern in the incoming stream                            |
| `serial_expect`            | Wait/send step sequences (login prompts, AT flows)                   |
| `serial_send_break`        | Send a break signal                                                  |
| `serial_set_dtr`           | Set DTR line state                                                   |
| `serial_set_rts`           | Set RTS line state                                                   |
| `serial_reset_device`      | Reset device via DTR/RTS sequence                                    |
| `serial_flush`             | Flush serial buffers                                                 |
| `serial_disconnect`        | Close a serial connection                                            |
| `serial_list_connections`  | Show active serial connections                                       |

---

## Workflows

`mcp-remote-access` fits in the following [eng-mcp-suite](https://github.com/RFingAdam/eng-mcp-suite)
workflow bundles:

- **`lab-automation`** — pair with `mcp-rs-spectrum-analyzer`,
  `mcp-rs-siggen`, `copper-mountain-vna-mcp` to fully script a
  bench (DUT login over SSH or UART, lab gear over SCPI).
- **`embedded-bringup`** — `serial_connect_match` + `serial_expect` +
  `ssh_upload` for boot-loader interaction and image flashing.

Part of [eng-mcp-suite](https://github.com/RFingAdam/eng-mcp-suite).
Use in the `lab-automation` workflow bundle.

See the [suite manifest](https://github.com/RFingAdam/eng-mcp-suite/blob/main/manifest.yaml)
for the full list of sibling MCPs and bundle definitions.

---

## Documentation

- [Quick Start](docs/index.md) — install through first call.
- [Tool reference](docs/tools.md) — every MCP tool, every argument.
- [Usage examples](docs/usage.md) — practical end-to-end walkthroughs.
- [Architecture](docs/architecture.md) — how this MCP fits in eng-mcp-suite.

---

## Part of eng-mcp-suite

This server is one piece of [eng-mcp-suite](https://github.com/RFingAdam/eng-mcp-suite),
an umbrella of engineering MCP servers covering RF, EMC, PCB, signal
integrity, EM simulation, and lab test. See the
[full catalog](https://github.com/RFingAdam/eng-mcp-suite#whats-included)
or jump to a sibling:

| Domain                      | Sibling MCPs                                                                 |
| --------------------------- | ---------------------------------------------------------------------------- |
| **RF / Transmission lines** | [lineforge](https://github.com/RFingAdam/lineforge)                          |
| **EMC regulatory**          | [mcp-emc-regulations](https://github.com/RFingAdam/mcp-emc-regulations)      |
| **PCB / SI**                | mcp-pcb-emcopilot *(private — public soon)*                                  |
| **EM simulation**           | mcp-openems, mcp-nec2-antenna *(private — public soon)*                      |
| **Diagrams**                | [drawio-engineering-mcp](https://github.com/RFingAdam/drawio-engineering-mcp) |
| **3D / rendering**          | [mcp-blender](https://github.com/RFingAdam/mcp-blender)                      |
| **Remote access**           | **mcp-remote-access** *(this repo)*                                          |
| **Lab gear**                | [copper-mountain-vna-mcp](https://github.com/RFingAdam/copper-mountain-vna-mcp), mcp-rs-spectrum-analyzer, mcp-rs-siggen, mcp-rs-cmw500 |

---

## Security notes

- SSH passwords are kept **in memory only** and cleared on server
  restart.
- Connections are session-scoped; the server does not persist a
  session store on disk.
- Use SSH keys where possible.
- The MCP server runs over stdio — it only accepts connections from the
  local MCP client, never from the network.

---

## Troubleshooting

**SSH connection issues** — verify the host is reachable
(`ping vpn-ap.local`), that SSH is listening on the target
(`ssh pi@vpn-ap.local` from the same shell), and that credentials are
correct.

**Serial port issues** — check port permissions
(`ls -la /dev/ttyUSB*`), add your user to the `dialout` group
(`sudo usermod -a -G dialout $USER` and re-login), and confirm the
device is present (`dmesg | tail`).

**VID/PID match selects wrong device** — `serial_connect_match` returns
the first hit; pair the match on `description` or `serial_number` to
disambiguate.

---

## Contributing

Contributions are welcome.

1. **Pick a [GitHub issue](https://github.com/RFingAdam/mcp-remote-access/issues)**.
2. **Fork + branch** (`feature/your-thing` or `fix/your-bug`).
3. **Run tests** (`uv run pytest`) if present.
4. **Open a PR** — link the issue, request review.

---

## License

[AGPL-3.0-or-later](LICENSE). Relicensed from Apache-2.0 in v0.2.0 to
align with the eng-mcp-suite toolkit-wide AGPL move.

## Acknowledgments

- **[paramiko](https://www.paramiko.org/)** — SSH transport.
- **[pyserial](https://pyserial.readthedocs.io/)** — serial / UART transport.
- **The MCP working group** — for the [Model Context Protocol](https://modelcontextprotocol.io) specification.

<div align="center">

<sub>Part of <a href="https://github.com/RFingAdam/eng-mcp-suite">eng-mcp-suite</a>.</sub>

</div>
