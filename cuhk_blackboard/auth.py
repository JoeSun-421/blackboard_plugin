"""Authentication Manager for CUHK Blackboard.

Allows the user or agent to dynamically configure and use different authentication methods:
1. COOKIE: User inputs session cookies (e.g., from browser DevTools).
2. TOKEN: User inputs OAuth Bearer token or Mobile app token.
3. CREDENTIALS: Username + Password (+ Duo 2FA passcode).
4. INTERACTIVE: Interactive guide to help user grab credentials.
5. SAVED_SESSION / ENV: Loads from saved file (~/.cuhk_blackboard/session.json) or env vars.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from .models import AuthConfig, AuthMethod


DEFAULT_HOST = "https://blackboard.cuhk.edu.hk"
DEFAULT_SESSION_DIR = Path.home() / ".cuhk_blackboard"
DEFAULT_SESSION_FILE = DEFAULT_SESSION_DIR / "session.json"


class AuthManager:
    """Manages CUHK Blackboard authentication state, parsing, and persistence."""

    def __init__(self, session_file: Optional[Path] = None, host: str = DEFAULT_HOST):
        self.session_file = Path(session_file) if session_file else DEFAULT_SESSION_FILE
        self.host = host.rstrip("/")
        self._config: Optional[AuthConfig] = None
        # Auto-load existing session or env if available
        self.load_session()

    @property
    def config(self) -> AuthConfig:
        if self._config is None:
            self._config = AuthConfig(method=AuthMethod.COOKIE, host=self.host)
        return self._config

    @property
    def is_configured(self) -> bool:
        """Check if any credentials are provided in current config."""
        cfg = self.config
        if cfg.cookies and ("JSESSIONID" in cfg.cookies or "session_id" in cfg.cookies or len(cfg.cookies) > 0):
            return True
        if cfg.bearer_token:
            return True
        if cfg.username and cfg.password:
            return True
        return False

    def set_cookie_auth(
        self,
        cookie_input: Union[str, Dict[str, str]],
        host: Optional[str] = None,
        save: bool = True,
    ) -> AuthConfig:
        """Configure authentication using session cookies.
        
        Args:
            cookie_input: Cookie string ("JSESSIONID=...; session_id=...") or dict.
            host: Blackboard host (defaults to current host).
            save: Whether to persist session to disk.
        """
        cookies_dict = self.parse_cookie_input(cookie_input)
        if not cookies_dict:
            raise ValueError("No valid cookies found in provided input.")

        target_host = (host or self.host).rstrip("/")
        self._config = AuthConfig(
            method=AuthMethod.COOKIE,
            host=target_host,
            cookies=cookies_dict,
            session_file=str(self.session_file),
        )
        self.host = target_host
        if save:
            self.save_session()
        return self._config

    def set_token_auth(
        self,
        token: str,
        host: Optional[str] = None,
        save: bool = True,
    ) -> AuthConfig:
        """Configure authentication using Bearer / OAuth token.
        
        Args:
            token: Access token string (with or without 'Bearer ').
            host: Blackboard host.
            save: Whether to persist session to disk.
        """
        clean_token = token.strip()
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()

        if not clean_token:
            raise ValueError("Bearer token cannot be empty.")

        target_host = (host or self.host).rstrip("/")
        self._config = AuthConfig(
            method=AuthMethod.TOKEN,
            host=target_host,
            bearer_token=clean_token,
            session_file=str(self.session_file),
        )
        self.host = target_host
        if save:
            self.save_session()
        return self._config

    def set_credentials_auth(
        self,
        username: str,
        password: str,
        duo_passcode: Optional[str] = None,
        host: Optional[str] = None,
        save: bool = False,
    ) -> AuthConfig:
        """Configure authentication using OnePass username/password and optional Duo 2FA code.
        
        Args:
            username: CUHK OnePass student/staff username (e.g., s1155xxxxxx).
            password: CWEM password.
            duo_passcode: 6-digit Duo Mobile passcode if applicable.
            host: Blackboard host.
            save: Whether to save to disk (defaults to False for password safety).
        """
        if not username.strip() or not password.strip():
            raise ValueError("Username and password cannot be empty.")

        target_host = (host or self.host).rstrip("/")
        self._config = AuthConfig(
            method=AuthMethod.CREDENTIALS,
            host=target_host,
            username=username.strip(),
            password=password.strip(),
            duo_passcode=duo_passcode.strip() if duo_passcode else None,
            session_file=str(self.session_file),
        )
        self.host = target_host
        if save:
            self.save_session()
        return self._config

    @staticmethod
    def parse_cookie_input(raw: Union[str, Dict[str, str]]) -> Dict[str, str]:
        """Parses various cookie input formats into a key-value dictionary.
        
        Supports:
        - HTTP Header format (case-insensitive): "Cookie: JSESSIONID=abc; ..." or "cookie: JSESSIONID=abc; ..."
        - cURL format: "-H 'Cookie: ...'", "-b '...'", "--cookie '...'"
        - DevTools Application table copy (tab-separated lines: Name \\t Value \\t Domain ...)
        - Newline-separated pairs: "JSESSIONID=abc\\nsession_id=def"
        - JSON string: '{"JSESSIONID": "abc", "session_id": "def"}'
        - Existing dictionary: {"JSESSIONID": "abc"}
        """
        if isinstance(raw, dict):
            return {k.strip(): str(v).strip() for k, v in raw.items() if k.strip()}

        raw_str = raw.strip()

        # If wrapped in cURL -H 'Cookie: ...'
        m_h = re.search(r"cookie:\s*([^'\"\r\n]+)", raw_str, re.IGNORECASE)
        if m_h:
            raw_str = m_h.group(1).strip()
        else:
            # If wrapped in cURL -b '...' or --cookie '...'
            m_b = re.search(r"(?:-b|--cookie)\s+['\"]?([^'\"\r\n]+)", raw_str, re.IGNORECASE)
            if m_b:
                raw_str = m_b.group(1).strip()

        # If JSON formatted (dict or Cookie-Editor list of cookies)
        if (raw_str.startswith("{") and raw_str.endswith("}")) or (raw_str.startswith("[") and raw_str.endswith("]")):
            try:
                parsed = json.loads(raw_str)
                if isinstance(parsed, dict):
                    return {k.strip(): str(v).strip() for k, v in parsed.items() if k.strip()}
                elif isinstance(parsed, list):
                    res = {}
                    for item in parsed:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("Name") or item.get("key")
                            val = item.get("value") or item.get("Value")
                            if name and val is not None:
                                res[str(name).strip()] = str(val).strip()
                    if res:
                        return res
            except json.JSONDecodeError:
                pass

        cookies: Dict[str, str] = {}
        # Handle newline-separated lines
        lines = [line.strip() for line in re.split(r"[\r\n]+", raw_str) if line.strip()]
        for line in lines:
            # Check for tab-separated table copy from browser DevTools Application/Storage tab
            if "\t" in line:
                parts = [p.strip() for p in line.split("\t") if p.strip()]
                if len(parts) >= 2:
                    k, v = parts[0], parts[1]
                    cookies[k] = v
                    continue

            # Check semicolon-separated parts
            for part in line.split(";"):
                part = part.strip()
                if not part:
                    continue
                # Strip leading "cookie:" if present in fragment
                if part.lower().startswith("cookie:"):
                    part = part[7:].strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    k = k.strip().strip("'\"")
                    v = v.strip().strip("'\"")
                    if k:
                        cookies[k] = v
        return cookies

    def save_session(self, path: Optional[Path] = None) -> Path:
        """Persist current session configuration to disk."""
        target_path = Path(path) if path else self.session_file
        target_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "method": self.config.method.value,
            "host": self.config.host,
            "cookies": self.config.cookies,
            "bearer_token": self.config.bearer_token,
            "username": self.config.username,
            "session_file": str(target_path),
        }
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return target_path

    def load_session(self, path: Optional[Path] = None) -> bool:
        """Load session from session file or environment variables.
        
        Returns True if a session was successfully restored.
        """
        target_path = Path(path) if path else self.session_file

        # 1. First check environment variables
        env_cookie = os.getenv("CUHK_BB_COOKIE")
        env_token = os.getenv("CUHK_BB_TOKEN")
        env_host = os.getenv("CUHK_BB_HOST", self.host)

        if env_cookie:
            self.set_cookie_auth(env_cookie, host=env_host, save=False)
            return True
        elif env_token:
            self.set_token_auth(env_token, host=env_host, save=False)
            return True

        # 2. Then check session file
        if target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                method_val = data.get("method", "cookie")
                method = AuthMethod(method_val) if method_val in [m.value for m in AuthMethod] else AuthMethod.COOKIE
                host = data.get("host", self.host)
                cookies = data.get("cookies", {})
                token = data.get("bearer_token")
                username = data.get("username")

                self._config = AuthConfig(
                    method=method,
                    host=host,
                    cookies=cookies,
                    bearer_token=token,
                    username=username,
                    session_file=str(target_path),
                )
                self.host = host
                return True
            except Exception:
                return False

        return False

    def clear_session(self) -> bool:
        """Clear session configuration and remove stored file."""
        self._config = AuthConfig(method=AuthMethod.COOKIE, host=self.host)
        if self.session_file.exists():
            try:
                self.session_file.unlink()
                return True
            except Exception:
                return False
        return True

    def get_auth_headers(self) -> Dict[str, str]:
        """Construct HTTP headers based on the current authentication config."""
        headers: Dict[str, str] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36 Blackboard/1.0"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,zh-HK;q=0.8,zh-CN;q=0.7",
            "Referer": f"{self.host}/",
            "Origin": self.host,
        }

        cfg = self.config
        if cfg.bearer_token:
            headers["Authorization"] = f"Bearer {cfg.bearer_token}"

        # If cookies are present, format Cookie header and Anti-CSRF token
        if cfg.cookies:
            cookie_parts = [f"{k}={v}" for k, v in cfg.cookies.items()]
            headers["Cookie"] = "; ".join(cookie_parts)
            if "X-Blackboard-SXS" in cfg.cookies:
                headers["X-Blackboard-SXS"] = cfg.cookies["X-Blackboard-SXS"]

        return headers

    @staticmethod
    def get_auth_guide(method: str = "cookie") -> str:
        """Returns step-by-step guidance on how to obtain authentication credentials."""
        method_norm = method.lower().strip()
        if method_norm in ["cookie", "cookies"]:
            return """### 📋 香港中文大学 Blackboard 浏览器 Cookie 获取指南 (推荐 / Recommended)

因为 CUHK Blackboard 开启了 CUHK Single Sign-On (CWEM / OnePass) 与 Duo 2FA 双重身份验证，最稳妥、最便捷的验证方式是直接复用您在浏览器中已通过 Duo 2FA 登录的会话 Cookie。

#### 获取步骤：
1. 打开浏览器（Chrome / Edge / Firefox / Safari）。
2. 访问香港中文大学 Blackboard：`https://blackboard.cuhk.edu.hk`
3. 输入您的 CUHK OnePass (CWEM) 账号密码，并在手机上通过 **Duo Mobile** 确认推送 (Duo Push) 或输入 6 位验证码完成登录。
4. 登录成功进入 Blackboard 首页后，按 **F12** 键（或右键点击页面任意位置选择“检查/Inspect”）。
5. 切换到 **“应用程序” (Application)** 标签页（Firefox 为“存储 / Storage”）。
6. 在左侧面板展开 **“Cookie”**，点击 `https://blackboard.cuhk.edu.hk`。
7. 复制关键 Cookie 的值：
   - `JSESSIONID`
   - `session_id`
   - `X-Blackboard-SXS` (如有)
   - `xythos` (如有)
8. **快捷方式（推荐）**：切换到 **“网络” (Network)** 标签页，按 F5 刷新一次页面，点击第一个请求（如 `portal` 或 `webapps`），在右侧面板的 **Request Headers** 中找到 `Cookie:` 字段，直接将整段字符串复制下来！
9. 调用 Agent 工具：
   `cuhk_bb_configure_auth(method="cookie", value="JSESSIONID=...; session_id=...")`
   即可开始抓取所有课程、作业、课件和成绩！
"""
        elif method_norm in ["token", "bearer"]:
            return """### 🔑 Blackboard REST API Bearer Token / Mobile Token 指南

如果您拥有 Blackboard Mobile App 的 OAuth 授权 Token，或者从 CUHK API Portal 获取了 API 凭证：

1. 提取形如 `eyJhbGciOi...` 的 JWT 访问令牌 (Access Token)。
2. 调用 Agent 工具：
   `cuhk_bb_configure_auth(method="token", value="eyJhbGciOi...")`
3. 插件将在所有 API 请求的 `Authorization: Bearer <token>` 请求头中自动注入该令牌。
"""
        elif method_norm in ["credentials", "password"]:
            return """### 🔐 CUHK OnePass 账号密码认证说明

1. 账号：CUHK OnePass / CWEM ID（例如 `1155xxxxxx` 或 `s1155xxxxxx@link.cuhk.edu.hk`）。
2. 密码：CWEM 登录密码。
3. Duo 2FA 验证码：在 Duo Mobile 手机应用生成的 6 位数字离线验证码。
4. 调用 Agent 工具：
   `cuhk_bb_configure_auth(method="credentials", username="s1155xxxxxx", password="your_password", duo_passcode="123456")`

⚠️ 注意：由于 CUHK 启用了 Duo 动态安全验证策略，直接账号密码模拟登录可能受到 Duo Push 握手限制，建议优先选用 Cookie 方式。
"""
        else:
            return """### 🛠️ 支持的验证方式选项：
- **`cookie`** (推荐): 粘贴浏览器中已登录的 Blackboard Cookie 字符串。
- **`token`**: 传入 Bearer Token / OAuth 访问令牌。
- **`credentials`**: 输入 OnePass 账号、密码以及 Duo 动态验证码。
- **`saved_session`**: 自动从本地 `~/.cuhk_blackboard/session.json` 或环境变量加载已保存的配置。
"""
