<p align="center">
  <img src="assets/logo.svg" alt="MCP Remote Access" width="400">
</p>

<p align="center">
  <strong>SSH & Serial port access for MCP-compatible clients</strong>
</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#features">Features</a> •
  <a href="#usage-examples">Usage</a>
</p>

---

An MCP server providing SSH and UART/serial port access for MCP-compatible clients (for example, Codex CLI or Claude Code). Enables direct control of remote devices like Raspberry Pi, embedded systems, and IoT devices.

## Features

### SSH Tools
- **ssh_connect** - Connect to remote hosts via SSH (password or key auth)
- **ssh_execute** - Run commands on connected hosts
- **ssh_upload** - Upload files via SFTP
- **ssh_download** - Download files via SFTP
- **ssh_disconnect** - Close connections
- **ssh_list_connections** - Show active connections

### UART/Serial Tools
- **serial_list_ports** - List available serial ports
- **serial_connect** - Connect to a serial port
- **serial_connect_match** - Connect by matching VID/PID/serial/description
- **serial_send** - Send data (with optional response reading and configurable line ending)
- **serial_read** - Read data from port
- **serial_wait_for** - Wait for a specific pattern in output
- **serial_expect** - Wait/send sequences for prompts and AT flows
- **serial_send_break** - Send a break signal
- **serial_set_dtr** - Set DTR line state
- **serial_set_rts** - Set RTS line state
- **serial_reset_device** - Reset devices via DTR/RTS sequences
- **serial_flush** - Flush serial buffers
- **serial_disconnect** - Close connections
- **serial_list_connections** - Show active connections

## Installation

### 1. Clone and install

```bash
git clone https://github.com/RFingAdam/mcp-remote-access.git
cd mcp-remote-access
uv pip install -e .
```

### 2. Add to your MCP client

Codex CLI example:

```bash
codex mcp add remote-access -- uv run --directory /path/to/mcp-remote-access mcp-remote-access
```

Claude Code example:

```bash
claude mcp add remote-access -- uv run --directory /path/to/mcp-remote-access mcp-remote-access
```

If your client uses a config file, set the MCP server command to:

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/path/to/mcp-remote-access", "mcp-remote-access"]
}
```

### 3. Start your client

For example:

```bash
codex
```

```bash
claude
```

## Usage Examples

### SSH to a Raspberry Pi

```
Connect to my Pi at vpn-ap.local with username pi and password raspberry
```

The client will use:
1. `ssh_connect` to establish connection
2. `ssh_execute` to run commands
3. `ssh_upload/download` for file transfers

### Serial Connection to Embedded Device

```
List available serial ports and connect to /dev/ttyUSB0 at 115200 baud
```

The client will use:
1. `serial_list_ports` to show available ports
2. `serial_connect` to establish connection
3. `serial_send` / `serial_read` for communication

```
Connect to the USB serial device with VID 0x10c4 and PID 0xea60 at 115200 baud
```

The client will use:
1. `serial_connect_match` to select the port
2. `serial_send` / `serial_read` for communication

### Serial Prompt Automation

```
Connect to the UART and log in as root (password summit), then wait for a shell prompt
```

The client will use:
1. `serial_connect` or `serial_connect_match` to open the port
2. `serial_expect` to wait for prompts and send responses

## Security Notes

- SSH passwords are passed in memory only, never stored
- Connections are session-based and cleared on server restart
- Use SSH keys when possible for better security
- The server only accepts connections from the local MCP client (stdio transport)

## Troubleshooting

### SSH Connection Issues

- Verify the host is reachable: `ping vpn-ap.local`
- Check SSH is running on target: `ssh pi@vpn-ap.local`
- Ensure credentials are correct

### Serial Port Issues

- Check port permissions: `ls -la /dev/ttyUSB*`
- Add user to dialout group: `sudo usermod -a -G dialout $USER`
- Verify device is connected: `dmesg | tail`

## License

MIT
