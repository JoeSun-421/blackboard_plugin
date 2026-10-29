"""Unit tests for BlackboardClient."""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from cuhk_blackboard.auth import AuthManager
from cuhk_blackboard.client import BlackboardClient
from cuhk_blackboard.models import ContentType


@pytest.fixture
def client(tmp_path: Path):
    auth_file = tmp_path / "session.json"
    mgr = AuthManager(session_file=auth_file)
    mgr.set_cookie_auth("JSESSIONID=test_session_id; session_id=test_cookie_val", save=False)
    return BlackboardClient(auth_manager=mgr)


def test_verify_auth_unconfigured():
    mgr = AuthManager(session_file=Path("/non_existent/session.json"))
    mgr.clear_session()
    client = BlackboardClient(auth_manager=mgr)
    is_valid, msg = client.verify_auth()
    assert is_valid is False
    assert "not configured" in msg.lower()


def test_verify_auth_success(client: BlackboardClient):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "_1001_1",
        "userName": "s1155123456",
        "name": {"given": "Tai Man", "family": "Chan"},
        "contact": {"email": "s1155123456@link.cuhk.edu.hk"},
    }

    with patch.object(client.session, "request", return_value=mock_resp):
        is_valid, result = client.verify_auth()
        assert is_valid is True
        assert result.username == "s1155123456"
        assert result.display_name == "Tai Man Chan"


def test_verify_auth_failure(client: BlackboardClient):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    # Also make portal fallback fail
    portal_resp = MagicMock()
    portal_resp.status_code = 401
    portal_resp.text = "Login page"

    with patch.object(client.session, "request", side_effect=[mock_resp, portal_resp]):
        is_valid, result = client.verify_auth()
        assert is_valid is False
        assert "expired" in str(result).lower() or "failed" in str(result).lower()


def test_list_courses_api(client: BlackboardClient):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "id": "_c1_1",
                "courseId": "2024R1-CSCI3150",
                "name": "Operating Systems",
                "termId": "2024R1",
                "ultraStatus": "Ultra",
            },
            {
                "id": "_c2_1",
                "courseId": "2024R1-AIST1000",
                "name": "Intro to AI",
                "termId": "2024R1",
            },
        ]
    }

    with patch.object(client.session, "request", return_value=mock_resp):
        courses = client.list_courses()
        assert len(courses) == 2
        assert courses[0].course_id == "2024R1-CSCI3150"
        assert courses[0].is_ultra is True
        assert courses[1].name == "Intro to AI"


def test_list_courses_html_fallback(client: BlackboardClient):
    api_fail = MagicMock()
    api_fail.status_code = 404

    portal_html = """
    <html><body>
        <div class="portlet">
            <a href="/webapps/blackboard/execute/launcher?type=Course&id=_9988_1">2024R1-CSCI2100: Data Structures</a>
            <a href="/webapps/blackboard/execute/launcher?type=Course&id=_9989_1">2024R1-MATH1510: Linear Algebra</a>
        </div>
    </body></html>
    """
    portal_ok = MagicMock()
    portal_ok.status_code = 200
    portal_ok.text = portal_html

    with patch.object(client.session, "request", side_effect=[api_fail, api_fail, portal_ok]):
        courses = client.list_courses()
        assert len(courses) == 2
        assert courses[0].id == "_9988_1"
        assert "Data Structures" in courses[0].name


def test_list_course_contents_with_attachments(client: BlackboardClient):
    contents_resp = MagicMock()
    contents_resp.status_code = 200
    contents_resp.json.return_value = {
        "results": [
            {
                "id": "_item_1",
                "title": "Lecture 01 Notes",
                "contentHandler": {"id": "resource/x-bb-file"},
                "hasChildren": False,
            }
        ]
    }

    att_resp = MagicMock()
    att_resp.status_code = 200
    att_resp.json.return_value = {
        "results": [
            {
                "id": "_att_101",
                "fileName": "lecture01.pdf",
                "fileSize": 524288,
            }
        ]
    }

    with patch.object(client.session, "request", side_effect=[contents_resp, att_resp]):
        items = client.list_course_contents(course_id="_c1_1")
        assert len(items) == 1
        assert items[0].title == "Lecture 01 Notes"
        assert len(items[0].attachments) == 1
        assert items[0].attachments[0].file_name == "lecture01.pdf"


def test_list_announcements(client: BlackboardClient):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "id": "_ann_01",
                "title": "Welcome to class",
                "body": "<p>First lecture will be on Zoom.</p>",
                "created": "2024-09-02T09:00:00Z",
            }
        ]
    }

    with patch.object(client.session, "request", return_value=mock_resp):
        anns = client.list_announcements(course_id="_c1_1")
        assert len(anns) == 1
        assert anns[0].title == "Welcome to class"
        assert "First lecture will be on Zoom." in anns[0].content_text


def test_get_grades(client: BlackboardClient):
    cols_resp = MagicMock()
    cols_resp.status_code = 200
    cols_resp.json.return_value = {
        "results": [
            {
                "id": "_col_1",
                "name": "Homework 1",
                "grading": {"type": "Numeric", "scoreTotal": 100.0},
            }
        ]
    }

    user_grade_resp = MagicMock()
    user_grade_resp.status_code = 200
    user_grade_resp.json.return_value = {
        "score": 98.0,
        "status": "Graded",
        "feedback": "Well done",
    }

    with patch.object(client.session, "request", side_effect=[cols_resp, user_grade_resp]):
        grades = client.get_grades(course_id="_c1_1")
        assert len(grades) == 1
        assert grades[0].column_name == "Homework 1"
        assert grades[0].score == 98.0
        assert grades[0].percentage == 98.0
        assert grades[0].feedback == "Well done"


def test_download_material(client: BlackboardClient, tmp_path: Path):
    file_bytes = b"%PDF-1.4 simulated pdf document data"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Disposition": 'attachment; filename="syllabus.pdf"'}
    mock_resp.iter_content.return_value = [file_bytes]

    with patch.object(client.session, "request", return_value=mock_resp):
        dl_path = client.download_material(
            course_id="_c1_1",
            content_id="_item_1",
            attachment_id="_att_1",
            target_dir=tmp_path,
        )
        assert dl_path.exists()
        assert dl_path.name == "syllabus.pdf"
        assert dl_path.read_bytes() == file_bytes


def test_search_materials(client: BlackboardClient):
    # Mock course
    course_resp = MagicMock()
    course_resp.status_code = 200
    course_resp.json.return_value = {
        "id": "_c1_1",
        "courseId": "2024R1-CSCI3150",
        "name": "Operating Systems",
    }

    # Mock announcements
    ann_resp = MagicMock()
    ann_resp.status_code = 200
    ann_resp.json.return_value = {
        "results": [
            {
                "id": "_a1",
                "title": "Virtual Memory Project",
                "body": "Details about paging and segmentation",
            }
        ]
    }

    # Mock contents
    contents_resp = MagicMock()
    contents_resp.status_code = 200
    contents_resp.json.return_value = {
        "results": [
            {
                "id": "_cnt1",
                "title": "Virtual Memory Slides",
                "body": "Slide deck for VM",
                "contentHandler": {"id": "resource/x-bb-file"},
            }
        ]
    }

    with patch.object(client.session, "request", side_effect=[course_resp, ann_resp, contents_resp]):
        res = client.search_materials(query="Virtual Memory", course_id="_c1_1")
        assert len(res["announcements"]) == 1
        assert res["announcements"][0].title == "Virtual Memory Project"
        assert len(res["contents"]) == 1
        assert res["contents"][0].title == "Virtual Memory Slides"


def test_verify_auth_cuhk_login_redirect_is_failure(client: BlackboardClient):
    """Ensure that CUHK Blackboard's unauthenticated login redirect is NOT treated as valid."""
    mock_api = MagicMock()
    mock_api.status_code = 401
    mock_api.text = "Unauthorized"

    mock_portal = MagicMock()
    mock_portal.status_code = 200
    mock_portal.url = "https://blackboard.cuhk.edu.hk/webapps/login/"
    mock_portal.text = '<HEAD><meta http-equiv="REFRESH" content="0;url=https://blackboard.cuhk.edu.hk/auth-saml/saml/login?apId=_290_1"></HEAD> CUHK Blackboard'

    with patch.object(client.session, "request", side_effect=[mock_api, mock_portal]):
        is_valid, err = client.verify_auth()
        assert is_valid is False
        assert "failed" in err.lower() or "expired" in err.lower()


def test_list_assignments_upcoming_only_filter(client: BlackboardClient):
    cols_resp = MagicMock()
    cols_resp.status_code = 200
    cols_resp.json.return_value = {
        "results": [
            {
                "id": "_past_col",
                "name": "Past Homework 1",
                "dueDate": "2020-01-01T00:00:00Z",
                "grading": {"scoreTotal": 100.0},
            },
            {
                "id": "_future_col",
                "name": "Future Homework 2",
                "dueDate": "2099-12-31T23:59:00Z",
                "grading": {"scoreTotal": 100.0},
            },
            {
                "id": "_nodue_col",
                "name": "Participation (No Deadline)",
                "grading": {"scoreTotal": 10.0},
            },
        ]
    }

    mock_course = MagicMock()
    mock_course.id = "_c1"
    mock_course.course_id = "CSCI3150"

    with patch.object(client, "get_course", return_value=mock_course), \
         patch.object(client.session, "request", return_value=cols_resp):
        upcoming = client.list_assignments(course_id="_c1", upcoming_only=True)
        assert len(upcoming) == 1
        assert upcoming[0].id == "_future_col"
        assert upcoming[0].status == "Upcoming"

        all_items = client.list_assignments(course_id="_c1", upcoming_only=False)
        assert len(all_items) == 3


def test_download_material_direct_url(client: BlackboardClient, tmp_path: Path):
    file_bytes = b"webdav binary content"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Disposition": 'attachment; filename="notes.pdf"'}
    mock_resp.iter_content.return_value = [file_bytes]

    with patch.object(client.session, "request", return_value=mock_resp):
        dl_path = client.download_material(
            course_id="_c1_1",
            content_id="_item_1",
            attachment_id="/bbcswebdav/courses/CSCI3150/notes.pdf",
            target_dir=tmp_path,
        )
        assert dl_path.exists()
        assert dl_path.name == "notes.pdf"


def test_get_course_lookup_fallbacks(client: BlackboardClient):
    # Test primary ID lookup failure followed by courseId: prefix lookup success
    fail_resp = MagicMock()
    fail_resp.status_code = 404

    success_resp = MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = {
        "id": "_c999_1",
        "courseId": "2024R1-CSCI3150",
        "name": "Operating Systems",
    }

    with patch.object(client.session, "request", side_effect=[fail_resp, success_resp]):
        course = client.get_course("2024R1-CSCI3150")
        assert course.id == "_c999_1"
        assert course.course_id == "2024R1-CSCI3150"


def test_search_materials_empty_query(client: BlackboardClient):
    res = client.search_materials(query="   ")
    assert res == {"courses": [], "contents": [], "announcements": []}


def test_list_courses_ultra_html(client: BlackboardClient):
    api_fail = MagicMock()
    api_fail.status_code = 404

    portal_html = """
    <html><body>
        <div class="courses-list">
            <a href="/ultra/courses/_8877_1/outline">CSCI3180: Principles of Programming Languages</a>
            <a href="/ultra/courses/_8878_1">ENGG2440: Discrete Mathematics</a>
        </div>
    </body></html>
    """
    portal_ok = MagicMock()
    portal_ok.status_code = 200
    portal_ok.text = portal_html

    with patch.object(client.session, "request", side_effect=[api_fail, api_fail, portal_ok]):
        courses = client.list_courses()
        assert len(courses) == 2
        assert courses[0].id == "_8877_1"
        assert "Principles of Programming Languages" in courses[0].name
        assert courses[1].id == "_8878_1"


def test_list_assignments_and_course_summary_deadlines(client: BlackboardClient):
    course_resp = MagicMock()
    course_resp.status_code = 200
    course_resp.json.return_value = {
        "id": "_c1_1",
        "courseId": "CSCI3150",
        "name": "Operating Systems",
    }

    cols_resp = MagicMock()
    cols_resp.status_code = 200
    cols_resp.json.return_value = {
        "results": [
            {
                "id": "_col_asg1",
                "name": "Lab 1 Assignment",
                "dueDate": "2099-12-31T23:59:59Z",
                "grading": {"scoreTotal": 100.0},
            },
            {
                "id": "_col_past",
                "name": "Past Quiz",
                "dueDate": "2020-01-01T00:00:00Z",
                "grading": {"scoreTotal": 10.0},
            },
            {
                "id": "_col_null_grading",
                "name": "Survey",
                "grading": None,
            },
        ]
    }

    # Test list_assignments directly
    with patch.object(client.session, "request", side_effect=[course_resp, cols_resp]):
        asgs = client.list_assignments(course_id="_c1_1", upcoming_only=False)
        assert len(asgs) == 3
        assert asgs[0].title == "[CSCI3150] Lab 1 Assignment"
        assert asgs[0].points_possible == 100.0
        assert asgs[2].points_possible is None  # Handled grading=None gracefully

    # Test get_course_summary includes upcoming_deadlines
    anns_resp = MagicMock()
    anns_resp.status_code = 200
    anns_resp.json.return_value = {"results": []}

    contents_resp = MagicMock()
    contents_resp.status_code = 200
    contents_resp.json.return_value = {"results": []}

    empty_cols_resp = MagicMock()
    empty_cols_resp.status_code = 200
    empty_cols_resp.json.return_value = {"results": []}

    with patch.object(
        client.session,
        "request",
        side_effect=[course_resp, anns_resp, contents_resp, empty_cols_resp, course_resp, cols_resp],
    ):
        summary = client.get_course_summary("_c1_1")
        assert summary["course_id"] == "_c1_1"
        assert "upcoming_deadlines" in summary
        assert len(summary["upcoming_deadlines"]) >= 1
        assert summary["upcoming_deadlines"][0]["title"] == "[CSCI3150] Lab 1 Assignment"


