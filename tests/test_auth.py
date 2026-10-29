"""Unit tests for AuthManager."""

import json
from pathlib import Path

import pytest
from cuhk_blackboard.auth import AuthManager
from cuhk_blackboard.models import AuthConfig, AuthMethod


def test_parse_cookie_header_string():
    raw = "JSESSIONID=ABCDEF123456; session_id=7890XYZ; X-Blackboard-SXS=token_val"
    cookies = AuthManager.parse_cookie_input(raw)
    assert cookies["JSESSIONID"] == "ABCDEF123456"
    assert cookies["session_id"] == "7890XYZ"
    assert cookies["X-Blackboard-SXS"] == "token_val"


def test_parse_cookie_json_string():
    raw = json.dumps({"JSESSIONID": "json_cookie_123", "session_id": "json_sess_456"})
    cookies = AuthManager.parse_cookie_input(raw)
    assert cookies["JSESSIONID"] == "json_cookie_123"
    assert cookies["session_id"] == "json_sess_456"


def test_parse_cookie_curl_format():
    raw = "-H 'Cookie: JSESSIONID=curl_val_99; session_id=curl_sess_88'"
    cookies = AuthManager.parse_cookie_input(raw)
    assert cookies["JSESSIONID"] == "curl_val_99"
    assert cookies["session_id"] == "curl_sess_88"


def test_parse_cookie_http2_lowercase_and_curl_b():
    raw_h2 = "cookie: JSESSIONID=h2_val; session_id=h2_sess"
    cookies_h2 = AuthManager.parse_cookie_input(raw_h2)
    assert cookies_h2["JSESSIONID"] == "h2_val"
    assert cookies_h2["session_id"] == "h2_sess"

    raw_b = 'curl -b "JSESSIONID=b_val; session_id=b_sess" https://blackboard.cuhk.edu.hk'
    cookies_b = AuthManager.parse_cookie_input(raw_b)
    assert cookies_b["JSESSIONID"] == "b_val"
    assert cookies_b["session_id"] == "b_sess"


def test_parse_cookie_multiline_and_tab_separated():
    # Newline separated
    raw_newlines = "JSESSIONID=nl_val\nsession_id=nl_sess"
    cookies_nl = AuthManager.parse_cookie_input(raw_newlines)
    assert cookies_nl["JSESSIONID"] == "nl_val"
    assert cookies_nl["session_id"] == "nl_sess"

    # Tab separated from browser DevTools Application/Storage cookies table
    raw_tab = "JSESSIONID\ttab_val_1\tblackboard.cuhk.edu.hk\t/\nsession_id\ttab_val_2\tblackboard.cuhk.edu.hk\t/"
    cookies_tab = AuthManager.parse_cookie_input(raw_tab)
    assert cookies_tab["JSESSIONID"] == "tab_val_1"
    assert cookies_tab["session_id"] == "tab_val_2"


def test_parse_cookie_dict_input():
    raw = {"JSESSIONID": "dict_val_1", "custom_cookie": "dict_val_2"}
    cookies = AuthManager.parse_cookie_input(raw)
    assert cookies["JSESSIONID"] == "dict_val_1"
    assert cookies["custom_cookie"] == "dict_val_2"


def test_set_cookie_auth(tmp_path: Path):
    session_file = tmp_path / "test_session.json"
    mgr = AuthManager(session_file=session_file)
    cfg = mgr.set_cookie_auth("JSESSIONID=sess123; session_id=val456", save=True)

    assert cfg.method == AuthMethod.COOKIE
    assert cfg.cookies["JSESSIONID"] == "sess123"
    assert mgr.is_configured is True
    assert session_file.exists()

    # Test restoring
    new_mgr = AuthManager(session_file=session_file)
    assert new_mgr.is_configured is True
    assert new_mgr.config.cookies["session_id"] == "val456"


def test_set_token_auth(tmp_path: Path):
    session_file = tmp_path / "test_session.json"
    mgr = AuthManager(session_file=session_file)
    cfg = mgr.set_token_auth("Bearer test_bearer_token_xyz", save=True)

    assert cfg.method == AuthMethod.TOKEN
    assert cfg.bearer_token == "test_bearer_token_xyz"
    assert mgr.is_configured is True

    headers = mgr.get_auth_headers()
    assert headers["Authorization"] == "Bearer test_bearer_token_xyz"


def test_set_credentials_auth(tmp_path: Path):
    session_file = tmp_path / "test_session.json"
    mgr = AuthManager(session_file=session_file)
    cfg = mgr.set_credentials_auth(
        username="s1155999999",
        password="TestPassword123",
        duo_passcode="654321",
        save=False,
    )
    assert cfg.method == AuthMethod.CREDENTIALS
    assert cfg.username == "s1155999999"
    assert cfg.password == "TestPassword123"
    assert cfg.duo_passcode == "654321"
    assert mgr.is_configured is True


def test_clear_session(tmp_path: Path):
    session_file = tmp_path / "test_session.json"
    mgr = AuthManager(session_file=session_file)
    mgr.set_cookie_auth("JSESSIONID=sess123", save=True)
    assert session_file.exists()

    cleared = mgr.clear_session()
    assert cleared is True
    assert not session_file.exists()
    assert not mgr.is_configured


def test_get_auth_guide():
    guide_cookie = AuthManager.get_auth_guide("cookie")
    assert "Duo" in guide_cookie
    assert "F12" in guide_cookie

    guide_token = AuthManager.get_auth_guide("token")
    assert "Bearer" in guide_token

    guide_creds = AuthManager.get_auth_guide("credentials")
    assert "OnePass" in guide_creds


def test_parse_cookie_json_array_cookie_editor():
    raw_array = json.dumps([
        {"name": "JSESSIONID", "value": "arr_sess_111"},
        {"name": "session_id", "value": "arr_sess_222"},
        {"name": "X-Blackboard-SXS", "value": "sxs_token_333"},
    ])
    cookies = AuthManager.parse_cookie_input(raw_array)
    assert cookies["JSESSIONID"] == "arr_sess_111"
    assert cookies["session_id"] == "arr_sess_222"
    assert cookies["X-Blackboard-SXS"] == "sxs_token_333"

    mgr = AuthManager()
    mgr.set_cookie_auth(cookies, save=False)
    headers = mgr.get_auth_headers()
    assert headers["X-Blackboard-SXS"] == "sxs_token_333"
    assert "JSESSIONID=arr_sess_111" in headers["Cookie"]
