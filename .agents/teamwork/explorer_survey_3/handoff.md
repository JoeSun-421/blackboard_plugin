# Technical Survey Report: Blackboard Core API/Tool Implementations & Test Architecture

**Author**: `teamwork_explorer` (`explorer_survey_3`)  
**Target Path**: `d:\blackboard_plugin`  
**Timestamp**: 2026-10-29T14:55:00Z  

---

## 1. Observation

### 1.1 Core API & Agent Tools Implementation

Directly inspected files:
- `cuhk_blackboard/models.py` (363 lines)
- `cuhk_blackboard/client.py` (674 lines)
- `cuhk_blackboard/tools.py` (629 lines)
- `cuhk_blackboard/mcp_server.py` (202 lines)

Key observations and code structures:

1. **Tool Registry & Global Client Instance**:
   - `cuhk_blackboard/tools.py:20-27`: Defines a module-level singleton `_global_client: Optional[BlackboardClient] = None` retrieved via `get_client()`.
   - `cuhk_blackboard/tools.py:366-612`: `AGENT_TOOLS_DEFINITIONS` exposes 13 JSON Schema definitions compatible with MCP, OpenAI function calling, and Claude Tools.
   - `cuhk_blackboard/tools.py:614-628`: `TOOL_FUNCTION_MAP` maps tool names 1:1 to callable Python functions:
     - Auth & Session: `cuhk_bb_configure_auth`, `cuhk_bb_auth_status`, `cuhk_bb_capture_browser_session`, `cuhk_bb_get_auth_guide`
     - Courses: `cuhk_bb_list_courses`, `cuhk_bb_get_course_details`
     - Contents & Materials: `cuhk_bb_list_course_contents`, `cuhk_bb_download_material`, `cuhk_bb_search_materials`
     - Announcements & Communication: `cuhk_bb_list_announcements`
     - Assignments & Deadlines: `cuhk_bb_list_assignments`
     - Grades & Feedback: `cuhk_bb_get_grades`
     - Context Aggregation: `cuhk_bb_get_course_summary`

2. **Course Operations (`cuhk_blackboard/client.py:144-210`)**:
   - `list_courses(include_hidden=False)`:
     - Tier 1: `GET /learn/api/public/v1/users/me/courses`
     - Tier 2: `GET /learn/api/public/v1/courses`
     - Tier 3: HTML fallback via `GET /webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1` parsed by `_parse_courses_from_html()` using regex `r"(?:(?:course_id|id)=|/courses/)(_\d+_\d+)"`
   - `get_course(course_id)`:
     - Tier 1: `GET /learn/api/public/v1/courses/{course_id}`
     - Tier 2: `GET /learn/api/public/v1/courses/courseId:{course_id}` (if not prefixed)
     - Tier 3: In-memory fuzzy search across enrolled courses (`list_courses()`) comparing id, course_id, and name.

3. **Content & Folder Hierarchy Traversal (`cuhk_blackboard/client.py:212-282`)**:
   - `list_course_contents(course_id, content_id=None, recursive=False, max_depth=3)`:
     - `_fetch_contents_level()`: calls `GET /learn/api/public/v1/courses/{course_id}/contents/{content_id}/children` (or root `/contents`).
     - Attachment enrichment: if item content type is `FILE`, `DOCUMENT`, or `ASSIGNMENT` and payload has no inline attachments, invokes `_fetch_item_attachments(course_id, item.id)` (`GET .../contents/{content_id}/attachments`).
     - HTML fallback: `GET /webapps/blackboard/content/listContentEditable.jsp?content_id={content_id}&course_id={course_id}` parsed by `_parse_contents_from_html()`.
     - Recursive traversal: when `recursive=True` and `item.has_children` or type is `FOLDER`, recursively invokes `list_course_contents` with decremented `max_depth - 1`.

4. **Announcements (`cuhk_blackboard/client.py:298-341` & `models.py:257-285`)**:
   - Specific course: `GET /learn/api/public/v1/courses/{course_id}/announcements`; HTML fallback `GET /webapps/blackboard/execute/announcement?course_id={course_id}`.
   - Cross-course aggregation: if `course_id` is omitted, fetches system announcements (`GET /learn/api/public/v1/announcements`) and queries up to 5 enrolled courses (5 announcements each), sorting descending by creation timestamp.
   - Markdown link preservation: in `Announcement.from_api()`, BeautifulSoup parses raw HTML:
     ```python
     for a_tag in soup.find_all("a", href=True):
         href = a_tag["href"].strip()
         text_inside = a_tag.get_text().strip()
         if href and text_inside and href != text_inside:
             a_tag.replace_with(f"[{text_inside}]({href})")
         elif href:
             a_tag.replace_with(href)
     ```
     Block tags (`<br>`, `<p>`, `<div>`, `<tr>`, `<h1>`-`<h4>`, `<li>`) are converted to newlines, producing clean Markdown text for LLMs.

5. **Assignments & Deadlines (`cuhk_blackboard/client.py:342-396`)**:
   - Queries gradebook columns: `GET /learn/api/public/v1/courses/{c.id}/gradebook/columns`.
   - Deadline calculation: parses ISO timestamps (`clean_due = due_date.replace("Z", "+00:00")`), compares against UTC `now` when `upcoming_only=True`, filtering out expired deadlines.
   - Status tagging: dynamically tags status as `"Upcoming"` or `"Normal"`.

6. **Grades & Feedback (`cuhk_blackboard/client.py:398-430`)**:
   - Queries column schemas (`GET .../gradebook/columns`), then for each column queries user attempt score via `GET /learn/api/public/v1/courses/{course_id}/gradebook/columns/{col_id}/users/me`.
   - HTML fallback: `GET /webapps/gradebook/do/student/viewGrades?course_id={course_id}` parsed by `_parse_grades_from_html()` with regex score matching.
   - Percentage calculation in `GradeItem.from_api()`: `pct = round((score / pts_possible) * 100, 2)`.

7. **Material Downloads (`cuhk_blackboard/client.py:431-473`)**:
   - Handles REST attachment URLs, relative paths (`/bbcswebdav/...`), and absolute URLs.
   - REST download endpoint: `/learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments/{attachment_id}/download`.
   - Streams response (`stream=True`) in 8192-byte chunks.
   - Extracts filenames from `Content-Disposition` header regex:
     `r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)'`
   - Sanitizes Windows/POSIX illegal characters via `re.sub(r'[\\/*?:"<>|]', "_", filename)`.

8. **Unified Keyword Search (`cuhk_blackboard/client.py:474-526`)**:
   - `search_materials(query, course_id=None)`:
     - Validates query (returns immediately if whitespace/empty).
     - Searches course codes and names.
     - Searches announcements (title and `content_text`).
     - Searches course contents recursively up to depth 2 (title, description, and body).
     - Returns aggregate dictionary: `{"courses": [...], "contents": [...], "announcements": [...]}`.

9. **LLM Course Summary Generation (`cuhk_blackboard/client.py:528-569`)**:
   - Compact high-density representation designed to minimize token usage:
     - Top 3 recent announcements with 150-character previews.
     - Top 5 upcoming deadlines with point weights.
     - Top 10 top-level contents with child indicator and attachment count.
     - Top 5 recent grades with points possible and status.

---

### 1.2 Request Dispatching, Scraping vs REST, Pagination, Error Handling & Rate Limiting

1. **Request Dispatching Pipeline (`cuhk_blackboard/client.py:50-84`)**:
   ```python
   def _request(self, method, path, params=None, json_data=None, data=None, stream=False, headers=None):
       url = urljoin(self.host, path)
       req_headers = self.auth_manager.get_auth_headers()
       req_headers.pop("Cookie", None) # Prevents conflicting Cookie header overrides
       if headers:
           req_headers.update(headers)
       self.session.cookies.clear()
       if self.auth_manager.config.cookies:
           self.session.cookies.update(self.auth_manager.config.cookies)
       return self.session.request(...)
   ```
   - Normalizes host URLs and path concatenation using `urljoin`.
   - Headers include browser-like `User-Agent`, `Accept`, `Referer`, `Origin`, and optional `Authorization: Bearer <token>` or `X-Blackboard-SXS`.
   - Clears and sets `session.cookies` to allow standard `requests.Session` cookie jar handling.

2. **REST vs HTML Fallback Matrix**:

   | Operation | Primary REST Endpoint | Fallback HTML URL | Parser Mechanism |
   |---|---|---|---|
   | **Auth Verification** | `GET /learn/api/public/v1/users/me` | `GET /webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1` | Checks for redirect to SAML ADFS/login vs logout button / `.user-name` |
   | **List Courses** | `GET /learn/api/public/v1/users/me/courses`<br>`GET /learn/api/public/v1/courses` | `GET /webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1` | BeautifulSoup parses `<a href>` matching `r"(?:(?:course_id\|id)=\|/courses/)(_\d+_\d+)"` |
   | **Course Contents** | `GET .../contents/{id}/children`<br>`GET .../contents` | `GET /webapps/blackboard/content/listContentEditable.jsp?content_id=...` | BeautifulSoup parses `.contentList`, `.content-item`, `.clearfix` |
   | **Announcements** | `GET .../courses/{id}/announcements`<br>`GET .../announcements` | `GET /webapps/blackboard/execute/announcement?course_id=...` | BeautifulSoup parses `.announcementItem`, `.announcement-details` |
   | **Grades** | `GET .../gradebook/columns` & `.../users/me` | `GET /webapps/gradebook/do/student/viewGrades?course_id=...` | BeautifulSoup parses `.graded_item_row`, `.grade-item` |

3. **Strict Login Redirect & False-Positive Prevention (`cuhk_blackboard/client.py:107-128`)**:
   - Avoids false-positive authentication when CUHK SSO redirects unauthenticated requests with HTTP 200:
     ```python
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
     ```

4. **Pagination**:
   - Single-page batch parsing: Blackboard REST responses return `{"results": [...]}`.
   - Slicing limits: API endpoints apply local `[:limit]` slices (default 15/20) and bounded iteration (e.g. top 5 courses in `list_announcements`).
   - Tree depth limiting: `list_course_contents` enforces `max_depth` (default 3) to prevent infinite directory recursion or deep-link loops.

5. **Error Handling & Resilience**:
   - Multi-tier exception trapping: nested `try...except` blocks in secondary data fetching (such as fetching user grades for every gradebook column or fetching attachments for individual content items) prevent single-item errors from breaking full results.
   - Tool-level wrapper: all functions in `tools.py` catch `Exception` and return structured `{"success": False, "error": str(e)}`.
   - MCP protocol wrapper: `MCPServer.handle_request()` catches uncaught tool exceptions, returning JSON-RPC result with `isError: True` and full traceback formatted into text content.

6. **Rate Limiting & Safety**:
   - Built-in request timeout: `self.timeout = 15` seconds configured on every `requests.Session.request` call.
   - Bounded queries: prevents wide unconstrained scraping by restricting `max_depth=3`, limiting cross-course announcements to 5 courses * 5 items, and limiting summary items.
   - Empty search fast-return: `search_materials` aborts on empty or whitespace strings without making any network requests.

---

### 1.3 Test Suite Structure & Execution Metrics

Directly inspected test files:
- `tests/__init__.py`
- `tests/test_models.py` (154 lines)
- `tests/test_auth.py` (151 lines)
- `tests/test_client.py` (454 lines)
- `tests/test_tools.py` (151 lines)
- `tests/test_mcp_server.py` (99 lines)
- `tests/test_cli.py` (63 lines)

Execution command and result:
- Command: `pytest -v --tb=short`
- Output:
  ```
  platform win32 -- Python 3.14.5, pytest-9.1.0, pluggy-1.6.0
  rootdir: D:\blackboard_plugin
  configfile: pyproject.toml
  collected 57 items

  tests/test_auth.py (12 passed)
  tests/test_cli.py (4 passed)
  tests/test_client.py (15 passed)
  tests/test_mcp_server.py (7 passed)
  tests/test_models.py (6 passed)
  tests/test_tools.py (13 passed)

  ============================= 57 passed in 0.22s ==============================
  ```

Test Architecture Breakdown:
1. **Pytest Setup & Configuration**:
   - Configured in `pyproject.toml:26-29`: `[project.optional-dependencies] dev = ["pytest>=7.0.0"]`.
   - Co-located unit tests in root `tests/` directory.

2. **Fixtures & Isolation**:
   - `client(tmp_path)` fixture in `test_client.py:14-19`: creates an isolated `AuthManager` with an ephemeral session file path inside pytest's built-in `tmp_path`, preventing pollution of `~/.cuhk_blackboard/session.json`.
   - `capsys` fixture: used in `test_cli.py` to capture and assert CLI terminal outputs (`captured.out`).
   - `tmp_path`: used in `test_download_material` to verify binary file writing (`b"%PDF-1.4..."`) and directory creation.

3. **Mocking Strategies (`unittest.mock`)**:
   - `patch.object(client.session, "request", return_value=mock_resp)`: intercepts HTTP requests and returns mock response objects with customized `.status_code`, `.json()`, and `.text`.
   - `patch.object(client.session, "request", side_effect=[...])`: simulates fallback chains, e.g.:
     - In `test_list_courses_html_fallback`: passes `[api_fail, api_fail, portal_ok]` to verify automatic REST failure -> HTML fallback transition.
     - In `test_verify_auth_failure`: passes `[mock_resp, portal_resp]`.
     - In `test_get_course_lookup_fallbacks`: passes `[fail_resp, success_resp]`.
     - In `test_get_grades`: passes `[cols_resp, user_grade_resp]`.
   - Subsystem mocking: `patch("cuhk_blackboard.interactive_login.capture_from_cdp")` and `patch.object(client, "verify_auth")` to test browser session capture without spawning Chrome/Edge or calling Playwright.
   - Zero live network dependencies: all 57 tests run completely offline and finish in under 250 milliseconds.

---

## 2. Logic Chain

1. **Premise 1**: Institutional systems like CUHK Blackboard utilize SAML SSO and Duo 2FA, which reject direct automated headless password authentication.
   - *Observation Reference*: `client.py:107-128`, `auth.py:326-371`, `README.md:17-30`.
   - *Deduction*: An agent plugin must decouple session acquisition from session execution. The client achieves this by accepting user-supplied session cookies, Bearer tokens, or CDP-captured sessions, validating them via REST `/users/me` or web portal tab action.

2. **Premise 2**: Blackboard Learn instances vary in REST API availability depending on institutional license, Ultra upgrade status, and endpoint permissions.
   - *Observation Reference*: `client.py:151-181` (courses), `client.py:250-282` (contents), `client.py:302-315` (announcements), `client.py:403-429` (grades).
   - *Deduction*: A pure REST client would fail if CUHK restricts public REST endpoints. Therefore, the implementation embeds an automated fallback chain: REST API -> Web HTML Scraping with BeautifulSoup -> Empty list / handled error.

3. **Premise 3**: LLM context windows and Agent execution speed require compact, high-signal data structures rather than raw, noisy HTML.
   - *Observation Reference*: `Announcement.from_api()` converting HTML anchor tags into Markdown links `[text](url)` and stripping HTML tags; `get_course_summary()` packaging recent announcements, upcoming deadlines, top-level items, and recent grades into a single JSON object.
   - *Deduction*: The tool layer acts as an adapter that distills complex web/API responses into token-efficient payloads designed specifically for AI consumption.

4. **Premise 4**: Code reliability and CI/CD pipelines require deterministic, isolated test coverage without requiring live student credentials.
   - *Observation Reference*: 57 unit tests in `tests/` leveraging `unittest.mock.MagicMock`, `patch.object`, `tmp_path`, and `side_effect` lists to simulate HTTP 200, 401, 404, redirect loops, and malformed HTML.
   - *Deduction*: The test suite comprehensively models all client states (authenticated, expired, fallback triggered, file download streaming, CLI invocation, MCP protocol dispatching) with 100% test pass rate in 0.22s.

---

## 3. Caveats

1. **Pagination of REST Endpoints**: The current implementation reads `data.get("results", [])` without looping through Blackboard's `paging.nextPage` cursor. For students with a large number of courses (>100) or thousands of content items in a single directory, only the first page is fetched.
2. **Explicit Rate Limiting**: There is no client-side sleep/leaky-bucket rate limiter (e.g. `time.sleep` between requests). While `self.timeout = 15` and recursion limits prevent infinite loops, rapid consecutive tool calls by an LLM agent could trigger university WAF rate limits if not throttled by the agent runner.
3. **Write Operations**: All core API implementations are strictly read-only (fetching courses, reading announcements, downloading materials, viewing grades). Submitting assignments or posting announcements is intentionally omitted for safety.
4. **Coverage Tooling**: `coverage` or `pytest-cov` is not pre-installed in the current Python environment; test completeness was verified by reading each test file, mapping test assertions to code branches, and running `pytest -v`.

---

## 4. Conclusion

1. **Architecture Quality**: The core API and tool implementation in `cuhk_blackboard` is modular, robust, and well-designed for AI agent integration. The dual-engine design (REST API with seamless HTML scraping fallback) ensures resilience against endpoint-level permission restrictions.
2. **LLM Optimization**: Data transformation in `models.py` and `tools.py` specifically addresses LLM context limitations by converting rich text to Markdown, extracting clickable URLs, filtering upcoming deadlines against UTC timestamps, and providing a unified `cuhk_bb_get_course_summary` endpoint.
3. **Test Integrity**: The existing test suite provides extensive coverage of models, authentication, client fallbacks, tool registry, MCP JSON-RPC protocol, and CLI commands. All 57 tests pass cleanly in 0.22 seconds with zero live network reliance.

---

## 5. Verification Method

To independently verify all findings and test suite execution:

1. **Run full pytest suite**:
   ```powershell
   pytest -v --tb=short
   ```
   *Expected outcome*: 57 passed tests in ~0.20-0.30s.

2. **Verify specific test suites**:
   - Client fallbacks: `pytest tests/test_client.py -v` (15 passed)
   - Tool schemas & consistency: `pytest tests/test_tools.py -v` (13 passed)
   - Models parsing: `pytest tests/test_models.py -v` (6 passed)
   - Auth & cookie parsing: `pytest tests/test_auth.py -v` (12 passed)
   - MCP Server protocol: `pytest tests/test_mcp_server.py -v` (7 passed)
   - CLI execution: `pytest tests/test_cli.py -v` (4 passed)

3. **Inspect primary implementation files**:
   - `cuhk_blackboard/client.py`: inspect lines 50-84 (`_request`), 86-133 (`verify_auth`), 144-182 (`list_courses`), 212-282 (`list_course_contents`), 342-396 (`list_assignments`), 431-473 (`download_material`), 528-569 (`get_course_summary`).
   - `cuhk_blackboard/tools.py`: inspect lines 366-612 (`AGENT_TOOLS_DEFINITIONS`) and 614-628 (`TOOL_FUNCTION_MAP`).
   - `cuhk_blackboard/models.py`: inspect lines 257-285 (`Announcement.from_api` markdown conversion) and 302-349 (`GradeItem.from_api`).

4. **Invalidation Conditions**:
   - If `pytest -v` fails or reports broken fixtures.
   - If any tool defined in `AGENT_TOOLS_DEFINITIONS` does not map to a function in `TOOL_FUNCTION_MAP`.
   - If REST failure does not trigger the corresponding HTML fallback method.
