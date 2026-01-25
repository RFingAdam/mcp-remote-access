#!/usr/bin/env python3
"""MCP server providing SSH and UART remote access tools for IoT/embedded development."""

import asyncio
import concurrent.futures
import os
import time
from typing import Any

import paramiko
import serial
import serial.tools.list_ports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# Store active connections
ssh_connections: dict[str, paramiko.SSHClient] = {}
serial_connections: dict[str, serial.Serial] = {}
# Store background task info: {task_id: {"connection_id": str, "output_file": str, "pid": int}}
ssh_background_tasks: dict[str, dict[str, Any]] = {}

# Thread pool with limited workers to prevent resource exhaustion
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)


async def run_with_timeout(func, timeout: float, *args, **kwargs):
    """Run a blocking function in executor with proper timeout handling."""
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_executor, lambda: func(*args, **kwargs)),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        raise TimeoutError(f"Operation timed out after {timeout}s")
    except asyncio.CancelledError:
        raise


def check_ssh_connection(client: paramiko.SSHClient) -> bool:
    """Check if SSH connection is still alive."""
    try:
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            return False
        # Send keepalive to verify connection
        transport.send_ignore()
        return True
    except Exception:
        return False


def configure_ssh_keepalive(client: paramiko.SSHClient):
    """Configure SSH keepalive to prevent stale connections."""
    transport = client.get_transport()
    if transport:
        transport.set_keepalive(30)  # Send keepalive every 30 seconds


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("mcp-remote-access")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available tools."""
        return [
            # SSH Tools
            Tool(
                name="ssh_connect",
                description="Connect to a remote host via SSH. Returns a connection ID for subsequent commands.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "host": {
                            "type": "string",
                            "description": "Hostname or IP address (e.g., 'vpn-ap.local' or '192.168.1.100')",
                        },
                        "username": {
                            "type": "string",
                            "description": "SSH username",
                        },
                        "password": {
                            "type": "string",
                            "description": "SSH password (optional if using key)",
                        },
                        "key_path": {
                            "type": "string",
                            "description": "Path to SSH private key file (optional)",
                        },
                        "port": {
                            "type": "integer",
                            "description": "SSH port (default: 22)",
                            "default": 22,
                        },
                    },
                    "required": ["host", "username"],
                },
            ),
            Tool(
                name="ssh_execute",
                description="Execute a command on a connected SSH host. Returns stdout, stderr, and exit code.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from ssh_connect",
                        },
                        "command": {
                            "type": "string",
                            "description": "Command to execute",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Command timeout in seconds (default: 30)",
                            "default": 30,
                        },
                    },
                    "required": ["connection_id", "command"],
                },
            ),
            Tool(
                name="ssh_upload",
                description="Upload a file to the remote host via SFTP.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from ssh_connect",
                        },
                        "local_path": {
                            "type": "string",
                            "description": "Local file path to upload",
                        },
                        "remote_path": {
                            "type": "string",
                            "description": "Remote destination path",
                        },
                    },
                    "required": ["connection_id", "local_path", "remote_path"],
                },
            ),
            Tool(
                name="ssh_download",
                description="Download a file from the remote host via SFTP.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from ssh_connect",
                        },
                        "remote_path": {
                            "type": "string",
                            "description": "Remote file path to download",
                        },
                        "local_path": {
                            "type": "string",
                            "description": "Local destination path",
                        },
                    },
                    "required": ["connection_id", "remote_path", "local_path"],
                },
            ),
            Tool(
                name="ssh_disconnect",
                description="Close an SSH connection.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID to disconnect",
                        },
                    },
                    "required": ["connection_id"],
                },
            ),
            Tool(
                name="ssh_list_connections",
                description="List all active SSH connections.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="ssh_execute_background",
                description="Execute a long-running command in the background. Returns a task ID and output file path. Use ssh_check_background to monitor progress.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from ssh_connect",
                        },
                        "command": {
                            "type": "string",
                            "description": "Command to execute in background",
                        },
                    },
                    "required": ["connection_id", "command"],
                },
            ),
            Tool(
                name="ssh_check_background",
                description="Check status and get output from a background command. Returns whether it's still running and the latest output.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "Task ID from ssh_execute_background",
                        },
                        "tail_lines": {
                            "type": "integer",
                            "description": "Number of lines to return from the end of output (default: 50)",
                            "default": 50,
                        },
                    },
                    "required": ["task_id"],
                },
            ),
            Tool(
                name="ssh_list_background",
                description="List all background tasks and their status.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            # UART/Serial Tools
            Tool(
                name="serial_list_ports",
                description="List available serial ports on the system.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="serial_connect",
                description="Connect to a serial port. Returns a connection ID.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "port": {
                            "type": "string",
                            "description": "Serial port (e.g., '/dev/ttyUSB0' or 'COM3')",
                        },
                        "baudrate": {
                            "type": "integer",
                            "description": "Baud rate (default: 115200)",
                            "default": 115200,
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Read timeout in seconds (default: 1.0)",
                            "default": 1.0,
                        },
                    },
                    "required": ["port"],
                },
            ),
            Tool(
                name="serial_connect_match",
                description="Connect to a serial port by matching VID/PID/serial/description. Returns a connection ID.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "vid": {
                            "type": "integer",
                            "description": "USB vendor ID (e.g., 0x0403 or 1027)",
                        },
                        "pid": {
                            "type": "integer",
                            "description": "USB product ID (e.g., 0x6001 or 24577)",
                        },
                        "serial_number": {
                            "type": "string",
                            "description": "USB serial number (exact match)",
                        },
                        "description_contains": {
                            "type": "string",
                            "description": "Substring match in port description",
                        },
                        "hwid_contains": {
                            "type": "string",
                            "description": "Substring match in HWID",
                        },
                        "port_contains": {
                            "type": "string",
                            "description": "Substring match in device path (e.g., ttyUSB)",
                        },
                        "baudrate": {
                            "type": "integer",
                            "description": "Baud rate (default: 115200)",
                            "default": 115200,
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Read timeout in seconds (default: 1.0)",
                            "default": 1.0,
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="serial_send",
                description="Send data to a serial port. Optionally wait for and return response.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from serial_connect",
                        },
                        "data": {
                            "type": "string",
                            "description": "Data to send (newline added automatically unless raw=true)",
                        },
                        "raw": {
                            "type": "boolean",
                            "description": "Send raw data without adding newline (default: false)",
                            "default": False,
                        },
                        "line_ending": {
                            "type": "string",
                            "description": "Line ending to append when raw=false: 'lf', 'cr', 'crlf', or 'none' (default: 'lf')",
                            "default": "lf",
                        },
                        "read_response": {
                            "type": "boolean",
                            "description": "Wait and read response after sending (default: true)",
                            "default": True,
                        },
                        "read_timeout": {
                            "type": "number",
                            "description": "Timeout for reading response in seconds (default: 2.0)",
                            "default": 2.0,
                        },
                    },
                    "required": ["connection_id", "data"],
                },
            ),
            Tool(
                name="serial_read",
                description="Read available data from a serial port.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from serial_connect",
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Read timeout in seconds (default: 2.0)",
                            "default": 2.0,
                        },
                        "bytes": {
                            "type": "integer",
                            "description": "Maximum bytes to read (default: 4096)",
                            "default": 4096,
                        },
                    },
                    "required": ["connection_id"],
                },
            ),
            Tool(
                name="serial_disconnect",
                description="Close a serial port connection.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID to disconnect",
                        },
                    },
                    "required": ["connection_id"],
                },
            ),
            Tool(
                name="serial_list_connections",
                description="List all active serial connections.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            # NEW: Hardware control tools for embedded development
            Tool(
                name="serial_set_dtr",
                description="Set DTR (Data Terminal Ready) line state. Used for device reset on many boards.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from serial_connect",
                        },
                        "state": {
                            "type": "boolean",
                            "description": "DTR state (true=high, false=low)",
                        },
                    },
                    "required": ["connection_id", "state"],
                },
            ),
            Tool(
                name="serial_set_rts",
                description="Set RTS (Request To Send) line state. Used for bootloader entry on ESP32/STM32.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from serial_connect",
                        },
                        "state": {
                            "type": "boolean",
                            "description": "RTS state (true=high, false=low)",
                        },
                    },
                    "required": ["connection_id", "state"],
                },
            ),
            Tool(
                name="serial_reset_device",
                description="Reset an embedded device using DTR/RTS sequence. Supports ESP32, STM32, and generic reset.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from serial_connect",
                        },
                        "method": {
                            "type": "string",
                            "description": "Reset method: 'esp32' (into app), 'esp32_bootloader' (into bootloader), 'stm32', 'dtr_pulse', 'rts_pulse'",
                            "enum": ["esp32", "esp32_bootloader", "stm32", "dtr_pulse", "rts_pulse"],
                            "default": "dtr_pulse",
                        },
                    },
                    "required": ["connection_id"],
                },
            ),
            Tool(
                name="serial_flush",
                description="Flush serial buffers (clear pending input/output data).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from serial_connect",
                        },
                        "input": {
                            "type": "boolean",
                            "description": "Flush input buffer (default: true)",
                            "default": True,
                        },
                        "output": {
                            "type": "boolean",
                            "description": "Flush output buffer (default: true)",
                            "default": True,
                        },
                    },
                    "required": ["connection_id"],
                },
            ),
            Tool(
                name="serial_wait_for",
                description="Wait for a specific string/pattern in serial output. Useful for boot messages, prompts.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from serial_connect",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "String to wait for in output",
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Maximum time to wait in seconds (default: 30)",
                            "default": 30.0,
                        },
                    },
                    "required": ["connection_id", "pattern"],
                },
            ),
            Tool(
                name="serial_expect",
                description="Wait for patterns and optionally send responses. Useful for login prompts and AT flows.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from serial_connect",
                        },
                        "steps": {
                            "type": "array",
                            "description": "Sequence of steps (each with wait_for and/or send)",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "wait_for": {
                                        "type": "string",
                                        "description": "Pattern to wait for before sending",
                                    },
                                    "send": {
                                        "type": "string",
                                        "description": "Data to send after wait_for (if provided)",
                                    },
                                    "raw": {
                                        "type": "boolean",
                                        "description": "Send raw data without line ending (default: false)",
                                        "default": False,
                                    },
                                    "line_ending": {
                                        "type": "string",
                                        "description": "Line ending when raw=false: 'lf', 'cr', 'crlf', or 'none' (default: 'lf')",
                                        "default": "lf",
                                    },
                                    "timeout": {
                                        "type": "number",
                                        "description": "Timeout for wait_for in seconds (default: 30)",
                                        "default": 30.0,
                                    },
                                },
                            },
                        },
                        "flush_input": {
                            "type": "boolean",
                            "description": "Flush input buffer before starting (default: false)",
                            "default": False,
                        },
                        "default_timeout": {
                            "type": "number",
                            "description": "Default timeout for steps without timeout (default: 30)",
                            "default": 30.0,
                        },
                        "default_line_ending": {
                            "type": "string",
                            "description": "Default line ending for sends when raw=false (default: 'lf')",
                            "default": "lf",
                        },
                    },
                    "required": ["connection_id", "steps"],
                },
            ),
            Tool(
                name="serial_send_break",
                description="Send a serial break signal. Used to interrupt U-Boot, enter debug modes.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID from serial_connect",
                        },
                        "duration": {
                            "type": "number",
                            "description": "Break duration in seconds (default: 0.25)",
                            "default": 0.25,
                        },
                    },
                    "required": ["connection_id"],
                },
            ),
            Tool(
                name="serial_esp32_connect",
                description="Connect to ESP32 with automatic reset and boot wait. Handles the ESP32 boot sequence (74880 baud boot messages, then app at 115200). Resets the device and waits for it to be ready.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "port": {
                            "type": "string",
                            "description": "Serial port (e.g., '/dev/ttyUSB0' or 'COM3')",
                        },
                        "baudrate": {
                            "type": "integer",
                            "description": "Baud rate for application (default: 115200)",
                            "default": 115200,
                        },
                        "reset": {
                            "type": "boolean",
                            "description": "Reset ESP32 after connecting (default: true)",
                            "default": True,
                        },
                        "wait_for_boot": {
                            "type": "boolean",
                            "description": "Wait for boot to complete (default: true)",
                            "default": True,
                        },
                        "boot_timeout": {
                            "type": "number",
                            "description": "Timeout waiting for boot in seconds (default: 5)",
                            "default": 5.0,
                        },
                        "ready_pattern": {
                            "type": "string",
                            "description": "Optional pattern to wait for after boot (e.g., 'ready' or prompt)",
                        },
                    },
                    "required": ["port"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if name == "ssh_connect":
                return await handle_ssh_connect(arguments)
            elif name == "ssh_execute":
                return await handle_ssh_execute(arguments)
            elif name == "ssh_upload":
                return await handle_ssh_upload(arguments)
            elif name == "ssh_download":
                return await handle_ssh_download(arguments)
            elif name == "ssh_disconnect":
                return await handle_ssh_disconnect(arguments)
            elif name == "ssh_list_connections":
                return await handle_ssh_list_connections()
            elif name == "ssh_execute_background":
                return await handle_ssh_execute_background(arguments)
            elif name == "ssh_check_background":
                return await handle_ssh_check_background(arguments)
            elif name == "ssh_list_background":
                return await handle_ssh_list_background()
            elif name == "serial_list_ports":
                return await handle_serial_list_ports()
            elif name == "serial_connect":
                return await handle_serial_connect(arguments)
            elif name == "serial_connect_match":
                return await handle_serial_connect_match(arguments)
            elif name == "serial_send":
                return await handle_serial_send(arguments)
            elif name == "serial_read":
                return await handle_serial_read(arguments)
            elif name == "serial_disconnect":
                return await handle_serial_disconnect(arguments)
            elif name == "serial_list_connections":
                return await handle_serial_list_connections()
            # New hardware control tools
            elif name == "serial_set_dtr":
                return await handle_serial_set_dtr(arguments)
            elif name == "serial_set_rts":
                return await handle_serial_set_rts(arguments)
            elif name == "serial_reset_device":
                return await handle_serial_reset_device(arguments)
            elif name == "serial_flush":
                return await handle_serial_flush(arguments)
            elif name == "serial_wait_for":
                return await handle_serial_wait_for(arguments)
            elif name == "serial_expect":
                return await handle_serial_expect(arguments)
            elif name == "serial_send_break":
                return await handle_serial_send_break(arguments)
            elif name == "serial_esp32_connect":
                return await handle_serial_esp32_connect(arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {type(e).__name__}: {str(e)}")]

    return server


# SSH Handlers


async def handle_ssh_connect(args: dict[str, Any]) -> list[TextContent]:
    """Connect to an SSH host."""
    host = args["host"]
    username = args["username"]
    password = args.get("password")
    key_path = args.get("key_path")
    port = args.get("port", 22)

    # Create connection ID
    conn_id = f"{username}@{host}:{port}"

    # Check if already connected and connection is alive
    if conn_id in ssh_connections:
        existing = ssh_connections[conn_id]
        if check_ssh_connection(existing):
            return [TextContent(type="text", text=f"Already connected: {conn_id}")]
        else:
            # Connection is stale, close and reconnect
            try:
                existing.close()
            except Exception:
                pass
            del ssh_connections[conn_id]

    # Create SSH client
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Connect
    connect_kwargs = {
        "hostname": host,
        "port": port,
        "username": username,
        "timeout": 15,
        "allow_agent": True,
        "look_for_keys": True,
        "banner_timeout": 30,
        "auth_timeout": 30,
    }

    if password:
        connect_kwargs["password"] = password
    if key_path:
        connect_kwargs["key_filename"] = os.path.expanduser(key_path)

    # Run in thread pool with timeout
    def do_connect():
        client.connect(**connect_kwargs)
        configure_ssh_keepalive(client)
        return client

    await run_with_timeout(do_connect, timeout=45.0)

    ssh_connections[conn_id] = client

    return [
        TextContent(
            type="text",
            text=f"Connected successfully!\nConnection ID: {conn_id}\nUse this ID for subsequent commands.",
        )
    ]


async def handle_ssh_execute(args: dict[str, Any]) -> list[TextContent]:
    """Execute a command via SSH."""
    conn_id = args["connection_id"]
    command = args["command"]
    timeout = args.get("timeout", 30)

    if conn_id not in ssh_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}\nUse ssh_connect first.")]

    client = ssh_connections[conn_id]

    # Check connection health first
    if not check_ssh_connection(client):
        del ssh_connections[conn_id]
        return [TextContent(type="text", text=f"Connection lost: {conn_id}\nPlease reconnect with ssh_connect.")]

    def execute():
        # Use get_transport for more reliable command execution
        transport = client.get_transport()
        if not transport or not transport.is_active():
            raise ConnectionError("SSH transport is not active")

        channel = transport.open_session()
        channel.settimeout(timeout)
        channel.exec_command(command)

        # Read output with proper timeout handling
        stdout_data = b""
        stderr_data = b""

        # Wait for command to finish with timeout
        start_time = time.time()
        while not channel.exit_status_ready():
            if time.time() - start_time > timeout:
                channel.close()
                raise TimeoutError(f"Command timed out after {timeout}s")

            # Read available data to prevent buffer filling
            if channel.recv_ready():
                stdout_data += channel.recv(65536)
            if channel.recv_stderr_ready():
                stderr_data += channel.recv_stderr(65536)
            time.sleep(0.1)

        # Read remaining data
        while channel.recv_ready():
            stdout_data += channel.recv(65536)
        while channel.recv_stderr_ready():
            stderr_data += channel.recv_stderr(65536)

        exit_code = channel.recv_exit_status()
        channel.close()

        return (
            stdout_data.decode("utf-8", errors="replace"),
            stderr_data.decode("utf-8", errors="replace"),
            exit_code
        )

    try:
        # Add extra buffer time for the async wrapper
        stdout_text, stderr_text, exit_code = await run_with_timeout(execute, timeout=timeout + 10)
    except TimeoutError as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]
    except ConnectionError as e:
        del ssh_connections[conn_id]
        return [TextContent(type="text", text=f"Connection error: {str(e)}\nPlease reconnect.")]

    result = f"Exit code: {exit_code}\n"
    if stdout_text:
        result += f"\n--- STDOUT ---\n{stdout_text}"
    if stderr_text:
        result += f"\n--- STDERR ---\n{stderr_text}"

    return [TextContent(type="text", text=result)]


async def handle_ssh_upload(args: dict[str, Any]) -> list[TextContent]:
    """Upload a file via SFTP."""
    conn_id = args["connection_id"]
    local_path = os.path.expanduser(args["local_path"])
    remote_path = args["remote_path"]

    if conn_id not in ssh_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    if not os.path.exists(local_path):
        return [TextContent(type="text", text=f"Local file not found: {local_path}")]

    client = ssh_connections[conn_id]

    if not check_ssh_connection(client):
        del ssh_connections[conn_id]
        return [TextContent(type="text", text=f"Connection lost: {conn_id}\nPlease reconnect.")]

    def upload():
        sftp = client.open_sftp()
        sftp.get_channel().settimeout(60.0)
        sftp.put(local_path, remote_path)
        stat = sftp.stat(remote_path)
        sftp.close()
        return stat.st_size

    try:
        size = await run_with_timeout(upload, timeout=120.0)
    except TimeoutError:
        return [TextContent(type="text", text=f"Upload timed out after 120s")]

    return [TextContent(type="text", text=f"Uploaded successfully!\n{local_path} -> {remote_path}\nSize: {size} bytes")]


async def handle_ssh_download(args: dict[str, Any]) -> list[TextContent]:
    """Download a file via SFTP."""
    conn_id = args["connection_id"]
    remote_path = args["remote_path"]
    local_path = os.path.expanduser(args["local_path"])

    if conn_id not in ssh_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    client = ssh_connections[conn_id]

    if not check_ssh_connection(client):
        del ssh_connections[conn_id]
        return [TextContent(type="text", text=f"Connection lost: {conn_id}\nPlease reconnect.")]

    def download():
        sftp = client.open_sftp()
        sftp.get_channel().settimeout(60.0)
        sftp.get(remote_path, local_path)
        sftp.close()
        return os.path.getsize(local_path)

    try:
        size = await run_with_timeout(download, timeout=120.0)
    except TimeoutError:
        return [TextContent(type="text", text=f"Download timed out after 120s")]

    return [TextContent(type="text", text=f"Downloaded successfully!\n{remote_path} -> {local_path}\nSize: {size} bytes")]


async def handle_ssh_disconnect(args: dict[str, Any]) -> list[TextContent]:
    """Disconnect an SSH session."""
    conn_id = args["connection_id"]

    if conn_id not in ssh_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    client = ssh_connections.pop(conn_id)
    client.close()

    return [TextContent(type="text", text=f"Disconnected: {conn_id}")]


async def handle_ssh_list_connections() -> list[TextContent]:
    """List active SSH connections."""
    if not ssh_connections:
        return [TextContent(type="text", text="No active SSH connections.")]

    lines = ["Active SSH connections:"]
    for conn_id in ssh_connections:
        lines.append(f"  - {conn_id}")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_ssh_execute_background(args: dict[str, Any]) -> list[TextContent]:
    """Execute a command in the background."""
    conn_id = args["connection_id"]
    command = args["command"]

    if conn_id not in ssh_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}\nUse ssh_connect first.")]

    client = ssh_connections[conn_id]

    if not check_ssh_connection(client):
        del ssh_connections[conn_id]
        return [TextContent(type="text", text=f"Connection lost: {conn_id}\nPlease reconnect.")]

    # Generate unique task ID and output file
    task_id = f"bg_{int(time.time())}_{len(ssh_background_tasks)}"
    output_file = f"/tmp/mcp_bg_{task_id}.log"

    # Run command in background with nohup, redirect output to file
    # Escape single quotes in command
    escaped_command = command.replace("'", "'\\''")
    bg_command = f"nohup bash -c '{escaped_command}' > {output_file} 2>&1 & echo $!"

    def execute():
        stdin, stdout, stderr = client.exec_command(bg_command, timeout=30)
        pid = stdout.read().decode("utf-8", errors="replace").strip()
        return pid

    try:
        pid = await run_with_timeout(execute, timeout=45.0)

        ssh_background_tasks[task_id] = {
            "connection_id": conn_id,
            "output_file": output_file,
            "pid": pid,
            "command": command[:100] + "..." if len(command) > 100 else command,
            "started": time.time(),
        }

        return [
            TextContent(
                type="text",
                text=f"Background task started!\nTask ID: {task_id}\nPID: {pid}\nOutput file: {output_file}\n\nUse ssh_check_background with task_id='{task_id}' to monitor progress.",
            )
        ]
    except Exception as e:
        return [TextContent(type="text", text=f"Failed to start background task: {str(e)}")]


async def handle_ssh_check_background(args: dict[str, Any]) -> list[TextContent]:
    """Check status of a background task."""
    task_id = args["task_id"]
    tail_lines = args.get("tail_lines", 50)

    if task_id not in ssh_background_tasks:
        return [TextContent(type="text", text=f"Unknown task: {task_id}\nUse ssh_list_background to see active tasks.")]

    task = ssh_background_tasks[task_id]
    conn_id = task["connection_id"]

    if conn_id not in ssh_connections:
        return [TextContent(type="text", text=f"Connection lost: {conn_id}")]

    client = ssh_connections[conn_id]

    if not check_ssh_connection(client):
        del ssh_connections[conn_id]
        return [TextContent(type="text", text=f"Connection lost: {conn_id}\nPlease reconnect.")]

    def check_status():
        # Check if process is still running
        stdin, stdout, stderr = client.exec_command(f"ps -p {task['pid']} -o pid= 2>/dev/null", timeout=10)
        is_running = bool(stdout.read().decode("utf-8", errors="replace").strip())

        # Get tail of output file
        stdin, stdout, stderr = client.exec_command(f"tail -n {tail_lines} {task['output_file']} 2>/dev/null", timeout=30)
        output = stdout.read().decode("utf-8", errors="replace")

        # Get file size
        stdin, stdout, stderr = client.exec_command(f"wc -l {task['output_file']} 2>/dev/null | cut -d' ' -f1", timeout=10)
        total_lines = stdout.read().decode("utf-8", errors="replace").strip()

        return is_running, output, total_lines

    try:
        is_running, output, total_lines = await run_with_timeout(check_status, timeout=60.0)

        status = "RUNNING" if is_running else "COMPLETED"
        elapsed = int(time.time() - task["started"])
        elapsed_str = f"{elapsed // 60}m {elapsed % 60}s"

        result = f"Task: {task_id}\n"
        result += f"Status: {status}\n"
        result += f"PID: {task['pid']}\n"
        result += f"Elapsed: {elapsed_str}\n"
        result += f"Total lines: {total_lines}\n"
        result += f"Command: {task['command']}\n"
        result += f"\n--- Last {tail_lines} lines ---\n{output}"

        return [TextContent(type="text", text=result)]
    except TimeoutError:
        return [TextContent(type="text", text=f"Timeout checking task status")]
    except Exception as e:
        return [TextContent(type="text", text=f"Failed to check task status: {str(e)}")]


async def handle_ssh_list_background() -> list[TextContent]:
    """List all background tasks."""
    if not ssh_background_tasks:
        return [TextContent(type="text", text="No background tasks.")]

    lines = ["Background tasks:"]
    for task_id, task in ssh_background_tasks.items():
        elapsed = int(time.time() - task["started"])
        elapsed_str = f"{elapsed // 60}m {elapsed % 60}s"
        lines.append(f"  - {task_id}: PID {task['pid']} ({elapsed_str}) - {task['command']}")

    return [TextContent(type="text", text="\n".join(lines))]


# Serial Handlers


LINE_ENDINGS = {
    "lf": "\n",
    "cr": "\r",
    "crlf": "\r\n",
    "none": "",
}


def normalize_line_ending(line_ending: str | None) -> str:
    """Normalize line ending names to actual characters."""
    if line_ending is None:
        return LINE_ENDINGS["lf"]
    if line_ending in ("\n", "\r", "\r\n", ""):
        return line_ending
    key = line_ending.lower()
    if key in LINE_ENDINGS:
        return LINE_ENDINGS[key]
    raise ValueError("line_ending must be one of: lf, cr, crlf, none")


def prepare_serial_payload(data: str, raw: bool, line_ending: str | None) -> str:
    """Prepare serial payload with optional line ending."""
    if raw:
        return data
    return data + normalize_line_ending(line_ending)


def describe_serial_port(port) -> list[str]:
    """Format port details for display."""
    lines = [f"  - {port.device}: {port.description}"]
    if port.hwid:
        lines.append(f"    HWID: {port.hwid}")
    if port.vid is not None and port.pid is not None:
        lines.append(f"    VID:PID: {port.vid:04x}:{port.pid:04x}")
    if port.serial_number:
        lines.append(f"    SERIAL: {port.serial_number}")
    return lines


def wait_for_serial_pattern(ser: serial.Serial, pattern: str, timeout: float) -> tuple[bool, str]:
    """Wait for a pattern in serial output."""
    buffer = ""
    deadline = time.time() + timeout
    old_timeout = ser.timeout
    ser.timeout = 0.1

    try:
        while time.time() < deadline:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting)
                if chunk:
                    buffer += chunk.decode("utf-8", errors="replace")
                    if pattern in buffer:
                        return True, buffer
            time.sleep(0.05)
    finally:
        ser.timeout = old_timeout

    return False, buffer


def open_serial_connection(port: str, baudrate: int, timeout: float) -> serial.Serial:
    """Open a serial port and clear buffers."""
    ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return ser


async def handle_serial_list_ports() -> list[TextContent]:
    """List available serial ports."""
    ports = serial.tools.list_ports.comports()

    if not ports:
        return [TextContent(type="text", text="No serial ports found.")]

    lines = ["Available serial ports:"]
    for port in ports:
        lines.extend(describe_serial_port(port))

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_serial_connect(args: dict[str, Any]) -> list[TextContent]:
    """Connect to a serial port."""
    port = args["port"]
    baudrate = args.get("baudrate", 115200)
    timeout = args.get("timeout", 1.0)

    conn_id = f"{port}@{baudrate}"

    if conn_id in serial_connections:
        existing = serial_connections[conn_id]
        if existing.is_open:
            return [TextContent(type="text", text=f"Already connected: {conn_id}")]
        else:
            del serial_connections[conn_id]

    def connect():
        return open_serial_connection(port, baudrate, timeout)

    try:
        ser = await run_with_timeout(connect, timeout=15.0)
    except TimeoutError:
        return [TextContent(type="text", text=f"Timeout connecting to {port}")]

    serial_connections[conn_id] = ser

    return [
        TextContent(
            type="text",
            text=f"Connected successfully!\nConnection ID: {conn_id}\nPort: {port}\nBaudrate: {baudrate}",
        )
    ]


async def handle_serial_connect_match(args: dict[str, Any]) -> list[TextContent]:
    """Connect to a serial port by matching port attributes."""
    baudrate = args.get("baudrate", 115200)
    timeout = args.get("timeout", 1.0)
    serial_number = args.get("serial_number")
    description_contains = args.get("description_contains")
    hwid_contains = args.get("hwid_contains")
    port_contains = args.get("port_contains")

    def parse_int(value: Any, name: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value, 0)
            except ValueError as exc:
                raise ValueError(f"{name} must be an int or hex string") from exc
        raise ValueError(f"{name} must be an int or hex string")

    vid = parse_int(args.get("vid"), "vid")
    pid = parse_int(args.get("pid"), "pid")

    if not any([vid, pid, serial_number, description_contains, hwid_contains, port_contains]):
        return [
            TextContent(
                type="text",
                text="Provide at least one match field: vid, pid, serial_number, description_contains, hwid_contains, or port_contains.",
            )
        ]

    ports = serial.tools.list_ports.comports()
    if not ports:
        return [TextContent(type="text", text="No serial ports found.")]

    matches = []
    for port in ports:
        if vid is not None and port.vid != vid:
            continue
        if pid is not None and port.pid != pid:
            continue
        if serial_number and (port.serial_number or "") != serial_number:
            continue
        if description_contains and description_contains.lower() not in (port.description or "").lower():
            continue
        if hwid_contains and hwid_contains.lower() not in (port.hwid or "").lower():
            continue
        if port_contains and port_contains.lower() not in (port.device or "").lower():
            continue
        matches.append(port)

    if not matches:
        lines = ["No matching serial ports found.", "Available serial ports:"]
        for port in ports:
            lines.extend(describe_serial_port(port))
        return [TextContent(type="text", text="\n".join(lines))]

    if len(matches) > 1:
        lines = ["Multiple matching serial ports found. Refine your match criteria:"]
        for port in matches:
            lines.extend(describe_serial_port(port))
        return [TextContent(type="text", text="\n".join(lines))]

    selected = matches[0]
    port_name = selected.device
    conn_id = f"{port_name}@{baudrate}"

    if conn_id in serial_connections:
        return [TextContent(type="text", text=f"Already connected: {conn_id}")]

    loop = asyncio.get_event_loop()

    def connect():
        return open_serial_connection(port_name, baudrate, timeout)

    ser = await loop.run_in_executor(None, connect)
    serial_connections[conn_id] = ser

    details = "\n".join(describe_serial_port(selected))
    return [
        TextContent(
            type="text",
            text=(
                "Connected successfully!\n"
                f"Connection ID: {conn_id}\n"
                f"Port: {port_name}\n"
                f"Baudrate: {baudrate}\n"
                f"{details}"
            ),
        )
    ]


async def handle_serial_send(args: dict[str, Any]) -> list[TextContent]:
    """Send data to a serial port."""
    conn_id = args["connection_id"]
    data = args["data"]
    raw = args.get("raw", False)
    line_ending = args.get("line_ending", "lf")
    read_response = args.get("read_response", True)
    read_timeout = args.get("read_timeout", 2.0)

    if conn_id not in serial_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    ser = serial_connections[conn_id]

    if not ser.is_open:
        del serial_connections[conn_id]
        return [TextContent(type="text", text=f"Connection closed: {conn_id}")]

    payload = prepare_serial_payload(data, raw, line_ending)

    def send_and_read():
        # Clear input buffer before sending to get fresh response
        ser.reset_input_buffer()

        ser.write(payload.encode("utf-8"))
        ser.flush()

        if read_response:
            # Wait a bit for device to process and respond
            time.sleep(0.1)

            # Set temporary timeout
            old_timeout = ser.timeout
            ser.timeout = read_timeout

            response = b""
            deadline = time.time() + read_timeout

            # Read with timeout - don't loop forever
            while time.time() < deadline:
                # Check how much data is waiting
                waiting = ser.in_waiting
                if waiting > 0:
                    chunk = ser.read(waiting)
                    if chunk:
                        response += chunk
                    # Small delay to allow more data to arrive
                    time.sleep(0.05)
                else:
                    # No data waiting, check if we have anything
                    if response:
                        # Wait a bit more to see if more comes
                        time.sleep(0.1)
                        if ser.in_waiting == 0:
                            break  # No more data coming
                    else:
                        # Still waiting for first data
                        time.sleep(0.05)

            ser.timeout = old_timeout
            return response.decode("utf-8", errors="replace")
        return None

    try:
        response = await run_with_timeout(send_and_read, timeout=read_timeout + 5.0)
    except TimeoutError:
        return [TextContent(type="text", text=f"Timeout sending/reading serial data")]

    result = f"Sent: {repr(payload)}"
    if response is not None:
        result += f"\n\n--- Response ---\n{response}"

    return [TextContent(type="text", text=result)]


async def handle_serial_read(args: dict[str, Any]) -> list[TextContent]:
    """Read from a serial port."""
    conn_id = args["connection_id"]
    timeout = args.get("timeout", 2.0)
    max_bytes = args.get("bytes", 4096)

    if conn_id not in serial_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    ser = serial_connections[conn_id]

    if not ser.is_open:
        return [TextContent(type="text", text=f"Connection closed: {conn_id}")]

    loop = asyncio.get_event_loop()

    def read():
        old_timeout = ser.timeout
        ser.timeout = timeout

        response = b""
        deadline = time.time() + timeout

        # Read with timeout - don't block forever
        while time.time() < deadline and len(response) < max_bytes:
            waiting = ser.in_waiting
            if waiting > 0:
                to_read = min(waiting, max_bytes - len(response))
                chunk = ser.read(to_read)
                if chunk:
                    response += chunk
                time.sleep(0.01)
            else:
                if response:
                    # Have some data, wait a bit more
                    time.sleep(0.05)
                    if ser.in_waiting == 0:
                        break
                else:
                    time.sleep(0.05)

        ser.timeout = old_timeout
        return response.decode("utf-8", errors="replace")

    data = await loop.run_in_executor(None, read)

    if not data:
        return [TextContent(type="text", text="No data received (timeout).")]

    return [TextContent(type="text", text=f"Received {len(data)} bytes:\n{data}")]


async def handle_serial_disconnect(args: dict[str, Any]) -> list[TextContent]:
    """Disconnect a serial port."""
    conn_id = args["connection_id"]

    if conn_id not in serial_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    ser = serial_connections.pop(conn_id)
    if ser.is_open:
        ser.close()

    return [TextContent(type="text", text=f"Disconnected: {conn_id}")]


async def handle_serial_list_connections() -> list[TextContent]:
    """List active serial connections."""
    if not serial_connections:
        return [TextContent(type="text", text="No active serial connections.")]

    lines = ["Active serial connections:"]
    for conn_id, ser in serial_connections.items():
        lines.append(f"  - {conn_id} (open={ser.is_open})")

    return [TextContent(type="text", text="\n".join(lines))]


# NEW: Hardware control handlers for embedded development


async def handle_serial_set_dtr(args: dict[str, Any]) -> list[TextContent]:
    """Set DTR line state."""
    conn_id = args["connection_id"]
    state = args["state"]

    if conn_id not in serial_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    ser = serial_connections[conn_id]

    if not ser.is_open:
        return [TextContent(type="text", text=f"Connection closed: {conn_id}")]

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: setattr(ser, 'dtr', state))

    return [TextContent(type="text", text=f"DTR set to {'HIGH' if state else 'LOW'}")]


async def handle_serial_set_rts(args: dict[str, Any]) -> list[TextContent]:
    """Set RTS line state."""
    conn_id = args["connection_id"]
    state = args["state"]

    if conn_id not in serial_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    ser = serial_connections[conn_id]

    if not ser.is_open:
        return [TextContent(type="text", text=f"Connection closed: {conn_id}")]

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: setattr(ser, 'rts', state))

    return [TextContent(type="text", text=f"RTS set to {'HIGH' if state else 'LOW'}")]


async def handle_serial_reset_device(args: dict[str, Any]) -> list[TextContent]:
    """Reset device using DTR/RTS sequence."""
    conn_id = args["connection_id"]
    method = args.get("method", "dtr_pulse")

    if conn_id not in serial_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    ser = serial_connections[conn_id]

    if not ser.is_open:
        return [TextContent(type="text", text=f"Connection closed: {conn_id}")]

    loop = asyncio.get_event_loop()

    def reset_esp32():
        """Reset ESP32 into application mode."""
        ser.dtr = False
        ser.rts = True
        time.sleep(0.1)
        ser.dtr = True
        ser.rts = False
        time.sleep(0.05)
        ser.dtr = False
        time.sleep(0.5)
        ser.reset_input_buffer()

    def reset_esp32_bootloader():
        """Reset ESP32 into bootloader/download mode."""
        ser.dtr = False
        ser.rts = False
        time.sleep(0.1)
        ser.dtr = True  # Hold GPIO0 low
        ser.rts = True  # Assert reset
        time.sleep(0.1)
        ser.rts = False  # Release reset (GPIO0 still low)
        time.sleep(0.4)
        ser.dtr = False  # Release GPIO0
        time.sleep(0.1)

    def reset_stm32():
        """Reset STM32 using DTR."""
        ser.dtr = True
        time.sleep(0.1)
        ser.dtr = False
        time.sleep(0.5)
        ser.reset_input_buffer()

    def reset_dtr_pulse():
        """Generic DTR pulse reset."""
        ser.dtr = True
        time.sleep(0.1)
        ser.dtr = False
        time.sleep(0.3)
        ser.reset_input_buffer()

    def reset_rts_pulse():
        """Generic RTS pulse reset."""
        ser.rts = True
        time.sleep(0.1)
        ser.rts = False
        time.sleep(0.3)
        ser.reset_input_buffer()

    reset_funcs = {
        "esp32": reset_esp32,
        "esp32_bootloader": reset_esp32_bootloader,
        "stm32": reset_stm32,
        "dtr_pulse": reset_dtr_pulse,
        "rts_pulse": reset_rts_pulse,
    }

    if method not in reset_funcs:
        return [TextContent(type="text", text=f"Unknown reset method: {method}")]

    await loop.run_in_executor(None, reset_funcs[method])

    return [TextContent(type="text", text=f"Device reset using method: {method}")]


async def handle_serial_flush(args: dict[str, Any]) -> list[TextContent]:
    """Flush serial buffers."""
    conn_id = args["connection_id"]
    flush_input = args.get("input", True)
    flush_output = args.get("output", True)

    if conn_id not in serial_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    ser = serial_connections[conn_id]

    if not ser.is_open:
        return [TextContent(type="text", text=f"Connection closed: {conn_id}")]

    loop = asyncio.get_event_loop()

    def flush():
        if flush_input:
            ser.reset_input_buffer()
        if flush_output:
            ser.reset_output_buffer()

    await loop.run_in_executor(None, flush)

    flushed = []
    if flush_input:
        flushed.append("input")
    if flush_output:
        flushed.append("output")

    return [TextContent(type="text", text=f"Flushed {' and '.join(flushed)} buffer(s)")]


async def handle_serial_wait_for(args: dict[str, Any]) -> list[TextContent]:
    """Wait for a specific pattern in serial output."""
    conn_id = args["connection_id"]
    pattern = args["pattern"]
    timeout = args.get("timeout", 30.0)

    if conn_id not in serial_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    ser = serial_connections[conn_id]

    if not ser.is_open:
        return [TextContent(type="text", text=f"Connection closed: {conn_id}")]

    loop = asyncio.get_event_loop()

    def wait_for_pattern():
        return wait_for_serial_pattern(ser, pattern, timeout)

    found, buffer = await loop.run_in_executor(None, wait_for_pattern)

    if found:
        return [TextContent(type="text", text=f"Pattern '{pattern}' found!\n\n--- Output ---\n{buffer}")]
    else:
        return [TextContent(type="text", text=f"Timeout waiting for '{pattern}'\n\n--- Output received ---\n{buffer}")]


async def handle_serial_expect(args: dict[str, Any]) -> list[TextContent]:
    """Run a sequence of expect/send steps on a serial connection."""
    conn_id = args["connection_id"]
    steps = args["steps"]
    flush_input = args.get("flush_input", False)
    default_timeout = args.get("default_timeout", 30.0)
    default_line_ending = args.get("default_line_ending", "lf")

    if conn_id not in serial_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    ser = serial_connections[conn_id]

    if not ser.is_open:
        return [TextContent(type="text", text=f"Connection closed: {conn_id}")]

    if not steps:
        return [TextContent(type="text", text="No steps provided.")]

    loop = asyncio.get_event_loop()

    def expect_sequence():
        if flush_input:
            ser.reset_input_buffer()

        output_chunks: list[str] = []
        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                return False, f"Step {idx} must be an object.", "".join(output_chunks)

            pattern = step.get("wait_for")
            send_data = step.get("send")

            if not pattern and send_data is None:
                return False, f"Step {idx} must include wait_for or send.", "".join(output_chunks)

            if pattern:
                timeout = step.get("timeout", default_timeout)
                found, buffer = wait_for_serial_pattern(ser, pattern, timeout)
                output_chunks.append(buffer)
                if not found:
                    return False, f"Timeout waiting for '{pattern}' at step {idx}.", "".join(output_chunks)

            if send_data is not None:
                raw = step.get("raw", False)
                line_ending = step.get("line_ending", default_line_ending)
                payload = prepare_serial_payload(send_data, raw, line_ending)
                ser.write(payload.encode("utf-8"))
                ser.flush()
                time.sleep(0.05)

        return True, f"Serial expect completed ({len(steps)} steps).", "".join(output_chunks)

    ok, message, output = await loop.run_in_executor(None, expect_sequence)

    if output:
        message += f"\n\n--- Output ---\n{output}"

    return [TextContent(type="text", text=message)]


async def handle_serial_send_break(args: dict[str, Any]) -> list[TextContent]:
    """Send a serial break signal."""
    conn_id = args["connection_id"]
    duration = args.get("duration", 0.25)

    if conn_id not in serial_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    ser = serial_connections[conn_id]

    if not ser.is_open:
        return [TextContent(type="text", text=f"Connection closed: {conn_id}")]

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: ser.send_break(duration))

    return [TextContent(type="text", text=f"Break signal sent ({duration}s)")]


async def handle_serial_esp32_connect(args: dict[str, Any]) -> list[TextContent]:
    """Connect to ESP32 with automatic reset and boot wait handling."""
    port = args["port"]
    baudrate = args.get("baudrate", 115200)
    do_reset = args.get("reset", True)
    wait_for_boot = args.get("wait_for_boot", True)
    boot_timeout = args.get("boot_timeout", 5.0)
    ready_pattern = args.get("ready_pattern")

    conn_id = f"{port}@{baudrate}"

    # Close existing connection if present
    if conn_id in serial_connections:
        try:
            serial_connections[conn_id].close()
        except Exception:
            pass
        del serial_connections[conn_id]

    loop = asyncio.get_event_loop()
    status_messages = []

    def connect_and_setup():
        nonlocal status_messages

        # Connect at target baud rate
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=1.0,
            write_timeout=1.0,
        )
        status_messages.append(f"Connected to {port} at {baudrate} baud")

        if do_reset:
            # ESP32 reset sequence: into application mode
            # This uses the same sequence as esptool's hard_reset
            ser.dtr = False
            ser.rts = True
            time.sleep(0.1)
            ser.dtr = True
            ser.rts = False
            time.sleep(0.05)
            ser.dtr = False
            time.sleep(0.1)
            ser.reset_input_buffer()
            status_messages.append("ESP32 reset triggered")

        if wait_for_boot:
            # Wait for boot messages to settle
            # ESP32 outputs boot messages at 74880 baud, which appear as garbage at 115200
            # We wait for them to finish, then look for readable output
            boot_start = time.time()
            boot_complete = False
            garbage_count = 0
            readable_count = 0
            buffer = ""

            while (time.time() - boot_start) < boot_timeout:
                if ser.in_waiting:
                    try:
                        data = ser.read(ser.in_waiting)
                        text = data.decode('utf-8', errors='replace')
                        buffer += text

                        # Count readable vs garbage characters
                        for c in text:
                            if c.isprintable() or c in '\r\n\t':
                                readable_count += 1
                            else:
                                garbage_count += 1

                        # Check for boot completion indicators
                        if 'rst:' in buffer.lower() or 'boot:' in buffer.lower():
                            # ESP32 boot message seen
                            pass

                        # If we see mostly readable output after garbage, boot is complete
                        if garbage_count > 10 and readable_count > garbage_count:
                            boot_complete = True
                            break

                        # If we haven't seen garbage but see readable output
                        if garbage_count == 0 and readable_count > 50:
                            boot_complete = True
                            break

                    except Exception:
                        pass
                else:
                    time.sleep(0.1)

            # Clear any remaining boot garbage
            time.sleep(0.2)
            ser.reset_input_buffer()

            if boot_complete:
                status_messages.append("Boot sequence complete")
            else:
                status_messages.append(f"Boot wait timeout ({boot_timeout}s) - continuing anyway")

        # If ready_pattern specified, wait for it
        if ready_pattern:
            found, output = wait_for_serial_pattern(ser, ready_pattern, boot_timeout)
            if found:
                status_messages.append(f"Ready pattern '{ready_pattern}' found")
            else:
                status_messages.append(f"Ready pattern '{ready_pattern}' not found (timeout)")

        return ser

    try:
        ser = await loop.run_in_executor(None, connect_and_setup)
        serial_connections[conn_id] = ser

        result = f"ESP32 connected successfully!\n"
        result += f"Connection ID: {conn_id}\n"
        result += f"Port: {port}\n"
        result += f"Baudrate: {baudrate}\n"
        result += "\nStatus:\n" + "\n".join(f"  - {msg}" for msg in status_messages)

        return [TextContent(type="text", text=result)]

    except serial.SerialException as e:
        return [TextContent(type="text", text=f"Failed to connect to {port}: {str(e)}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {str(e)}")]


def main():
    """Run the MCP server."""
    server = create_server()

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
