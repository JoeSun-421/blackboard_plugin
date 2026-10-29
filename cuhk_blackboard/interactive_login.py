"""Interactive Login and Authentication Helper for CUHK Blackboard.

Allows the user to interactively choose their preferred authentication method,
input their credentials/cookies, and verify connectivity immediately.
"""

from __future__ import annotations

import getpass
import sys
from typing import Optional, Tuple

from .auth import AuthManager
from .client import BlackboardClient
from .models import AuthConfig, AuthMethod, UserProfile


def prompt_user_auth(
    client: Optional[BlackboardClient] = None,
    host: str = "https://blackboard.cuhk.edu.hk",
) -> Tuple[bool, Optional[UserProfile]]:
    """Interactive command-line wizard for configuring CUHK Blackboard authentication."""
    client = client or BlackboardClient(host=host)

    print("\n" + "=" * 60)
    print("🎓 香港中文大学 (CUHK) Blackboard 认证配置向导")
    print("=" * 60)
    print(f"目标系统: {client.host}")
    print("\n请选择您希望使用的认证方式 (Select Authentication Method):")
    print("  [1] 浏览器 Cookie 认证 (推荐 / Recommended for Duo 2FA)")
    print("  [2] Bearer Token / OAuth 访问令牌认证")
    print("  [3] OnePass 账号密码认证 (受 Duo 2FA 策略限制)")
    print("  [4] 本地可视化浏览器辅助登录 (启动 Chromium 登录并自动捕获 Cookie)")
    print("  [5] 查看各认证方式详细提取说明 (Guide)")
    print("  [6] 退出 (Exit)")
    print("-" * 60)

    choice = input("请输入选项编号 [1-6] (默认 1): ").strip() or "1"

    if choice == "1":
        print("\n" + AuthManager.get_auth_guide("cookie"))
        print("-" * 60)
        cookie_str = input("请粘贴您的 Blackboard Cookie 字符串:\n> ").strip()
        if not cookie_str:
            print("❌ 未输入有效 Cookie，取消配置。")
            return False, None

        try:
            client.auth_manager.set_cookie_auth(cookie_str, host=client.host, save=True)
            print("💾 Cookie 已保存至本地会话配置。")
        except Exception as e:
            print(f"❌ 解析 Cookie 失败: {e}")
            return False, None

    elif choice == "2":
        print("\n" + AuthManager.get_auth_guide("token"))
        print("-" * 60)
        token_str = input("请粘贴您的 Bearer Token:\n> ").strip()
        if not token_str:
            print("❌ 未输入有效 Token，取消配置。")
            return False, None

        try:
            client.auth_manager.set_token_auth(token_str, host=client.host, save=True)
            print("💾 Token 已保存至本地会话配置。")
        except Exception as e:
            print(f"❌ 设置 Token 失败: {e}")
            return False, None

    elif choice == "3":
        print("\n" + AuthManager.get_auth_guide("credentials"))
        print("-" * 60)
        username = input("CUHK OnePass / CWEM 账号 (如 1155xxxxxx 或 user@link.cuhk.edu.hk): ").strip()
        password = getpass.getpass("CWEM 登录密码: ").strip()
        duo_code = input("Duo Mobile 6 位离线动态码 (可选，直接回车跳过): ").strip() or None

        if not username or not password:
            print("❌ 账号或密码为空，取消配置。")
            return False, None

        try:
            save_choice = input("是否将账号信息保存至本地? (y/N): ").strip().lower() == "y"
            client.auth_manager.set_credentials_auth(
                username=username,
                password=password,
                duo_passcode=duo_code,
                host=client.host,
                save=save_choice,
            )
        except Exception as e:
            print(f"❌ 配置账号失败: {e}")
            return False, None

    elif choice == "4":
        captured_cookie = launch_browser_login(client.host)
        if not captured_cookie:
            print("❌ 未能通过浏览器获取 Cookie（请确保安装了 playwright: pip install playwright && playwright install）。")
            return False, None
        try:
            client.auth_manager.set_cookie_auth(captured_cookie, host=client.host, save=True)
            print("💾 浏览器 Cookie 提取成功并已保存！")
        except Exception as e:
            print(f"❌ 解析捕获的 Cookie 失败: {e}")
            return False, None

    elif choice == "5":
        print("\n" + AuthManager.get_auth_guide("cookie"))
        print("\n" + AuthManager.get_auth_guide("token"))
        print("\n" + AuthManager.get_auth_guide("credentials"))
        return prompt_user_auth(client=client, host=host)

    elif choice == "6":
        print("已退出。")
        return False, None
    else:
        print("❌ 无效选项。")
        return False, None

    # Verify connection
    print("\n🔍 正在向 CUHK Blackboard 验证身份，请稍候...")
    is_valid, profile_or_err = client.verify_auth()
    if is_valid:
        profile = profile_or_err
        print("\n" + "🎉 认证成功！")
        print(f"  学生姓名: {profile.display_name}")
        print(f"  用户账号: {profile.username}")
        if profile.student_id:
            print(f"  学号: {profile.student_id}")
        if profile.email:
            print(f"  邮箱: {profile.email}")
        print(f"  会话文件: {client.auth_manager.session_file}")
        return True, profile
    else:
        print(f"\n❌ 验证失败: {profile_or_err}")
        print("💡 建议您检查 Cookie 是否过期，并参考上述指南重新获取。")
        return False, None


def capture_from_cdp(cdp_url: str = "http://127.0.0.1:9222") -> Optional[str]:
    """Capture cookies from an existing running browser via Chrome DevTools Protocol."""
    import json
    import urllib.request
    try:
        req = urllib.request.Request(f"{cdp_url}/json/list")
        with urllib.request.urlopen(req, timeout=2) as resp:
            tabs = json.loads(resp.read().decode())
        
        bb_tabs = [t for t in tabs if "blackboard.cuhk.edu.hk" in t.get("url", "")]
        if not bb_tabs:
            return None
        
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_url)
            for context in browser.contexts:
                cookies = context.cookies(["https://blackboard.cuhk.edu.hk"])
                if any(c["name"] == "JSESSIONID" for c in cookies):
                    return "; ".join([f"{c['name']}={c['value']}" for c in cookies if "blackboard" in c.get("domain", "")])
    except Exception:
        pass
    return None


def launch_browser_login(
    host: str = "https://blackboard.cuhk.edu.hk",
    timeout_seconds: int = 120,
) -> Optional[str]:
    """Automated browser launcher using Playwright (Edge/Chrome/Chromium).
    
    Opens browser for user to perform SSO + Duo login, then captures cookies.
    """
    import re
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return None

    # First probe if an existing CDP session is already active (e.g. sidebar browser)
    for port in (9222, 9229, 9333):
        cdp_cookie = capture_from_cdp(f"http://127.0.0.1:{port}")
        if cdp_cookie:
            return cdp_cookie

    print("\n🌐 正在启动本地浏览器以进行 CUHK SSO & Duo 2FA 登录...")
    with sync_playwright() as p:
        browser = None
        for channel in ("msedge", "chrome", None):
            try:
                if channel:
                    browser = p.chromium.launch(channel=channel, headless=False)
                else:
                    browser = p.chromium.launch(headless=False)
                if browser:
                    break
            except Exception:
                continue

        if not browser:
            return None

        context = browser.new_context()
        page = context.new_page()
        page.goto(host)

        print("👉 请在弹出的浏览器窗口中完成 CUHK OnePass 登录及 Duo 2FA 验证...")
        pattern = re.compile(r"blackboard\.cuhk\.edu\.hk/(?:ultra|webapps/(?:portal|blackboard))")
        try:
            page.wait_for_url(pattern, timeout=timeout_seconds * 1000)
            # Give page 3 seconds to finish setting final session cookies
            try:
                page.wait_for_timeout(3000)
            except Exception:
                pass

            # Wait up to 15 seconds for session_id or JSESSIONID to appear
            import time
            end_time = time.time() + 15
            cookies = []
            while time.time() < end_time:
                cookies = context.cookies()
                has_session = any(c.get("name") in ("session_id", "JSESSIONID") for c in cookies if "cuhk.edu.hk" in c.get("domain", ""))
                if has_session:
                    break
                time.sleep(1)

            cookie_str = "; ".join([
                f"{c['name']}={c['value']}" 
                for c in cookies 
                if "blackboard" in c.get("domain", "") or "cuhk.edu.hk" in c.get("domain", "")
            ])
            try:
                browser.close()
            except Exception:
                pass
            return cookie_str
        except Exception:
            try:
                browser.close()
            except Exception:
                pass
            return None
