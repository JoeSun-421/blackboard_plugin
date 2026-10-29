"""Unit tests for Agent Tools and schemas."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cuhk_blackboard.models import Course, UserProfile
from cuhk_blackboard.tools import (
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
    get_client,
)


def test_tool_definitions_consistency():
    def_names = {t["name"] for t in AGENT_TOOLS_DEFINITIONS}
    map_names = set(TOOL_FUNCTION_MAP.keys())
    assert def_names == map_names
    for name in def_names:
        assert callable(TOOL_FUNCTION_MAP[name])


def test_configure_auth_missing_value():
    res = cuhk_bb_configure_auth(method="cookie")
    assert res["success"] is False
    assert "Missing 'value'" in res["error"]
    assert "guide" in res


def test_configure_auth_unsupported_method():
    res = cuhk_bb_configure_auth(method="unknown_method")
    assert res["success"] is False
    assert "Unsupported authentication method" in res["error"]


def test_configure_auth_cookie_success():
    client = get_client()
    mock_profile = UserProfile(
        user_id="_101_1",
        username="s1155123456",
        display_name="Tai Man Chan",
    )
    with patch.object(client, "verify_auth", return_value=(True, mock_profile)):
        res = cuhk_bb_configure_auth(
            method="cookie",
            value="JSESSIONID=test_val; session_id=sess_val",
            save=False,
        )
        assert res["success"] is True
        assert "Tai Man Chan" in res["user"]["display_name"]


def test_auth_status():
    client = get_client()
    mock_profile = UserProfile(
        user_id="_101_1",
        username="s1155123456",
        display_name="Tai Man Chan",
    )
    with patch.object(client, "verify_auth", return_value=(True, mock_profile)):
        status = cuhk_bb_auth_status()
        assert status["authenticated"] is True
        assert status["user_profile"]["username"] == "s1155123456"


def test_get_auth_guide():
    res = cuhk_bb_get_auth_guide(method="cookie")
    assert "instructions" in res
    assert "Duo" in res["instructions"]


def test_list_courses():
    client = get_client()
    mock_courses = [
        Course(id="_c1", course_id="CSCI3150", name="OS"),
    ]
    with patch.object(client, "list_courses", return_value=mock_courses):
        res = cuhk_bb_list_courses()
        assert res["success"] is True
        assert res["total"] == 1
        assert res["courses"][0]["course_id"] == "CSCI3150"


def test_get_course_summary():
    client = get_client()
    mock_summary = {
        "course_id": "_c1",
        "code": "CSCI3150",
        "name": "OS",
        "recent_announcements": [],
    }
    with patch.object(client, "get_course_summary", return_value=mock_summary):
        res = cuhk_bb_get_course_summary(course_id="_c1")
        assert res["success"] is True
        assert res["summary"]["code"] == "CSCI3150"


def test_configure_auth_auto_detect():
    client = get_client()
    mock_profile = UserProfile(
        user_id="_101_1",
        username="s1155123456",
        display_name="Tai Man Chan",
    )
    with patch.object(client, "verify_auth", return_value=(True, mock_profile)):
        # Omit method, provide cookie in value
        res = cuhk_bb_configure_auth(
            method="auto",
            value="JSESSIONID=auto_val; session_id=auto_sess",
            save=False,
        )
        assert res["success"] is True
        assert res["method"] == "cookie"


def test_configure_auth_credentials_failure_includes_duo_note():
    client = get_client()
    with patch.object(client, "verify_auth", return_value=(False, "Unauthorized")):
        res = cuhk_bb_configure_auth(
            method="credentials",
            username="s1155999999",
            password="WrongPassword",
            save=False,
        )
        assert res["success"] is False
        assert "Duo 2FA" in res["message"]


def test_capture_browser_session_success(tmp_path):
    from cuhk_blackboard.tools import cuhk_bb_capture_browser_session
    mock_profile = UserProfile(user_id="_u1", username="s1155123456", display_name="Test Student")
    with patch("cuhk_blackboard.interactive_login.capture_from_cdp", return_value="JSESSIONID=sess_abc; session_id=sess_xyz"):
        with patch("cuhk_blackboard.client.BlackboardClient.verify_auth", return_value=(True, mock_profile)):
            with patch("cuhk_blackboard.auth.AuthManager.save_session"):
                res = cuhk_bb_capture_browser_session()
                assert res["success"] is True
                assert "Test Student" in res["message"]
                assert res["user"]["username"] == "s1155123456"

