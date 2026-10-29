"""Data models for CUHK Blackboard plugin.

Represents courses, contents, attachments, announcements, grades,
user profiles, and authentication configurations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class AuthMethod(str, Enum):
    """Supported user authentication methods for CUHK Blackboard."""
    COOKIE = "cookie"                  # Direct session cookie (JSESSIONID, session_id)
    TOKEN = "token"                    # OAuth Bearer Token / Mobile Token
    CREDENTIALS = "credentials"        # Username + Password + Duo 2FA
    INTERACTIVE = "interactive"        # Guided browser login prompt
    SAVED_SESSION = "saved_session"    # Stored session file or environment variable


class ContentType(str, Enum):
    """Blackboard content item types."""
    FOLDER = "folder"
    DOCUMENT = "document"
    FILE = "file"
    ASSIGNMENT = "assignment"
    TEST = "test"
    LINK = "link"
    ANNOUNCEMENT = "announcement"
    FORUM = "forum"
    UNKNOWN = "unknown"


@dataclass
class AuthConfig:
    """Authentication configuration for connecting to CUHK Blackboard."""
    method: AuthMethod = AuthMethod.COOKIE
    host: str = "https://blackboard.cuhk.edu.hk"
    cookies: Dict[str, str] = field(default_factory=dict)
    bearer_token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    duo_passcode: Optional[str] = None
    session_file: Optional[str] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None

    def to_dict(self, mask_secrets: bool = False) -> Dict[str, Any]:
        """Convert config to dictionary, optionally masking credentials."""
        masked_pwd = "********" if (mask_secrets and self.password) else self.password
        masked_token = (
            f"{self.bearer_token[:8]}...{self.bearer_token[-4:]}"
            if (mask_secrets and self.bearer_token and len(self.bearer_token) > 12)
            else self.bearer_token
        )
        cookies_copy = dict(self.cookies)
        if mask_secrets:
            for k in cookies_copy:
                val = cookies_copy[k]
                if len(val) > 8:
                    cookies_copy[k] = f"{val[:4]}...{val[-4:]}"
        return {
            "method": self.method.value,
            "host": self.host,
            "cookies": cookies_copy,
            "bearer_token": masked_token,
            "username": self.username,
            "password": masked_pwd,
            "has_duo_passcode": bool(self.duo_passcode),
            "session_file": self.session_file,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


@dataclass
class UserProfile:
    """Blackboard user profile."""
    user_id: str
    username: str
    student_id: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    system_role_ids: List[str] = field(default_factory=list)
    created: Optional[str] = None
    last_login: Optional[str] = None

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> UserProfile:
        name_info = data.get("name") or {}
        contact_info = data.get("contact") or {}
        given = name_info.get("given", "") if isinstance(name_info, dict) else ""
        family = name_info.get("family", "") if isinstance(name_info, dict) else ""
        display = f"{given} {family}".strip() or data.get("userName", "Student")
        return cls(
            user_id=data.get("id", ""),
            username=data.get("userName", ""),
            student_id=data.get("studentId"),
            given_name=given,
            family_name=family,
            display_name=display,
            email=contact_info.get("email") if isinstance(contact_info, dict) else None,
            system_role_ids=data.get("systemRoleIds", []),
            created=data.get("created"),
            last_login=data.get("lastLogin"),
        )


@dataclass
class Course:
    """Enrolled Blackboard course information."""
    id: str                                  # Primary key, e.g. "_12345_1"
    course_id: str                           # Course code string, e.g. "2024R1-CSCI3150"
    name: str                                # Title, e.g. "Operating Systems"
    description: Optional[str] = None
    term_id: Optional[str] = None
    term_name: Optional[str] = None
    instructors: List[str] = field(default_factory=list)
    is_ultra: bool = False
    is_available: bool = True
    role: Optional[str] = "Student"          # e.g. Student, Instructor, TeachingAssistant

    @classmethod
    def from_api(cls, data: Dict[str, Any], course_obj: Optional[Dict[str, Any]] = None) -> Course:
        # Handles both direct course item and membership object
        c = course_obj or data.get("course") or data
        raw_id = c.get("id") or data.get("courseId") or ""
        code = c.get("courseId") or c.get("id") or ""
        title = c.get("name") or code
        desc = c.get("description")
        term = c.get("termId")
        ultra = c.get("ultraStatus") == "Ultra"
        role = data.get("courseRoleId") or "Student"
        return cls(
            id=raw_id,
            course_id=code,
            name=title,
            description=desc,
            term_id=term,
            is_ultra=ultra,
            is_available=(c.get("availability") or {}).get("available", "Yes") == "Yes",
            role=role,
        )


@dataclass
class Attachment:
    """File attachment inside a course content item."""
    id: str
    file_name: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    download_url: Optional[str] = None

    @classmethod
    def from_api(cls, data: Dict[str, Any], course_id: str, content_id: str, base_host: str = "") -> Attachment:
        att_id = data.get("id", "")
        name = data.get("fileName") or data.get("name") or f"attachment_{att_id}"
        size = data.get("fileSize")
        mime = data.get("mimeType")
        # Blackboard standard REST download route
        dl_url = f"{base_host}/learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments/{att_id}/download"
        return cls(
            id=att_id,
            file_name=name,
            file_size=size,
            mime_type=mime,
            download_url=dl_url,
        )


@dataclass
class ContentItem:
    """Course content entry (Folder, Document, File, Assignment, etc.)."""
    id: str
    title: str
    content_type: ContentType
    body: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[str] = None
    has_children: bool = False
    attachments: List[Attachment] = field(default_factory=list)
    web_link: Optional[str] = None
    created: Optional[str] = None
    modified: Optional[str] = None
    position: Optional[int] = None

    @classmethod
    def from_api(cls, data: Dict[str, Any], course_id: str = "", base_host: str = "") -> ContentItem:
        cid = data.get("id", "")
        title = data.get("title") or "Untitled Item"
        body = data.get("body")
        desc = data.get("description")
        pid = data.get("parentId")
        has_ch = bool(data.get("hasChildren", False))
        handler_data = data.get("contentHandler") or {}
        handler_id = (handler_data.get("id", "") if isinstance(handler_data, dict) else "").lower()

        # Deduce content type from Blackboard contentHandler id
        ctype = ContentType.DOCUMENT
        if "folder" in handler_id:
            ctype = ContentType.FOLDER
            has_ch = True
        elif "file" in handler_id:
            ctype = ContentType.FILE
        elif "asg-test" in handler_id or "assessment" in handler_id or "assignment" in handler_id:
            ctype = ContentType.ASSIGNMENT
        elif "link" in handler_id:
            ctype = ContentType.LINK
        elif "forum" in handler_id:
            ctype = ContentType.FORUM

        # Parse attached files if present directly in payload
        attachments = []
        raw_atts = data.get("attachmentList") or data.get("attachments") or []
        for att in raw_atts:
            attachments.append(Attachment.from_api(att, course_id=course_id, content_id=cid, base_host=base_host))

        link_data = data.get("link") or {}
        web_link = (link_data.get("url") if isinstance(link_data, dict) else None) or data.get("url")

        return cls(
            id=cid,
            title=title,
            content_type=ctype,
            body=body,
            description=desc,
            parent_id=pid,
            has_children=has_ch,
            attachments=attachments,
            web_link=web_link,
            created=data.get("created"),
            modified=data.get("modified"),
            position=data.get("position"),
        )


@dataclass
class Announcement:
    """Course announcement."""
    id: str
    title: str
    content_html: str
    content_text: str
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    course_id: Optional[str] = None
    course_name: Optional[str] = None
    creator_id: Optional[str] = None

    @classmethod
    def from_api(cls, data: Dict[str, Any], course_id: Optional[str] = None, course_name: Optional[str] = None) -> Announcement:
        from bs4 import BeautifulSoup
        raw_body = data.get("body") or data.get("description") or ""
        soup = BeautifulSoup(raw_body, "html.parser")

        # Convert links to markdown format [text](href) so agent receives clickable URLs
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            text_inside = a_tag.get_text().strip()
            if href and text_inside and href != text_inside:
                a_tag.replace_with(f"[{text_inside}]({href})")
            elif href:
                a_tag.replace_with(href)

        for tag in soup.find_all(["br", "p", "div", "tr", "h1", "h2", "h3", "h4", "li"]):
            tag.append("\n")
        lines = [line.strip() for line in soup.get_text().splitlines()]
        text = "\n".join(l for l in lines if l).strip()
        return cls(
            id=data.get("id", ""),
            title=data.get("title") or "No Title",
            content_html=raw_body,
            content_text=text,
            created_at=data.get("created"),
            modified_at=data.get("modified"),
            course_id=course_id or data.get("courseId"),
            course_name=course_name,
            creator_id=data.get("creatorUserId"),
        )


@dataclass
class GradeItem:
    """Gradebook entry / score for a student."""
    column_id: str
    column_name: str
    score: Optional[float] = None
    points_possible: Optional[float] = None
    percentage: Optional[float] = None
    letter_grade: Optional[str] = None
    status: Optional[str] = None             # e.g., "Graded", "NeedsGrading", "NotAttempted"
    due_date: Optional[str] = None
    feedback: Optional[str] = None
    course_id: Optional[str] = None

    @classmethod
    def from_api(cls, col_data: Dict[str, Any], grade_data: Optional[Dict[str, Any]] = None, course_id: Optional[str] = None) -> GradeItem:
        col_id = col_data.get("id", "")
        name = col_data.get("name") or "Unnamed Item"
        due = col_data.get("dueDate")
        grading = col_data.get("grading", {})
        raw_pts = grading.get("scoreTotal")

        pts_possible = None
        if raw_pts is not None:
            try:
                pts_possible = float(raw_pts)
            except (ValueError, TypeError):
                pts_possible = None

        score = None
        status = "NotAttempted"
        feedback = None
        text_val = None

        if grade_data:
            raw_score = grade_data.get("score")
            if raw_score is not None:
                try:
                    score = float(raw_score)
                except (ValueError, TypeError):
                    score = None
            status = grade_data.get("status") or "Graded"
            feedback = grade_data.get("feedback")
            text_val = grade_data.get("text")

        pct = None
        if score is not None and pts_possible and pts_possible > 0:
            pct = round((score / pts_possible) * 100, 2)

        return cls(
            column_id=col_id,
            column_name=name,
            score=score,
            points_possible=pts_possible,
            percentage=pct,
            letter_grade=text_val,
            status=status,
            due_date=due,
            feedback=feedback,
            course_id=course_id,
        )


@dataclass
class Assignment:
    """Course assignment item."""
    id: str
    course_id: str
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    points_possible: Optional[float] = None
    submitted: bool = False
    grade: Optional[float] = None
    status: str = "Pending"                  # Pending, Submitted, Overdue, Graded
