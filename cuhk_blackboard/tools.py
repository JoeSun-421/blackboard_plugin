"""Agent Tools Registry for CUHK Blackboard.

Exposes standard functions and tool schemas for AI Agents (MCP, LangChain, Claude, OpenAI).
Supports user-specified authentication methods and comprehensive scraping operations.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .auth import AuthManager
from .client import BlackboardClient
from .models import AuthMethod


# Shared global client instance for stateful agent workflows
_global_client: Optional[BlackboardClient] = None


def get_client() -> BlackboardClient:
    global _global_client
    if _global_client is None:
        _global_client = BlackboardClient()
    else:
        # Check if saved session on disk has been updated
        _global_client.auth_manager.load_session()
    return _global_client


def cuhk_bb_configure_auth(
    method: str = "cookie",
    value: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    duo_passcode: Optional[str] = None,
    host: Optional[str] = None,
    save: bool = True,
) -> Dict[str, Any]:
    """Configure or update the authentication method for CUHK Blackboard.
    
    Supports:
    - 'cookie': Provide session cookie string from browser (e.g., 'JSESSIONID=...; session_id=...').
    - 'token': Provide Bearer / OAuth token.
    - 'credentials': Provide CUHK OnePass username, password, and optional Duo passcode.
    - 'saved_session': Loads previously stored session from disk or environment.
    """
    client = get_client()

    # Smart auto-detection of auth method if unspecified or ambiguous
    if not method or method.strip().lower() in ("auto", "detect", "default"):
        if value:
            if "jsessionid" in value.lower() or "session_id" in value.lower() or "=" in value or "\t" in value:
                method_lower = "cookie"
            else:
                method_lower = "token"
        elif username and password:
            method_lower = "credentials"
        else:
            method_lower = "saved_session"
    else:
        method_lower = method.lower().strip()

    try:
        if method_lower in ("cookie", "cookies", "session", "session_cookie", "cookie_header"):
            if not value:
                return {
                    "success": False,
                    "error": "Missing 'value'. Please provide your Blackboard cookie string (e.g. 'JSESSIONID=...; session_id=...').",
                    "guide": AuthManager.get_auth_guide("cookie"),
                }
            client.auth_manager.set_cookie_auth(value, host=host, save=save)

        elif method_lower in ("token", "bearer", "oauth", "jwt"):
            if not value:
                return {
                    "success": False,
                    "error": "Missing 'value'. Please provide your Bearer / OAuth access token string.",
                    "guide": AuthManager.get_auth_guide("token"),
                }
            client.auth_manager.set_token_auth(value, host=host, save=save)

        elif method_lower in ("credentials", "password", "cwem", "onepass"):
            if not username or not password:
                return {
                    "success": False,
                    "error": "Missing username or password. Please provide both 'username' and 'password'.",
                    "guide": AuthManager.get_auth_guide("credentials"),
                }
            client.auth_manager.set_credentials_auth(
                username=username,
                password=password,
                duo_passcode=duo_passcode,
                host=host,
                save=save,
            )

        elif method_lower in ("saved_session", "env", "file", "saved"):
            loaded = client.auth_manager.load_session()
            if not loaded:
                return {
                    "success": False,
                    "error": "No saved session found in ~/.cuhk_blackboard/session.json or environment variables.",
                    "guide": AuthManager.get_auth_guide("cookie"),
                }
        else:
            return {
                "success": False,
                "error": f"Unsupported authentication method: '{method}'. Choose from: 'cookie', 'token', 'credentials', 'saved_session'.",
                "guide": AuthManager.get_auth_guide("all"),
            }

        # Clear session cookies to ensure fresh sync
        client.session.cookies.clear()

        # Verify new auth configuration with Blackboard
        is_valid, profile_or_err = client.verify_auth()
        if is_valid:
            profile = profile_or_err
            return {
                "success": True,
                "message": f"Successfully authenticated with CUHK Blackboard ({client.host})!",
                "method": method_lower,
                "user": asdict(profile) if hasattr(profile, "__dataclass_fields__") else str(profile),
            }
        else:
            error_hint = str(profile_or_err)
            if method_lower in ("credentials", "password", "cwem", "onepass"):
                error_hint += " Note: CUHK strictly enforces SAML SSO with Duo 2FA push notifications. Please use method='cookie' with session cookies extracted from browser DevTools after completing Duo 2FA."
            return {
                "success": False,
                "message": f"Credentials configured, but verification failed: {error_hint}",
                "method": method_lower,
                "guide": AuthManager.get_auth_guide(method_lower),
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error configuring authentication: {str(e)}",
        }


def cuhk_bb_auth_status() -> Dict[str, Any]:
    """Check current authentication status, verify credentials with server, and return user profile."""
    client = get_client()
    if not client.auth_manager.is_configured:
        return {
            "authenticated": False,
            "message": "Authentication is not configured.",
            "guide": AuthManager.get_auth_guide("cookie"),
        }

    is_valid, result = client.verify_auth()
    return {
        "authenticated": is_valid,
        "host": client.host,
        "method": client.auth_manager.config.method.value,
        "user_profile": asdict(result) if is_valid and hasattr(result, "__dataclass_fields__") else None,
        "error": str(result) if not is_valid else None,
        "instructions": None if is_valid else AuthManager.get_auth_guide("cookie"),
    }


def cuhk_bb_capture_browser_session(
    cdp_port: int = 9222,
    auto_launch: bool = True,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """Capture authenticated session cookies from the browser.
    
    Checks active browser tabs via CDP (e.g. side panel browser or remote debug port)
    or launches an interactive browser window for the user to complete OnePass + Duo 2FA.
    Once authenticated, automatically stores the session and verifies connectivity.
    """
    from .interactive_login import capture_from_cdp, launch_browser_login
    client = get_client()

    # 1. First probe CDP port (for side panel browser or existing remote debugging session)
    cookie_str = capture_from_cdp(f"http://127.0.0.1:{cdp_port}")
    if not cookie_str:
        for p in (9229, 9333):
            cookie_str = capture_from_cdp(f"http://127.0.0.1:{p}")
            if cookie_str:
                break

    # 2. If no CDP session found and auto_launch is True, launch browser
    if not cookie_str and auto_launch:
        cookie_str = launch_browser_login(host=client.host, timeout_seconds=timeout_seconds)

    if not cookie_str:
        return {
            "success": False,
            "message": "未能自动从浏览器捕获有效会话。请确认已在侧边栏浏览器中完成登录，或使用 cuhk_bb_configure_auth 直接粘贴 Cookie。",
            "guide": AuthManager.get_auth_guide("cookie"),
        }

    # 3. Configure and verify captured cookies
    client.auth_manager.set_cookie_auth(cookie_str, host=client.host, save=True)
    is_valid, profile_or_err = client.verify_auth()
    if is_valid:
        profile = profile_or_err
        return {
            "success": True,
            "message": f"🎉 成功从浏览器捕获并验证 Blackboard 会话！用户: {profile.display_name} ({profile.username})",
            "user": asdict(profile),
        }
    else:
        return {
            "success": False,
            "message": f"从浏览器捕获了 Cookie，但向 Blackboard 验证失败: {profile_or_err}",
        }


def cuhk_bb_get_auth_guide(method: str = "cookie") -> Dict[str, str]:
    """Retrieve detailed instructions on how to obtain cookies, tokens, or set up Duo 2FA SSO."""
    return {
        "method": method,
        "instructions": AuthManager.get_auth_guide(method),
    }


def cuhk_bb_list_courses(include_hidden: bool = False) -> Dict[str, Any]:
    """List all enrolled Blackboard courses (course ID, code, name, term, instructor)."""
    client = get_client()
    try:
        courses = client.list_courses(include_hidden=include_hidden)
        return {
            "success": True,
            "total": len(courses),
            "courses": [asdict(c) for c in courses],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def cuhk_bb_get_course_details(course_id: str) -> Dict[str, Any]:
    """Get full details for a specific course by ID or course code."""
    client = get_client()
    try:
        course = client.get_course(course_id)
        return {"success": True, "course": asdict(course)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def cuhk_bb_list_course_contents(
    course_id: str,
    content_id: Optional[str] = None,
    recursive: bool = False,
    max_depth: int = 3,
) -> Dict[str, Any]:
    """List folders, lecture slides, files, and syllabus within a course."""
    client = get_client()
    try:
        items = client.list_course_contents(
            course_id=course_id,
            content_id=content_id,
            recursive=recursive,
            max_depth=max_depth,
        )
        return {
            "success": True,
            "course_id": course_id,
            "total_items": len(items),
            "contents": [asdict(item) for item in items],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def cuhk_bb_list_announcements(course_id: Optional[str] = None, limit: int = 15) -> Dict[str, Any]:
    """List announcements for a specific course or across all active courses."""
    client = get_client()
    try:
        anns = client.list_announcements(course_id=course_id, limit=limit)
        return {
            "success": True,
            "total": len(anns),
            "announcements": [asdict(a) for a in anns],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def cuhk_bb_list_assignments(course_id: Optional[str] = None, upcoming_only: bool = False) -> Dict[str, Any]:
    """List upcoming assignments, due dates, instructions, and point totals."""
    client = get_client()
    try:
        asgs = client.list_assignments(course_id=course_id, upcoming_only=upcoming_only)
        return {
            "success": True,
            "total": len(asgs),
            "assignments": [asdict(a) for a in asgs],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def cuhk_bb_get_grades(course_id: str) -> Dict[str, Any]:
    """Fetch student grades, scores, possible points, and feedback for a course."""
    client = get_client()
    try:
        grades = client.get_grades(course_id)
        return {
            "success": True,
            "course_id": course_id,
            "total_items": len(grades),
            "grades": [asdict(g) for g in grades],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def cuhk_bb_download_material(
    course_id: str,
    content_id: str,
    attachment_id: str,
    target_dir: str = "./downloaded_materials",
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Download a course attachment file to the local directory."""
    client = get_client()
    try:
        saved_path = client.download_material(
            course_id=course_id,
            content_id=content_id,
            attachment_id=attachment_id,
            target_dir=target_dir,
            filename=filename,
        )
        return {
            "success": True,
            "saved_path": str(saved_path),
            "file_size": saved_path.stat().st_size if saved_path.exists() else 0,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def cuhk_bb_search_materials(query: str, course_id: Optional[str] = None) -> Dict[str, Any]:
    """Search course materials, syllabus, and announcements by keyword."""
    client = get_client()
    try:
        raw_results = client.search_materials(query=query, course_id=course_id)
        return {
            "success": True,
            "query": query,
            "courses_matched": [asdict(c) for c in raw_results["courses"]],
            "contents_matched": [asdict(i) for i in raw_results["contents"]],
            "announcements_matched": [asdict(a) for a in raw_results["announcements"]],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def cuhk_bb_get_course_summary(course_id: str) -> Dict[str, Any]:
    """Get a concise, LLM-ready summary of recent announcements, contents, and grades."""
    client = get_client()
    try:
        summary = client.get_course_summary(course_id)
        return {"success": True, "summary": summary}
    except Exception as e:
        return {"success": False, "error": str(e)}


# Schema definitions for MCP and Agent function calls
AGENT_TOOLS_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "cuhk_bb_configure_auth",
        "description": "Configure or update user authentication method for CUHK Blackboard (cookie, token, credentials, or saved session).",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["cookie", "token", "credentials", "saved_session"],
                    "description": "Authentication method to use: 'cookie' (recommended for Duo 2FA), 'token', 'credentials', or 'saved_session'.",
                },
                "value": {
                    "type": "string",
                    "description": "Cookie string (e.g. 'JSESSIONID=...; session_id=...') or Bearer token.",
                },
                "username": {
                    "type": "string",
                    "description": "CUHK OnePass / CWEM username (e.g., s1155xxxxxx) when using credentials.",
                },
                "password": {
                    "type": "string",
                    "description": "CWEM password when using credentials.",
                },
                "duo_passcode": {
                    "type": "string",
                    "description": "Optional 6-digit Duo Mobile passcode when using credentials.",
                },
                "host": {
                    "type": "string",
                    "description": "Blackboard instance URL (defaults to https://blackboard.cuhk.edu.hk, supports https://bb.cuhk.edu.cn).",
                },
                "save": {
                    "type": "boolean",
                    "description": "Whether to persist session to ~/.cuhk_blackboard/session.json (default: true).",
                },
            },
            "required": ["method"],
        },
    },
    {
        "name": "cuhk_bb_auth_status",
        "description": "Check current authentication status and verify session validity with CUHK Blackboard.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "cuhk_bb_capture_browser_session",
        "description": "Automatically capture authenticated session cookies from the browser (e.g. side panel browser, CDP port 9222, or interactive login window) after user logs in.",
        "parameters": {
            "type": "object",
            "properties": {
                "cdp_port": {
                    "type": "integer",
                    "description": "Optional Chrome DevTools Protocol port (default: 9222).",
                },
                "auto_launch": {
                    "type": "boolean",
                    "description": "Whether to launch an interactive browser window if no CDP browser is active (default: true).",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Seconds to wait for user to finish OnePass and Duo 2FA (default: 120).",
                },
            },
        },
    },
    {
        "name": "cuhk_bb_get_auth_guide",
        "description": "Get detailed step-by-step guidance on how to obtain authentication credentials (cookies from browser DevTools, tokens, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["cookie", "token", "credentials", "all"],
                    "description": "Specific auth method to get guidance for.",
                }
            },
        },
    },
    {
        "name": "cuhk_bb_list_courses",
        "description": "List all enrolled CUHK Blackboard courses with course IDs, codes, names, terms, and instructors.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_hidden": {
                    "type": "boolean",
                    "description": "Whether to include hidden or past courses.",
                }
            },
        },
    },
    {
        "name": "cuhk_bb_get_course_details",
        "description": "Get detailed information for a specific Blackboard course by course ID or course code.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {
                    "type": "string",
                    "description": "Course ID (e.g. '_12345_1' or '2024R1-CSCI3150').",
                }
            },
            "required": ["course_id"],
        },
    },
    {
        "name": "cuhk_bb_list_course_contents",
        "description": "List lecture notes, syllabus, slides, documents, and folders inside a course.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {
                    "type": "string",
                    "description": "Target course ID.",
                },
                "content_id": {
                    "type": "string",
                    "description": "Optional subfolder content ID to browse inside a folder.",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to traverse subfolders recursively.",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max recursion depth (default 3).",
                },
            },
            "required": ["course_id"],
        },
    },
    {
        "name": "cuhk_bb_list_announcements",
        "description": "List announcements with cleaned text content for a course or across enrolled courses.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {
                    "type": "string",
                    "description": "Optional course ID. If omitted, lists recent announcements across courses.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of announcements to return (default: 15).",
                },
            },
        },
    },
    {
        "name": "cuhk_bb_list_assignments",
        "description": "List assignments, due dates, instructions, and points possible.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {
                    "type": "string",
                    "description": "Optional course ID filter.",
                },
                "upcoming_only": {
                    "type": "boolean",
                    "description": "Filter for upcoming tasks only.",
                },
            },
        },
    },
    {
        "name": "cuhk_bb_get_grades",
        "description": "Fetch student grades, scores, gradebook columns, and teacher feedback for a course.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {
                    "type": "string",
                    "description": "Course ID.",
                }
            },
            "required": ["course_id"],
        },
    },
    {
        "name": "cuhk_bb_download_material",
        "description": "Download a course attachment/file (PDF, PPTX, ZIP, etc.) to the local file system.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {
                    "type": "string",
                    "description": "Course ID.",
                },
                "content_id": {
                    "type": "string",
                    "description": "Content item ID containing the attachment.",
                },
                "attachment_id": {
                    "type": "string",
                    "description": "Attachment ID to download.",
                },
                "target_dir": {
                    "type": "string",
                    "description": "Local destination directory (default: ./downloaded_materials).",
                },
                "filename": {
                    "type": "string",
                    "description": "Optional custom filename.",
                },
            },
            "required": ["course_id", "content_id", "attachment_id"],
        },
    },
    {
        "name": "cuhk_bb_search_materials",
        "description": "Search across course titles, announcements, and lecture materials by keywords.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term or keyword.",
                },
                "course_id": {
                    "type": "string",
                    "description": "Optional course ID filter.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "cuhk_bb_get_course_summary",
        "description": "Get a compact, high-signal summary of a course (recent announcements, materials, grades) optimized for LLM context.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {
                    "type": "string",
                    "description": "Course ID.",
                }
            },
            "required": ["course_id"],
        },
    },
]

TOOL_FUNCTION_MAP: Dict[str, Callable[..., Any]] = {
    "cuhk_bb_configure_auth": cuhk_bb_configure_auth,
    "cuhk_bb_auth_status": cuhk_bb_auth_status,
    "cuhk_bb_capture_browser_session": cuhk_bb_capture_browser_session,
    "cuhk_bb_get_auth_guide": cuhk_bb_get_auth_guide,
    "cuhk_bb_list_courses": cuhk_bb_list_courses,
    "cuhk_bb_get_course_details": cuhk_bb_get_course_details,
    "cuhk_bb_list_course_contents": cuhk_bb_list_course_contents,
    "cuhk_bb_list_announcements": cuhk_bb_list_announcements,
    "cuhk_bb_list_assignments": cuhk_bb_list_assignments,
    "cuhk_bb_get_grades": cuhk_bb_get_grades,
    "cuhk_bb_download_material": cuhk_bb_download_material,
    "cuhk_bb_search_materials": cuhk_bb_search_materials,
    "cuhk_bb_get_course_summary": cuhk_bb_get_course_summary,
}
