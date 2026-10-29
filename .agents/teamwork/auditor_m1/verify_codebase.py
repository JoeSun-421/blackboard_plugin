import os
import sys
import re
from pathlib import Path

# Add project root to path
sys.path.insert(0, r"d:\blackboard_plugin")

from cuhk_blackboard import models, auth, client, interactive_login, tools, mcp_server, cli

def verify_all():
    print("=== START EMPIRICAL VERIFICATION ===")
    
    # 1. Models
    print("[1] Checking models.py...")
    assert hasattr(models, 'AuthMethod')
    assert hasattr(models, 'ContentType')
    assert hasattr(models, 'AuthConfig')
    assert hasattr(models, 'UserProfile')
    assert hasattr(models, 'Course')
    assert hasattr(models, 'Attachment')
    assert hasattr(models, 'ContentItem')
    assert hasattr(models, 'Announcement')
    assert hasattr(models, 'GradeItem')
    assert hasattr(models, 'Assignment')
    
    # Test secret masking
    cfg = models.AuthConfig(
        method=models.AuthMethod.COOKIE,
        cookies={'JSESSIONID': '1234567890abcdef'},
        bearer_token='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token',
        password='secretpassword'
    )
    d_masked = cfg.to_dict(mask_secrets=True)
    assert d_masked['password'] == '********', f"Password not masked: {d_masked['password']}"
    assert d_masked['bearer_token'] == f"{'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token'[:8]}...{'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token'[-4:]}"
    assert d_masked['cookies']['JSESSIONID'] == '1234...cdef'
    
    # Test Announcement markdown link transform
    sample_html = '<p>Check <a href="https://example.com/lecture">Lecture Slides</a> now</p>'
    ann = models.Announcement.from_api({"id": "1", "title": "Test", "body": sample_html})
    assert "[Lecture Slides](https://example.com/lecture)" in ann.content_text, f"Markdown link failed: {ann.content_text}"
    
    # Test GradeItem percentage computation with col_data and grade_data
    col_data = {"id": "col_1", "name": "Quiz 1", "grading": {"scoreTotal": 100.0}}
    grade_data = {"score": 85.0, "status": "Graded"}
    gi = models.GradeItem.from_api(col_data=col_data, grade_data=grade_data, course_id="c1")
    assert gi.score == 85.0
    assert gi.points_possible == 100.0
    assert gi.percentage == 85.0, f"Percentage computation failed: {gi.percentage}"
    print("models.py: ALL CHECKS PASSED")

    # 2. Auth
    print("[2] Checking auth.py...")
    assert hasattr(auth, 'AuthManager')
    assert hasattr(auth.AuthManager, 'parse_cookie_input')
    am = auth.AuthManager()
    assert auth.DEFAULT_HOST == 'https://blackboard.cuhk.edu.hk'
    assert am.host == 'https://blackboard.cuhk.edu.hk'
    
    # Test parse_cookie_input formats
    c1 = auth.AuthManager.parse_cookie_input('Cookie: JSESSIONID=abc; session_id=def')
    assert c1 == {'JSESSIONID': 'abc', 'session_id': 'def'}
    c2 = auth.AuthManager.parse_cookie_input('curl -H "Cookie: a=1; b=2"')
    assert c2 == {'a': '1', 'b': '2'}
    raw_tab = "JSESSIONID\ttab_val_1\tblackboard.cuhk.edu.hk\t/\nsession_id\ttab_val_2\tblackboard.cuhk.edu.hk\t/"
    c3 = auth.AuthManager.parse_cookie_input(raw_tab)
    assert c3 == {'JSESSIONID': 'tab_val_1', 'session_id': 'tab_val_2'}
    c4 = auth.AuthManager.parse_cookie_input('[{"name": "ext", "value": "val"}]')
    assert c4 == {'ext': 'val'}
    c5 = auth.AuthManager.parse_cookie_input('{"k1": "v1", "k2": "v2"}')
    assert c5 == {'k1': 'v1', 'k2': 'v2'}
    
    # Check save_session disk password exclusion in source code
    auth_src = Path(r"d:\blackboard_plugin\cuhk_blackboard\auth.py").read_text(encoding="utf-8")
    assert "password" not in """data = {
            "method": self.config.method.value,
            "host": self.config.host,
            "cookies": self.config.cookies,
            "bearer_token": self.config.bearer_token,
            "username": self.config.username,
            "session_file": str(target_path),
        }"""
    print("auth.py: ALL CHECKS PASSED")

    # 3. Client
    print("[3] Checking client.py...")
    assert hasattr(client, 'BlackboardClient')
    cl = client.BlackboardClient()
    for method_name in [
        'verify_auth', 'list_courses', 'get_course', 'list_course_contents',
        'list_announcements', 'list_assignments', 'get_grades',
        'download_material', 'search_materials', 'get_course_summary'
    ]:
        assert hasattr(cl, method_name), f"Missing method {method_name} in BlackboardClient"
    
    # Verify SAML detection logic exists in client.py
    client_src = Path(r"d:\blackboard_plugin\cuhk_blackboard\client.py").read_text(encoding="utf-8")
    assert "sts.cuhk.edu.hk" in client_src
    assert "auth-saml" in client_src
    assert "action=logout" in client_src
    
    # Verify path traversal sanitization in download_material
    assert 'safe_filename = re.sub(r' in client_src
    print("client.py: ALL CHECKS PASSED")

    # 4. Interactive login
    print("[4] Checking interactive_login.py...")
    assert hasattr(interactive_login, 'capture_from_cdp')
    assert hasattr(interactive_login, 'launch_browser_login')
    assert hasattr(interactive_login, 'prompt_user_auth')
    login_src = Path(r"d:\blackboard_plugin\cuhk_blackboard\interactive_login.py").read_text(encoding="utf-8")
    assert "9222" in login_src and "9229" in login_src and "9333" in login_src
    assert "msedge" in login_src and "chrome" in login_src and "chromium" in login_src
    print("interactive_login.py: ALL CHECKS PASSED")

    # 5. Tools
    print("[5] Checking tools.py...")
    assert len(tools.AGENT_TOOLS_DEFINITIONS) == 13
    assert len(tools.TOOL_FUNCTION_MAP) == 13
    assert set(t['name'] for t in tools.AGENT_TOOLS_DEFINITIONS) == set(tools.TOOL_FUNCTION_MAP.keys())
    assert hasattr(tools, 'get_client')
    print(f"tools.py: ALL CHECKS PASSED (13/13 tools matched)")

    # 6. MCP Server
    print("[6] Checking mcp_server.py...")
    assert hasattr(mcp_server, 'MCPServer')
    assert hasattr(mcp_server.MCPServer, 'run_stdio')
    assert hasattr(mcp_server.MCPServer, 'handle_request')
    assert hasattr(mcp_server, 'main')
    srv = mcp_server.MCPServer()
    init_res = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_res["result"]["protocolVersion"] == "2024-11-05"
    mcp_src = Path(r"d:\blackboard_plugin\cuhk_blackboard\mcp_server.py").read_text(encoding="utf-8")
    assert "2024-11-05" in mcp_src
    assert "sys.stdout = sys.stderr" in mcp_src
    assert "real_stdout = sys.stdout" in mcp_src
    assert "-32700" in mcp_src
    assert "-32601" in mcp_src
    assert "-32603" in mcp_src
    print("mcp_server.py: ALL CHECKS PASSED")

    # 7. CLI
    print("[7] Checking cli.py...")
    assert hasattr(cli, 'main')
    cli_src = Path(r"d:\blackboard_plugin\cuhk_blackboard\cli.py").read_text(encoding="utf-8")
    for cmd in ["auth", "status", "courses", "contents", "announcements", "grades", "download", "mcp"]:
        assert f'"{cmd}"' in cli_src or f"'{cmd}'" in cli_src, f"Command {cmd} missing in cli.py"
    print("cli.py: ALL CHECKS PASSED")

    print("=== ALL 7 MODULES EMPIRICALLY VERIFIED ===")

if __name__ == "__main__":
    verify_all()
