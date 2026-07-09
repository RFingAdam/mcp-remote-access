# Changelog

All notable changes to **mcp-remote-access** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- `ssh_connect` dropped an explicitly empty `password` (treated the same
  as "no password supplied"), so hosts configured for
  `PermitEmptyPasswords yes` could never authenticate through this tool.
- `serial_connect`/`serial_connect_match` trusted pyserial's `is_open`
  flag to decide whether a pooled connection could be reused. That flag
  stays `True` after the OS handle is invalidated by an external event
  (a physical USB replug is the common case on Windows), so a dead
  connection could be reported as `"already_connected"` and every
  subsequent call against it would fail with a raw `PermissionError`
  instead of a clean reconnect. Added `is_port_alive()`, which probes
  `in_waiting` before trusting the handle, and applied it everywhere the
  code previously checked `is_open` directly.

### Docs
- Corrected several tool-reference entries that had drifted from the
  actual `server.py` schemas (tool count, `serial_connect`'s real
  arguments, `serial_expect`'s `steps`/`wait_for` shape,
  `ssh_execute_background`'s `task_id`, two undocumented tools —
  `serial_send_bytes`/`serial_read_bytes`).

## [0.2.0] — 2026-05-13

### Changed
- **License: Apache-2.0 → AGPL-3.0-or-later.** Aligns with the
  eng-mcp-suite toolkit-wide AGPL move. See the
  [LICENSE_SUMMARY](https://github.com/RFingAdam/eng-mcp-suite/blob/main/LICENSE_SUMMARY.md)
  for the toolkit-wide rationale.

## [0.1.0]

Initial release. MCP server for SSH and UART/serial remote device
access. Connection-pool managed, memory-only credentials, no on-disk
session store. DTR/RTS pin control for embedded MCU reset.
