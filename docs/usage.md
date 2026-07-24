# Usage

Two practical walkthroughs: bringing up an embedded board over UART,
and running a long-running build on a remote target over SSH. For the
full tool reference, see [Tools](tools.md).

---

## Scenario 1 — embedded board bring-up over UART

You've plugged in a new board (Silicon Labs CP210x USB-serial bridge,
VID `0x10c4`, PID `0xea60`). It boots into a U-Boot prompt at 115200
baud. You want to log in, dump the boot args, and reset cleanly.

### Setup

```bash
git clone https://github.com/RFingAdam/mcp-remote-access.git
cd mcp-remote-access
uv pip install -e .
```

Register with your MCP client (see [`index.md`](index.md)).

### Step 1 — find the right port by VID/PID

> *"List serial ports and connect to the CP210x bridge (VID 0x10c4, PID 0xea60) at 115200 baud."*

The agent calls `serial_list_ports` (sees three /dev/ttyUSB* devices),
then `serial_connect_match`:

```json
{ "vid": 4292, "pid": 60000, "baudrate": 115200 }
```

(0x10c4 = 4292; 0xea60 = 60000.) Returns `connection_id: "/dev/ttyUSB0@115200"`.

### Step 2 — log in and read boot args

> *"Log in as `root` (password `changeme`) and capture `printenv`."*

`serial_expect`:

```json
{
  "connection_id": "/dev/ttyUSB0@115200",
  "steps": [
    { "wait_for": "login:",    "send": "root\n" },
    { "wait_for": "Password:", "send": "changeme\n" },
    { "wait_for": "[#$] ",     "send": "printenv\n" },
    { "wait_for": "[#$] ",     "send": "" }
  ],
  "default_timeout": 15
}
```

The captured output comes back as a structured response.

### Step 3 — reset the board cleanly

> *"Reset the device and disconnect."*

`serial_reset_device` pulses DTR; `serial_disconnect` closes the
port. Done.

---

## Scenario 2 — remote build with background SSH

You're cross-compiling on a beefy build server (`build.lab.local`).
The build takes ~8 minutes. You don't want to block the MCP channel.

### Step 1 — connect

> *"SSH into build.lab.local as `ci` with my key."*

```json
{ "host": "build.lab.local", "username": "ci",
  "key_path": "/home/me/.ssh/id_ed25519" }
```

Returns `connection_id: "ci@build.lab.local:22"`.

### Step 2 — kick off the build async

> *"Start `make -j16 release` in `/srv/build/firmware`."*

```json
{
  "connection_id": "ci@build.lab.local:22",
  "command": "cd /srv/build/firmware && make -j16 release"
}
```

via `ssh_execute_background` — returns a `task_id` (e.g.
`bg_1748812345_0`) and the PID. The MCP channel is free for other
tools.

### Step 3 — poll until done

The agent calls `ssh_check_background` every ~60 s while doing other
work (running tests on the bench, drafting docs, …). Eventually the
`Status:` line in the response flips from `RUNNING` to `COMPLETED`,
with the tail of the build log attached.

### Step 4 — pull the artifact

> *"Download `/srv/build/firmware/build/firmware-2026.05.bin` to `./fw/`."*

`ssh_download`. Done.

---

## What just happened

Two transports, four real workflows: VID/PID port match, prompt-aware
UART login, async SSH build, SFTP pull. The MCP server stays thin — the
agent does the routing.

- For more tools: [Tool reference](tools.md)
- For how this fits in the suite: [Architecture](architecture.md)
- For sibling MCPs: [eng-mcp-suite catalog](https://github.com/RFingAdam/eng-mcp-suite#whats-included)
