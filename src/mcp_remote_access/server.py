#!/usr/bin/env python3
"""MCP server providing SSH and UART remote access tools for IoT/embedded development."""

import asyncio
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
            elif name == "serial_list_ports":
                return await handle_serial_list_ports()
            elif name == "serial_connect":
                return await handle_serial_connect(arguments)
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
            elif name == "serial_send_break":
                return await handle_serial_send_break(arguments)
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

    # Check if already connected
    if conn_id in ssh_connections:
        return [TextContent(type="text", text=f"Already connected: {conn_id}")]

    # Create SSH client
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Connect
    connect_kwargs = {
        "hostname": host,
        "port": port,
        "username": username,
        "timeout": 10,
        "allow_agent": True,
        "look_for_keys": True,
    }

    if password:
        connect_kwargs["password"] = password
    if key_path:
        connect_kwargs["key_filename"] = os.path.expanduser(key_path)

    # Run in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: client.connect(**connect_kwargs))

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

    # Execute command in thread pool
    loop = asyncio.get_event_loop()

    def execute():
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        return stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace"), exit_code

    stdout_text, stderr_text, exit_code = await loop.run_in_executor(None, execute)

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

    loop = asyncio.get_event_loop()

    def upload():
        sftp = client.open_sftp()
        sftp.put(local_path, remote_path)
        stat = sftp.stat(remote_path)
        sftp.close()
        return stat.st_size

    size = await loop.run_in_executor(None, upload)

    return [TextContent(type="text", text=f"Uploaded successfully!\n{local_path} -> {remote_path}\nSize: {size} bytes")]


async def handle_ssh_download(args: dict[str, Any]) -> list[TextContent]:
    """Download a file via SFTP."""
    conn_id = args["connection_id"]
    remote_path = args["remote_path"]
    local_path = os.path.expanduser(args["local_path"])

    if conn_id not in ssh_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    client = ssh_connections[conn_id]

    loop = asyncio.get_event_loop()

    def download():
        sftp = client.open_sftp()
        sftp.get(remote_path, local_path)
        sftp.close()
        return os.path.getsize(local_path)

    size = await loop.run_in_executor(None, download)

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


# Serial Handlers


async def handle_serial_list_ports() -> list[TextContent]:
    """List available serial ports."""
    ports = serial.tools.list_ports.comports()

    if not ports:
        return [TextContent(type="text", text="No serial ports found.")]

    lines = ["Available serial ports:"]
    for port in ports:
        lines.append(f"  - {port.device}: {port.description}")
        if port.hwid:
            lines.append(f"    HWID: {port.hwid}")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_serial_connect(args: dict[str, Any]) -> list[TextContent]:
    """Connect to a serial port."""
    port = args["port"]
    baudrate = args.get("baudrate", 115200)
    timeout = args.get("timeout", 1.0)

    conn_id = f"{port}@{baudrate}"

    if conn_id in serial_connections:
        return [TextContent(type="text", text=f"Already connected: {conn_id}")]

    loop = asyncio.get_event_loop()

    def connect():
        ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        # Clear any pending data
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        return ser

    ser = await loop.run_in_executor(None, connect)
    serial_connections[conn_id] = ser

    return [
        TextContent(
            type="text",
            text=f"Connected successfully!\nConnection ID: {conn_id}\nPort: {port}\nBaudrate: {baudrate}",
        )
    ]


async def handle_serial_send(args: dict[str, Any]) -> list[TextContent]:
    """Send data to a serial port."""
    conn_id = args["connection_id"]
    data = args["data"]
    raw = args.get("raw", False)
    read_response = args.get("read_response", True)
    read_timeout = args.get("read_timeout", 2.0)

    if conn_id not in serial_connections:
        return [TextContent(type="text", text=f"Not connected: {conn_id}")]

    ser = serial_connections[conn_id]

    if not ser.is_open:
        return [TextContent(type="text", text=f"Connection closed: {conn_id}")]

    if not raw:
        data = data + "\n"

    loop = asyncio.get_event_loop()

    def send_and_read():
        # Clear input buffer before sending to get fresh response
        ser.reset_input_buffer()

        ser.write(data.encode("utf-8"))
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

    response = await loop.run_in_executor(None, send_and_read)

    result = f"Sent: {repr(data)}"
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
        buffer = ""
        deadline = time.time() + timeout
        old_timeout = ser.timeout
        ser.timeout = 0.1

        while time.time() < deadline:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting)
                if chunk:
                    buffer += chunk.decode("utf-8", errors="replace")
                    if pattern in buffer:
                        ser.timeout = old_timeout
                        return True, buffer
            time.sleep(0.05)

        ser.timeout = old_timeout
        return False, buffer

    found, buffer = await loop.run_in_executor(None, wait_for_pattern)

    if found:
        return [TextContent(type="text", text=f"Pattern '{pattern}' found!\n\n--- Output ---\n{buffer}")]
    else:
        return [TextContent(type="text", text=f"Timeout waiting for '{pattern}'\n\n--- Output received ---\n{buffer}")]


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


def main():
    """Run the MCP server."""
    server = create_server()

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
