# Agent rules

Use these rules whenever an agent tests or controls a device under test (DUT) or lab host over SSH or serial/UART. The same policy is in the repository [`CLAUDE.md`](../CLAUDE.md) and in the `dut-remote-access` skill.

## Goal

Every SSH or serial/UART interaction with a DUT or lab host goes through this MCP, so setups and methods stay consistent and the tool improves over time.

## Rules

1. **MCP first, always.** For SSH to a DUT or lab host, serial/UART consoles, port matching by VID/PID, expect-style prompts, DTR/RTS resets, and held sessions, use this MCP's tools (for example `ssh_execute`, `serial_send`). Do not shell out to `ssh`, `screen`, `minicom`, `picocom`, or Python serial scripts instead.
2. **Never silently bypass.** If an MCP call fails, do not fall back to bash and carry on. Stop, capture the exact error and inputs, and find the root cause in this MCP (config, host entry, port mapping, timeout, prompt pattern, or bug).
3. **Patch this MCP.** Fix it on a branch: a config or host-profile change, or a code fix with a test that reproduces the failure. Open a PR, restart the MCP, and retry the original step through the MCP.
4. **Temporary bypass only with a record.** If the test is time-critical and the fix cannot land now, a one-off bash fallback is allowed only if you say so explicitly in your report, log it in [KNOWN_ISSUES.md](KNOWN_ISSUES.md) (or open an issue) with the failing call, and come back to fix it.
5. **Keep methods consistent.** Reuse saved host and port profiles and existing expect patterns; add new ones to the MCP config rather than inlining them in a session.
6. **Plain bash is fine for non-DUT work:** local files, builds, git, and the agent's own machine.

## Report

State which MCP tools were used, any failure and the fix PR, and any bypass with its issue or known-issues entry.
