# AI Career OS · 岗位导入助手（Manifest V3）

在 Edge / Chrome 里浏览 BOSS 直聘职位详情页时，点击扩展图标即可把**页面上已经显示的岗位**导入本机运行的 AI Career OS。

## 权限（最小化）

| 权限 | 用途 |
| --- | --- |
| `activeTab` | 只有**你点击扩展图标之后**才临时获得当前标签页的读取能力 |
| `scripting` | 注入 `extract.js` 读取可见文本 |
| `storage` | 保存配对令牌与本机 API 地址 |
| `host_permissions: http://127.0.0.1:*`, `http://localhost:*` | 只与本机 AI Career OS 通信 |

**没有**请求 `cookies`、`webRequest`、`tabs`、`downloads`、`<all_urls>`，也没有任何后台常驻抓取。

## 明确不做的事

- 不读取 Cookie、账号密码、验证码、聊天记录；
- 不模拟点击、不自动提交表单、不自动开聊、不批量群发；
- 不使用隐藏私有接口、不伪装指纹、不绕过登录或反自动化措施；
- 不把岗位数据上传到任何外部服务器（只发往 `127.0.0.1`）；
- 页面结构变化时不会硬填字段：选择器命中不了就降级为整页可见文本并把置信度标成 `LOW`，
  读不到就提示「复制原文后在 AI Career OS 里粘贴导入」，绝不显示虚假成功。

## 安装（开发者模式 · 无需上架）

1. 双击桌面上的 **AI Career OS** 图标启动本地服务；
2. 打开 `edge://extensions`（Chrome 为 `chrome://extensions`），打开「开发人员模式」；
3. 点「加载解压缩的扩展」，选择本目录 `apps/extension`；
4. 在 AI Career OS → **设置 → 浏览器扩展配对** 点「生成配对码」；
5. 点击扩展图标 → 填入 6 位配对码 → 「配对」。

## 使用

1. 在 Edge 打开一个 BOSS 职位详情页；
2. 点击扩展图标 → 「读取当前岗位」；
3. 核对（可修改）公司 / 岗位 / 薪资 / 地点 / 学历 / 经验 / 工作类型 / 原始链接 / JD；
4. 「预览并导入 AI Career OS」；
5. 到 AI Career OS 的岗位库打开该岗位，继续匹配分析 → 简历 → 话术 → 投递。

## 本机服务未启动时

扩展会明确提示「连不上本机 AI Career OS（http://127.0.0.1:8100）」，不会静默失败。
此时可以用「打开 AI Career OS」按钮，或改用网页端的复制粘贴导入。

## 文件

- `manifest.json` — MV3 清单
- `extract.js` — 页面可见文本抽取（选择器优先，失败降级整页文本）
- `background.js` — 注入 + 本地 API 通信（写请求带配对令牌）
- `popup.html` / `popup.js` / `popup.css` — 弹窗界面
