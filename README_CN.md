# 香港中文大学 (CUHK) Blackboard 信息抓取 Agent 插件

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io)
[![院校](https://img.shields.io/badge/院校-香港中文大学%20CUHK-purple.svg)](https://blackboard.cuhk.edu.hk)

针对**香港中文大学 (CUHK)** Blackboard Learn 教学平台 (`https://blackboard.cuhk.edu.hk`，同时兼顾深圳校区 `https://bb.cuhk.edu.cn`) 打造的高可用 AI Agent 插件与 [Model Context Protocol (MCP)](https://modelcontextprotocol.io) 服务端。

支持任何现代 AI Agent（Claude Desktop, Cursor, Antigravity, LangGraph, Open-Interpreter 等）直接调用，扒取课程大纲、课件课件（PDF/PPT）、作业截止日期、公告通知、成绩单等核心数据，并**支持用户自主选择并输入验证方式**（完全兼容 CUHK 的 Duo 2FA 双重身份验证机制与 CWEM SSO 单点登录）。

---

## 🔎 CUHK Blackboard 系统架构与认证深度调研

### 1. 认证机制与安全挑战
香港中文大学 Blackboard 系统登录经过两道安全校验：
1. **CUHK OnePass / CWEM SSO 单点登录**：用户通过统一身份认证页面输入学号邮箱 (`s1155xxxxxx@link.cuhk.edu.hk`) 及 OnePass 密码。
2. **Duo 2FA (双因素身份验证)**：系统强制向绑定的手机端 **Duo Mobile** 发送推送通知（Duo Push），或要求输入 6 位离线动态码。

由于 Duo 2FA 包含动态挑战和人机交互，纯无头密码暴力请求极易被拦截或触发风控。

### 2. Blackboard Mobile App 原理与机制
在 Blackboard 官方移动 App 中，当用户选择香港中文大学后：
- App 会触发 **Force-to-Web**（重定向至嵌入式网页）流程；
- 引导学生在 App 内嵌浏览器中完成 CWEM SSO 和 Duo 2FA 授权；
- 验证通过后，Learn 系统颁发长效 Session Cookie（如 `JSESSIONID`, `session_id`, `X-Blackboard-SXS`）以及 OAuth Bearer 令牌；
- 移动端会话有效期最长可维持 **336 小时（约 14 天）** 无需重复输入密码。

### 3. 本插件解决方案：用户自选输入验证方式
针对上述特性，本插件设计了 **6 种灵活的用户自选认证方式**：

| 认证方式 (Method) | 适用场景 | 优势与特点 |
|---|---|---|
| **`browser_capture`** (零复制) | IDE 侧边栏浏览器 / 本地环境 | 侧边栏打开 Blackboard 登录后，Agent 一键全自动捕获 Session，无需任何手动复制粘贴。 |
| **`cookie`** (强烈推荐) | 本地及远程 Agent | 浏览器中登录一次 Duo，复制 Cookie 粘贴即可。极度稳定、无需暴露密码、免除 Duo 握手阻碍。 |
| **`token`** | 移动端抓包 / API 用户 | 直接传入 Bearer Access Token，原生兼容 REST 接口。 |
| **`credentials`** | 命令行自动化脚本 | 输入 OnePass 账号 + 密码 + Duo 动态验证码。 |
| **`interactive`** | 本地终端交互 / 桌面 | 交互式命令行引导或 Playwright 弹出窗口完成登录并自动提取。 |
| **`saved_session`** | 持久化使用 | 自动从 `~/.cuhk_blackboard/session.json` 或环境变量加载已保存凭据。 |

---

## 🚀 快速上手

### 安装

```bash
cd d:/blackboard_plugin
pip install -e .
```

### 1. 交互式认证配置向导

在终端运行：
```bash
python -m cuhk_blackboard.cli auth
```
根据提示输入数字，可粘贴浏览器 Cookie 或输入 Token。

### 2. 检查会话状态

```bash
python -m cuhk_blackboard.cli status
```

---

## 🤖 接入 AI Agent (MCP 协议)

在 Claude Desktop 或 Cursor 的 MCP 配置文件（如 `claude_desktop_config.json`）中添加：

```json
{
  "mcpServers": {
    "cuhk-blackboard": {
      "command": "python",
      "args": ["-m", "cuhk_blackboard.mcp_server"],
      "cwd": "d:/blackboard_plugin",
      "env": {
        "CUHK_BB_HOST": "https://blackboard.cuhk.edu.hk"
      }
    }
  }
}
```

配置后，Agent 将自动拥有访问 Blackboard 的所有工具！

---

## 🛠️ Agent 工具完整列表

| 工具名称 | 参数 | 说明 |
|---|---|---|
| `cuhk_bb_configure_auth` | `method`, `value`, `username`, `password`, `duo_passcode`, `host`, `save` | 动态设置或更新用户的认证方式。 |
| `cuhk_bb_auth_status` | *(无)* | 向 Blackboard 校验当前凭证有效性并返回学生身份信息。 |
| `cuhk_bb_get_auth_guide` | `method` (`cookie`, `token`, `credentials`, `all`) | 获取对应认证方式的详细图文操作指南。 |
| `cuhk_bb_list_courses` | `include_hidden` | 获取当前学期所有已选修课程（课程ID、代码、名称、学期、教师）。 |
| `cuhk_bb_get_course_details` | `course_id` | 获取指定课程详细属性。 |
| `cuhk_bb_list_course_contents`| `course_id`, `content_id`, `recursive`, `max_depth` | 遍历课程各章节、文件夹、讲义 Slides、大纲及文件。 |
| `cuhk_bb_list_announcements` | `course_id`, `limit` | 抓取课程公告列表（已清洗 HTML，转为纯文本/Markdown）。 |
| `cuhk_bb_list_assignments` | `course_id`, `upcoming_only` | 列出待交作业、Deadline 截止日期及满分值。 |
| `cuhk_bb_get_grades` | `course_id` | 查询课程 Gradebook 成绩表、各项得分与教师评语。 |
| `cuhk_bb_download_material` | `course_id`, `content_id`, `attachment_id`, `target_dir` | 批量或单项下载附件文件到本地。 |
| `cuhk_bb_search_materials` | `query`, `course_id` | 在课程标题、课件和公告中进行关键词全文检索。 |
| `cuhk_bb_get_course_summary` | `course_id` | 生成专为大模型上下文优化的课程摘要（包含最新公告+近期DDL+成绩一览）。 |

---

## 📋 浏览器 Cookie 获取详细教程（推荐）

1. 打开 Chrome、Edge 或 Firefox 浏览器；
2. 访问香港中文大学 Blackboard 首页：`https://blackboard.cuhk.edu.hk`；
3. 输入您的 OnePass (CWEM) 账号密码，并在手机上通过 **Duo Mobile** 确认推送（Duo Push）；
4. 进入系统首页后，按 **F12** 键打开开发者工具；
5. 点击上方 **“网络” (Network)** 标签页，按 **F5** 刷新一次页面；
6. 在请求列表中点击最上面的请求（如 `portal` 或 `tabAction`）；
7. 在右侧面板的 **Request Headers** 中找到 `Cookie:` 字段；
8. 复制整段 Cookie 文本（或包含 `JSESSIONID` 与 `session_id` 的部分）；
9. 直接告诉您的 Agent：
   > *"帮我配置 Blackboard 认证，Cookie 是：`JSESSIONID=...; session_id=...`"*
   
   插件将自动验证会话并保存，之后即可随时让 Agent 整理复习资料与待办事项！

---

## 💻 命令行常用操作示例

```bash
# 查看所有已选课程
python -m cuhk_blackboard.cli courses

# 递归列出某门课程的全部课件
python -m cuhk_blackboard.cli contents --course _12345_1 --recursive

# 查看最新课程公告
python -m cuhk_blackboard.cli announcements --course _12345_1

# 查看该课程各项成绩得分
python -m cuhk_blackboard.cli grades --course _12345_1

# 下载课件附件
python -m cuhk_blackboard.cli download --course _12345_1 --content _cnt_01 --attachment _att_01 --dir ./my_notes
```

---

## 🔒 隐私与安全性

1. **本地存储**：认证配置文件仅保存在当前系统的用户主目录下 (`~/.cuhk_blackboard/session.json`)，不上传任何第三方服务器。
2. **敏感信息脱敏**：密码与令牌在打印和日志输出中自动执行掩码脱敏（`********`）。
3. **只读保护**：默认所有抓取操作均为只读，避免意外修改学生提交状态。
4. **快速清除**：随时可通过 `client.auth_manager.clear_session()` 一键销毁本地保存的凭据。
