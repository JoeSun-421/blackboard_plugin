# Reverse Engineering Blackboard Mobile App with REA (Reverse Engineer Anything)

This guide documents how to use the **REA MCP Tools** (`/mcp:rea`) to reverse-engineer the official Blackboard Mobile App (Android APK / iOS IPA) to discover hidden endpoints, internal token parameters, and custom institutional configurations.

---

## 1. Prerequisites & REA Environment

Verify that the REA MCP server is installed and configured:
```powershell
npx rea-agents setup
```

REA provides 207 specialized static and dynamic reverse-engineering tools accessible directly to AI agents via the Model Context Protocol (MCP).

---

## 2. Analyzing Blackboard Android APK with REA

If you obtain the official Blackboard Mobile APK (`Blackboard_Learn.apk` from Google Play or APKPure), you can place it in your workspace and use REA tools:

### Step 2.1: Inspect Package Manifest & Intent Filters
Analyze package details, version, target SDK, and custom deep-link URI schemes:
```python
# Tool: inspect_android_package
args = {
    "package_path": "d:/blackboard_plugin/Blackboard.apk"
}
```
**What to look for**:
- Scheme handlers: `blackboard://`, `bb-learn://` for OAuth redirect callbacks.
- Exported activities: In-app browser / WebView login activity (e.g. `com.blackboard.android.central.login.OAuthLoginActivity`).

### Step 2.2: Decode Resources & Institutional Server Configs
Extract strings, endpoints, and default client IDs:
```python
# Tool: decode_android_resources
args = {
    "package_path": "d:/blackboard_plugin/Blackboard.apk"
}
```
**What to look for**:
- `strings.xml`: Search for `oauth_client_id`, `mobile_learn_prefix`, `developer_portal_url`.
- Central discovery service URLs: e.g. `https://mlcs.medu.com/` (Blackboard Mobile Central Service).

### Step 2.3: Decompile and Search Classes
Search for API client implementations (Retrofit, OkHttp):
```python
# Tool: search_android_classes
args = {
    "package_path": "d:/blackboard_plugin/Blackboard.apk",
    "query": "RestAdapter"  # Or "TokenManager", "LearnClient", "OAuth"
}
```

Inspect specific classes to find exact endpoint signatures:
```python
# Tool: inspect_android_class
args = {
    "package_path": "d:/blackboard_plugin/Blackboard.apk",
    "class_name": "com.blackboard.android.central.api.LearnRestService"
}
```

---

## 3. Blackboard Mobile Network Protocol Analysis

REA also supports analyzing network capture files (PCAP / HAR):
```python
# Tool: inspect_pcap_capture
args = {
    "capture_path": "d:/blackboard_plugin/bb_traffic.pcapng"
}
```

### Key Request Headers Identified from Mobile App:
1. `User-Agent`: `Blackboard/10.x.x (Android 14; Mobile; CUHK)`
2. `X-Blackboard-SXS`: Anti-CSRF / session sync header returned during login.
3. `Authorization`: `Bearer <token>` when using mobile OAuth token.

---

## 4. Mapping Discovered Endpoints to the Plugin

Any endpoints discovered during REA analysis can be added directly into `cuhk_blackboard/client.py`:

| Discovered Endpoint | Purpose | Plugin Implementation |
|---|---|---|
| `/learn/api/public/v1/users/me` | Current user profile | `client.get_current_user()` |
| `/learn/api/public/v1/users/me/courses` | User enrolled courses | `client.list_courses()` |
| `/learn/api/public/v1/courses/{id}/contents` | Course outline & folders | `client.list_course_contents()` |
| `/learn/api/public/v1/courses/{id}/contents/{cid}/attachments` | File attachments | `client.list_attachments()` |
| `/learn/api/public/v1/courses/{id}/gradebook/columns` | Assignments & grades | `client.list_assignments()`, `client.get_grades()` |
| `/learn/api/public/v1/courses/{id}/announcements` | Course announcements | `client.list_announcements()` |

---

## 5. Security & Ethical Boundaries

When using REA with educational platforms:
- **Only scrape your own enrolled courses and personal data.**
- **Do not share your `JSESSIONID` or Bearer tokens.**
- **Honor rate limits:** The plugin includes built-in request timeouts and exponential backoff to avoid putting strain on university infrastructure.
