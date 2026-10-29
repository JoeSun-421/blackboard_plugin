# Project: cuhk-blackboard-plugin Architecture Review & Interactive Technical Quiz

## Architecture
The `cuhk-blackboard-plugin` project is a modular Python package providing an AI agent plugin and MCP server for CUHK Blackboard Learn (`blackboard.cuhk.edu.hk`).
- **Core Domain & Models** (`cuhk_blackboard/models.py`): Pydantic / dataclass schemas (`AuthConfig`, `UserProfile`, `Course`, `ContentItem`, `GradeItem`, `Announcement`, `Assignment`) with secret masking.
- **Authentication Engine** (`cuhk_blackboard/auth.py`): Multi-tier auth manager supporting 5 routes (CDP zero-copy browser capture, multi-format cookie parser, mobile bearer tokens, CWEM credentials with Duo handling, and session persistence).
- **Core API & Scraper Client** (`cuhk_blackboard/client.py`): Dual-tier query engine with REST endpoints (`/learn/api/public/v1/...`) and BeautifulSoup Web Portal scraping fallback.
- **Interactive Browser & CDP Login** (`cuhk_blackboard/interactive_login.py`): Playwright browser automation and remote debugging probe on ports 9222/9229/9333.
- **Agent Tools Registry** (`cuhk_blackboard/tools.py`): 13 AI agent tools with JSON schema definitions and singleton client lifecycle.
- **MCP Server** (`cuhk_blackboard/mcp_server.py`): Native JSON-RPC 2.0 stdio server (Protocol 2024-11-05) with stdout/stderr stream isolation.
- **CLI & Test Suite** (`cuhk_blackboard/cli.py`, `tests/`): Subcommands and 68 unit tests.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Architecture & Module Layout Review | Complete decomposition of package modules, responsibilities, entry points, and dependencies | M1 | survey (DONE) |
| 2 | 5-Route Authentication Analysis | Detailed breakdown of CDP zero-copy capture, multi-format cookie parsing, OAuth token, CWEM credentials, and session persistence | M1 | survey (DONE) |
| 3 | Security Controls & Hardening Analysis | Analysis of password exclusion from disk, secret masking, ADFS false-positive redirect rejection, MCP stream isolation, and path traversal sanitization | M1 | survey (DONE) |
| 4 | Core API & Dual-Engine Fallback Review | Detailed review of courses, contents, announcements, assignments, grades, search, download, and LLM summary generation | M1 | survey (DONE) |
| 5 | Test Suite & Reliability Analysis | In-depth analysis of the 57 pytest tests, mocking strategy without network reliance, and fixtures | M1 | survey (DONE) |
| 6 | Technical Quiz Design (MCQs) | Design at least 5 deep multiple-choice questions covering architecture, auth, security, dual-engine fallbacks, and tests | M2 | user_req (DONE) |
| 7 | Technical Quiz Design (Analysis Questions) | Design at least 2 comprehensive technical scenario/architectural analysis questions | M2 | user_req (DONE) |
| 8 | Interactive Quiz Engine & Runner | Implement an interactive CLI runner with self-scoring, answer verification, and in-depth technical explanations | M2 | user_req (DONE) |
| 9 | Execution Verification & Scoring Validation | Execute the interactive quiz runner, validate automated scoring and explanations, verify zero regression against existing test suites | M3 | user_req (DONE) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Architecture & Core Mechanisms Review Report | Write comprehensive structured review document `ARCHITECTURE_REVIEW.md` | none | DONE |
| 2 | Interactive Technical Quiz Suite & Runner Engine | Create `quiz/` package containing questions (`quiz_data.json`), interactive CLI & verification runner (`quiz_runner.py`), and documentation | M1 | DONE |
| 3 | Execution, Empirical Verification & Handoff | Execute quiz engine, verify scoring accuracy, run full regression tests, compile final report | M2 | DONE |

## Interface Contracts
### Quiz Engine ↔ User / Agent
- Input: interactive terminal inputs or CLI argument `--auto` / `--test`
- Output: objective numerical scores, detailed rationale, pass/fail evaluation
- Return code: 0 on successful execution

## Code Layout
- Documentation: `d:\blackboard_plugin\ARCHITECTURE_REVIEW.md`
- Quiz Suite & Runner: `d:\blackboard_plugin\quiz\quiz_data.json`, `d:\blackboard_plugin\quiz\quiz_runner.py`, `d:\blackboard_plugin\quiz\__init__.py`
- Test Suite: `d:\blackboard_plugin\tests\test_quiz.py`
- Execution Report: `d:\blackboard_plugin\QUIZ_EXECUTION_REPORT.md`
