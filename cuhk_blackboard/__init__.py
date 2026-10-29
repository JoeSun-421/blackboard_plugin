"""CUHK Blackboard Scraper & AI Agent Plugin.

A modular agent plugin and MCP server for the Chinese University of Hong Kong (CUHK)
Blackboard Learn platform, featuring flexible user authentication (cookies, tokens,
credentials) and deep scraping of courses, materials, announcements, and grades.
"""

from .auth import AuthManager
from .client import BlackboardClient
# from .mcp_server import MCPServer
from .models import (
    Announcement,
    Assignment,
    Attachment,
    AuthConfig,
    AuthMethod,
    ContentItem,
    ContentType,
    Course,
    GradeItem,
    UserProfile,
)
from .tools import (
    AGENT_TOOLS_DEFINITIONS,
    TOOL_FUNCTION_MAP,
    cuhk_bb_auth_status,
    cuhk_bb_configure_auth,
    cuhk_bb_download_material,
    cuhk_bb_get_auth_guide,
    cuhk_bb_get_course_details,
    cuhk_bb_get_course_summary,
    cuhk_bb_get_grades,
    cuhk_bb_list_announcements,
    cuhk_bb_list_assignments,
    cuhk_bb_list_course_contents,
    cuhk_bb_list_courses,
    cuhk_bb_search_materials,
)

__version__ = "1.0.0"

__all__ = [
    "AuthManager",
    "AuthConfig",
    "AuthMethod",
    "BlackboardClient",
    "UserProfile",
    "Course",
    "ContentItem",
    "ContentType",
    "Attachment",
    "Announcement",
    "GradeItem",
    "Assignment",
    "AGENT_TOOLS_DEFINITIONS",
    "TOOL_FUNCTION_MAP",
    "cuhk_bb_configure_auth",
    "cuhk_bb_auth_status",
    "cuhk_bb_get_auth_guide",
    "cuhk_bb_list_courses",
    "cuhk_bb_get_course_details",
    "cuhk_bb_list_course_contents",
    "cuhk_bb_list_announcements",
    "cuhk_bb_list_assignments",
    "cuhk_bb_get_grades",
    "cuhk_bb_capture_browser_session",
    "cuhk_bb_download_material",
    "cuhk_bb_search_materials",
    "cuhk_bb_get_course_summary",
]
