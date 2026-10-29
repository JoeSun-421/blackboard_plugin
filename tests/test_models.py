"""Unit tests for models."""

import pytest
from cuhk_blackboard.models import (
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


def test_auth_config_to_dict_masking():
    cfg = AuthConfig(
        method=AuthMethod.COOKIE,
        host="https://blackboard.cuhk.edu.hk",
        cookies={"session_id": "1234567890abcdef", "JSESSIONID": "secretval123"},
        bearer_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0",
        password="MySecretPassword123",
        username="s1155123456",
        duo_passcode="654321",
    )
    unmasked = cfg.to_dict(mask_secrets=False)
    assert unmasked["password"] == "MySecretPassword123"
    assert "session_id" in unmasked["cookies"]
    assert unmasked["cookies"]["session_id"] == "1234567890abcdef"

    masked = cfg.to_dict(mask_secrets=True)
    assert masked["password"] == "********"
    assert "..." in masked["cookies"]["session_id"]
    assert "..." in masked["bearer_token"]


def test_user_profile_from_api():
    api_data = {
        "id": "_1001_1",
        "userName": "s1155999999",
        "studentId": "1155999999",
        "name": {"given": "Tai Man", "family": "Chan"},
        "contact": {"email": "s1155999999@link.cuhk.edu.hk"},
        "systemRoleIds": ["Student"],
        "created": "2023-09-01T08:00:00Z",
    }
    profile = UserProfile.from_api(api_data)
    assert profile.user_id == "_1001_1"
    assert profile.username == "s1155999999"
    assert profile.student_id == "1155999999"
    assert profile.display_name == "Tai Man Chan"
    assert profile.email == "s1155999999@link.cuhk.edu.hk"
    assert "Student" in profile.system_role_ids


def test_course_from_api():
    api_data = {
        "id": "_2001_1",
        "courseId": "2024R1-CSCI3150",
        "name": "CSCI3150 - Operating Systems",
        "description": "Fundamental concepts in operating systems",
        "termId": "2024R1",
        "ultraStatus": "Ultra",
        "availability": {"available": "Yes"},
    }
    course = Course.from_api(api_data)
    assert course.id == "_2001_1"
    assert course.course_id == "2024R1-CSCI3150"
    assert course.name == "CSCI3150 - Operating Systems"
    assert course.is_ultra is True
    assert course.is_available is True


def test_content_item_from_api():
    api_data = {
        "id": "_3001_1",
        "title": "Lecture 1: Introduction",
        "body": "Welcome to the course",
        "contentHandler": {"id": "resource/x-bb-document"},
        "hasChildren": False,
        "attachmentList": [
            {
                "id": "_att_101",
                "fileName": "lecture1.pdf",
                "fileSize": 1048576,
                "mimeType": "application/pdf",
            }
        ],
    }
    item = ContentItem.from_api(api_data, course_id="_2001_1", base_host="https://blackboard.cuhk.edu.hk")
    assert item.id == "_3001_1"
    assert item.title == "Lecture 1: Introduction"
    assert item.content_type == ContentType.DOCUMENT
    assert len(item.attachments) == 1
    assert item.attachments[0].file_name == "lecture1.pdf"
    assert "attachments/_att_101/download" in item.attachments[0].download_url


def test_announcement_from_api():
    api_data = {
        "id": "_ann_01",
        "title": "Assignment 1 Released",
        "body": "<p>Please check <b>Homework</b> tab for details.</p>",
        "created": "2024-10-01T10:00:00Z",
    }
    ann = Announcement.from_api(api_data, course_id="_2001_1", course_name="CSCI3150")
    assert ann.id == "_ann_01"
    assert ann.title == "Assignment 1 Released"
    assert "<p>" in ann.content_html
    # Text version should have HTML tags stripped
    assert "Please check Homework tab for details." in ann.content_text
    assert "<p>" not in ann.content_text

    # Test link preservation in announcement markdown conversion
    link_data = {
        "id": "_ann_02",
        "title": "Zoom Link",
        "body": '<p>Join session at <a href="https://cuhk.zoom.us/j/999999">Zoom Room</a> now.</p>',
    }
    ann_link = Announcement.from_api(link_data)
    assert "[Zoom Room](https://cuhk.zoom.us/j/999999)" in ann_link.content_text


def test_grade_item_from_api():
    col_data = {
        "id": "_col_501",
        "name": "Midterm Exam",
        "dueDate": "2024-10-20T23:59:00Z",
        "grading": {"type": "Numeric", "scoreTotal": 100.0},
    }
    grade_data = {
        "score": 92.5,
        "status": "Graded",
        "feedback": "Great job on the virtual memory section!",
    }
    item = GradeItem.from_api(col_data=col_data, grade_data=grade_data, course_id="_2001_1")
    assert item.column_id == "_col_501"
    assert item.column_name == "Midterm Exam"
    assert item.score == 92.5
    assert item.points_possible == 100.0
    assert item.percentage == 92.5
    assert item.feedback == "Great job on the virtual memory section!"
    assert item.status == "Graded"

    # Test string score conversion without TypeError
    str_col = {"id": "_c2", "name": "Lab 1", "grading": {"scoreTotal": "50.0"}}
    str_grade = {"score": "45.0", "status": "Graded"}
    item_str = GradeItem.from_api(col_data=str_col, grade_data=str_grade)
    assert item_str.score == 45.0
    assert item_str.points_possible == 50.0
    assert item_str.percentage == 90.0
