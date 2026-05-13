# Tools

`mcp-remote-access` exposes 24 MCP tools. Tools are registered under
the `remote-access` namespace when the server is loaded by an MCP
client. Tool source lives in
[`src/mcp_remote_access/server.py`](https://github.com/RFingAdam/mcp-remote-access/blob/main/src/mcp_remote_access/server.py).

## Tool index

### SSH (9)

| Tool                       | Purpose                                                              |
| -------------------------- | -------------------------------------------------------------------- |
| [`ssh_connect`](#ssh_connect)                       | Connect to a host (password or key auth)      |
| [`ssh_execute`](#ssh_execute)                       | Run a command synchronously                   |
| [`ssh_execute_background`](#ssh_execute_background) | Run a command async, returns `job_id`         |
| [`ssh_check_background`](#ssh_check_background)     | Poll status / output of a background command  |
| [`ssh_list_background`](#ssh_list_background)       | List all active background commands           |
| [`ssh_upload`](#ssh_upload)                         | Upload via SFTP                               |
| [`ssh_download`](#ssh_download)                     | Download via SFTP                             |
| [`ssh_disconnect`](#ssh_disconnect)                 | Close a connection                            |
| [`ssh_list_connections`](#ssh_list_connections)     | Show active SSH connections                   |

### Serial / UART (15)

| Tool                       | Purpose                                                              |
| -------------------------- | -------------------------------------------------------------------- |
| [`serial_list_ports`](#serial_list_ports)           | List available serial ports (with VID/PID)    |
| [`serial_connect`](#serial_connect)                 | Connect by port name                          |
| [`serial_connect_match`](#serial_connect_match)     | Connect by VID/PID/serial/description match   |
| [`serial_esp32_connect`](#serial_esp32_connect)     | ESP32-aware connect (BOOT/RESET sequence)     |
| [`serial_send`](#serial_send)                       | Send data + optional response                 |
| [`serial_read`](#serial_read)                       | Read available data                           |
| [`serial_wait_for`](#serial_wait_for)               | Wait for a pattern in stream                  |
| [`serial_expect`](#serial_expect)                   | Expect / send sequences (AT, login)           |
| [`serial_send_break`](#serial_send_break)           | Send break                                    |
| [`serial_set_dtr`](#serial_set_dtr)                 | Set DTR line                                  |
| [`serial_set_rts`](#serial_set_rts)                 | Set RTS line                                  |
| [`serial_reset_device`](#serial_reset_device)       | Reset via DTR/RTS                             |
| [`serial_flush`](#serial_flush)                     | Flush buffers                                 |
| [`serial_disconnect`](#serial_disconnect)           | Close a serial connection                     |
| [`serial_list_connections`](#serial_list_connections) | Show active serial connections              |

---

## `ssh_connect`

Connect to a remote host via SSH.

**Arguments**

| Name           | Type   | Default | Description                                          |
| -------------- | ------ | ------- | ---------------------------------------------------- |
| `host`         | string | —       | Hostname or IP                                       |
| `username`     | string | —       | Login user                                           |
| `password`     | string | `null`  | Password (in-memory only)                            |
| `key_path`     | string | `null`  | Path to private key                                  |
| `key_passphrase` | string | `null`  | Optional passphrase for the key                    |
| `port`         | int    | `22`    | SSH port                                             |
| `connection_id`| string | auto    | Override the returned id                             |

**Returns** `connection_id` for use with subsequent `ssh_*` tools.

## `ssh_execute`

Run a shell command on a connected host.

**Arguments**

| Name            | Type   | Default | Description                                          |
| --------------- | ------ | ------- | ---------------------------------------------------- |
| `connection_id` | string | —       | From `ssh_connect`                                   |
| `command`       | string | —       | Shell command                                        |
| `timeout`       | int    | `30`    | Seconds                                              |

**Returns** `stdout`, `stderr`, `exit_code`.

## `ssh_execute_background`

Run a long-running command without blocking the MCP channel.

**Arguments** — same as `ssh_execute`, returns a `job_id`.

## `ssh_check_background`

Poll a background command. **Arguments**: `job_id`. **Returns** `status`
(`running` / `done` / `error`), accumulated `stdout` / `stderr`, and
`exit_code` once done.

## `ssh_list_background`

No arguments. Returns the list of background jobs across all
connections.

## `ssh_upload` / `ssh_download`

SFTP put / get.

**Arguments**: `connection_id`, `local_path`, `remote_path`.

## `ssh_disconnect`

Close a connection. **Arguments**: `connection_id`.

## `ssh_list_connections`

No arguments. Returns the active connection list.

---

## `serial_list_ports`

List available serial ports. **No arguments.** **Returns** array of
`{ device, description, hwid, vid, pid, serial_number }`.

## `serial_connect`

Open a serial port by device name.

**Arguments**

| Name            | Type   | Default | Description                                          |
| --------------- | ------ | ------- | ---------------------------------------------------- |
| `port`          | string | —       | `/dev/ttyUSB0` (Linux) / `COM3` (Windows)            |
| `baud`          | int    | `115200`| Baud rate                                            |
| `parity`        | string | `"N"`   | `"N"`, `"E"`, `"O"`                                  |
| `stopbits`      | int    | `1`     | 1 or 2                                               |
| `bytesize`      | int    | `8`     | 7 or 8                                               |
| `timeout`       | float  | `1.0`   | Read timeout (s)                                     |
| `connection_id` | string | auto    | Override the returned id                             |

## `serial_connect_match`

Open a serial port by matching VID / PID / serial / description (instead
of guessing `/dev/ttyUSB*`).

**Arguments**

| Name           | Type   | Default | Description                                          |
| -------------- | ------ | ------- | ---------------------------------------------------- |
| `vid`          | int    | `null`  | USB vendor ID (e.g. `0x10c4`)                        |
| `pid`          | int    | `null`  | USB product ID (e.g. `0xea60`)                       |
| `serial_number`| string | `null`  | USB serial number                                    |
| `description`  | string | `null`  | Substring match on description                       |
| Plus all `serial_connect` baud / parity / timeout args.                  |

## `serial_esp32_connect`

ESP32-aware connect that toggles BOOT and RESET via DTR/RTS for
flash-friendly entry, with auto-baud probing.

## `serial_send`

Send data. **Arguments**: `connection_id`, `data` (string or bytes),
`line_ending` (`"\n"`, `"\r\n"`, `""`), optional `wait_response_ms`.

## `serial_read`

Read available data. **Arguments**: `connection_id`, optional
`max_bytes`, `timeout`.

## `serial_wait_for`

Wait until a pattern appears in the stream. **Arguments**:
`connection_id`, `pattern` (string or regex), `timeout`.

## `serial_expect`

Run an expect / send sequence — list of `{ expect, send }` pairs.

```json
{
  "connection_id": "uart-1",
  "sequence": [
    { "expect": "login:",    "send": "root\n" },
    { "expect": "Password:", "send": "summit\n" },
    { "expect": "[#$] ",     "send": "uname -a\n" }
  ],
  "timeout": 10
}
```

## `serial_send_break`

Send a break signal. **Arguments**: `connection_id`, `duration_ms`.

## `serial_set_dtr` / `serial_set_rts`

Set the DTR / RTS line state. **Arguments**: `connection_id`,
`state` (`true` / `false`).

## `serial_reset_device`

Pulse DTR (and optionally RTS) to reset an MCU. **Arguments**:
`connection_id`, optional `hold_ms`, `dtr_polarity`, `rts_polarity`.

## `serial_flush`

Flush input / output buffers. **Arguments**: `connection_id`,
optional `direction` (`"input"` / `"output"` / `"both"`).

## `serial_disconnect` / `serial_list_connections`

Close a connection / list active connections.
