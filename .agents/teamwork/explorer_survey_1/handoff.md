# Comprehensive Architectural Survey Report: `cuhk-blackboard-plugin`

**Author**: `explorer_survey_1` (teamwork_explorer)  
**Date**: 2026-10-29T14:57:00Z  
**Target Codebase**: `d:\blackboard_plugin`  
**Milestone**: Codebase Architectural Survey & System Review (M1)

---

## 1. Observation

### 1.1 Repository Structure and File Layout
Direct inspection of `d:\blackboard_plugin` via `list_dir` and `find_by_name` revealed the following file and directory structure:

```
d:\blackboard_plugin
├── pyproject.toml                     # Build system and dependency configuration (850 bytes)
├── README.md                          # Primary English documentation & architectural guide (8,049 bytes)
├── README_CN.md                       # Comprehensive Chinese documentation & user guide (7,720 bytes)
├── REVERSE_ENGINEERING.md             # Reverse-engineering notes using REA MCP tools (4,029 bytes)
├── cuhk_blackboard/                   # Core Python package
│   ├── __init__.py                    # Public exports and package versioning (71 lines, 1,748 bytes)
│   ├── models.py                      # Data models, enums, dataclass schemas (363 lines, 13,074 bytes)
│   ├── auth.py                        # AuthManager, multi-format cookie parser, persistence (379 lines, 15,882 bytes)
│   ├── client.py                      # BlackboardClient, REST + HTML scraping fallback (674 lines, 28,218 bytes)
│   ├── interactive_login.py           # CLI wizard, CDP probe, Playwright browser login (219 lines, 8,573 bytes)
│   ├── tools.py                       # 13 agent tool functions, JSON schemas, tool map (629 lines, 24,153 bytes)
│   ├── mcp_server.py                  # JSON-RPC 2.0 stdio MCP server implementation (202 lines, 6,858 bytes)
│   └── cli.py                         # Command-line interface with subcommands (155 lines, 6,047 bytes)
├── examples/                          # Integration examples
│   ├── agent_usage.py                 # Multi-step agent workflow demonstration (63 lines, 2,322 bytes)
│   ├── langgraph_agent.py             # LangGraph / OpenAI function calling binding (39 lines, 1,212 bytes)
│   └── mcp_config_example.json        # MCP client configuration template (16 lines, 277 bytes)
├── tests/                             # Pytest test suite
│   ├── __init__.py                    # Test package marker (33 bytes)
│   ├── test_auth.py                   # Tests for AuthManager & cookie parsing (151 lines, 5,426 bytes)
│   ├── test_cli.py                    # Tests for CLI subcommands (63 lines, 2,272 bytes)
│   ├── test_client.py                 # Tests for BlackboardClient & HTML fallback (454 lines, 15,347 bytes)
│   ├── test_mcp_server.py             # Tests for JSON-RPC MCP server protocol (99 lines, 2,769 bytes)
│   ├── test_models.py                 # Tests for models, masking, and factories (154 lines, 5,366 bytes)
│   └── test_tools.py                  # Tests for agent tools and auto-detection (151 lines, 4,899 bytes)
└── cuhk_blackboard_plugin.egg-info/   # Setuptools egg metadata
```

### 1.2 Package Metadata & Dependency Analysis (`pyproject.toml`)
Inspected `d:\blackboard_plugin\pyproject.toml` (lines 1–37):
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "cuhk-blackboard-plugin"
version = "1.0.0"
description = "CUHK Blackboard Scraper and AI Agent Plugin with flexible user authentication"
readme = "README.md"
requires-python = ">=3.9"
authors = [
    { name = "CUHK Agent Plugin Team" }
]
classifiers = [
    "Programming Language :: Python :: 3",
    "Operating System :: OS Independent",
    "Topic :: Education",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
]
dependencies = [
    "requests>=2.28.0",
    "beautifulsoup4>=4.11.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
]
browser = [
    "playwright>=1.30.0",
]

[project.scripts]
cuhk-blackboard = "cuhk_blackboard.cli:main"
cuhk-bb-mcp = "cuhk_blackboard.mcp_server:main"
```
**Key Dependency Findings**:
- **Zero Third-Party MCP Library Dependency**: The project does *not* depend on the `mcp` Python package (`mcp>=0.1.0`). It natively implements a lightweight, pure-standard-library JSON-RPC 2.0 stdio server in `cuhk_blackboard/mcp_server.py`.
- **Minimal Core Dependencies**: Core runtime requires only 3 packages: `requests>=2.28.0`, `beautifulsoup4>=4.11.0`, and `pydantic>=2.0.0`.
- **Optional Browser Automation**: `playwright>=1.30.0` is quarantined under `[project.optional-dependencies] browser`, meaning headless environments or servers without browser binaries can run without Playwright installed.
- **Console Entry Points**: Two console scripts are registered: `cuhk-blackboard` (mapped to `cuhk_blackboard.cli:main`) and `cuhk-bb-mcp` (mapped to `cuhk_blackboard.mcp_server:main`).

### 1.3 Architectural Components & Module Breakdown

#### Component A: Data Models & Secret Masking (`models.py`)
- **Enums**:
  - `AuthMethod` (line 15): `cookie`, `token`, `credentials`, `interactive`, `saved_session`.
  - `ContentType` (line 24): `folder`, `document`, `file`, `assignment`, `test`, `link`, `announcement`, `forum`, `unknown`.
- **Dataclass Entities**:
  - `AuthConfig` (lines 38–76): Holds credentials and contains `to_dict(mask_secrets: bool = False)`. When `mask_secrets=True`, `password` is replaced with `"********"`, `bearer_token` with first 8 and last 4 characters, and cookies with first 4 and last 4 characters.
  - `UserProfile` (lines 80–111): `from_api` parses Blackboard User JSON (`id`, `userName`, `studentId`, `name: {given, family}`, `contact: {email}`, `systemRoleIds`, `lastLogin`).
  - `Course` (lines 115–148): `from_api` normalizes both direct course items and membership objects (`id`, `course_id`, `name`, `term_id`, `is_ultra`, `is_available`, `role`).
  - `Attachment` (lines 152–174): Generates standard Blackboard REST attachment download URL:
    `{base_host}/learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments/{att_id}/download`.
  - `ContentItem` (lines 178–241): `from_api` deduces `ContentType` based on Blackboard's internal `contentHandler` string (e.g. `resource/x-bb-file` -> `FILE`, `resource/x-bb-assignment` -> `ASSIGNMENT`, `resource/x-bb-folder` -> `FOLDER`).
  - `Announcement` (lines 244–285): `from_api` parses HTML bodies using BeautifulSoup, converts `<a href="...">text</a>` tags to markdown `[text](href)` format, strips HTML block tags, and produces clean newline-separated `content_text`.
  - `GradeItem` (lines 289–348): Safely converts gradebook score strings and floats, calculates percentage `(score / points_possible) * 100`, handles missing or string-based scores without raising `TypeError`.
  - `Assignment` (lines 352–363): Represents assignment deadlines and point totals.

#### Component B: Authentication Engine (`auth.py`)
- **State Management & Persistence**:
  - Managed by `AuthManager` (lines 27–378).
  - Default session directory: `~/.cuhk_blackboard/session.json` (`DEFAULT_SESSION_FILE`).
  - Default host: `https://blackboard.cuhk.edu.hk` (`DEFAULT_HOST`).
  - Configuration Loading Order in `load_session()` (lines 241–285):
    1. Environment variables (`CUHK_BB_COOKIE`, `CUHK_BB_TOKEN`, `CUHK_BB_HOST`).
    2. Session file on disk (`~/.cuhk_blackboard/session.json`).
- **Universal Cookie Parsing Engine (`parse_cookie_input`, lines 151–222)**:
  Directly parses 6 distinct input formats:
  1. Standard HTTP header: `Cookie: JSESSIONID=...; session_id=...`
  2. cURL format: `-H 'Cookie: ...'`, `-b '...'`, `--cookie '...'`
  3. Browser DevTools Application/Storage tab copy: tab-separated lines (`Name \t Value \t Domain ...`)
  4. Newline-delimited pairs: `JSESSIONID=...\nsession_id=...`
  5. JSON string: `{"JSESSIONID": "...", "session_id": "..."}`
  6. Browser Extension (Cookie-Editor) JSON array format: `[{"name": "JSESSIONID", "value": "..."}, ...]`
- **HTTP Header Construction (`get_auth_headers`, lines 298–323)**:
  - Injects realistic Chrome User-Agent: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Blackboard/1.0`.
  - Sets `Referer` and `Origin` headers to the Blackboard host.
  - Injects `Authorization: Bearer <token>` when using Bearer tokens.
  - Constructs `Cookie` header from dictionary.
  - Automatically extracts `X-Blackboard-SXS` from cookies and sets it as an HTTP header for Anti-CSRF protection on Blackboard API endpoints.

#### Component C: Core API Client & Scraper (`client.py`)
- **Dual-Layer Architecture**:
  - Primary Layer: Official Blackboard Learn REST API (`/learn/api/public/v1/...`).
  - Fallback Layer: Web Portal / Classic Blackboard HTML scraping via BeautifulSoup.
- **Verification Mechanism (`verify_auth`, lines 86–133)**:
  - Step 1: Query REST API `/learn/api/public/v1/users/me`. If status 200, return `(True, UserProfile)`.
  - Step 2: If 401/403, send GET request to portal endpoint `/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1`.
  - Step 3: Evaluate portal response:
    - Checks for unauthenticated redirects: `webapps/login`, `auth-saml`, `sts.cuhk.edu.hk`, `loginform`, `refresh" content="0;url=`. If present, immediately marks authentication as failed.
    - Checks for authenticated logout tokens: `action=logout`, `/webapps/login?action=logout`, or user name found via `#global-nav-link` or `.user-name`.
    - If valid, returns `(True, UserProfile(user_id="me", display_name=extracted_name))`.
- **API Operations & HTML Fallbacks**:
  - `list_courses()`: Tries `/users/me/courses`, then `/courses`, then scrapes portal HTML links matching regex `r"(?:(?:course_id|id)=|/courses/)(_\d+_\d+)"` (including Ultra courses `/ultra/courses/_...`).
  - `get_course(course_id)`: Attempts direct ID lookup, then `courseId:` prefixed lookup, then enrolled course list scan.
  - `list_course_contents(...)`: Queries `/courses/{id}/contents[/{cid}/children]`, recursively traverses subfolders up to `max_depth`, fetches missing attachments via `_fetch_item_attachments`, falls back to HTML scraping `/webapps/blackboard/content/listContentEditable.jsp`.
  - `list_announcements(...)`: Queries `/courses/{id}/announcements` or system `/announcements`, parses HTML bodies with BeautifulSoup, falls back to `/webapps/blackboard/execute/announcement`.
  - `list_assignments(...)`: Queries Gradebook columns `/gradebook/columns`, parses ISO-8601 UTC dates, filters `upcoming_only` against current UTC time, extracts grading totals.
  - `get_grades(...)`: Fetches gradebook columns and user attempt scores via `/gradebook/columns/{col_id}/users/me`, falls back to `/webapps/gradebook/do/student/viewGrades`.
  - `download_material(...)`: Stream downloads files, extracts filename from `Content-Disposition` header, sanitizes filename using `re.sub(r'[\\/*?:"<>|]', "_", filename)`.
  - `search_materials(...)`: Multi-source keyword search across enrolled course titles, content descriptions/bodies, and announcement texts.
  - `get_course_summary(...)`: High-density LLM summary packaging recent announcements, upcoming deadlines, top-level contents, and grades into a single payload.

#### Component D: Interactive Login & CDP Session Capture (`interactive_login.py`)
- **Live Browser Session Capture via CDP (`capture_from_cdp`, lines 139–162)**:
  - Connects to Chrome DevTools Protocol endpoints across common ports: `http://127.0.0.1:9222`, `9229`, `9333`.
  - Queries `/json/list` to find browser tabs matching `blackboard.cuhk.edu.hk`.
  - Uses Playwright CDP connector (`p.chromium.connect_over_cdp`) to inspect browser context cookies and extract `JSESSIONID` and `session_id`.
  - Enables **Zero-Copy Session Capture** from the IDE sidebar browser.
- **Interactive Browser Automation (`launch_browser_login`, lines 164–218)**:
  - Launches local browser with fallback order: `msedge` -> `chrome` -> `chromium`.
  - Opens Blackboard login portal and waits for URL regex `blackboard\.cuhk\.edu\.hk/(?:ultra|webapps/(?:portal|blackboard))` indicating successful Duo 2FA SSO.
  - Captures cookies, stores them in `AuthManager`, and closes browser cleanly.
- **Interactive CLI Wizard (`prompt_user_auth`, lines 18–137)**:
  - Interactive terminal menu providing 6 options (Cookie, Token, OnePass credentials, Local browser launch, Guides, Exit).

#### Component E: Agent Tools Registry & Lifecycle (`tools.py`)
- **Singleton Lifecycle**: `_global_client` managed via `get_client()` (lines 20–27).
- **13 Registered Tools**:
  1. `cuhk_bb_configure_auth`: Dynamic auth configuration with auto-detection.
  2. `cuhk_bb_auth_status`: Session validation & user profile retrieval.
  3. `cuhk_bb_capture_browser_session`: Automated CDP & browser capture.
  4. `cuhk_bb_get_auth_guide`: Multi-method authentication instructions.
  5. `cuhk_bb_list_courses`: Course enumeration.
  6. `cuhk_bb_get_course_details`: Specific course inspection.
  7. `cuhk_bb_list_course_contents`: Folder and material navigation.
  8. `cuhk_bb_list_announcements`: Cleaned announcement retrieval.
  9. `cuhk_bb_list_assignments`: Graded task and deadline tracking.
  10. `cuhk_bb_get_grades`: Gradebook score and feedback extraction.
  11. `cuhk_bb_download_material`: Local file download.
  12. `cuhk_bb_search_materials`: Unified keyword search.
  13. `cuhk_bb_get_course_summary`: High-density LLM summary.
- **Registry & Schemas**:
  - `AGENT_TOOLS_DEFINITIONS`: Array of JSON schemas defining tool names, descriptions, parameter types, enums, and required fields (lines 366–612).
  - `TOOL_FUNCTION_MAP`: Dictionary mapping tool names to callable Python functions (lines 614–628).

#### Component F: MCP Server Architecture (`mcp_server.py`)
- **Protocol Details**:
  - Implements Model Context Protocol specification `2024-11-05` over stdio JSON-RPC 2.0 (lines 17–19).
  - Server info: `name = "cuhk-blackboard-plugin"`, `version = "1.0.0"`.
- **JSON-RPC Handlers**:
  - `initialize`: Returns protocol version, tool capabilities, and server info.
  - `ping`: Health check.
  - `notifications/initialized`: Handles client initialization notification.
  - `tools/list`: Converts `AGENT_TOOLS_DEFINITIONS` to MCP `tools` array with `inputSchema`.
  - `tools/call`: Dispatches to `TOOL_FUNCTION_MAP[tool_name](**arguments)` and formats result as `{content: [{type: "text", text: ...}], isError: bool}`.
- **Crucial Stream Isolation Design (`run_stdio`, lines 149–193)**:
  ```python
  # Ensure utf-8 encoding on Windows consoles
  sys.stdin.reconfigure(encoding="utf-8")
  sys.stdout.reconfigure(encoding="utf-8")

  # Protect JSON-RPC communication stream: keep private reference to real stdout,
  # and redirect global sys.stdout to sys.stderr so any stray prints don't corrupt the protocol.
  real_stdout = sys.stdout
  sys.stdout = sys.stderr
  ```
  This is a critical architectural defense pattern preventing external libraries or inadvertent `print()` calls from injecting non-JSON text into the MCP communication channel.

#### Component G: CLI Interface (`cli.py`)
- Argparse subcommands: `auth`, `status`, `courses`, `contents`, `announcements`, `grades`, `download`, `mcp`.
- Supports custom host parameter `--host` (default: `https://blackboard.cuhk.edu.hk`).

### 1.4 Test Suite Execution Results
Executed test command `pytest -v` via `run_command`:
```
============================= test session starts =============================
platform win32 -- Python 3.14.5, pytest-9.1.0, pluggy-1.6.0
collected 57 items

tests/test_auth.py::test_parse_cookie_header_string PASSED               [  1%]
...
tests/test_cli.py::test_cli_courses_command PASSED                       [ 22%]
...
tests/test_client.py::test_verify_auth_unconfigured PASSED               [ 29%]
...
tests/test_mcp_server.py::test_mcp_initialize PASSED                     [ 59%]
...
tests/test_models.py::test_auth_config_to_dict_masking PASSED            [ 71%]
...
tests/test_tools.py::test_tool_definitions_consistency PASSED            [ 82%]
...
tests/test_tools.py::test_capture_browser_session_success PASSED         [100%]

============================= 57 passed in 0.17s ==============================
```
**Test Coverage Breakdown**:
- `test_auth.py` (12 tests): Cookie header parsing, JSON parsing, cURL formats, HTTP/2 lowercase, multi-line, tab-separated tables, dicts, Cookie-Editor arrays, token auth, credentials auth, session saving/restoring, clear session, auth guides.
- `test_cli.py` (4 tests): CLI courses, contents, announcements, grades commands with mocked client.
- `test_client.py` (17 tests): Auth verification (success, failure, unconfigured, SAML redirect rejection), courses API and HTML fallback, Ultra course parsing, contents with attachments, announcements, grades with point calculation, download with Content-Disposition, keyword search, assignment date filtering, course summary generation.
- `test_mcp_server.py` (7 tests): MCP initialize, ping, tools/list schema validation, tools/call execution, tool not found (-32601), unknown method (-32601), notification handling.
- `test_models.py` (6 tests): AuthConfig secret masking, UserProfile factory, Course factory, ContentItem factory, Announcement HTML stripping & Markdown link preservation, GradeItem numerical conversions.
- `test_tools.py` (11 tests): Schema-to-function consistency, configure_auth error paths, auth_status, get_auth_guide, list_courses, get_course_summary, auto-detection, Duo warning note, capture_browser_session mock.

---

## 2. Logic Chain

The architecture of `cuhk-blackboard-plugin` is designed to solve a specific engineering problem: enabling autonomous AI agents to access a university LMS protected by Single Sign-On and multi-factor authentication (Duo 2FA), without requiring institutional administrator API tokens or credentials storage that would violate institutional policies.

```
                    ┌───────────────────────────────┐
                    │  AI Agent / Host Application  │
                    │   (Claude, Cursor, LangGraph) │
                    └───────────────┬───────────────┘
                                    │ (JSON-RPC 2.0 over stdio)
                    ┌───────────────▼───────────────┐
                    │         mcp_server.py         │
                    │   (Protocol: 2024-11-05)      │
                    │  [sys.stdout -> stderr isol]  │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │           tools.py            │
                    │   (13 Agent Tool Wrappers)    │
                    └───────┬───────────────┬───────┘
                            │               │
            ┌───────────────▼┐             ┌▼────────────────┐
            │    auth.py     │             │    client.py    │
            │  (AuthManager) │             │(BlackboardClient│
            └───────┬────────┘             └────────┬────────┘
                    │                               │
        ┌───────────┴───────────┐         ┌─────────┴─────────┐
        ▼                       ▼         ▼                   ▼
┌───────────────┐       ┌───────────────┐ ┌─────────────┐ ┌─────────────┐
│ 5 Auth Routes │       │ ~/.cuhk_...   │ │REST API v1  │ │HTML Scraping│
│(Cookie, CDP,  │       │ session.json  │ │(/learn/api/ │ │(Beautiful-  │
│ Token, Creds) │       │ & Env Vars    │ │ public/v1/) │ │ Soup 4)     │
└───────────────┘       └───────────────┘ └──────┬──────┘ └──────┬──────┘
                                                 │               │
                                                 └───────┬───────┘
                                                         │ HTTPS
                                                         ▼
                                          ┌─────────────────────────────┐
                                          │ CUHK Blackboard Learn Core  │
                                          │ (blackboard.cuhk.edu.hk)    │
                                          └─────────────────────────────┘
```

### Step 1: Solving the Duo 2FA Challenge through Multi-Modal Authentication
- **Premise**: CUHK Blackboard enforces SAML SSO and Duo 2FA push notifications. Direct HTTP headless username/password POST requests fail against Duo MFA challenge walls.
- **Deduction**: The system must decouple credential submission from session consumption.
- **Implementation**: `AuthManager` supports 5 distinct pathways:
  1. `browser_capture` (via CDP port probing): Probes local running Chromium/Edge instances on ports 9222/9229/9333, finds existing authenticated Blackboard tabs, and grabs session cookies directly without manual copy-pasting.
  2. `cookie`: Accepts raw cookie strings from user browser DevTools, parsing various formats (cURL, DevTools table, Cookie-Editor array) through regex and JSON parsing.
  3. `interactive`: Launches a local Playwright browser instance, opens Blackboard, lets the user perform SSO & Duo Push, waits for URL transition to Blackboard portal, extracts cookies, and closes browser.
  4. `token`: Accepts Mobile OAuth Bearer tokens.
  5. `saved_session`: Auto-restores credentials from `~/.cuhk_blackboard/session.json` or environment variables `CUHK_BB_COOKIE`.
- **Observation Reference**: `auth.py` lines 151–222, `interactive_login.py` lines 139–218.

### Step 2: Protocol Isolation & Zero-Dependency MCP Integration
- **Premise**: An MCP server communicating over stdio must never output non-JSON text to `stdout`, as any stray `print()` statement from downstream libraries (requests, urllib3) would corrupt JSON-RPC message framing and crash the MCP client.
- **Deduction**: Standard library redirection must be established at the entry point of the server loop.
- **Implementation**: In `mcp_server.py:run_stdio()`, the server retains a private handle `real_stdout = sys.stdout`, and immediately reassigns `sys.stdout = sys.stderr`. All logging and unexpected prints route safely to `stderr`, while validated JSON-RPC responses are written strictly to `real_stdout`.
- **Observation Reference**: `mcp_server.py` lines 163–167.

### Step 3: Resilient Data Extraction via Dual-Tier Querying
- **Premise**: Institutional Blackboard instances may have certain REST endpoints disabled, restricted by role permissions, or altered between Ultra and Classic views.
- **Deduction**: A robust client must not rely solely on REST API v1 or solely on web scraping.
- **Implementation**: `BlackboardClient` implements a primary REST call with an automatic fallback to HTML parsing with BeautifulSoup. For example:
  - `verify_auth`: Tries `/learn/api/public/v1/users/me` -> Falls back to `/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1`.
  - `list_courses`: Tries `/learn/api/public/v1/users/me/courses` -> `/learn/api/public/v1/courses` -> Scrapes `/webapps/portal/...` HTML table links.
  - `list_course_contents`: Tries `/learn/api/public/v1/courses/{id}/contents` -> Scrapes `/webapps/blackboard/content/listContentEditable.jsp`.
  - `list_announcements`: Tries `/learn/api/public/v1/courses/{id}/announcements` -> Scrapes `/webapps/blackboard/execute/announcement`.
  - `get_grades`: Tries `/learn/api/public/v1/courses/{id}/gradebook/columns` -> Scrapes `/webapps/gradebook/do/student/viewGrades`.
- **Observation Reference**: `client.py` lines 96–130, 151–181, 250–282, 302–315, 402–428.

### Step 4: Token-Efficient Information Synthesis for LLMs
- **Premise**: AI agents have limited context windows and high latency when making multiple sequential API tool calls across dozens of courses.
- **Deduction**: The plugin should provide high-density composite tools that condense state into context-friendly representations.
- **Implementation**: `cuhk_bb_get_course_summary` aggregates announcements (with HTML stripped and links formatted in Markdown), upcoming assignments (with ISO UTC deadlines evaluated against current time), top-level content outlines, and grade summaries into a single structured dictionary.
- **Observation Reference**: `client.py` lines 528–569, `tools.py` lines 355–363.

---

## 3. Caveats

1. **CUHK Live Network Reachability & Active Session**:
   - The test suite relies on mock objects (`unittest.mock.MagicMock`, `patch`) for unit testing, which pass 100% (57/57).
   - In live testing without valid credentials, `python -m cuhk_blackboard.cli status` accurately reaches `https://blackboard.cuhk.edu.hk` and reports `Authentication failed (HTTP 401): Session cookie or token is expired/invalid`. An active student cookie or Duo push is required for live end-to-end data retrieval against the live university server.
2. **Playwright Optionality**:
   - Playwright is an optional dependency (`playwright>=1.30.0`). In environments where browser binaries (`playwright install`) are not downloaded, `launch_browser_login` returns `None` gracefully and guides the user to the cookie or CDP method.
3. **Blackboard Ultra vs. Original Course View**:
   - CUHK hosts both Blackboard Original (9.1) and Ultra courses. The client handles Ultra status flags and URL routes (`/ultra/courses/...`), but some deeply nested Ultra documents may structure attachments differently than traditional content items.

---

## 4. Conclusion

1. **System Health & Code Quality**:
   - The `cuhk-blackboard-plugin` codebase is cleanly designed, adhering to modern Python 3.9+ typing and dataclass conventions.
   - All 57 unit tests across 6 test modules pass in 0.17 seconds.
   - Architecture exhibits high modularity with clear separation of concerns between data models (`models.py`), authentication lifecycle (`auth.py`), scraping logic (`client.py`), agent tool wrappers (`tools.py`), and transport layers (`mcp_server.py` and `cli.py`).
2. **Key Architectural Strengths**:
   - **Self-contained MCP Server**: Zero-dependency JSON-RPC stdio implementation eliminates dependency conflicts.
   - **Stream Isolation**: Reassigning `sys.stdout = sys.stderr` while preserving `real_stdout` guarantees protocol integrity.
   - **Authentication Flexibility**: 5 authentication mechanisms (especially CDP auto-capture and multi-format cookie parsing) make it suitable for both headless AI agents and interactive desktop workflows.
   - **Dual-Layer Resilience**: Primary REST v1 API coupled with HTML scraping fallbacks protects against API version mismatches or restricted student endpoints.
   - **Secret Masking**: `AuthConfig.to_dict(mask_secrets=True)` prevents inadvertent credential leaking in agent logs.
3. **Readiness for Subsequent Milestones**:
   - The codebase is fully prepared for Milestone 1 (Deep Architecture & Technical Review Documentation) and Milestone 2 (Interactive Quiz Design & Execution).

---

## 5. Verification Method

To independently verify the observations and conclusions in this survey report:

1. **Execute Unit Test Suite**:
   ```powershell
   pytest -v
   ```
   *Expected Result*: 57 passed tests in < 1.0s.

2. **Verify CLI Entry Point and Help Command**:
   ```powershell
   python -m cuhk_blackboard.cli --help
   ```
   *Expected Result*: Lists subcommands `auth`, `status`, `courses`, `contents`, `announcements`, `grades`, `download`, `mcp`.

3. **Verify MCP Server Protocol Handshake via Stdio**:
   Run an inline Python verification script:
   ```powershell
   python -c "from cuhk_blackboard.mcp_server import MCPServer; s = MCPServer(); res = s.handle_request({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}); assert res['result']['protocolVersion'] == '2024-11-05'; print('MCP Handshake Verified successfully!')"
   ```
   *Expected Result*: Output `MCP Handshake Verified successfully!`.

4. **Verify Tool Definition and Function Map Consistency**:
   ```powershell
   python -c "from cuhk_blackboard.tools import AGENT_TOOLS_DEFINITIONS, TOOL_FUNCTION_MAP; assert len(AGENT_TOOLS_DEFINITIONS) == 13; assert set(t['name'] for t in AGENT_TOOLS_DEFINITIONS) == set(TOOL_FUNCTION_MAP.keys()); print('All 13 Agent Tools Verified!')"
   ```
   *Expected Result*: Output `All 13 Agent Tools Verified!`.

5. **Invalidation Conditions**:
   - If any of the 57 tests fail upon running `pytest`.
   - If `AGENT_TOOLS_DEFINITIONS` does not match `TOOL_FUNCTION_MAP`.
   - If `mcp_server.py` outputs non-JSON-RPC text to `stdout` during `run_stdio`.
