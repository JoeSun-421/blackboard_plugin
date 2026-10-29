"""Model Context Protocol (MCP) Server for CUHK Blackboard.

Allows any MCP-compliant AI Agent (Claude, Cursor, Antigravity, etc.) to connect
over STDIO and access CUHK Blackboard tools with custom user authentication.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Dict, Optional

from .tools import AGENT_TOOLS_DEFINITIONS, TOOL_FUNCTION_MAP


PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "cuhk-blackboard-plugin"
SERVER_VERSION = "1.0.0"


class MCPServer:
    """Stdio-based Model Context Protocol Server."""

    def __init__(self):
        self.running = False

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Dispatch JSON-RPC request to appropriate MCP handler."""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        # Handle notifications (requests without an id)
        if req_id is None:
            if method == "notifications/initialized":
                # Client initialization complete notification
                return None
            return None

        # Handle standard RPC calls
        try:
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {
                            "tools": {},
                        },
                        "serverInfo": {
                            "name": SERVER_NAME,
                            "version": SERVER_VERSION,
                        },
                    },
                }

            elif method == "ping":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {},
                }

            elif method == "tools/list":
                tools = []
                for tool_def in AGENT_TOOLS_DEFINITIONS:
                    tools.append({
                        "name": tool_def["name"],
                        "description": tool_def["description"],
                        "inputSchema": tool_def.get("parameters", {"type": "object", "properties": {}}),
                    })
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": tools,
                    },
                }

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if tool_name not in TOOL_FUNCTION_MAP:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Tool '{tool_name}' not found.",
                        },
                    }

                func = TOOL_FUNCTION_MAP[tool_name]
                try:
                    output = func(**arguments)
                    text_result = json.dumps(output, ensure_ascii=False, indent=2)
                    is_error = isinstance(output, dict) and output.get("success") is False
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": text_result,
                                }
                            ],
                            "isError": is_error,
                        },
                    }
                except Exception as ex:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Error executing tool '{tool_name}': {str(ex)}\n{traceback.format_exc()}",
                                }
                            ],
                            "isError": True,
                        },
                    }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method '{method}' not found.",
                    },
                }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}",
                },
            }

    def run_stdio(self):
        """Run the MCP server listening on stdin and responding on stdout."""
        # Ensure utf-8 encoding on Windows consoles
        if hasattr(sys.stdin, "reconfigure"):
            try:
                sys.stdin.reconfigure(encoding="utf-8")
            except Exception:
                pass
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

        # Protect JSON-RPC communication stream: keep private reference to real stdout,
        # and redirect global sys.stdout to sys.stderr so any stray prints don't corrupt the protocol.
        real_stdout = sys.stdout
        sys.stdout = sys.stderr

        self.running = True
        sys.stderr.write(f"[{SERVER_NAME}] Starting stdio MCP server...\n")
        sys.stderr.flush()

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                if response is not None:
                    real_stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                    real_stdout.flush()
            except json.JSONDecodeError:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
                real_stdout.write(json.dumps(err_resp) + "\n")
                real_stdout.flush()
            except Exception as e:
                sys.stderr.write(f"Unhandled server error: {e}\n")
                sys.stderr.flush()


def main():
    server = MCPServer()
    server.run_stdio()


if __name__ == "__main__":
    main()
