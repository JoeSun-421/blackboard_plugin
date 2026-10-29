"""Unit tests for the MCP Server."""

import json
from cuhk_blackboard.mcp_server import MCPServer


def test_mcp_initialize():
    server = MCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    resp = server.handle_request(req)
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in resp["result"]["capabilities"]


def test_mcp_ping():
    server = MCPServer()
    req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    resp = server.handle_request(req)
    assert resp["id"] == 2
    assert resp["result"] == {}


def test_mcp_tools_list():
    server = MCPServer()
    req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    resp = server.handle_request(req)
    assert resp["id"] == 3
    tools = resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "cuhk_bb_configure_auth" in tool_names
    assert "cuhk_bb_auth_status" in tool_names
    assert "cuhk_bb_list_courses" in tool_names
    # Verify inputSchema
    auth_tool = next(t for t in tools if t["name"] == "cuhk_bb_configure_auth")
    assert "inputSchema" in auth_tool
    assert auth_tool["inputSchema"]["type"] == "object"


def test_mcp_tools_call_success():
    server = MCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "cuhk_bb_get_auth_guide",
            "arguments": {"method": "cookie"},
        },
    }
    resp = server.handle_request(req)
    assert resp["id"] == 4
    content = resp["result"]["content"]
    assert len(content) == 1
    assert content[0]["type"] == "text"
    parsed_text = json.loads(content[0]["text"])
    assert "Duo" in parsed_text["instructions"]


def test_mcp_tools_call_not_found():
    server = MCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "non_existent_tool",
            "arguments": {},
        },
    }
    resp = server.handle_request(req)
    assert resp["id"] == 5
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_mcp_unknown_method():
    server = MCPServer()
    req = {"jsonrpc": "2.0", "id": 6, "method": "custom/unknown"}
    resp = server.handle_request(req)
    assert resp["id"] == 6
    assert resp["error"]["code"] == -32601


def test_mcp_notification():
    server = MCPServer()
    req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    resp = server.handle_request(req)
    assert resp is None
