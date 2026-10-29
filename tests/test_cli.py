"""Unit tests for the CLI."""

from unittest.mock import MagicMock, patch

import pytest
from cuhk_blackboard import cli
from cuhk_blackboard.models import Announcement, ContentItem, ContentType, Course, GradeItem


def test_cli_courses_command(capsys):
    mock_courses = [
        Course(id="_c1", course_id="CSCI3150", name="Operating Systems"),
    ]
    with patch("cuhk_blackboard.cli.BlackboardClient") as mock_client_cls:
        instance = mock_client_cls.return_value
        instance.list_courses.return_value = mock_courses

        cli.main(["courses"])
        captured = capsys.readouterr()
        assert "CSCI3150" in captured.out
        assert "Operating Systems" in captured.out


def test_cli_contents_command(capsys):
    mock_contents = [
        ContentItem(id="_cnt1", title="Syllabus", content_type=ContentType.DOCUMENT),
    ]
    with patch("cuhk_blackboard.cli.BlackboardClient") as mock_client_cls:
        instance = mock_client_cls.return_value
        instance.list_course_contents.return_value = mock_contents

        cli.main(["contents", "--course", "_c1"])
        captured = capsys.readouterr()
        assert "Syllabus" in captured.out


def test_cli_announcements_command(capsys):
    mock_ann = [
        Announcement(id="_a1", title="Midterm date changed", content_html="", content_text="Exam moved to Monday"),
    ]
    with patch("cuhk_blackboard.cli.BlackboardClient") as mock_client_cls:
        instance = mock_client_cls.return_value
        instance.list_announcements.return_value = mock_ann

        cli.main(["announcements", "--course", "_c1"])
        captured = capsys.readouterr()
        assert "Midterm date changed" in captured.out
        assert "Exam moved to Monday" in captured.out


def test_cli_grades_command(capsys):
    mock_grades = [
        GradeItem(column_id="_col1", column_name="Quiz 1", score=10.0, points_possible=10.0, status="Graded"),
    ]
    with patch("cuhk_blackboard.cli.BlackboardClient") as mock_client_cls:
        instance = mock_client_cls.return_value
        instance.get_grades.return_value = mock_grades

        cli.main(["grades", "--course", "_c1"])
        captured = capsys.readouterr()
        assert "Quiz 1" in captured.out
        assert "10.0/10.0" in captured.out
