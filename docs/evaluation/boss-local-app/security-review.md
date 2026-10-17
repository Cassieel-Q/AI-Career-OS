# 本地服务与浏览器扩展安全评审

分支：`feature/boss-local-app` · 评审时间：2026-10-17

## 一、威胁模型

本地跑在 `127.0.0.1` 的服务面临两类特有风险：

1. **任意网页都能向 localhost 发请求**（DNS rebinding、CSRF、`<form>` 简单 POST、
   `<img>` GET）。因此「来源是 localhost」或「Origin 是 localhost」都**不能**作为写权限依据。
2. **多项目共用一台机器**：本机 8000 端口是另一个项目（CityQuest）。
   启停脚本如果按端口粗暴 kill，会误杀别人的服务。

## 二、启停器（M1）的安全约束与验证

| 约束 | 实现 | 验证 |
| --- | --- | --- |
| 只监听回环 | uvicorn `--host 127.0.0.1`；next `-H 127.0.0.1`；浏览器桥本身只绑 `127.0.0.1` | 脚本固定参数，无外部可改入口 |
| 端口归属必须证明 | `Get-NetTCPConnection` 取监听 PID → `Win32_Process.CommandLine` 必须包含本项目路径 | `test-launcher.ps1` 全程核对 8000（CityQuest）PID 不变 |
| 不抢占他人端口 | 候选端口全被占用就报错退出；被占用时顺延（前端 3000→3005，后端 8100→8105，桥 8770→8773） | 同上 |
| 停止只停自己 | 先按状态文件 PID 二次校验命令行，再清扫「命令行带本项目路径」的 api/web/bridge 进程 | 同上 |
| 不省略鉴权 | 后端 CORS 仍限本地前端（并把实际前端端口写入 `FRONTEND_ORIGINS`）；浏览器桥仍要求 Bearer token | 代码固定 |

**没有**为了本地运行而关闭 CORS、关闭 bridge token、或改成 `0.0.0.0`。

## 三、浏览器扩展（M2.3–2.5）

### 权限最小化

`manifest.json` 只申请：`activeTab`、`scripting`、`storage`，
host 权限只有 `http://127.0.0.1:*` 与 `http://localhost:*`。

**没有**申请：`cookies`、`webRequest`、`webRequestBlocking`、`tabs`、`downloads`、
`<all_urls>`、`declarativeNetRequest`、`debugger`。

### 明确不做

- `extract.js` 读取前会克隆节点并删除 `script / style / noscript / input / textarea / select / button`，
  所以**密码框、输入框、Cookie 都不可能被读取**；
- 不模拟点击、不自动提交表单、不自动开聊、不批量群发；
- 不使用隐藏私有接口、不伪装 UA/指纹、不绕过登录或验证码；
- 数据只发往 `127.0.0.1`，没有任何外部上报。

### 本地 API 通信鉴权

1. 令牌落在 `%LOCALAPPDATA%\AICareerOS\extension.token`（**不在** DOM / URL / 静态资源里）；
2. 用户在本地网页「设置 → 浏览器扩展配对」生成 **6 位配对码**（5 分钟有效、单次使用、
   有尝试次数与失败窗口限制），扩展用码换令牌；
3. 写请求必须带 `X-AI-Career-Token`，用 `hmac.compare_digest` 恒定时间比较；
4. `Origin` 只允许扩展来源（`chrome-extension://` / `moz-extension://` / `edge://`）或本地前端，
   其他来源一律 403；
5. 请求体 > 1 MiB → 413；内容里出现 `password / cookie / token / api_key / 验证码` → 422 拒绝保存；
6. 未配对时写接口返回 409 并提示去生成配对码。

### 已验证项（自动化）

后端 `tests/test_manual_import.py`：

- 未配对时写接口 409；
- 配对码 6 位、一次性、错码 401；
- 正确令牌可用；错令牌 401；外来 Origin（`https://evil.example.com`）403；
- 超大请求体 413/422；
- 状态接口只返回令牌**指纹**，不含令牌本身；
- 导入内容含凭据字段 → 422。

浏览器侧 `scripts/e2e-extension-safety.cjs`：

- 页面里的 `input[type=password]`、`document.cookie`、隐藏注入文本**都不会**出现在抽取结果里；
- 非岗位页面返回 `NOT_A_JOB_PAGE`；
- 页面结构变化时降级为整页文本且置信度不为 `HIGH`（不谎报）；
- 另一个端口的**外来网页** `fetch` 本地写接口被拦截（CORS）；
- 本地服务不可用时给出明确错误。

## 四、已知残余风险（如实记录）

| 风险 | 等级 | 说明 |
| --- | --- | --- |
| 本地 API 无账号体系 | 低 | 设计为单用户本地优先模式；任何能在本机发请求的**进程**（非网页）都能调用。网页侧已被 CORS + 自定义头 + 令牌挡住。 |
| 配对令牌明文存文件 | 低 | 位于用户自己的 `%LOCALAPPDATA%`，与数据目录同权限；可通过删除文件 + 重新配对吊销。 |
| `job-import/parse` 接口不需要令牌 | 低 | 它只解析、不写库；且 CORS 限制使外来网页读不到响应。 |
| 扩展在 Edge 的实机加载未验证 | 中 | `DONE_UNVERIFIED`：需要你在 `edge://extensions` 手动加载一次 |

## 五、明确禁止（代码与流程两层）

- 不自动登录任何招聘平台；
- 不读取、不存储 Cookie / 密码 / 验证码 / 聊天记录；
- 不实现无人值守自动开聊、批量群发、自动海投；
- 不把岗位数据上传到任何外部服务器；
- 不删除、不覆盖用户数据集；不合并 main。
