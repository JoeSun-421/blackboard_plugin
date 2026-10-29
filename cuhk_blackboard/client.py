"""Blackboard API Client and Scraper for CUHK.

Provides REST API access and fallback HTML scraping for courses, contents,
announcements, assignments, grades, and file downloads.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .auth import AuthManager
from .models import (
    Announcement,
    Assignment,
    Attachment,
    ContentItem,
    ContentType,
    Course,
    GradeItem,
    UserProfile,
)


class BlackboardClient:
    """Client for interacting with CUHK Blackboard Learn."""

    def __init__(
        self,
        auth_manager: Optional[AuthManager] = None,
        host: Optional[str] = None,
        timeout: int = 15,
    ):
        self.auth_manager = auth_manager or AuthManager()
        if host:
            self.auth_manager.host = host.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    @property
    def host(self) -> str:
        return self.auth_manager.host

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        stream: bool = False,
        headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        """Execute an authenticated HTTP request to Blackboard."""
        url = urljoin(self.host, path)
        req_headers = self.auth_manager.get_auth_headers()
        if headers:
            req_headers.update(headers)

        # Set cookies directly into Cookie header if present
        if self.auth_manager.config.cookies and "Cookie" not in req_headers:
            req_headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in self.auth_manager.config.cookies.items()])

        resp = self.session.request(
            method=method,
            url=url,
            params=params,
            json=json_data,
            data=data,
            headers=req_headers,
            timeout=self.timeout,
            stream=stream,
            allow_redirects=True,
        )
        return resp

    def verify_auth(self) -> Tuple[bool, Union[UserProfile, str]]:
        """Verify if current authentication credentials are valid.
        
        Returns:
            Tuple of (is_valid: bool, profile_or_error: UserProfile or str message)
        """
        if not self.auth_manager.is_configured:
            return False, "Authentication not configured. Please use cuhk_bb_configure_auth to set cookies or token."

        try:
            # 1. Try REST API endpoint /learn/api/public/v1/users/me
            resp = self._request("GET", "/learn/api/public/v1/users/me")
            if resp.status_code == 200:
                data = resp.json()
                profile = UserProfile.from_api(data)
                return True, profile
            elif resp.status_code in (401, 403):
                # 2. Try web portal check as fallback for browser session cookies
                portal_resp = self._request("GET", "/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1")
                
                # Check whether redirected to unauthenticated login / SAML ADFS pages
                is_login_page = (
                    "webapps/login" in portal_resp.url.lower()
                    or "auth-saml" in portal_resp.text.lower()
                    or "sts.cuhk.edu.hk" in portal_resp.url.lower()
                    or "loginform" in portal_resp.text.lower()
                    or 'refresh" content="0;url=' in portal_resp.text.lower()
                )
                has_logout = (
                    "action=logout" in portal_resp.text.lower()
                    or "/webapps/login?action=logout" in portal_resp.text.lower()
                    or bool(self._parse_user_name_from_portal(portal_resp.text))
                )

                if portal_resp.status_code == 200 and has_logout and not is_login_page:
                    extracted_name = self._parse_user_name_from_portal(portal_resp.text)
                    profile = UserProfile(
                        user_id="me",
                        username=self.auth_manager.config.username or "cuhk_student",
                        display_name=extracted_name or "CUHK Student",
                    )
                    return True, profile
                return False, f"Authentication failed (HTTP {resp.status_code}): Session cookie or token is expired/invalid."
            else:
                return False, f"Server returned unexpected status code {resp.status_code}."
        except requests.RequestException as e:
            return False, f"Network error during verification: {str(e)}"

    def get_user_profile(self) -> UserProfile:
        """Fetch current authenticated user profile."""
        resp = self._request("GET", "/learn/api/public/v1/users/me")
        if resp.status_code == 200:
            return UserProfile.from_api(resp.json())
        elif resp.status_code in (401, 403):
            raise PermissionError("Authentication invalid or expired. Please update session cookies.")
        else:
            raise RuntimeError(f"Failed to fetch user profile: HTTP {resp.status_code}")

    def list_courses(self, include_hidden: bool = False) -> List[Course]:
        """Fetch all courses the user is enrolled in.
        
        Tries user memberships endpoint first, then courses endpoint, with HTML scraping fallback.
        """
        courses: List[Course] = []

        # Attempt 1: /learn/api/public/v1/users/me/courses
        resp = self._request("GET", "/learn/api/public/v1/users/me/courses")
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            for item in results:
                # If course name is already present or nested course object is included
                if "name" in item or "course" in item:
                    courses.append(Course.from_api(item))
                else:
                    c_id = item.get("courseId")
                    course_detail = self._get_course_detail_safely(c_id) if c_id else None
                    courses.append(Course.from_api(item, course_obj=course_detail))
            return courses

        # Attempt 2: /learn/api/public/v1/courses
        resp = self._request("GET", "/learn/api/public/v1/courses")
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("results", []):
                courses.append(Course.from_api(item))
            return courses

        # Attempt 3: Web Portal HTML fallback
        portal_resp = self._request("GET", "/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1")
        if portal_resp.status_code == 200:
            courses = self._parse_courses_from_html(portal_resp.text)
            if courses:
                return courses

        raise RuntimeError(f"Failed to list courses: HTTP {resp.status_code} - {resp.text[:200]}")

    def get_course(self, course_id: str) -> Course:
        """Fetch details for a specific course by ID or course code."""
        # Attempt 1: Direct course ID (e.g. primary key _12345_1)
        resp = self._request("GET", f"/learn/api/public/v1/courses/{course_id}")
        if resp.status_code == 200:
            return Course.from_api(resp.json())

        # Attempt 2: Course code with courseId: prefix if not already prefixed
        if not course_id.startswith("courseId:") and not course_id.startswith("_"):
            resp_code = self._request("GET", f"/learn/api/public/v1/courses/courseId:{course_id}")
            if resp_code.status_code == 200:
                return Course.from_api(resp_code.json())

        # Attempt 3: Search within user's enrolled courses
        try:
            courses = self.list_courses()
            for c in courses:
                if (
                    c.id == course_id
                    or c.course_id.lower() == course_id.lower()
                    or course_id.lower() in c.course_id.lower()
                    or course_id.lower() in c.name.lower()
                ):
                    return c
        except Exception:
            pass

        raise RuntimeError(f"Course '{course_id}' not found (HTTP {resp.status_code})")

    def list_course_contents(
        self,
        course_id: str,
        content_id: Optional[str] = None,
        recursive: bool = False,
        max_depth: int = 3,
    ) -> List[ContentItem]:
        """Fetch course materials, lecture notes, syllabus, and folders.
        
        Args:
            course_id: Course ID (e.g. "_12345_1" or "2024R1-CSCI3150").
            content_id: If specified, fetches children of this folder; if None, fetches top-level.
            recursive: Whether to recursively traverse subfolders.
            max_depth: Maximum recursion depth for subfolders.
        """
        items = self._fetch_contents_level(course_id, content_id)
        if not recursive or max_depth <= 1:
            return items

        result: List[ContentItem] = []
        for item in items:
            result.append(item)
            if item.has_children or item.content_type == ContentType.FOLDER:
                try:
                    sub_items = self.list_course_contents(
                        course_id=course_id,
                        content_id=item.id,
                        recursive=True,
                        max_depth=max_depth - 1,
                    )
                    result.extend(sub_items)
                except Exception:
                    # Ignore partial folder read failure and continue
                    pass
        return result

    def _fetch_contents_level(self, course_id: str, content_id: Optional[str] = None) -> List[ContentItem]:
        """Fetch a single level of course contents."""
        path = (
            f"/learn/api/public/v1/courses/{course_id}/contents/{content_id}/children"
            if content_id
            else f"/learn/api/public/v1/courses/{course_id}/contents"
        )
        resp = self._request("GET", path)
        if resp.status_code == 200:
            data = resp.json()
            raw_items = data.get("results", [])
            items = []
            for raw in raw_items:
                item = ContentItem.from_api(raw, course_id=course_id, base_host=self.host)
                # Fetch attachments if item indicates files and none were in payload
                if item.content_type in (ContentType.FILE, ContentType.DOCUMENT, ContentType.ASSIGNMENT) and not item.attachments:
                    try:
                        item.attachments = self._fetch_item_attachments(course_id, item.id)
                    except Exception:
                        pass
                items.append(item)
            return items

        # Fallback to web content view if REST API fails
        try:
            html_resp = self._request(
                "GET",
                f"/webapps/blackboard/content/listContentEditable.jsp?content_id={content_id or ''}&course_id={course_id}",
            )
            if html_resp.status_code == 200:
                return self._parse_contents_from_html(html_resp.text, course_id)
        except Exception:
            pass

        return []

    def _fetch_item_attachments(self, course_id: str, content_id: str) -> List[Attachment]:
        """Fetch attachments for a specific content item."""
        try:
            resp = self._request("GET", f"/learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments")
            if resp.status_code == 200:
                data = resp.json()
                return [
                    Attachment.from_api(raw, course_id=course_id, content_id=content_id, base_host=self.host)
                    for raw in data.get("results", [])
                ]
        except Exception:
            pass
        return []

    def list_announcements(self, course_id: Optional[str] = None, limit: int = 20) -> List[Announcement]:
        """Fetch announcements for a specific course or across enrolled courses."""
        announcements: List[Announcement] = []

        if course_id:
            resp = self._request("GET", f"/learn/api/public/v1/courses/{course_id}/announcements")
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("results", [])[:limit]:
                    announcements.append(Announcement.from_api(item, course_id=course_id))
                return announcements

            # Fallback to web announcement page
            web_resp = self._request("GET", f"/webapps/blackboard/execute/announcement?course_id={course_id}")
            if web_resp.status_code == 200:
                return self._parse_announcements_from_html(web_resp.text, course_id=course_id)[:limit]
            return []

        # If no course_id provided, fetch system or iterate courses
        # If no course_id provided, fetch both system-wide and course-level announcements
        resp = self._request("GET", "/learn/api/public/v1/announcements")
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("results", [])[:limit]:
                announcements.append(Announcement.from_api(item))

        # Also iterate active courses to collect course announcements
        try:
            courses = self.list_courses()
            for c in courses[:5]:
                try:
                    course_anns = self.list_announcements(course_id=c.id, limit=5)
                    for ann in course_anns:
                        ann.course_name = c.name
                        announcements.append(ann)
                except Exception:
                    continue
        except Exception:
            pass

        # Sort descending by created timestamp if available
        announcements.sort(key=lambda a: a.created or a.created_at or "", reverse=True)
        return announcements[:limit]

    def list_assignments(self, course_id: Optional[str] = None, upcoming_only: bool = False) -> List[Assignment]:
        """Fetch assignments and deadlines from gradebook and content items."""
        assignments: List[Assignment] = []
        target_courses = [self.get_course(course_id)] if course_id else self.list_courses()

        now_utc = None
        if upcoming_only:
            from datetime import datetime, timezone
            now_utc = datetime.now(timezone.utc)

        for c in target_courses:
            try:
                # Query gradebook columns to find graded tasks and assignments
                resp = self._request("GET", f"/learn/api/public/v1/courses/{c.id}/gradebook/columns")
                if resp.status_code == 200:
                    data = resp.json()
                    for col in data.get("results", []):
                        name = col.get("name", "")
                        due_date = col.get("dueDate")

                        # If upcoming_only requested, filter out items without due dates or already passed
                        is_upcoming = False
                        if due_date:
                            try:
                                from datetime import datetime, timezone
                                clean_due = due_date.replace("Z", "+00:00")
                                due_dt = datetime.fromisoformat(clean_due)
                                if now_utc and due_dt < now_utc:
                                    # Past deadline
                                    continue
                                is_upcoming = True
                            except Exception:
                                is_upcoming = True
                        elif upcoming_only:
                            continue

                        # Include if marked as assignment/test or has a due date
                        grading = col.get("grading") or {}
                        raw_points = grading.get("scoreTotal") if isinstance(grading, dict) else None
                        points = float(raw_points) if raw_points is not None else None
                        assignments.append(
                            Assignment(
                                id=col.get("id", ""),
                                course_id=c.id,
                                title=f"[{c.course_id}] {name}",
                                description=col.get("description"),
                                due_date=due_date,
                                points_possible=points,
                                status="Upcoming" if is_upcoming else "Normal",
                            )
                        )
            except Exception:
                continue

        return assignments

    def get_grades(self, course_id: str) -> List[GradeItem]:
        """Fetch student gradebook scores and feedback for a course."""
        grade_items: List[GradeItem] = []

        # 1. Get Gradebook Columns
        resp = self._request("GET", f"/learn/api/public/v1/courses/{course_id}/gradebook/columns")
        if resp.status_code == 200:
            cols = resp.json().get("results", [])
            for col in cols:
                col_id = col.get("id")
                # Try fetching user attempt score for this column
                grade_data = None
                try:
                    user_grade_resp = self._request(
                        "GET", f"/learn/api/public/v1/courses/{course_id}/gradebook/columns/{col_id}/users/me"
                    )
                    if user_grade_resp.status_code == 200:
                        grade_data = user_grade_resp.json()
                except Exception:
                    pass

                grade_items.append(
                    GradeItem.from_api(col_data=col, grade_data=grade_data, course_id=course_id)
                )
            return grade_items

        # Fallback to web Gradebook
        html_resp = self._request("GET", f"/webapps/gradebook/do/student/viewGrades?course_id={course_id}")
        if html_resp.status_code == 200:
            return self._parse_grades_from_html(html_resp.text, course_id)

        return []

    def download_material(
        self,
        course_id: str,
        content_id: str,
        attachment_id: str,
        target_dir: Union[str, Path] = "./downloaded_materials",
        filename: Optional[str] = None,
    ) -> Path:
        """Download course attachment file to local disk."""
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        if attachment_id.startswith("http://") or attachment_id.startswith("https://"):
            download_path = attachment_id
        elif attachment_id.startswith("/"):
            download_path = attachment_id
        else:
            download_path = f"/learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments/{attachment_id}/download"
        
        resp = self._request("GET", download_path, stream=True)

        if resp.status_code != 200:
            raise RuntimeError(f"Download failed with HTTP {resp.status_code}: {resp.text[:200]}")

        # Determine file name from Content-Disposition header if not provided
        if not filename:
            cd = resp.headers.get("Content-Disposition", "")
            match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
            if match:
                filename = match.group(1).strip()
            else:
                filename = f"file_{attachment_id.split('/')[-1]}"

        safe_filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
        file_path = target_dir / safe_filename

        with open(file_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return file_path

    def search_materials(self, query: str, course_id: Optional[str] = None) -> Dict[str, Any]:
        """Search course contents and announcements by keyword."""
        query_clean = query.strip()
        results: Dict[str, List[Any]] = {
            "courses": [],
            "contents": [],
            "announcements": [],
        }
        if not query_clean:
            return results

        query_lower = query_clean.lower()

        # Search course names
        courses = []
        if course_id:
            try:
                courses = [self.get_course(course_id)]
            except Exception:
                courses = []
        else:
            try:
                courses = self.list_courses()
            except Exception:
                courses = []

        for c in courses:
            if query_lower in c.name.lower() or query_lower in c.course_id.lower():
                results["courses"].append(c)

            # Search announcements
            try:
                anns = self.list_announcements(course_id=c.id, limit=20)
                for a in anns:
                    if query_lower in a.title.lower() or query_lower in a.content_text.lower():
                        results["announcements"].append(a)
            except Exception:
                pass

            # Search contents
            try:
                contents = self.list_course_contents(course_id=c.id, recursive=True, max_depth=2)
                for item in contents:
                    if (
                        query_lower in item.title.lower()
                        or (item.description and query_lower in item.description.lower())
                        or (item.body and query_lower in item.body.lower())
                    ):
                        results["contents"].append(item)
            except Exception:
                pass

        return results

    def get_course_summary(self, course_id: str) -> Dict[str, Any]:
        """Generate a concise, LLM-optimized summary of course state, deadlines, materials, and announcements."""
        course = self.get_course(course_id)
        recent_announcements = self.list_announcements(course_id=course.id, limit=3)
        contents = self.list_course_contents(course_id=course.id, recursive=False)
        grades = self.get_grades(course_id=course.id)

        try:
            assignments = self.list_assignments(course_id=course.id, upcoming_only=True)
            upcoming_deadlines = [
                {"title": a.title, "due_date": a.due_date, "points": a.points_possible}
                for a in assignments[:5]
            ]
        except Exception:
            upcoming_deadlines = []

        announcement_summaries = [
            {"title": a.title, "date": a.created_at, "preview": a.content_text[:150] + ("..." if len(a.content_text) > 150 else "")}
            for a in recent_announcements
        ]

        content_previews = [
            {"title": item.title, "type": item.content_type.value, "has_children": item.has_children, "attachments_count": len(item.attachments)}
            for item in contents[:10]
        ]

        recent_grades = [
            {"item": g.column_name, "score": g.score, "total": g.points_possible, "status": g.status}
            for g in grades[:5] if g.score is not None or g.status == "Graded"
        ]

        return {
            "course_id": course.id,
            "code": course.course_id,
            "name": course.name,
            "term": course.term_id,
            "recent_announcements": announcement_summaries,
            "upcoming_deadlines": upcoming_deadlines,
            "top_level_contents": content_previews,
            "grades_overview": recent_grades,
        }

    # Internal helper parsers
    def _get_course_detail_safely(self, course_id: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self._request("GET", f"/learn/api/public/v1/courses/{course_id}")
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def _parse_user_name_from_portal(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        name_elem = soup.find(id="global-nav-link") or soup.find(class_="user-name")
        if name_elem:
            return name_elem.get_text().strip()
        return None

    def _parse_courses_from_html(self, html: str) -> List[Course]:
        courses: List[Course] = []
        soup = BeautifulSoup(html, "html.parser")
        pattern = re.compile(r"(?:(?:course_id|id)=|/courses/)(_\d+_\d+)")
        links = soup.find_all("a", href=pattern)
        seen = set()
        for link in links:
            match = pattern.search(link.get("href", ""))
            if match:
                c_id = match.group(1)
                if c_id not in seen:
                    seen.add(c_id)
                    title = link.get_text().strip()
                    if title:
                        courses.append(
                            Course(
                                id=c_id,
                                course_id=title.split(":")[0].strip() if ":" in title else title,
                                name=title,
                            )
                        )
        return courses

    def _parse_announcements_from_html(self, html: str, course_id: str) -> List[Announcement]:
        announcements: List[Announcement] = []
        soup = BeautifulSoup(html, "html.parser")
        items = soup.find_all(class_=re.compile(r"announcementItem|announcement-item"))
        for item in items:
            title_elem = item.find(["h3", "h4", "a"])
            title = title_elem.get_text().strip() if title_elem else "Announcement"
            body_elem = item.find(class_=re.compile(r"announcement-details|details")) or item
            body_text = body_elem.get_text(separator="\n").strip()
            announcements.append(
                Announcement(
                    id=item.get("id", ""),
                    title=title,
                    content_html=str(body_elem),
                    content_text=body_text,
                    course_id=course_id,
                )
            )
        return announcements

    def _parse_contents_from_html(self, html: str, course_id: str) -> List[ContentItem]:
        contents: List[ContentItem] = []
        soup = BeautifulSoup(html, "html.parser")
        content_nodes = soup.find_all(class_=re.compile(r"contentList|content-item|clearfix"))
        for node in content_nodes:
            title_elem = node.find(["h3", "a"])
            if not title_elem:
                continue
            title = title_elem.get_text().strip()
            item_id = node.get("id") or f"item_{len(contents)}"
            contents.append(
                ContentItem(
                    id=item_id,
                    title=title,
                    content_type=ContentType.DOCUMENT,
                    body=node.get_text().strip(),
                )
            )
        return contents

    def _parse_grades_from_html(self, html: str, course_id: str) -> List[GradeItem]:
        grades: List[GradeItem] = []
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all(class_=re.compile(r"graded_item_row|grade-item"))
        for row in rows:
            name_elem = row.find(class_=re.compile(r"cell|item-name|title"))
            score_elem = row.find(class_=re.compile(r"grade|score"))
            if name_elem:
                name = name_elem.get_text().strip()
                score_str = score_elem.get_text().strip() if score_elem else None
                score_val = None
                if score_str:
                    num_match = re.search(r"(\d+(?:\.\d+)?)", score_str)
                    if num_match:
                        score_val = float(num_match.group(1))
                grades.append(
                    GradeItem(
                        column_id=f"col_{len(grades)}",
                        column_name=name,
                        score=score_val,
                        course_id=course_id,
                    )
                )
        return grades
