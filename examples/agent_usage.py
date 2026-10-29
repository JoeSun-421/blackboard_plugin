"""Example demonstrating how an LLM Agent interacts with the CUHK Blackboard Plugin.

Scenarios demonstrated:
1. Agent checks authentication status.
2. If unauthenticated, agent prompts user for authentication method (e.g. cookie).
3. User supplies cookie, agent configures auth and verifies connection.
4. Agent lists courses, inspects materials, lists announcements, checks grades.
"""

import json
import os
import sys
from pathlib import Path

# Ensure cuhk_blackboard is importable when running script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cuhk_blackboard.tools import (
    cuhk_bb_auth_status,
    cuhk_bb_configure_auth,
    cuhk_bb_get_auth_guide,
    cuhk_bb_get_course_summary,
    cuhk_bb_list_announcements,
    cuhk_bb_list_assignments,
    cuhk_bb_list_courses,
)


def run_agent_demonstration():
    print("=== Step 1: Agent checks authentication status ===")
    status = cuhk_bb_auth_status()
    print("Auth Status:", json.dumps(status, indent=2, ensure_ascii=False))

    if not status.get("authenticated"):
        print("\n=== Step 2: Agent requests user authentication method ===")
        guide = cuhk_bb_get_auth_guide(method="cookie")
        print("Agent Guide message to user:")
        print(guide["instructions"])

        # Simulated user inputting session cookies from browser DevTools:
        simulated_user_cookie = "JSESSIONID=MOCK_SESSION_12345; session_id=MOCK_SESS_67890; X-Blackboard-SXS=token_abc"
        print(f"\nUser inputs cookie: {simulated_user_cookie[:30]}...")

        print("\n=== Step 3: Agent configures authentication ===")
        # Here we configure auth (save=False in demo so we don't overwrite user file)
        cfg_result = cuhk_bb_configure_auth(
            method="cookie",
            value=simulated_user_cookie,
            save=False,
        )
        print("Configuration result:", json.dumps(cfg_result, indent=2, ensure_ascii=False))

    print("\n=== Step 4: Agent scrapes information (when authenticated) ===")
    print("Agent can call:")
    print("- cuhk_bb_list_courses()")
    print("- cuhk_bb_list_announcements(course_id=...)")
    print("- cuhk_bb_list_assignments(course_id=...)")
    print("- cuhk_bb_get_course_summary(course_id=...)")


if __name__ == "__main__":
    run_agent_demonstration()
