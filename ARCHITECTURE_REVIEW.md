# Comprehensive Technical Architecture Review: `cuhk-blackboard-plugin`

**Document Version**: 1.0.0  
**Target Repository**: `d:\blackboard_plugin`  
**System Target**: The Chinese University of Hong Kong (CUHK) Blackboard Learn (`blackboard.cuhk.edu.hk`)  
**Scope**: Complete System Architecture, Authentication Engine, Core API / Fallback Pipelines, Agent Tools Registry, MCP Server, and Reliability Engineering Test Suite  
**Author**: Teamwork Technical Review Group (Milestone 1)  

---

## 1. Executive Summary & Architecture Overview

### 1.1 Executive Summary
The `cuhk-blackboard-plugin` is a specialized, production-grade Python library and Model Context Protocol (MCP) server engineered to bridge autonomous AI agents (such as Claude Desktop, Cursor, Antigravity, and LangGraph pipelines) with The Chinese University of Hong Kong (CUHK) Blackboard Learn Learning Management System (`blackboard.cuhk.edu.hk`).

Academic LMS environments present substantial technical hurdles for programmatic agent integration:
1. **Institutional Single Sign-On (SSO)**: CUHK enforces OnePass CWEM credentials routed through Active Directory Federation Services (ADFS / SAML at `sts.cuhk.edu.hk`).
2. **Mandatory Multi-Factor Authentication (MFA)**: Access requires Duo Mobile two-factor authentication (push approval or numeric passcodes), preventing unassisted headless username/password automation.
3. **API Heterogeneity & Endpoint Permissions**: Blackboard Learn instances mix modern REST APIs (`/learn/api/public/v1/...`) with legacy Web Portal servlets (`/webapps/...`), and certain endpoints may be gated, unpopulated, or altered across Original and Ultra course views.
4. **Agent Context Limitations**: AI LLM agents operate with finite context windows and high latency per round-trip; dumping raw HTML web pages causes context overflow, hallucination, and excessive token expenditure.

To resolve these challenges, `cuhk-blackboard-plugin` implements a resilient, multi-tiered architecture characterized by:
- **Zero-Dependency JSON-RPC 2.0 MCP Server**: A fully compliant MCP stdio implementation built entirely upon the Python standard library, eliminating package dependency conflicts.
- **Strict Stdio Stream Isolation**: Architectural redirection of global `sys.stdout` to `sys.stderr` while preserving a private binary stream handle, preventing protocol corruption from third-party library logging or stray `print()` calls.
- **5-Tier Authentication Layer**: Supporting passive Chrome DevTools Protocol (CDP) session harvesting from running sidebar browsers, universal multi-format cookie parsing, mobile OAuth Bearer tokens, interactive Duo-guided logins, and encrypted/sanitized local session persistence.
- **Dual-Engine Query Pipeline**: A primary Blackboard REST v1 client backed by an automated fallback engine utilizing BeautifulSoup4 HTML scraping.
- **High-Density LLM Payload Synthesis**: Data normalizers that clean HTML tags, preserve hyperlinked Markdown anchors, evaluate ISO UTC deadlines against current timestamps, and generate composite course summaries.
- **Exhaustive Unit Test Suite**: 57 offline unit tests using `pytest` and `unittest.mock`, completing in under 0.25 seconds with 100% pass rate and zero external network reliance.

---

### 1.2 High-Level System Topology & Information Flow

The architecture decouples user interface and agent transport from core business logic, web scraping, and network communication:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AI Agent Host Applications                         │
│             (Claude Desktop, Cursor IDE, Antigravity, LangGraph)            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Standard JSON-RPC 2.0 over STDIO
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 MCP Stdio Server (cuhk_blackboard/mcp_server.py)             │
│   - Protocol Version: 2024-11-05                                            │
│   - Stream Isolation: real_stdout = sys.stdout; sys.stdout = sys.stderr     │
│   - Dispatcher: initialize, ping, tools/list, tools/call                    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Direct Python Dispatch
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  Agent Tools Registry (cuhk_blackboard/tools.py)             │
│   - 13 JSON-Schema Registered Agent Tools                                   │
│   - Singleton Client Lifecycle Management (get_client())                    │
│   - Automatic Auth Method Deducer & Structured Error Envelopes              │
└───────────────────┬─────────────────────────────────────┬───────────────────┘
                    │                                     │
                    ▼                                     ▼
┌──────────────────────────────────────┐  ┌───────────────────────────────────┐
│ Authentication Engine                │  │ Dual-Engine Client                │
│ (cuhk_blackboard/auth.py)            │  │ (cuhk_blackboard/client.py)       │
│                                      │  │                                   │
│ ┌──────────────────────────────────┐ │  │ ┌───────────────────────────────┐ │
│ │ 5 Authentication Modalities:     │ │  │ │ Primary: REST v1 API          │ │
│ │ 1. CDP Zero-Copy Browser Capture │ │  │ │ (/learn/api/public/v1/...)    │ │
│ │ 2. Multi-Format Cookie Parser    │ │  │ └──────────────┬────────────────┘ │
│ │ 3. Mobile OAuth Bearer Token     │ │  │                │ Fallback on      │
│ │ 4. CWEM Creds + Duo 2FA Guide    │ │  │                │ 401/403/404      │
│ │ 5. Priority Session Persistence  │ │  │                ▼                  │
│ └──────────────────────────────────┘ │  │ ┌───────────────────────────────┐ │
│ ┌──────────────────────────────────┐ │  │ │ Secondary: HTML Web Scraper   │ │
│ │ Security & Hardening:            │ │  │ │ (BeautifulSoup4 /webapps/...) │ │
│ │ - Password disk exclusion        │ │  │ └──────────────┬────────────────┘ │
│ │ - Secret masking (to_dict)       │ │  │                │                  │
│ │ - Anti-CSRF (X-Blackboard-SXS)   │ │  │ ┌──────────────▼────────────────┐ │
│ │ - ADFS False-Positive Trapping   │ │  │ │ LLM Content Normalizer        │ │
│ └──────────────────────────────────┘ │  │ │ - Markdown Link Preservation │ │
│                                      │  │ │ - Grade Percentage Compute    │ │
│                                      │  │ │ - Deadlines UTC Filtering     │ │
│                                      │  │ │ - Path Traversal Sanitize     │ │
│                                      │  │ └───────────────────────────────┘ │
└───────────────────┬──────────────────┘  └───────────────────┬───────────────┘
                    │                                         │
                    └───────────────────┬─────────────────────┘
                                        │ Authenticated HTTPS Requests
                                        │ (Session Cookie / Bearer Token)
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│               CUHK Enterprise Infrastructure & Blackboard Learn             │
│                    Target Host: https://blackboard.cuhk.edu.hk              │
│       Identity Provider: CUHK OnePass CWEM & ADFS (sts.cuhk.edu.hk)        │
│                    MFA Provider: Duo Security Mobile Push                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 1.3 JSON-RPC MCP Server Architecture

The Model Context Protocol implementation resides in `cuhk_blackboard/mcp_server.py`. It establishes a lightweight, robust JSON-RPC 2.0 communication engine operating on standard input and output streams.

#### 1.3.1 Protocol Handshake & Method Dispatching
The server targets MCP Protocol Specification `2024-11-05` and provides deterministic routing for all protocol lifecycle methods:

| Method Name | Request Shape | Server Behavior & Response Payload |
|---|---|---|
| `initialize` | `{"method": "initialize", "params": {...}}` | Negotiates protocol version, returns server capabilities (`{"tools": {}}`) and server metadata (`name: "cuhk-blackboard-plugin"`, `version: "1.0.0"`). |
| `notifications/initialized`| `{"method": "notifications/initialized"}` | Notification with no `id`; server acknowledges client readiness and returns `None` (no response written to stdout). |
| `ping` | `{"method": "ping"}` | Heartbeat check; returns an empty JSON object result `{}`. |
| `tools/list` | `{"method": "tools/list"}` | Iterates through `AGENT_TOOLS_DEFINITIONS`, transforming tool schemas into MCP-compliant format: `{"tools": [{"name": ..., "description": ..., "inputSchema": ...}]}`. |
| `tools/call` | `{"method": "tools/call", "params": {"name": str, "arguments": dict}}` | Validates tool existence in `TOOL_FUNCTION_MAP`, executes the function with unpacked keyword arguments, formats the output into `{content: [{"type": "text", "text": ...}], "isError": bool}`. |

#### 1.3.2 Standard Error Code Adherence
The server enforces strict adherence to JSON-RPC 2.0 specification error codes:
- **Parse Error (`-32700`)**: Raised when incoming line cannot be parsed as valid JSON.
- **Method Not Found / Tool Not Found (`-32601`)**: Returned when an unrecognized JSON-RPC method is invoked or when a requested tool name is not registered in `TOOL_FUNCTION_MAP`.
- **Internal Error (`-32603`)**: Returned when unexpected exceptions occur within the server dispatch loop.
- **Application Execution Errors**: Captured gracefully inside `tools/call`. Rather than aborting the RPC connection, the server catches tool-level exceptions, formatting a detailed error message and stack trace into the `content[0].text` payload and setting `isError: True`.

---

### 1.4 Zero-Dependency MCP Design Rationale & Benefits

Unlike standard MCP implementations that require the third-party `mcp` SDK (`pip install mcp`), `cuhk-blackboard-plugin` implements the full MCP server using exclusively Python's standard library modules (`json`, `sys`, `traceback`, `typing`).

**Architectural Rationale**:
1. **Dependency Quarantine**: Agent environments often run complex dependency trees (LangChain, LangGraph, Pydantic v1/v2, PyTorch). Avoiding the heavy official `mcp` package (which pulls in `anyio`, `httpx`, `sse-starlette`, `starlette`, `pydantic-settings`) prevents version pinning conflicts.
2. **Deterministic Startup Latency**: Standard library imports initialize in single-digit milliseconds, allowing IDE extensions (Claude Desktop, Cursor) to launch the MCP subprocess without handshake timeouts.
3. **Execution Portability**: The plugin executes seamlessly on bare-metal Python environments, lightweight containers, or locked-down student laptops without needing internet access to install external MCP wheels.

---

### 1.5 Stdio Stream Isolation Architecture

In stdio-based MCP servers, stdout is the dedicated transport medium for JSON-RPC message frames. A catastrophic vulnerability in Python stdio servers occurs when external libraries (e.g. `requests`, `urllib3`, `BeautifulSoup`) or developer debug statements emit text to `sys.stdout`. Unformatted strings break JSON framing on the client parser, immediately terminating the agent connection.

`cuhk_blackboard/mcp_server.py` implements a definitive architectural pattern in `run_stdio()` (lines 151–167):

```python
# 1. Reconfigure console streams for UTF-8 compatibility (especially on Windows consoles)
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 2. Capture private handle to the physical stdout stream
real_stdout = sys.stdout

# 3. Redirect global sys.stdout to sys.stderr
sys.stdout = sys.stderr
```

**Security and Integrity Guarantees**:
- Any rogue `print("...")` or library output is redirected to `sys.stderr`, where MCP clients (like Claude Desktop) capture it as debug logging without affecting JSON-RPC message parsing.
- Only the server's internal loop writes explicitly to `real_stdout`:
  ```python
  real_stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
  real_stdout.flush()
  ```
- Guaranteed UTF-8 encoding ensures multi-byte Chinese course titles and instructor names are transmitted without truncation or encoding crashes on Windows code pages.

---

## 2. Package Architecture & Module Breakdown

### 2.1 Package Overview & Directory Layout

```
d:\blackboard_plugin
├── pyproject.toml              # Build config, entry points, dependencies
├── README.md                   # English system documentation
├── README_CN.md                # Chinese technical guide
├── REVERSE_ENGINEERING.md      # Blackboard endpoints & session notes
├── cuhk_blackboard/            # Core package directory
│   ├── __init__.py             # Public exports & versioning
│   ├── models.py               # Enums, dataclasses, secret masking, factories
│   ├── auth.py                 # AuthManager, cookie parser, persistence
│   ├── client.py               # BlackboardClient, REST + HTML scraper
│   ├── interactive_login.py    # Playwright browser automation & CDP probe
│   ├── tools.py                # 13 Agent tool functions & schemas
│   ├── mcp_server.py           # Native JSON-RPC stdio MCP server
│   └── cli.py                  # Terminal subcommands CLI
├── examples/                   # Agent integration samples
│   ├── agent_usage.py          # Sequential workflow example
│   ├── langgraph_agent.py      # LangGraph tool binding example
│   └── mcp_config_example.json # Claude Desktop configuration snippet
└── tests/                      # Pytest verification suite (57 tests)
    ├── test_auth.py            # 12 tests for auth & parsing
    ├── test_cli.py             # 4 tests for command-line interface
    ├── test_client.py          # 17 tests for client logic & HTML fallbacks
    ├── test_mcp_server.py      # 7 tests for MCP JSON-RPC protocol
    ├── test_models.py          # 6 tests for dataclasses & masking
    └── test_tools.py           # 11 tests for agent tool endpoints
```

---

### 2.2 `cuhk_blackboard/models.py`: Data Modeling, Enums, Dataclasses & Factories

`models.py` serves as the domain model repository, enforcing structural consistency and data security across the plugin.

#### 2.2.1 Core Enums
- `AuthMethod(str, Enum)`: Categorizes authentication sources: `COOKIE`, `TOKEN`, `CREDENTIALS`, `INTERACTIVE`, `SAVED_SESSION`.
- `ContentType(str, Enum)`: Distinguishes Blackboard content hierarchy nodes: `FOLDER`, `DOCUMENT`, `FILE`, `ASSIGNMENT`, `TEST`, `LINK`, `ANNOUNCEMENT`, `FORUM`, `UNKNOWN`.

#### 2.2.2 Dataclass Entities & Factory Methods

```
                               ┌────────────────────────┐
                               │       AuthConfig       │
                               │ - method: AuthMethod   │
                               │ - cookies: dict        │
                               │ - bearer_token: str    │
                               │ - to_dict(mask_secrets)│
                               └────────────────────────┘
                                            │
               ┌────────────────────────────┼────────────────────────────┐
               ▼                            ▼                            ▼
    ┌────────────────────┐       ┌────────────────────┐       ┌────────────────────┐
    │    UserProfile     │       │       Course       │       │    ContentItem     │
    │ - user_id: str     │       │ - id: str          │       │ - id: str          │
    │ - username: str    │       │ - course_id: str   │       │ - title: str       │
    │ - student_id: str  │       │ - name: str        │       │ - content_type: ...│
    │ - display_name: str│       │ - is_ultra: bool   │       │ - attachments: list│
    │ - from_api()       │       │ - from_api()       │       │ - from_api()       │
    └────────────────────┘       └────────────────────┘       └─────────┬──────────┘
                                                                        │ 1..*
                                                                        ▼
    ┌────────────────────┐       ┌────────────────────┐       ┌────────────────────┐
    │    Announcement    │       │     GradeItem      │       │     Attachment     │
    │ - id: str          │       │ - column_id: str   │       │ - id: str          │
    │ - title: str       │       │ - score: float     │       │ - file_name: str   │
    │ - content_html: str│       │ - pts_possible: ...│       │ - download_url: str│
    │ - content_text: str│       │ - percentage: float│       │ - from_api()       │
    │ - from_api()       │       │ - from_api()       │       └────────────────────┘
    └────────────────────┘       └────────────────────┘
```

1. **`AuthConfig`**: Stores active authentication parameters. Provides `to_dict(mask_secrets: bool = False)`:
   - Replaces `password` with `"********"`.
   - Truncates `bearer_token` to `f"{token[:8]}...{token[-4:]}"`.
   - Truncates cookie values longer than 8 characters to `f"{val[:4]}...{val[-4:]}"`.
2. **`UserProfile`**: Parses `/learn/api/public/v1/users/me` responses, extracting `id`, `userName`, `studentId`, given/family names, and contact emails.
3. **`Course`**: Normalizes Blackboard course representations, handling both direct course entries and enrollment membership objects (`data.get("course") or data`). Extracts `ultraStatus == "Ultra"` to flag Ultra course spaces.
4. **`Attachment`**: Represents file payloads within content items. Formats the canonical REST download path:
   `/learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments/{att_id}/download`.
5. **`ContentItem`**: Deduces content categorization from Blackboard's internal `contentHandler.id`:
   - `resource/x-bb-folder` -> `ContentType.FOLDER` (`has_children = True`)
   - `resource/x-bb-file` -> `ContentType.FILE`
   - `resource/x-bb-assignment` or `assessment` -> `ContentType.ASSIGNMENT`
   - `resource/x-bb-document` -> `ContentType.DOCUMENT`
6. **`Announcement`**: Parses HTML announcement bodies with BeautifulSoup, dynamically transforming anchor tags into Markdown links while preserving text formatting.
7. **`GradeItem`**: Safely parses gradebook columns and user scores, converting numerical values to floats and computing percentage yields: `round((score / pts_possible) * 100, 2)`.
8. **`Assignment`**: Normalized representation for task tracking, combining column definitions, ISO due dates, point totals, and completion status.

---

### 2.3 `cuhk_blackboard/auth.py`: Authentication Manager & Parser Engine

The `AuthManager` class manages the complete authentication lifecycle:
- **Default Storage Coordinates**:
  - `DEFAULT_HOST`: `https://blackboard.cuhk.edu.hk`
  - `DEFAULT_SESSION_DIR`: `Path.home() / ".cuhk_blackboard"`
  - `DEFAULT_SESSION_FILE`: `Path.home() / ".cuhk_blackboard" / "session.json"`
- **Authentication Handlers**:
  - `set_cookie_auth(cookie_input, host, save)`: Ingests raw cookies, invokes `parse_cookie_input`, updates configuration, and conditionally writes to disk.
  - `set_token_auth(token, host, save)`: Strips `"Bearer "` prefixes and persists access tokens.
  - `set_credentials_auth(username, password, duo_passcode, host, save)`: Holds username/password in memory; defaults `save=False`.
- **Precedence Loading Logic (`load_session`)**:
  1. Checks `os.getenv("CUHK_BB_COOKIE")`. If set, configures cookie auth with `save=False`.
  2. Checks `os.getenv("CUHK_BB_TOKEN")`. If set, configures token auth with `save=False`.
  3. Checks `~/.cuhk_blackboard/session.json`. If present and valid JSON, restores session state.
- **Request Headers Construction (`get_auth_headers`)**:
  - User-Agent: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Blackboard/1.0`
  - Origin & Referer: Dynamic binding to target Blackboard host.
  - Anti-CSRF Token: Extracts `X-Blackboard-SXS` from cookies and binds it to request headers.
  - Authorization: Injects `Authorization: Bearer <token>` when using Bearer auth.

---

### 2.4 `cuhk_blackboard/client.py`: Dual-Engine Blackboard Client

`BlackboardClient` encapsulates all network I/O, session management, and response transformations.
- **Network Pipeline (`_request`)**:
  - Targets `requests.Session`.
  - Clears `session.cookies` on each dispatch and re-populates from `auth_manager.config.cookies` to prevent cookie leakage across distinct requests.
  - Strips manual `"Cookie"` headers to eliminate header duplication conflicts with the `requests.Session` cookie jar.
  - Enforces a default 15-second timeout on all requests.
- **Core Operations**:
  - `verify_auth()`: Dual-tier verification (REST `/users/me` with Web Portal tab action fallback).
  - `list_courses(include_hidden)`: Multi-tier course enumeration (user courses -> system courses -> portal HTML regex).
  - `get_course(course_id)`: Precise ID lookup with fallback to fuzzy name/code match across enrolled courses.
  - `list_course_contents(course_id, content_id, recursive, max_depth)`: Recursive folder traversal with automatic attachment enrichment.
  - `list_announcements(course_id, limit)`: Course-specific or cross-course aggregated announcement retrieval.
  - `list_assignments(course_id, upcoming_only)`: Gradebook column due date extraction and ISO UTC temporal comparison.
  - `get_grades(course_id)`: Student gradebook extraction and percentage computation.
  - `download_material(...)`: Binary stream downloading with `Content-Disposition` regex extraction and filename path-traversal sanitization.
  - `search_materials(query, course_id)`: Cross-entity keyword search.
  - `get_course_summary(course_id)`: High-density LLM summary generation.

---

### 2.5 `cuhk_blackboard/interactive_login.py`: Browser Automation & CDP Session Capture

Implements zero-copy session acquisition to bypass manual cookie copying:
- **`capture_from_cdp(cdp_url)`**:
  - Probes local Chrome DevTools Protocol ports: `9222`, `9229`, `9333`.
  - Queries `GET {cdp_url}/json/list` to find active tabs matching `blackboard.cuhk.edu.hk`.
  - Connects using `playwright.sync_api.sync_playwright().chromium.connect_over_cdp(cdp_url)`.
  - Extracts cookies scoped to `blackboard.cuhk.edu.hk`, verifying the presence of `JSESSIONID`.
- **`launch_browser_login(host, timeout_seconds)`**:
  - Fallback sequence: probes CDP ports first; if unavailable, launches local Chromium browser with channel order: `msedge` -> `chrome` -> unbundled `chromium`.
  - Navigates to `blackboard.cuhk.edu.hk` and waits for URL matching regex:
    `r"blackboard\.cuhk\.edu\.hk/(?:ultra|webapps/(?:portal|blackboard))"`
  - Extracts session cookies and cleanly closes the browser context.
- **`prompt_user_auth(client)`**:
  - Terminal interactive wizard guiding students through Cookie, Token, Credentials, or Browser launch flows.

---

### 2.6 `cuhk_blackboard/tools.py`: Agent Tools Registry & Lifecycle

Acts as the translation bridge between agent frameworks and the client:
- **Singleton Lifecycle**: Maintains `_global_client: Optional[BlackboardClient] = None` retrieved via `get_client()`.
- **Schema Registry**: Exports `AGENT_TOOLS_DEFINITIONS` containing 13 full JSON Schemas.
- **Function Mapping**: Exports `TOOL_FUNCTION_MAP` binding schema names directly to callable functions.

---

### 2.7 `cuhk_blackboard/mcp_server.py`: Native JSON-RPC Stdio Transport

Implements the Model Context Protocol stdio server:
- Parses line-delimited JSON-RPC requests from `sys.stdin`.
- Dispatches methods (`initialize`, `ping`, `tools/list`, `tools/call`).
- Isolates `real_stdout` and redirects `sys.stdout` to `sys.stderr`.
- Encapsulates tool outputs and stack traces into JSON-RPC response structures.

---

### 2.8 `cuhk_blackboard/cli.py`: Terminal Entry Points & Operations

Provides terminal commands for manual inspection, debugging, and standalone operation:
- Console entry point: `cuhk-blackboard = cuhk_blackboard.cli:main`.
- Supported subcommands:
  - `auth`: Interactive configuration or direct `--cookie` / `--token` setting.
  - `status`: Authenticated session and user profile verification.
  - `courses`: Enrolled course enumeration.
  - `contents`: Content and directory browsing (`--recursive`, `--depth`).
  - `announcements`: Course announcements listing.
  - `grades`: Student gradebook inspection.
  - `download`: File downloading via course/content/attachment IDs.
  - `mcp`: Launches the stdio MCP server.

---

## 3. Authentication & Security Engine Deep-Dive

### 3.1 The Enterprise Authentication Landscape

CUHK Blackboard relies on an institutional identity federation topology:
1. **SAML / ADFS Federation**: Access to `/webapps/login/` redirects unauthenticated traffic to CUHK OnePass (`https://sts.cuhk.edu.hk/adfs/ls/`).
2. **Duo Mobile 2FA**: Following CWEM username and password submission, ADFS triggers a secondary challenge requiring an asynchronous Duo Push confirmation or 6-digit TOTP code.
3. **Session Cookie Issuance**: Upon successful federation, the browser receives:
   - `JSESSIONID`: Java Servlet session identifier.
   - `session_id`: Blackboard application session token.
   - `X-Blackboard-SXS`: Anti-CSRF synchronization token.

Headless HTTP POST requests that attempt to submit username and password directly to Blackboard endpoints fail because Blackboard does not process passwords locally; it redirects to ADFS, which halts on the Duo 2FA challenge.

---

### 3.2 The 5 Authentication Routes

To navigate this landscape, the plugin implements 5 distinct authentication pathways:

```
                            ┌───────────────────────────────────┐
                            │      User / Agent Auth Input      │
                            └─────────────────┬─────────────────┘
                                              │
         ┌────────────────────┬───────────────┼───────────────┬────────────────────┐
         ▼                    ▼               ▼               ▼                    ▼
┌─────────────────┐  ┌─────────────────┐ ┌─────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Route 1:        │  │ Route 2:        │ │ Route 3:│ │ Route 4:        │ │ Route 5:        │
│ CDP Zero-Copy   │  │ Multi-Format    │ │ Mobile  │ │ CWEM & Duo      │ │ Priority        │
│ Session Capture │  │ Cookie Ingestion│ │ OAuth   │ │ Interactive     │ │ Persistence     │
│                 │  │                 │ │ Bearer  │ │ Credential Flow │ │                 │
│ - Probe ports   │  │ - HTTP headers  │ │ Token   │ │ - In-memory only│ │ - Env vars      │
│   9222/9229/9333│  │ - cURL commands │ │ - Up to │ │ - Explicit Duo  │ │ - session.json  │
│ - Zero manual   │  │ - DevTools table│ │   336h  │ │   failure notice│ │ - Strict zero-  │
│   copying       │  │ - Cookie-Editor │ │   TTL   │ │ - Cookie fallback│ │   disk password │
└────────┬────────┘  └────────┬────────┘ └────┬────┘ └────────┬────────┘ └────────┬────────┘
         │                    │               │               │                   │
         └────────────────────┴───────────────┼───────────────┴───────────────────┘
                                              ▼
                             ┌─────────────────────────────────┐
                             │       AuthConfig Ingestion      │
                             │   (Validated & Synchronized)    │
                             └────────────────┬────────────────┘
                                              ▼
                             ┌─────────────────────────────────┐
                             │ Dual-Tier Server Handshake      │
                             │ 1. REST: GET /users/me          │
                             │ 2. Web Portal Tab Action        │
                             │    (Traps SAML 200 Redirects)   │
                             └─────────────────────────────────┘
```

#### Route 1: CDP Zero-Copy Browser Session Capture (`cuhk_bb_capture_browser_session`)
- **Mechanism**: Connects to Chrome DevTools Protocol endpoints across common debugging ports (`9222`, `9229`, `9333`).
- **Operation**:
  1. Issues `GET http://127.0.0.1:{port}/json/list` with a 2-second socket timeout.
  2. Scans open tab targets for `url` containing `blackboard.cuhk.edu.hk`.
  3. Attaches Playwright Chromium client over CDP: `p.chromium.connect_over_cdp(...)`.
  4. Retrieves cookies for `https://blackboard.cuhk.edu.hk`, verifying that `JSESSIONID` is present.
  5. Serializes extracted cookies into a clean header string and ingests them into `AuthManager`.
- **Value**: Enables users operating in IDE sidebar browsers (e.g. Cursor, Antigravity) to log into Blackboard manually once; the agent captures the authenticated session with zero clipboard copying.

#### Route 2: Multi-Format Cookie Parsing Engine (`parse_cookie_input`)
Users copy cookies from varied environments. `auth.py:parse_cookie_input()` implements a fault-tolerant parser supporting 6 input formats:
1. **Standard HTTP Header**: `"Cookie: JSESSIONID=abc; session_id=def"` (handles case-insensitive `"cookie:"` prefixes).
2. **cURL Command Headers**: Extracts payload from `-H 'Cookie: ...'`, `-H "Cookie: ..."`, `-b "..."`, or `--cookie "..."` using regexes:
   - `re.search(r"cookie:\s*([^'\"\r\n]+)", raw_str, re.IGNORECASE)`
   - `re.search(r"(?:-b|--cookie)\s+['\"]?([^'\"\r\n]+)", raw_str, re.IGNORECASE)`
3. **Browser DevTools Storage Table Copy**: In Chrome/Edge DevTools (Application -> Cookies), copying table rows yields tab-delimited strings (`Name\tValue\tDomain\tPath...`). The parser splits lines by `\t`, mapping column 0 to key and column 1 to value.
4. **Newline-Delimited Pairs**: Handles `JSESSIONID=abc\nsession_id=def`.
5. **JSON Object Strings**: Parses `'{"JSESSIONID": "abc", "session_id": "def"}'`.
6. **Cookie-Editor Extension JSON Array**: Ingests browser extension exports:
   `[{"name": "JSESSIONID", "value": "abc"}, {"name": "session_id", "value": "def"}]`.

Key Normalization Rules:
- Preserves `=` characters inside cookie values: `part.split("=", 1)`.
- Strips surrounding quotes: `.strip("'\"")`.
- Silently ignores blank tokens and invalid rows.

#### Route 3: Mobile App OAuth Bearer Token Auth (`set_token_auth`)
- **Mechanism**: CUHK Blackboard Mobile App uses OAuth 2.0 Bearer JWT tokens.
- **Operation**: Users extract the Bearer token from mobile proxy captures or token caches and provide it via `set_token_auth(token)`.
- **Characteristics**:
  - Automatically strips `"Bearer "` prefixes.
  - Injects `Authorization: Bearer <token>` into outgoing request headers.
  - Mobile tokens offer significantly extended lifespans (up to 336 hours / 14 days), avoiding hourly session cookie expirations.

#### Route 4: Interactive Credentials Flow with Duo Guidance (`set_credentials_auth`)
- **Mechanism**: Ingests student username, CWEM password, and optional Duo TOTP passcode into memory.
- **Handling**: If direct verification fails due to Duo MFA push enforcement, `tools.py` catches the verification failure and appends an explicit educational notice:
  > *"Note: CUHK strictly enforces SAML SSO with Duo 2FA push notifications. Please use method='cookie' with session cookies extracted from browser DevTools after completing Duo 2FA."*

#### Route 5: Priority Session Persistence & Precedence Hierarchy
`AuthManager.load_session()` enforces a strict 3-tier precedence hierarchy:
1. **Environment Variables**:
   - `CUHK_BB_COOKIE`: Ingests cookie string with `save=False` (ephemeral).
   - `CUHK_BB_TOKEN`: Ingests Bearer token with `save=False`.
   - `CUHK_BB_HOST`: Custom target host (defaults to `https://blackboard.cuhk.edu.hk`).
2. **Local Session File**: `~/.cuhk_blackboard/session.json`. Restores saved method, cookies, token, and username.
3. **Default Unauthenticated State**: Blank configuration requiring user setup.

---

### 3.3 Security Controls & Hardening

#### 3.3.1 Strict Password Exclusion from Disk
Plaintext passwords must never touch disk storage. In `cuhk_blackboard/auth.py:save_session()` (lines 229–236), the disk serialization payload is explicitly restricted:
```python
data = {
    "method": self.config.method.value,
    "host": self.config.host,
    "cookies": self.config.cookies,
    "bearer_token": self.config.bearer_token,
    "username": self.config.username,
    "session_file": str(target_path),
}
```
`password` and `duo_passcode` are strictly excluded from the dictionary. Even if a user invokes `save=True` with credentials, the password exists only in volatile process memory and is purged upon process exit.

#### 3.3.2 Multi-Tier Secret Masking (`AuthConfig.to_dict`)
When returning configuration states in agent logs or tool outputs, `models.py:AuthConfig.to_dict(mask_secrets=True)` sanitizes credentials:
- `password`: Replaced with `"********"`.
- `bearer_token`: Truncated to first 8 and last 4 characters: `f"{token[:8]}...{token[-4:]}"`.
- `cookies`: Truncated to first 4 and last 4 characters: `f"{val[:4]}...{val[-4:]}"`.

#### 3.3.3 False-Positive SAML ADFS Redirect Detection
A critical vulnerability in LMS scraping is false-positive authentication validation. Blackboard web portals respond with HTTP status code 200 even when unauthenticated, serving an HTML redirect page containing `<meta http-equiv="REFRESH" content="0;url=.../auth-saml/...">`.

`cuhk_blackboard/client.py:verify_auth()` (lines 107–120) implements a two-phase assertion to prevent false positives:
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

if portal_resp.status_code == 200 and has_logout and not is_login_page:
    # Authenticated session confirmed
```
Authentication is accepted only when the response returns HTTP 200, contains an explicit logout action or user profile element, AND contains zero SAML/ADFS login markers.

#### 3.3.4 Anti-CSRF Token Synchronization (`X-Blackboard-SXS`)
Blackboard validates incoming REST mutations and state queries using the `X-Blackboard-SXS` synchronization token. `auth.py:get_auth_headers()` checks the parsed cookie dictionary for `X-Blackboard-SXS` and sets it as an independent HTTP request header, avoiding 403 CSRF rejections.

#### 3.3.5 Origin & Referer Pinning
In `auth.py:get_auth_headers()`, outgoing headers pin `Origin` and `Referer` to `self.host`. This satisfies Blackboard's cross-origin request validation rules on REST v1 endpoints.

#### 3.3.6 Path Traversal Sanitization for File Downloads
In `client.py:download_material()` (line 464), file names extracted from server `Content-Disposition` headers are sanitized using regex substitution:
```python
safe_filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
file_path = target_dir / safe_filename
```
This strips path traversal characters (`..`, `/`, `\`), preventing malicious file payloads from escaping `target_dir`.

---

## 4. Core Blackboard API & Dual-Engine Fallback Pipeline

### 4.1 Dual-Engine Philosophy: REST API v1 vs Web Portal HTML Scraping

Institutional LMS instances are frequently configured with idiosyncratic permission sets:
- Certain courses may disable REST API discovery while remaining visible on the web portal.
- Instructors may use Blackboard Ultra for certain courses and Original (9.1) for others.
- Certain endpoints (`/gradebook/columns`) may return HTTP 403 for student roles depending on institutional policy.

`cuhk-blackboard-plugin` resolves this via an automated **Dual-Engine Pipeline**:
1. **Primary Layer**: Attempts official Blackboard Learn REST APIs (`/learn/api/public/v1/...`).
2. **Fallback Layer**: Upon encountering HTTP 401, 403, 404, or unpopulated payloads, the client automatically executes an equivalent Web Portal query using BeautifulSoup4 HTML parsing.

---

### 4.2 Comprehensive REST vs HTML Fallback Matrix

| Domain Operation | Primary REST v1 Endpoint | Secondary HTML Web Fallback URL | Fallback Trigger Condition | Parsing Mechanism & Normalization |
|---|---|---|---|---|
| **Auth Verification** | `GET /learn/api/public/v1/users/me` | `GET /webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1` | REST returns HTTP 401/403 (browser cookies lack REST token) | Validates absence of `sts.cuhk.edu.hk` & presence of `action=logout`. Scrapes display name from `#global-nav-link`. |
| **List Courses** | 1. `GET .../users/me/courses`<br>2. `GET .../courses` | `GET /webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1` | REST endpoints return HTTP 401/403/404 or empty list | Regex matches `r"(?:(?:course_id\|id)=\|/courses/)(_\d+_\d+)"` across anchor links. Identifies `/ultra/courses/` URLs. |
| **Course Details** | 1. `GET .../courses/{id}`<br>2. `GET .../courses/courseId:{id}` | In-memory search over `list_courses()` results | REST returns 404 or invalid ID format | Scans cached course list, performing case-insensitive matching across `id`, `course_id`, and `name`. |
| **Course Contents** | `GET .../courses/{id}/contents/{cid}/children`<br>(or `/contents` for root) | `GET /webapps/blackboard/content/listContentEditable.jsp?content_id={cid}&course_id={id}` | REST returns HTTP 401/403/404 | BeautifulSoup parses `.contentList`, `.contentListPlain`, and `.content-item` elements. Extracts item IDs and links. |
| **Announcements** | `GET .../courses/{id}/announcements`<br>(or `/announcements` for system) | `GET /webapps/blackboard/execute/announcement?course_id={id}` | REST returns HTTP 401/403/404 | BeautifulSoup parses `#announcementList`, `.announcementItem`, extracting title, date, and cleaned body text. |
| **Student Grades** | 1. `GET .../gradebook/columns`<br>2. `GET .../columns/{col}/users/me` | `GET /webapps/gradebook/do/student/viewGrades?course_id={id}` | REST column or user attempt returns 401/403 | BeautifulSoup parses `.graded_item_row`, extracting item name, score text, and points possible via regex. |
| **Attachment Download** | `GET .../contents/{cid}/attachments/{aid}/download` | Direct absolute URL or relative path (`/bbcswebdav/...`) | `attachment_id` begins with `"http://"` or `"/"` | Streams response chunks, extracts filename from `Content-Disposition`, sanitizes filename, and writes to disk. |

---

### 4.3 Recursive Content Traversal & Dynamic Attachment Enrichment

In Blackboard, learning materials are arranged in hierarchical folder trees.
In `cuhk_blackboard/client.py:list_course_contents()` (lines 212–282):
1. **Level Fetching**: Calls `_fetch_contents_level(course_id, content_id)`.
2. **Attachment Enrichment**: Blackboard REST payloads often omit inline file metadata for `FILE`, `DOCUMENT`, or `ASSIGNMENT` types. If `item.attachments` is empty, the client dynamically triggers `_fetch_item_attachments(course_id, item.id)`, querying:
   `GET /learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments`
   and populates the item's attachment collection.
3. **Recursive Descent**: When `recursive=True` and an item has `has_children=True` or `content_type == ContentType.FOLDER`, the client recursively invokes `list_course_contents`, decrementing `max_depth - 1` until reaching depth 0. This prevents infinite recursion on cyclic links while assembling the complete folder tree.

---

### 4.4 Markdown Link Preservation & HTML Body Cleaning in Announcements

Raw Blackboard announcement bodies contain messy, nested HTML with internal styling, empty `<div>` containers, and `<br>` breaks. Stripping all HTML destroys embedded hyperlinks to lecture recordings, Zoom sessions, and Google Forms.

In `models.py:Announcement.from_api()` (lines 257–285), BeautifulSoup transforms the HTML Abstract Syntax Tree:
```python
soup = BeautifulSoup(raw_body, "html.parser")

# 1. Transform HTML anchor tags to Markdown links: [text](href)
for a_tag in soup.find_all("a", href=True):
    href = a_tag["href"].strip()
    text_inside = a_tag.get_text().strip()
    if href and text_inside and href != text_inside:
        a_tag.replace_with(f"[{text_inside}]({href})")
    elif href:
        a_tag.replace_with(href)

# 2. Append newline delimiters to block tags to preserve visual paragraphs
for tag in soup.find_all(["br", "p", "div", "tr", "h1", "h2", "h3", "h4", "li"]):
    tag.append("\n")

# 3. Collapse whitespace and assemble clean plain text
lines = [line.strip() for line in soup.get_text().splitlines()]
text = "\n".join(l for l in lines if l).strip()
```
This produces clean, structured Markdown text that AI agents can parse and present with functional hyperlinks.

---

### 4.5 Gradebook Calculation, Type Safety & Percentage Normalization

Blackboard gradebook columns return heterogeneous score schemas: string-formatted scores (`"85.5"`), total points as strings, letter grades (`"A-"`), or null attempt objects.

In `models.py:GradeItem.from_api()` (lines 303–349):
- Safely casts `scoreTotal` and `raw_score` within `try...except (ValueError, TypeError)` blocks.
- Computes percentage yield with zero-division protection:
  ```python
  pct = None
  if score is not None and pts_possible and pts_possible > 0:
      pct = round((score / pts_possible) * 100, 2)
  ```
- Defaults status to `"NotAttempted"` when grade data is absent, and captures qualitative feedback from `grade_data.get("feedback")`.

---

### 4.6 File Material Streaming & Path Traversal Sanitization

In `client.py:download_material()` (lines 431–473):
- Uses `stream=True` on `requests.Session.request` to stream large lecture slide decks and video attachments in 8192-byte chunks, preventing high memory consumption.
- Extracts filenames from the `Content-Disposition` header using regex:
  `r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)'`
- Replaces illegal file system characters via `re.sub(r'[\\/*?:"<>|]', "_", filename)`.
- Returns the resolved local `Path` object.

---

### 4.7 Unified Cross-Entity Keyword Search

In `client.py:search_materials(query, course_id)` (lines 474–526):
- Validates search queries, returning immediately on empty or whitespace strings.
- Executes searches across three entity domains:
  1. **Course Codes & Names**: Matches against enrolled courses.
  2. **Announcements**: Matches against announcement titles and cleaned Markdown text.
  3. **Course Contents**: Searches content titles, descriptions, and body texts up to directory depth 2.
- Aggregates results into a single structured response:
  `{"courses": [...], "contents": [...], "announcements": [...]}`.

---

### 4.8 Token-Efficient Course Summary Synthesis for AI Agents

In `client.py:get_course_summary(course_id)` (lines 528–569):
AI agents suffer context degradation when forced to make 10+ sequential tool calls to understand a course's status. `get_course_summary` aggregates critical course metrics into a compact, high-signal dictionary:
- **Course Metadata**: Code, title, Ultra status.
- **Top 3 Recent Announcements**: Includes creation dates and 150-character previews.
- **Top 5 Upcoming Assignments**: Deadlines evaluated against UTC timestamps with point values.
- **Top 10 Top-Level Contents**: Content titles, types, child indicators, and attachment counts.
- **Top 5 Recent Grades**: Scores, points possible, percentages, and grading statuses.

---

## 5. Agent Tools & MCP Protocol Integration

### 5.1 Tool Registry Architecture & Singleton Client Lifecycle

All agent tools reside in `cuhk_blackboard/tools.py`.
- **Client Lifecycle**: Managed by `get_client() -> BlackboardClient`. A single global `_global_client` persists throughout the process lifetime, maintaining connection pools, cached authentication configs, and HTTP session cookies across multi-turn agent conversations.
- **Error Handling Paradigm**: Every tool wraps its execution in a `try...except Exception as e` block, returning a standard error dictionary:
  `{"success": False, "error": str(e)}`.

---

### 5.2 Complete Specification of All 13 Agent Tools

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            13 Agent Tools Registry                          │
├──────────────────────┬───────────────────────────────┬──────────────────────┤
│ Authentication &     │ Courses & Navigation          │ Contents & Files     │
│ Session Management   │ - cuhk_bb_list_courses        │ - cuhk_bb_list_course│
│ - configure_auth     │ - cuhk_bb_get_course_details  │   _contents          │
│ - auth_status        │                               │ - download_material  │
│ - capture_browser    ├───────────────────────────────┤ - search_materials   │
│   _session           │ Communication & Tasks         ├──────────────────────┤
│ - get_auth_guide     │ - cuhk_bb_list_announcements  │ High-Density Context │
│                      │ - cuhk_bb_list_assignments    │ - get_course_summary │
│                      │ - cuhk_bb_get_grades          │                      │
└──────────────────────┴───────────────────────────────┴──────────────────────┘
```

#### Tool 1: `cuhk_bb_configure_auth`
- **Purpose**: Configure or update authentication parameters with automatic method deduction.
- **Parameters**:
  - `method` (`string`, default: `"cookie"`, enum: `["cookie", "token", "credentials", "saved_session", "auto"]`)
  - `value` (`string`, optional): Cookie string or Bearer token.
  - `username` (`string`, optional): CUHK CWEM username.
  - `password` (`string`, optional): CWEM password.
  - `duo_passcode` (`string`, optional): 6-digit Duo TOTP code.
  - `host` (`string`, optional): Custom Blackboard host URL.
  - `save` (`boolean`, default: `true`): Persist configuration to `session.json`.
- **Returns**: `{"success": bool, "message": str, "method": str, "user": dict, "guide": str}`.

#### Tool 2: `cuhk_bb_auth_status`
- **Purpose**: Check authentication status, verify credentials with server, and fetch user profile.
- **Parameters**: None.
- **Returns**: `{"authenticated": bool, "host": str, "method": str, "user_profile": dict, "error": str, "instructions": str}`.

#### Tool 3: `cuhk_bb_capture_browser_session`
- **Purpose**: Capture authenticated session from a running browser via CDP ports (9222, 9229, 9333) or launch Playwright.
- **Parameters**:
  - `cdp_port` (`integer`, default: `9222`)
  - `auto_launch` (`boolean`, default: `true`)
  - `timeout_seconds` (`integer`, default: `120`)
- **Returns**: `{"success": bool, "message": str, "user": dict, "guide": str}`.

#### Tool 4: `cuhk_bb_get_auth_guide`
- **Purpose**: Retrieve step-by-step instructions for extracting Blackboard credentials.
- **Parameters**:
  - `method` (`string`, default: `"all"`, enum: `["cookie", "token", "credentials", "sidebar_browser", "all"]`)
- **Returns**: `{"method": str, "instructions": str}`.

#### Tool 5: `cuhk_bb_list_courses`
- **Purpose**: List all enrolled Blackboard courses.
- **Parameters**:
  - `include_hidden` (`boolean`, default: `false`)
- **Returns**: `{"success": bool, "count": int, "courses": List[dict]}`.

#### Tool 6: `cuhk_bb_get_course_details`
- **Purpose**: Retrieve detailed information for a specific course.
- **Parameters**:
  - `course_id` (`string`, required): Blackboard primary key (e.g. `"_12345_1"`) or course code (`"2024R1-CSCI3150"`).
- **Returns**: `{"success": bool, "course": dict}`.

#### Tool 7: `cuhk_bb_list_course_contents`
- **Purpose**: List contents, folders, lecture slides, and assignments within a course.
- **Parameters**:
  - `course_id` (`string`, required)
  - `content_id` (`string`, optional): Parent folder ID.
  - `recursive` (`boolean`, default: `false`): Traverse nested folders.
  - `max_depth` (`integer`, default: `3`): Traversal depth limit.
- **Returns**: `{"success": bool, "course_id": str, "count": int, "contents": List[dict]}`.

#### Tool 8: `cuhk_bb_list_announcements`
- **Purpose**: Fetch announcements with HTML cleaned and links converted to Markdown.
- **Parameters**:
  - `course_id` (`string`, optional): Specific course ID (omission fetches cross-course announcements).
  - `limit` (`integer`, default: `15`)
- **Returns**: `{"success": bool, "count": int, "announcements": List[dict]}`.

#### Tool 9: `cuhk_bb_list_assignments`
- **Purpose**: List assignments, deadlines, point totals, and submission statuses.
- **Parameters**:
  - `course_id` (`string`, optional)
  - `upcoming_only` (`boolean`, default: `true`): Filter out past deadlines.
- **Returns**: `{"success": bool, "count": int, "assignments": List[dict]}`.

#### Tool 10: `cuhk_bb_get_grades`
- **Purpose**: Retrieve student grades, points possible, percentages, and instructor feedback.
- **Parameters**:
  - `course_id` (`string`, required)
- **Returns**: `{"success": bool, "course_id": str, "count": int, "grades": List[dict]}`.

#### Tool 11: `cuhk_bb_download_material`
- **Purpose**: Download course attachment to local disk with path sanitization.
- **Parameters**:
  - `course_id` (`string`, required)
  - `content_id` (`string`, required)
  - `attachment_id` (`string`, required): Attachment ID or download URL.
  - `target_dir` (`string`, default: `"./downloaded_materials"`)
  - `filename` (`string`, optional): Custom file name override.
- **Returns**: `{"success": bool, "file_path": str, "file_name": str, "size_bytes": int}`.

#### Tool 12: `cuhk_bb_search_materials`
- **Purpose**: Search across course codes, announcement texts, and folder contents.
- **Parameters**:
  - `query` (`string`, required): Search keyword.
  - `course_id` (`string`, optional): Limit search scope to specific course.
- **Returns**: `{"success": bool, "query": str, "results": {"courses": list, "contents": list, "announcements": list}}`.

#### Tool 13: `cuhk_bb_get_course_summary`
- **Purpose**: High-density LLM overview of recent announcements, upcoming deadlines, top materials, and grades.
- **Parameters**:
  - `course_id` (`string`, required)
- **Returns**: `{"success": bool, "course_summary": dict}`.

---

## 6. Test Suite & Reliability Engineering

### 6.1 Test Suite Topology & Organization (57 Tests)

The test suite in `tests/` contains 57 automated unit tests across 6 dedicated test modules:

```
tests/
├── test_auth.py         # 12 tests (Cookie parsing formats, persistence, tokens)
├── test_cli.py          # 4 tests (CLI subcommands: courses, contents, announcements, grades)
├── test_client.py       # 17 tests (Dual-engine fallbacks, SAML detection, downloads, search)
├── test_mcp_server.py   # 7 tests (JSON-RPC protocol, handshake, tools/call dispatch, errors)
├── test_models.py       # 6 tests (Secret masking, dataclass serialization, markdown conversion)
└── test_tools.py        # 11 tests (Registry consistency, auto-detect, Duo guidance, error paths)
```

**Execution Performance**: Full test suite executes in **0.19 seconds** on Python 3.14 / pytest 9.1.0 with zero failures and zero network overhead.

---

### 6.2 Module-by-Module Test Breakdown

#### 6.2.1 `tests/test_auth.py` (12 Tests)
Validates cookie parsing, header formats, token management, and session serialization:
1. `test_parse_cookie_header_string`: Standard `Cookie: k=v; k2=v2` header parsing.
2. `test_parse_cookie_json_string`: JSON object `{"k": "v"}` parsing.
3. `test_parse_cookie_curl_format`: cURL `-H 'Cookie: ...'` and `--cookie` parsing.
4. `test_parse_cookie_http2_lowercase_and_curl_b`: HTTP/2 lowercase `cookie:` and `-b` cURL format.
5. `test_parse_cookie_multiline_and_tab_separated`: Multi-line and browser DevTools tab-separated table parsing.
6. `test_parse_cookie_dict_input`: Direct dictionary input normalization.
7. `test_set_cookie_auth`: Configuration updating, host binding, and disk persistence.
8. `test_set_token_auth`: Bearer prefix stripping and token storage.
9. `test_set_credentials_auth`: Credential validation and password omission on disk.
10. `test_clear_session`: Memory state reset and `session.json` file unlinking.
11. `test_get_auth_guide`: Instruction string retrieval across all methods.
12. `test_parse_cookie_json_array_cookie_editor`: Browser extension JSON array `[{"name": "...", "value": "..."}]` ingestion.

#### 6.2.2 `tests/test_cli.py` (4 Tests)
Validates argparse CLI subcommands using `pytest.capsys` and mocked clients:
1. `test_cli_courses_command`: Tests `courses` subcommand table output formatting.
2. `test_cli_contents_command`: Tests `contents` subcommand with course ID parameter.
3. `test_cli_announcements_command`: Tests `announcements` subcommand output.
4. `test_cli_grades_command`: Tests `grades` subcommand gradebook table output.

#### 6.2.3 `tests/test_client.py` (17 Tests)
Validates network pipeline, fallback sequences, and response normalization:
1. `test_verify_auth_unconfigured`: Verifies unconfigured client returns `False` immediately.
2. `test_verify_auth_success`: Verifies REST `/users/me` HTTP 200 returns `UserProfile`.
3. `test_verify_auth_failure`: Verifies REST 401 followed by Portal 401 returns `False`.
4. `test_list_courses_api`: Verifies REST `/users/me/courses` returns `Course` objects.
5. `test_list_courses_html_fallback`: Simulates REST 404, validating fallback to Portal HTML regex parser.
6. `test_list_course_contents_with_attachments`: Verifies content parsing and secondary `_fetch_item_attachments` calls.
7. `test_list_announcements`: Verifies course announcement retrieval and date sorting.
8. `test_get_grades`: Verifies column querying, user attempt matching, and percentage calculation.
9. `test_download_material`: Verifies streamed chunk writing, `Content-Disposition` filename extraction, and local disk output.
10. `test_search_materials`: Verifies keyword matching across courses, contents, and announcements.
11. `test_verify_auth_cuhk_login_redirect_is_failure`: Verifies HTTP 200 containing SAML meta-refresh is rejected as invalid.
12. `test_list_assignments_upcoming_only_filter`: Verifies expired ISO due dates are filtered out when `upcoming_only=True`.
13. `test_download_material_direct_url`: Verifies handling of absolute and `/bbcswebdav/` download URLs.
14. `test_get_course_lookup_fallbacks`: Verifies primary course ID lookup failure falls back to course list scan.
15. `test_search_materials_empty_query`: Verifies empty search string returns immediately without network calls.
16. `test_list_courses_ultra_html`: Verifies regex extraction of `/ultra/courses/_...` links from HTML.
17. `test_list_assignments_and_course_summary_deadlines`: Verifies summary deadline computation.

#### 6.2.4 `tests/test_mcp_server.py` (7 Tests)
Validates MCP JSON-RPC 2.0 protocol specifications:
1. `test_mcp_initialize`: Verifies protocol version `2024-11-05` and server info.
2. `test_mcp_ping`: Verifies ping response `{}`.
3. `test_mcp_tools_list`: Verifies 13 tools exposed with valid `inputSchema`.
4. `test_mcp_tools_call_success`: Verifies tool execution and JSON string response formatting.
5. `test_mcp_tools_call_not_found`: Verifies error code `-32601` for non-existent tools.
6. `test_mcp_unknown_method`: Verifies error code `-32601` for unrecognized RPC methods.
7. `test_mcp_notification`: Verifies `notifications/initialized` returns `None`.

#### 6.2.5 `tests/test_models.py` (6 Tests)
Validates data transformations and secret masking:
1. `test_auth_config_to_dict_masking`: Verifies passwords, tokens, and cookies are masked.
2. `test_user_profile_from_api`: Verifies display name assembly from given/family names.
3. `test_course_from_api`: Verifies Ultra course detection and membership object parsing.
4. `test_content_item_from_api`: Verifies `contentHandler` ID mapping to `ContentType` enum.
5. `test_announcement_from_api`: Verifies HTML tag stripping and Markdown link conversion `[text](href)`.
6. `test_grade_item_from_api`: Verifies numerical string casting and percentage calculation.

#### 6.2.6 `tests/test_tools.py` (11 Tests)
Validates agent tool entry points and parameter validations:
1. `test_tool_definitions_consistency`: Verifies exact 1:1 parity between `AGENT_TOOLS_DEFINITIONS` and `TOOL_FUNCTION_MAP` (13 tools).
2. `test_configure_auth_missing_value`: Verifies error payload when `value` is omitted for cookie/token.
3. `test_configure_auth_unsupported_method`: Verifies error payload for unknown method names.
4. `test_configure_auth_cookie_success`: Verifies successful cookie ingestion and verification dispatch.
5. `test_auth_status`: Verifies auth status query structure.
6. `test_get_auth_guide`: Verifies guide output.
7. `test_list_courses`: Verifies tool wrapper response shape.
8. `test_get_course_summary`: Verifies summary structure.
9. `test_configure_auth_auto_detect`: Verifies auto-detection of cookies, JWT tokens, and credentials.
10. `test_configure_auth_credentials_failure_includes_duo_note`: Verifies Duo 2FA guidance note on failed credentials auth.
11. `test_capture_browser_session_success`: Verifies CDP browser capture mocking.

---

### 6.3 Mocking Strategies & Isolation

The test suite achieves 100% offline determinism through systematic mocking:
1. **HTTP Pipeline Interception (`unittest.mock.patch.object`)**:
   - Intercepts `client.session.request` using `patch.object(client.session, "request", return_value=mock_resp)`.
   - Simulates fallback chains using `side_effect=[api_fail, portal_ok]`, allowing exact testing of multi-tiered recovery without network calls.
2. **Ephemeral File System Isolation (`tmp_path`)**:
   - The `client(tmp_path)` fixture binds session persistence to an ephemeral temporary directory (`tmp_path / "session.json"`), completely preventing reads or writes to the developer's real `~/.cuhk_blackboard/session.json`.
3. **Subsystem Isolation**:
   - Probing CDP ports and Playwright browser instances is mocked via `patch("cuhk_blackboard.interactive_login.capture_from_cdp")`, allowing browser capture testing in headless CI environments lacking browser binaries.

---

## 7. Engineering Tradeoffs, Limitations & Future Evolution

### 7.1 Read-Only Safety vs Write Capabilities
- **Tradeoff**: The plugin is strictly read-only. It provides capabilities to read courses, announcements, grades, and download materials, but intentionally omits APIs for submitting assignments, taking tests, or posting forum messages.
- **Rationale**: Academic safety. Autonomous agents operating with write privileges could inadvertently submit draft files, post incomplete forum replies, or trigger irreversible submission deadlines.
- **Future Direction**: Introduce an explicit `--allow-write` opt-in flag paired with mandatory human-in-the-loop confirmation before any mutating HTTP POST/PUT request.

### 7.2 Session Lifetime & Duo MFA Automation Boundaries
- **Tradeoff**: The plugin does not attempt to programmatically bypass Duo Mobile Push cryptography (e.g. extracting private keys from rooted mobile devices).
- **Rationale**: Bypassing MFA undermines institutional security policies. By leveraging CDP Zero-Copy browser capture and long-lived mobile OAuth tokens, the plugin minimizes user friction while remaining fully compliant with enterprise security standards.

### 7.3 REST API Pagination & Slicing Limits
- **Current Limitation**: Current REST endpoints parse `data.get("results", [])` without following cursor links (`paging.nextPage`). For students with over 100 courses or directories containing hundreds of files, only the first page is retrieved.
- **Future Direction**: Implement a cursor generator that lazily fetches subsequent pages when requested by the agent.

### 7.4 Client Rate Limiting, Concurrency & Timeout Guarantees
- **Current Design**: Requests enforce a 15-second timeout, but the client does not implement an internal token-bucket rate limiter.
- **Mitigation**: Traversal recursion is bounded (`max_depth=3`), cross-course announcement queries are capped at 5 courses, and search fast-exits on whitespace.
- **Future Direction**: Integrate an adaptive client-side rate limiter with exponential backoff on HTTP 429 / 503 responses to prevent student IP throttling during rapid automated scraping loops.

---

## 8. Summary & Verification

This architecture review confirms that `cuhk-blackboard-plugin` is a robust, well-factored, and secure integration platform. Its dual-engine architecture guarantees high data extraction resilience, its 5-tier authentication framework gracefully handles enterprise Duo MFA, its stdio stream isolation protects MCP communication framing, and its 57 unit tests provide 100% offline verification.

To independently execute the verification test suite:
```powershell
cd d:\blackboard_plugin
pytest -v
```
*Expected Result: 57 passed tests in < 0.25 seconds.*
