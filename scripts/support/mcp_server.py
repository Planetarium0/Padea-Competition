"""
mcp_server.py — Minimal JSON-RPC 2.0 MCP server over stdio for Padea support tools.

No extra pip dependencies — implements the protocol manually.

Usage:
    python scripts/support/mcp_server.py \\
        --parent-email foo@bar.com \\
        --case-id <uuid> \\
        --log-file /tmp/padea_mcp_abc123.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap: make sure the project src is importable
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def _build_mcp_tool_schemas(tool_schemas: list[dict]) -> list[dict]:
    """Convert TOOL_SCHEMAS (input_schema) to MCP format (inputSchema)."""
    result = []
    for schema in tool_schemas:
        mcp_schema = dict(schema)
        if "input_schema" in mcp_schema:
            mcp_schema["inputSchema"] = mcp_schema.pop("input_schema")
        result.append(mcp_schema)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Padea support MCP server (stdio)")
    parser.add_argument("--parent-email", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--log-file", required=True)
    args = parser.parse_args()

    parent_email: str = args.parent_email
    case_id: str = args.case_id
    log_file: str = args.log_file

    # Load environment variables from .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Initialise the database and executor
    from support import Database, Record
    from support.llm_tools import TOOL_SCHEMAS, make_tool_executor

    db = Database.from_env()

    students = [
        s for s in db.Students.all()
        if s.fields.get("parent_email", "").lower() == parent_email.lower()
    ]

    case = db.SupportCases.get(case_id)
    if case is None:
        # Create a minimal stub case
        case = Record(
            id=case_id,
            fields={
                "case_code": f"MCP-STUB-{case_id[:8]}",
                "parent_email": parent_email,
                "status": "Open",
                "messages": [],
            },
        )

    executor = make_tool_executor(db, parent_email, students, case)

    mcp_tool_schemas = _build_mcp_tool_schemas(TOOL_SCHEMAS)
    tool_call_log: list[dict] = []

    # ------------------------------------------------------------------
    # Message handler
    # ------------------------------------------------------------------

    def handle_message(msg: dict) -> dict | None:
        msg_id = msg.get("id")
        method = msg.get("method", "")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "padea-support", "version": "1.0"},
                },
            }

        elif method == "notifications/initialized":
            # Notification — no response
            return None

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": mcp_tool_schemas},
            }

        elif method == "tools/call":
            params = msg.get("params", {})
            tool_name: str = params.get("name", "")
            tool_input: dict[str, Any] = params.get("arguments", {})

            result = executor(tool_name, tool_input)
            tool_call_log.append({"tool": tool_name, "input": tool_input, "result": result})

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result}],
                },
            }

        else:
            if msg_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method!r}",
                    },
                }
            return None

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = handle_message(msg)
            if response is not None:
                print(json.dumps(response), flush=True)
    finally:
        # Write the tool call log when stdin closes
        try:
            with open(log_file, "w") as f:
                json.dump(
                    {
                        "tool_calls": tool_call_log,
                        "reply_sent": executor.reply_sent[0],
                    },
                    f,
                )
        except Exception as e:
            print(f"Warning: could not write log file {log_file!r}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
