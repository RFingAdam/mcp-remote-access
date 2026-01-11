#!/usr/bin/env python3
"""MCP server providing SSH and UART remote access tools."""

import asyncio
import base64
import io
import os
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

    if not raw:
        data = data + "\n"

    loop = asyncio.get_event_loop()

    def send_and_read():
        ser.write(data.encode("utf-8"))
        ser.flush()

        if read_response:
            # Wait a bit for response
            import time

            time.sleep(0.1)

            # Set temporary timeout
            old_timeout = ser.timeout
            ser.timeout = read_timeout

            response = b""
            while True:
                chunk = ser.read(1024)
                if not chunk:
                    break
                response += chunk

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

    loop = asyncio.get_event_loop()

    def read():
        old_timeout = ser.timeout
        ser.timeout = timeout

        data = ser.read(max_bytes)

        ser.timeout = old_timeout
        return data.decode("utf-8", errors="replace")

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


def main():
    """Run the MCP server."""
    import asyncio

    server = create_server()

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
