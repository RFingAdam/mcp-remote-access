# MCP Remote Access

An MCP server providing SSH and UART/serial port access for Claude Code. Enables direct control of remote devices like Raspberry Pi, embedded systems, and IoT devices.

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
- **serial_send** - Send data (with optional response reading)
- **serial_read** - Read data from port
- **serial_disconnect** - Close connections
- **serial_list_connections** - Show active connections

## Installation

### 1. Install with uv (recommended)

```bash
cd /home/swamp/projects/github/mcp-remote-access
uv pip install -e .
```

Or install dependencies directly:

```bash
uv pip install mcp paramiko pyserial
```

### 2. Add to Claude Code

Add this to your Claude Code MCP settings (`~/.claude/claude_desktop_config.json` or via `claude mcp add`):

```bash
claude mcp add remote-access -- uv run --directory /home/swamp/projects/github/mcp-remote-access mcp-remote-access
```

Or manually edit `~/.claude.json`:

```json
{
  "mcpServers": {
    "remote-access": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/home/swamp/projects/github/mcp-remote-access",
        "mcp-remote-access"
      ]
    }
  }
}
```

### 3. Restart Claude Code

```bash
claude
```

## Usage Examples

### SSH to a Raspberry Pi

```
Claude, connect to my Pi at vpn-ap.local with username pi and password raspberry
```

Claude will use:
1. `ssh_connect` to establish connection
2. `ssh_execute` to run commands
3. `ssh_upload/download` for file transfers

### Serial Connection to Embedded Device

```
Claude, list available serial ports and connect to /dev/ttyUSB0 at 115200 baud
```

Claude will use:
1. `serial_list_ports` to show available ports
2. `serial_connect` to establish connection
3. `serial_send` / `serial_read` for communication

## Security Notes

- SSH passwords are passed in memory only, never stored
- Connections are session-based and cleared on server restart
- Use SSH keys when possible for better security
- The server only accepts connections from Claude Code (localhost)

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
