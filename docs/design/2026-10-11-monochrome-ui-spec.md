# AI Career OS 黑白灰单色系 UI 设计规范

> 版本：v1.0 · 日期：2026-10-11
> 范围：`apps/web/app/` 全部页面（岗位档案 / 岗位识别 / 简历优化 / 简历工作台 / 模拟面试 / 面试记录库）
> 风格基准：Apple（Human Interface Guidelines 的克制备与留白）+ ChatGPT（中性灰阶 + 圆角 + 轻描边）
> 本文档仅作为设计规范落地依据，不修改代码。

---

## 0. 背景与目标

当前 `apps/web/app/globals.css`（约 1700 行）混杂三套互相冲突的设计系统：

1. **深绿 mission 主题**：`#f6f7f2` 米白底、`#36563d` 深绿主色、`#d6dfd4` 细绿边框、圆角白卡片；
2. **蓝色像素风 workbench**：`--canvas:#f3efe5`、`--primary:#3159b8`、`--pixel-border:#23304a`、2px 硬边框、`border-radius:2px`、`box-shadow:5px 5px 0` 硬阴影；
3. **散落旧样式**：红 `#9d2f24` / 黄 `#785600` / 绿 `#236333` 状态色、软阴影、杂色 chip、蓝色信息态 `#3656a0` 等。

另有 `apps/web/app/resume-studio/studio.css` 独立引入一套绿色 + 蓝色混杂的 Studio 样式。

**目标**：把上述全部视觉替换为一套 Apple / ChatGPT 风格的黑白灰单色系——高级简约、大量留白、统一圆角、克制的灰阶层次；**彻底去除绿色主色、蓝色像素风、彩色状态色**（状态一律用灰阶 + 描边 + 字重区分）。

---

## 1. 设计原则

1. **以灰阶层次传递信息，不用颜色**——所有状态用「填充深浅 + 描边 + 字重」三级区分，颜色只作为最后的、极少的例外。
2. **大量留白，一屏一个核心动作**——页面只突出一个主按钮与一段说明，弱化次要操作。
3. **统一圆角与轻阴影，层级克制**——圆角收敛到固定值，阴影最多一层、极轻，杜绝硬阴影与 2px 像素边框。
4. **排版即界面**——用字号 / 字重 / 行高建立层级，能用字重区分的不用分隔线，能用描边区分的不用色块。
5. **全部收敛到 design token**——任何颜色、圆角、间距只通过 `:root` 变量引用，消灭散落色值。

---

## 2. 配色系统（Design Token）

### 2.1 命名约定

- 前缀语义：`bg`（背景层）、`surface`（面板/卡片层）、`text`（文字层）、`border`（边框/分割线）、`fill`（填充/交互底）、`accent`（极少语义色）。
- 全部 token 定义在 `:root`（亮色）与 `.dark`（暗色，可选启用），组件内**禁止**出现裸色值。
- 灰阶采用「中性灰」（不带色相），保证与任何图片 / PDF 简历预览共存时不脏色。

### 2.2 亮色（Light）Token 表

| Token | 值（HEX） | 用途 |
|---|---|---|
| `--bg` | `#fafafa` | 页面底（替代 `#f6f7f2` / `--canvas:#f3efe5`） |
| `--bg-elevated` | `#f5f5f7` | 面板底 / 次级区域（侧边栏、预览背板、区块底） |
| `--surface` | `#ffffff` | 卡片底 / 表单 / 顶栏 |
| `--surface-muted` | `#f5f5f7` | 次级卡片底 / 内嵌条 / 代码块 |
| `--surface-hover` | `#f0f0f2` | 列表项 / 行 / chip hover 底 |
| `--surface-active` | `#e8e8ed` | 选中底 / 按下底 |
| `--surface-disabled` | `#f5f5f7` | 禁用输入底 |
| `--overlay` | `rgba(0,0,0,0.4)` | 弹窗遮罩（替代 `#111e38b8`） |
| `--text-primary` | `#111111` | 一级文字 / 标题（替代 `#172019` / `--ink`） |
| `--text-secondary` | `#3c3c43` | 二级文字 / 正文强调（替代 `#506054`） |
| `--text-tertiary` | `#6e6e73` | 三级文字 / 元信息（替代 `#5d685f`） |
| `--text-quaternary` | `#8e8e93` | 占位符 / 弱说明 |
| `--text-disabled` | `#c7c7cc` | 禁用文字 |
| `--text-inverse` | `#ffffff` | 实心黑底上的反白文字 |
| `--border-strong` | `#d1d1d6` | 强边框 / 输入框默认描边 |
| `--border-medium` | `#e5e5ea` | 中边框 / 卡片描边 / 分割线（替代 `#d6dfd4`） |
| `--border-weak` | `#f0f0f2` | 弱边框 / 内嵌分割线（替代 `#edf1eb`） |
| `--fill-selected` | `#111111` | 选中填充 / 实心主色（按钮、完成节点、选中 chip） |
| `--fill-selected-hover` | `#2c2c2e` | 主按钮 hover |
| `--fill-selected-active` | `#3c3c43` | 主按钮按下 |
| `--focus-ring` | `#111111` | 键盘 focus 环（2px outline） |
| `--accent-danger` | `#d70015` | 危险红（**唯一例外色**，仅错误/删除/危险按钮） |
| `--accent-danger-soft` | `#fff5f5` | 危险 hover 底 |
| `--accent-attention` | `#b25000` | 注意琥珀（**唯一例外色**，仅「待核对/缺失」点标记） |

### 2.3 暗色（Dark）Token 表（可选启用，挂 `.dark` 于 `<html>`）

| Token | 值（HEX） | 用途 |
|---|---|---|
| `--bg` | `#000000` | 页面底 |
| `--bg-elevated` | `#1c1c1e` | 面板底 |
| `--surface` | `#1c1c1e` | 卡片底 |
| `--surface-muted` | `#2c2c2e` | 次级底 |
| `--surface-hover` | `#2c2c2e` | hover 底 |
| `--surface-active` | `#3a3a3c` | 选中底 |
| `--surface-disabled` | `#1c1c1e` | 禁用底 |
| `--overlay` | `rgba(0,0,0,0.6)` | 遮罩 |
| `--text-primary` | `#f5f5f7` | 一级文字 |
| `--text-secondary` | `#d1d1d6` | 二级文字 |
| `--text-tertiary` | `#8e8e93` | 三级文字 |
| `--text-quaternary` | `#636366` | 占位 |
| `--text-disabled` | `#48484a` | 禁用 |
| `--text-inverse` | `#000000` | 反白 |
| `--border-strong` | `#48484a` | 强边框 |
| `--border-medium` | `#3a3a3c` | 中边框 |
| `--border-weak` | `#2c2c2e` | 弱边框 |
| `--fill-selected` | `#f5f5f7` | 选中填充（暗色下反白） |
| `--fill-selected-hover` | `#ffffff` | 主按钮 hover |
| `--fill-selected-active` | `#d1d1d6` | 按下 |
| `--focus-ring` | `#f5f5f7` | focus 环 |
| `--accent-danger` | `#ff6961` | 危险红 |
| `--accent-danger-soft` | `#2c1415` | 危险 hover 底 |
| `--accent-attention` | `#ffa14a` | 注意琥珀 |

> 暗色下主按钮采用「反白」策略：`--fill-selected` 为白、文字用 `--text-inverse`（黑），与 ChatGPT 一致。落地时主按钮需同时绑定 `--text-inverse`。

### 2.4 语义态在单色系下的表达（关键规则）

**原则上不用红 / 绿 / 黄。** 用「灰阶 + 描边 + 字重」表达，具体映射如下：

| 语义 | 单色表达方式 | 具体色值 / 样式 |
|---|---|---|
| 成功 / 已完成 / 已确认 | 实心黑填充 + 反白文字 + `✓` 图标 | fill `--fill-selected`，text `--text-inverse`，font-weight 700 |
| 信息 / 提示 | 浅灰填充 + 深灰文字 | fill `--surface-muted`，text `--text-secondary` |
| 警告 / 待行动 | 深描边加粗 + 深灰文字（可加 `!` 图标） | border `--fill-selected` 1.5px，text `--text-primary`，font-weight 600 |
| 错误 / 危险 | **保留危险红**（唯一例外） | text / border `--accent-danger`，不加填充底 |
| 锁定 / 禁用 | 浅灰填充 + 中灰文字 + 无描边 | fill `--surface-muted`，text `--text-quaternary` |

**极少量语义色（明确仅在何时用）：**

1. `--accent-danger #d70015`：仅用于 (a) 错误消息文字；(b) 危险按钮 / 删除操作的文字与描边；(c) 「阻塞缺失」事实的圆点标记。**绝不做大面积填充背景**。
2. `--accent-attention #b25000`：仅用于「待核对 / 需要用户行动」的小圆点标记（如事实核对的 `needs_confirmation`）。若团队想彻底去彩，可降级为「1.5px 黑描边 + 空心圆」。

> 迁移要点：现有 `#9d2f24`、`#236333`、`#785600`、`#4f9a61`、`#2f6f62`、`#a66b18` 等彩色状态色**全部删除**，替换为上表灰阶方案。

---

## 3. 字体

沿用当前字体族（`layout.tsx` 已加载 Noto Sans SC 400/500/600/700），不新增字体：

```
font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", -apple-system, system-ui, sans-serif;
```

### 3.1 字号阶（基准 16px = 1rem）

| 阶 | 字号 px / rem | 用途 | 字重 | 行高 | letter-spacing |
|---|---|---|---|---|---|
| display | 40 / 2.5 | 开始页 hero（可选） | 700 | 1.1 | -0.03em |
| h1 | 32 / 2 | 页面主标题 | 700 | 1.2 | -0.02em |
| h2 | 24 / 1.5 | 区块 / 卡片大标题 | 700 | 1.25 | -0.01em |
| h3 | 20 / 1.25 | 卡片标题 | 600 | 1.3 | 0 |
| h4 | 17 / 1.0625 | 小节标题 | 600 | 1.35 | 0 |
| body | 15 / 0.9375 | 正文 | 400 | 1.6 | 0 |
| body-sm | 13 / 0.8125 | 辅助 / 元信息 | 400 | 1.5 | 0 |
| caption | 11 / 0.6875 | 标注 / kicker / 徽章 | 600 | 1.3 | +0.04em |

> 说明：全站正文从 16px 降到 15px，更贴近 Apple / ChatGPT 的密度；`summary` / 说明段落统一用 body 15px。中文小字号（11px）需保证清晰度，仅用于英文 uppercase kicker 与徽章。

### 3.2 字重

- `400` 常规：正文、辅助文字
- `500` 中等：次要强调、链接、chip 文字
- `600` 半粗：卡片标题、按钮文字、状态徽章
- `700` 粗：页面标题、主按钮、已完成/选中态

### 3.3 行高与字距

- 标题行高统一 1.2～1.35，正文 1.6，密集列表 1.4。
- 标题 `letter-spacing: -0.02em`（h1）/ `-0.01em`（h2），正文 0。
- 英文 uppercase kicker（如 `FINAL RESUME`）`letter-spacing: 0.08em`、`font-size: 11px`、`font-weight: 600`、颜色 `--text-tertiary`。

---

## 4. 间距

统一 4px 基准间距 scale：

| Token | 值 | 用途 |
|---|---|---|
| `--space-1` | 4px | 图标与文字最小间隙 |
| `--space-2` | 8px | chip 内、按钮组间隙 |
| `--space-3` | 12px | 表单字段间隙 |
| `--space-4` | 16px | 卡片内 padding 最小档 / 网格间隙 |
| `--space-5` | 24px | 卡片 padding 标准档 / 区块间距 |
| `--space-6` | 32px | 大区块间距 |
| `--space-8` | 48px | 页面段落间距 |
| `--space-12` | 64px | 页面首尾留白 |

### 页面最大内容宽度

| 场景 | 宽度 |
|---|---|
| 全站内容外壳（顶栏 / 布局内衬） | `1200px` |
| 工作流 / 岗位布局（`.workflow-layout` / `.mission-layout`） | `1050px` |
| 表单 / 列表阅读列（`.mission-home-content`） | `720px` |
| 正文编辑列（`.mission-content`） | `840px` |
| 简历工作台三栏（`.rs-workbench`） | `1050px` |

---

## 5. 圆角半径

统一到 5 个固定值：

| Token | 值 | 用途 |
|---|---|---|
| `--radius-xs` | 4px | 小控件（chip 内图标、页眉徽标） |
| `--radius-sm` | 8px | 输入框、小按钮、行内条目 |
| `--radius-md` | 12px | 卡片、主按钮、下拉 |
| `--radius-lg` | 16px | 大卡片、面板、弹窗、画廊 |
| `--radius-pill` | 999px | 徽章、胶囊 chip、圆点 |

> 现有 `border-radius: 2px / 3px`（像素风）与 `0.35rem / 0.45rem / 0.55rem / 0.65rem / 0.8rem / 14px` 等散值**全部废除**，收敛为上表。

---

## 6. 卡片样式

| 属性 | 值 |
|---|---|
| 背景 | `--surface`（#ffffff） |
| 描边 | `1px solid --border-medium`（#e5e5ea） |
| 圆角 | `--radius-md`（12px） |
| 内边距 | `20px`（标准）；紧凑 `16px` |
| 阴影 | 默认无；悬浮层卡片 `0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04)`（仅一层，极轻） |
| hover | 描边加深为 `--border-strong`（#d1d1d6），背景不变 |
| 选中 | 描边 `1.5px solid --fill-selected`（#111111），背景不变（或 `--surface-muted`） |

- **列表卡片**（`.mission-list-card`）：hover 时描边 `--border-strong` + 可选 `--surface-hover` 浅底。
- **次级卡片 / 内嵌条**（`.profile-item` / `.resume-source-item`）：背景 `--surface-muted`，描边 `--border-weak`，圆角 `--radius-sm`（8px）。
- **虚线卡片 / 空状态**（`.mission-empty` / `.step-empty-state`）：`1px dashed --border-strong`，背景 `--surface-muted`，圆角 `--radius-md`。
- **选中卡片**（`.proof-select-card:has(input:checked)` / `.selected`）：描边 `1.5px --fill-selected`，背景 `--surface-muted`，**去掉 5px 硬阴影与彩色底**。

---

## 7. 按钮

统一高度：sm `32px` / md `40px` / lg `48px`（现有 `44px` 统一为 lg 或 md）。

### 7.1 主按钮（`.mission-primary-cta` / `.button-primary` / `.workflow-next` / `.rs-download`）

| 态 | 背景 | 文字 | 描边 | 圆角 |
|---|---|---|---|---|
| 默认 | `--fill-selected` #111111 | `--text-inverse` #ffffff，w600 | 无 | `--radius-md` 12px |
| hover | `--fill-selected-hover` #2c2c2e | 同上 | 无 | 同上 |
| active | `--fill-selected-active` #3c3c43 | 同上 | 无 | 同上 |
| disabled | `--text-disabled` #c7c7cc | #8e8e93 | 无 | 同上 |

高度 `40px`，内边距 `0 16px`，`font-size 15px`。

### 7.2 次按钮（`.button-secondary` / `.workflow-previous` / `.rs-secondary`）

| 态 | 背景 | 文字 | 描边 | 圆角 |
|---|---|---|---|---|
| 默认 | `--surface` #ffffff | `--text-primary` #111111，w600 | `1px --border-strong` #d1d1d6 | `--radius-md` 12px |
| hover | `--surface-hover` #f0f0f2 | 同上 | `--border-strong` | 同上 |
| active | `--surface-active` #e8e8ed | 同上 | `--border-strong` | 同上 |
| disabled | `--surface` | `--text-disabled` #c7c7cc | `--border-weak` #f0f0f2 | 同上 |

### 7.3 文字按钮（`.mission-text-btn` / `.text-button`）

- 背景透明，文字 `--text-primary`（默认）或 `--text-tertiary`（次级），w500，圆角 `--radius-sm` 8px，内边距 `4px 8px`。
- hover：背景 `--surface-hover`；active：`--surface-active`。
- 不再使用「绿色下划线」；链接类文字按钮用文字 `--text-primary` + 下划线仅在 hover 出现。

### 7.4 危险操作（`.delete-button` / `.mission-list-delete`）

| 态 | 背景 | 文字 | 描边 |
|---|---|---|---|
| 默认 | 透明 / `--surface` | `--accent-danger` #d70015，w600 | 无（列表右侧可加 `1px --border-weak` 左边分隔） |
| hover | `--accent-danger-soft` #fff5f5 | `--accent-danger` | 无 |
| disabled | 透明 | `--text-disabled` | 无 |

---

## 8. 表单与输入

| 控件 | 属性 | 值 |
|---|---|---|
| 输入框 / 下拉（input/select） | 背景 `--surface`；描边 `1px --border-strong`；圆角 `--radius-sm` 8px；内边距 `10px 12px`；高度 `40px`；字号 15px | |
| 文本域（textarea） | 同上，`resize: vertical`，行高 1.6 | |
| placeholder | `--text-quaternary` #8e8e93 | |
| hover | 描边 `--fill-selected` #111111 | |
| focus-visible | 描边 `--fill-selected`；`outline: 2px solid --focus-ring`；`outline-offset: 2px` | |
| disabled | 背景 `--surface-disabled` #f5f5f7；文字 `--text-disabled`；描边 `--border-weak` | |

- **单选卡片**（`.proof-select-card`，用于「主简历 / 上传 / 粘贴」选择）：背景 `--surface`，描边 `1px --border-medium`，圆角 `--radius-md`；选中态描边 `1.5px --fill-selected` + 背景 `--surface-muted`。
- **原生 radio/checkbox**：保留默认，仅缩放至 16px 并对齐文本；不引入彩色勾选态。
- 表单字段间距 `--space-3`（12px），label 用 `body-sm 13px`、`--text-secondary`、w600。

---

## 9. 导航与外壳

### 9.1 顶栏（`.workflow-header` / `.rs-topbar` / `.mission-topbar`）

- 高度 `60px`（移动端 `56px`）。
- 背景 `--surface` #ffffff；底部 `1px solid --border-medium`。
- 品牌 `A` 标记（`.workflow-brand-mark`）：`32px × 32px`，背景 `--fill-selected` #111111，文字 `--text-inverse`，圆角 `--radius-sm` 8px（**去掉蓝色像素边框与硬阴影**）。
- 顶栏内链接 / 返回按钮：用次按钮或文字按钮样式，`--text-secondary`。

### 9.2 侧边栏 / 步骤导航（`.workflow-sidebar` / `.mission-tab`）

- 宽度 `200px～230px`。
- 步骤按钮：圆角 `--radius-sm` 8px，内边距 `8px 12px`。
  - 默认：文字 `--text-secondary`，透明底；
  - hover：背景 `--surface-hover`；
  - 当前（current）：背景 `--surface-active` #e8e8ed，文字 `--text-primary` w600；
  - 完成（complete）：文字 `--text-primary` w600 + `✓` 标记（不用绿色）。
- 步骤圆形标记（`.workflow-step-marker`）：`24px` 圆，当前实心黑 `--fill-selected` + 白字；完成空心 + 黑描边 + `✓`；默认空心 + `--border-strong` + `--text-tertiary`。

### 9.3 进度指示（`.mission-progress`，顶部 4 步）

- 节点 `32px` 圆形：当前 = 空心黑描边 `1.5px --fill-selected` + 加粗数字；完成 = 实心黑 `--fill-selected` + `✓`；锁定 = 填充 `--surface-muted` + `--text-quaternary`。
- 连接线：`3px × 高度`，颜色 `--border-strong`（完成段用 `--fill-selected`）。
- **删除像素风硬边框与 `translate` 弹跳 hover**，改为 hover 背景 `--surface-hover`。

### 9.4 面包屑 / 返回

- 返回链接（`.mission-back`）：文字 `--text-secondary`，hover 文字 `--text-primary` + 下划线；前缀 `←`。
- 面包屑分隔符 `/`，当前页 `--text-primary` w600。

---

## 10. 状态徽章 / chip / 标签

单色系区分策略：**三种手段组合**——填充深浅（实心黑 / 空心 / 浅灰）、描边（黑 / 灰 / 虚线）、字重 + 图标。

| 状态 | 背景 | 文字 | 描边 | 字重 | 图标 |
|---|---|---|---|---|---|
| 已完成 / 已确认 | `--fill-selected` #111111 | `--text-inverse` | 无 | 600 | `✓` |
| 进行中 | 透明 / `--surface` | `--text-primary` | `1px --fill-selected` | 600 | `●` |
| 锁定 / 禁用 | `--surface-muted` | `--text-quaternary` | 无 | 400 | — |
| 草稿 / 待处理 | `--surface` | `--text-tertiary` | `1px --border-strong` | 500 | — |
| 已接受（bullet） | `--fill-selected` | `--text-inverse` | 无 | 600 | `✓` |
| 已拒绝（bullet） | `--surface-muted` | `--text-quaternary` | 无 | 400 | `×`（可加删除线） |
| 已编辑（bullet） | `--surface` | `--text-secondary` | `1px --border-strong` | 500 | `✎` |
| 待核对事实 | `--surface` | `--text-primary` | `1.5px --fill-selected` | 600 | `!`（或琥珀点） |
| 阻塞缺失事实 | `--surface` | `--accent-danger` | `1px dashed --accent-danger` | 600 | 红点 |

- 徽章圆角统一 `--radius-pill`（999px），内边距 `2px 8px`，字号 `11px`。
- **chip**（`.mission-chip` / `.status-chip` / `.decision-chip`）：
  - 默认：`--surface` 底 + `1px --border-strong` + `--text-secondary`，圆角 `--radius-pill`（中性 chip）或 `--radius-sm`（决策 chip）；
  - 选中 / active（`.decision-chip.active` / `.mission-company-pills button.active`）：`--fill-selected` 底 + `--text-inverse`（**替换原来的深绿 / 蓝底白字**）；
  - disabled：`--text-disabled`。

> 关键替换点：`.mission-bullet-badge-accepted/rejected/edited`（现为绿/红/蓝三色底）→ 上表灰阶方案；`.rs-fact-badge`（现为绿/黄/红/灰四色）→ 上表「已核对/待核对/缺失/已省略」方案。

---

## 11. 六个主要页面布局示意

### 11.1 岗位档案 `/missions`

```
┌──────────────────────────────────────────────────────────┐
│ [A  AI Career OS]                        60px 顶栏        │
├──────────────────────────────────────────────────────────┤
│                                                          │
│              AI CAREER OS (eyebrow, 11px)                │
│              岗位档案 (h1, 32px)                         │
│        集中管理目标岗位、简历版本与面试记录。(summary)      │
│                                                          │
│      [＋新建岗位]  [面试记录库]  [上传简历]   ← 主按钮40px  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 选择已有档案（可选）        [下拉]   [删除简历]      │  │
│  │ 恢复已有档案 [输入框]  [恢复已有档案]               │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 公司(kicker)        岗位名 (h3)            [状态徽章] │  │
│  │ 资深 / 简历:已选择 · 面试:进行中 · 更新于…  [删除]    │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌─ (重复列表卡片，描边 #e5e5ea，hover 描边加深) ──────┐  │
│  └────────────────────────────────────────────────────┘  │
│          max-width 720px 居中                            │
└──────────────────────────────────────────────────────────┘
```

**布局要点**：单列居中 720px；三个主操作并列但仅「新建岗位」为主按钮；档案表单与岗位列表用卡片分隔；列表项左信息右状态徽章 + 删除，右侧删除用危险红文字按钮。

### 11.2 岗位识别 `/missions/{id}/role`

```
┌──────────────────────────────────────────────────────────┐
│ [← 岗位档案]       公司 · 岗位       [状态徽章]  顶栏      │
├──────────────────────────────────────────────────────────┤
│  ①岗位识别 ──②简历──③面试 (进度指示 4 步，32px 圆点)      │
├──────────────────────────┬───────────────────────────────┤
│                          │                               │
│  (左侧栏，sticky)        │  AI CAREER OS (eyebrow)        │
│  岗位名 h2               │  岗位识别 (h1)                 │
│  元信息                  │  核对识别结果… (summary)        │
│                          │                               │
│  ▸ 岗位识别 (current)    │ ┌─ 岗位已识别 ─────────────┐  │
│  ▸ 简历    (locked)      │ │ 公司/岗位/地点/级别…      │  │
│  ▸ 面试    (locked)      │ │ 原始 JD (可折叠)          │  │
│                          │ └───────────────────────────┘  │
│                          │ ┌─ 需要更正时再编辑 ────────┐  │
│                          │ │ [公司][岗位][地点][级别]   │  │
│                          │ │            [保存岗位]     │  │
│                          │ └───────────────────────────┘  │
│   (200-230px)            │  (编辑列 840px)               │
└──────────────────────────┴───────────────────────────────┘
```

**布局要点**：左步骤导航 200–230px sticky + 右编辑列；进度指示在顶栏下横跨全宽；「已识别结果」与「可编辑表单」两块卡片；断点 58rem 以下隐藏侧栏，改用顶部进度条。

### 11.3 简历优化 `/missions/{id}/resume`

```
┌──────────────────────────────────────────────────────────┐
│ [← 岗位档案]       公司 · 岗位       [状态徽章]  顶栏      │
├──────────────────────────────────────────────────────────┤
│  ①岗位识别 ──②简历(当前)──③面试 (进度指示)               │
├──────────────────────────┬───────────────────────────────┤
│  (步骤导航)              │  简历 (h1)                     │
│                          │  对照原始简历审阅… (summary)    │
│                          │                               │
│                          │ ┌─ 简历来源 ────────────────┐  │
│                          │ │ 单选卡片: 主简历/上传/粘贴 │  │
│                          │ └───────────────────────────┘  │
│                          │ ┌─ 选择经历 ────────────────┐  │
│                          │ │ 经历卡片 + 决策chip:       │  │
│                          │ │ [突出][保留][弱化][不放入] │  │
│                          │ └───────────────────────────┘  │
│                          │ ┌─ 左:原始 ─── 右:岗位定向 ─┐  │
│                          │ │ 双栏对照改写 + 接受/拒绝    │  │
│                          │ └───────────────────────────┘  │
│                          │ [确认简历并导出 PDF] ← 主按钮   │
└──────────────────────────┴───────────────────────────────┘
```

**布局要点**：主列 `840px`；「简历来源」用三张单选卡片（`.proof-select-card`）；「经历排序」用卡片列表 + `decision-chip` 分组（突出/保留/弱化/不放入，选中实心黑）；「原始 vs 岗位定向」双栏（`.resume-optimization-workspace`，约 0.92fr : 1.08fr），断点 900px 单列。

### 11.4 简历工作台 `/missions/{id}/resume/studio`（三栏）

```
┌──────────────────────────────────────────────────────────────┐
│ [A  AI CAREER OS / RESUME STUDIO]   修订版 N · 编辑中 [返回↗] │
├──────────────────────────────────────────────────────────────┤
│  01 内容 ── 02 模板 ── 03 事实核对 ── 04 投递版 (stage 条)     │
├──────────────────────────────────────────────────────────────┤
│ FINAL RESUME (kicker)  把确认过的经历排成可投递简历 (h1)       │
│ [选择模板 b] [撤销] [重做]                        ← 工具栏     │
├──────────────┬──────────────────────┬────────────────────────┤
│ 简历内容      │ 实际页面预览          │ 编辑所选 / 事实与导出     │
│ (outline)    │ (preview, 灰底画布)   │ (inspector)            │
│              │                      │                        │
│ 基本信息      │  ┌──────────────┐   │ [事实徽章] [高风险]      │
│ 姓名/电话/    │  │  A4 页面      │   │ 文字内容 textarea        │
│ 邮箱/地点     │  │  (Typst SVG)  │   │ [保存][放弃]            │
│              │  └──────────────┘   │ 事实状态: 全部/已核对/…   │
│ 经历条目      │  ┌──────────────┐   │ ● 要点1                  │
│ ↑↓ 拖拽排序   │  │  第 2 页      │   │ ● 要点2 …               │
│              │  └──────────────┘   │ 生成投递版                │
│              │                      │ [确认] [下载 PDF ↗]      │
├──────────────┴──────────────────────┴────────────────────────┤
│  (三栏 220px : 1fr : 255-285px，1050px 容器，16px 间隙)        │
└──────────────────────────────────────────────────────────────┘
```

**布局要点**：`grid-template-columns: minmax(220px,245px) minmax(430px,1fr) minmax(255px,285px)`，`gap 16px`；左侧 outline 与右侧 inspector 用卡片（描边中 + 圆角 12px），中列预览画布背景 `--bg-elevated` #f5f5f7（**去掉绿色画布与硬阴影**）；A4 页面白底 + 极轻阴影 `0 1px 3px rgba(0,0,0,0.08)`；断点 1150px 双栏（inspector 下沉为全宽两列），760px 单列 + 移动 tab 切换。

### 11.5 模拟面试 `/missions/{id}/interview`

```
┌──────────────────────────────────────────────────────────┐
│ [← 岗位档案]       公司 · 岗位       [状态徽章]  顶栏      │
├──────────────────────────────────────────────────────────┤
│  ①岗位识别 ──②简历──③面试(当前) (进度指示)                │
├──────────────────────────┬───────────────────────────────┤
│  (步骤导航)              │  模拟面试 (h1)                 │
│                          │  (summary)                     │
│                          │ ┌─ 问题预览 ────────────────┐  │
│                          │ │ [01 主题] 问题 + 追问方向    │  │
│                          │ │ (details 折叠卡片列表)      │  │
│                          │ └───────────────────────────┘  │
│                          │ ┌─ 面试问答 ────────────────┐  │
│                          │ │ 问题 (h3)                  │  │
│                          │ │ [回答 textarea 16rem]      │  │
│                          │ │ [提交回答]                 │  │
│                          │ └───────────────────────────┘  │
│                          │ ┌─ 复盘 / 评分 ─────────────┐  │
│                          │ │ 得分 + 亮点 + 缺口 + 参考答 │  │
│                          │ └───────────────────────────┘  │
└──────────────────────────┴───────────────────────────────┘
```

**布局要点**：主列 `840px`；问题预览用 `details` 折叠卡片（`.interview-preview-card`，描边中 + 圆角 12px，展开态描边加深，**去掉像素风彩色底**）；问答区单题单列，回答文本域全宽 `min-height 16rem`；复盘用双栏卡片（`.debrief-grid` 1.1fr:0.9fr，断点单列）。

### 11.6 面试记录库 `/interview-records`

```
┌──────────────────────────────────────────────────────────┐
│ [A  AI Career OS]                             60px 顶栏   │
├──────────────────────────────────────────────────────────┤
│                                                          │
│              面试记录库 (h1, 32px)                        │
│        按公司归档的真实面试 (summary)                      │
│      [＋新建录入]  [返回岗位准备]   ← 主按钮/次按钮         │
│                                                          │
│      [选择档案 下拉]                                      │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 文件夹(kicker)   公司名 (h3)      N 场 · 最近… [打开] │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌─ (按公司分组卡片，点击进公司文件夹) ─────────────────┐  │
│  └────────────────────────────────────────────────────┘  │
│          max-width 720px 居中                            │
└──────────────────────────────────────────────────────────┘
```

**布局要点**：与岗位档案同构，单列居中 720px；公司分组卡片复用 `.mission-list-card`（左公司/轮次/最近日期，右「打开」徽章）；「新建录入」为主按钮。公司文件夹页、录入页、详情页沿用同一外壳与卡片体系。

---

## 12. 落地映射表（现有 class → 新 token / 样式）

> 策略：在 `:root` 定义 design token，把 `globals.css` 中散落色值全部替换为 `var(--token)`；像素风覆盖块（`globals.css:1493` 起的 `/* AI Career OS: restrained pixel workbench */`）整段删除。

### 12.1 全局与文字

| 现有 class / 选择器 | 现状 | 新样式 |
|---|---|---|
| `:root` | `background:#f6f7f2; color:#172019` + 蓝色 `--canvas/--primary/--pixel-border` | 仅保留 light token（见 §2.2），删蓝绿像素变量 |
| `body` | `background:var(--canvas)` | `background:var(--bg); color:var(--text-primary)` |
| `h1` | 全局 `clamp(2.25rem,7vw,4.5rem)` 巨号 | 收敛为 §3.1 的 h1（32px），去掉全局巨号 |
| `.eyebrow` | 绿 `#43694b` | `--text-tertiary`，11px，uppercase，`letter-spacing .08em` |
| `.summary` | 绿灰 `#5d685f` | `--text-secondary`，body 15px |
| `.section-kicker` | 绿 `#6c7c6e` | `--text-tertiary`，11px w600 |

### 12.2 卡片

| 现有 class | 新样式 |
|---|---|
| `.mission-card` / `.mission-list-card` / `.workflow-content-panel` / `.proof-card` / `.proof-entry-card` / `.role-card` / `.jd-card` | 背景 `--surface`，描边 `1px --border-medium`，圆角 `--radius-md` 12px，去硬阴影 |
| `.mission-list-card:hover` | 描边 `--border-strong` |
| `.mission-list-delete` | 文字 `--accent-danger`，hover `--accent-danger-soft` |
| `.profile-item` / `.resume-source-item` / `.resume-ai-item` | 背景 `--surface-muted`，描边 `--border-weak`，圆角 `--radius-sm` 8px |
| `.mission-empty` / `.step-empty-state` | `1px dashed --border-strong`，`--surface-muted`，`--radius-md` |
| `.resume-final-preview` / `.proof-select-card` | 卡片标准；选中描边 `1.5px --fill-selected`，去彩色底 |

### 12.3 按钮

| 现有 class | 新样式 |
|---|---|
| `.mission-primary-cta` / `.button-primary` / `.workflow-next` / `.rs-download` | 主按钮（§7.1）：黑底白字，圆角 12px，高 40px |
| `.button-secondary` / `.workflow-previous` / `.rs-secondary` | 次按钮（§7.2）：白底黑字 1px 描边 |
| `.mission-text-btn` / `.text-button` | 文字按钮（§7.3），去绿色 |
| `.delete-button` | 危险按钮（§7.4），文字 `--accent-danger` |

### 12.4 表单

| 现有选择器 | 新样式 |
|---|---|
| `.field-label input/textarea/select`、`.mission-form input/textarea/select`、`rs-edit-card textarea` | §8 输入规范；focus 环 `2px --focus-ring` |
| `.proof-select-card` / `.proof-select-card.selected` | 单选卡片规范（§8） |
| `.decision-chip` / `.decision-chip.active` | 默认描边中性；active 实心黑底白字 |

### 12.5 导航与进度

| 现有 class | 新样式 |
|---|---|
| `.workflow-header` / `.rs-topbar` / `.mission-topbar` | 高 60px，白底，`1px --border-medium` 底边 |
| `.workflow-brand-mark` / `.rs-logo` | 黑底白字 32px，圆角 8px，去硬阴影 |
| `.workflow-step-button` / `.mission-tab button` | 步骤项：hover `--surface-hover`；current `--surface-active` |
| `.workflow-step-marker` / `.mission-progress-number` | 圆形：当前实心黑，完成空心黑+✓，默认空心灰 |
| `.mission-progress-node` | 去像素边框与 `translate` 弹跳 |

### 12.6 状态徽章 / chip

| 现有 class | 新样式 |
|---|---|
| `.mission-status-badge` / `.status-chip` / `.mission-confidence` | §10 灰阶徽章（实心黑/描边/浅灰三档） |
| `.profile-status.draft/confirmed` | 草稿=描边灰；确认=实心黑 |
| `.mission-bullet-badge-*`（绿/红/蓝） | §10 已接受/已拒绝/已编辑灰阶方案 |
| `.rs-fact-badge.*` / `.rs-fact-dot.*`（绿/黄/红/灰） | §10 事实状态方案；`needs_confirmation` 可保留琥珀点 `--accent-attention`，`blocked_missing` 用 `--accent-danger` |
| `.mission-chip` / `.mission-company-pills button` | 中性 chip；active 实心黑 |

### 12.7 布局

| 现有 class | 新样式 |
|---|---|
| `.workflow-layout` / `.mission-layout` | 侧栏 200–230px + 主列，容器 1050px |
| `.mission-home-content` | 720px 居中，padding 48px 0 |
| `.resume-optimization-workspace` | 双栏 0.92fr:1.08fr，断点 900px 单列 |
| `.rs-workbench` | 三栏 220/1fr/255–285px，gap 16px |
| `.workflow-content-panel` | 白卡，圆角 16px（`--radius-lg`），去 `0 10px 32px` 软阴影 |

---

## 13. 迁移注意事项

### 13.1 必须全局清理的风险点

1. **硬阴影**：`box-shadow: 5px 5px 0 / 4px 4px 0 / 3px 3px 0`（像素风，`globals.css:1545/1563/1607/1620/1664/1689/1693` 等多处）→ 全部删除，只保留 §6 的极轻单层阴影（可选）。
2. **像素圆角**：`border-radius: 2px / 3px` 及 `--mission-radius: 2px`（`globals.css:1527`）→ 收敛到 §5 的 4/8/12/16px。
3. **蓝色主色**：`--primary:#3159b8`、`--primary-hover:#24489a`、`--primary-soft:#dce6ff`、`--pixel-border:#23304a` 及 `outline: 3px solid #3159b8` → 全部删除，替换为黑/灰 token。
4. **绿色主色**：`#36563d`、`#236333`、`#e2f4e5`、`#d6dfd4`、`#edf1eb` 及 `.mission-shell` 作用域下 `--mission-primary/--mission-accent/...` → 全部删除。
5. **彩色状态色**：`#9d2f24`、`#785600`、`#4f9a61`、`#2f6f62`、`#a66b18`、`#b84444`、`#8a3b3b`、`#0f7a3a`、`#b42318`、`#1d4ed8` 等 → 全部删除，按 §2.4 灰阶替换（危险红仅限错误/删除）。
6. **弹跳动效**：`transform: translate(...)` 配合 `steps()` 的像素按钮动画（`globals.css:1598-1626`）→ 删除，恢复标准 `transition: background-color 120ms`。
7. **焦点环颜色**：绿色 `#8aa78d`、蓝色 `#385cc3`、`#9bb6fa` 等 → 统一 `--focus-ring` 黑 2px。

### 13.2 `studio.css` 处理

`apps/web/app/resume-studio/studio.css` 内所有 `--rs-*` 变量（`#36563d` 绿、`#cfd7e2`、`#edf0f4` 蓝灰混搭）**一并收敛**：

- 建议把 `--rs-bg/--rs-surface/--rs-ink/--rs-primary/--rs-border/...` 全部改为引用全局 token（`--rs-primary` → `--fill-selected`，`--rs-border` → `--border-medium` 等），或删除 `studio.css` 中的颜色声明、仅保留布局规则。
- 关键项：`.rs-logo`（绿底）、`.rs-fact-badge`（四色）、`.rs-hotspot`（绿选中）、`.rs-template-card.active`（绿描边）、`.rs-gallery-backdrop`（`#111e38b8` 蓝遮罩）、`.rs-page`（`#25395b2a` 蓝阴影）→ 全部替换为灰阶。

### 13.3 `tailwind.config.ts` 扩展

当前为 `extend: {}`。建议扩展为与 design token 一致（页面手写 CSS 为主，Tailwind 用于局部）：

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        "bg-elevated": "var(--bg-elevated)",
        surface: "var(--surface)",
        "surface-muted": "var(--surface-muted)",
        "surface-hover": "var(--surface-hover)",
        "surface-active": "var(--surface-active)",
        ink: {
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          tertiary: "var(--text-tertiary)",
          quaternary: "var(--text-quaternary)",
          disabled: "var(--text-disabled)",
          inverse: "var(--text-inverse)",
        },
        border: {
          strong: "var(--border-strong)",
          medium: "var(--border-medium)",
          weak: "var(--border-weak)",
        },
        accent: {
          danger: "var(--accent-danger)",
          attention: "var(--accent-attention)",
        },
      },
      borderRadius: {
        xs: "4px",
        sm: "8px",
        md: "12px",
        lg: "16px",
        pill: "999px",
      },
      fontSize: {
        display: ["2.5rem", { lineHeight: "1.1", letterSpacing: "-0.03em" }],
        h1: ["2rem", { lineHeight: "1.2", letterSpacing: "-0.02em" }],
        h2: ["1.5rem", { lineHeight: "1.25" }],
        h3: ["1.25rem", { lineHeight: "1.3" }],
        body: ["0.9375rem", { lineHeight: "1.6" }],
        "body-sm": ["0.8125rem", { lineHeight: "1.5" }],
        caption: ["0.6875rem", { lineHeight: "1.3", letterSpacing: "0.04em" }],
      },
      spacing: { 1: "4px", 2: "8px", 3: "12px", 4: "16px", 5: "24px", 6: "32px", 8: "48px", 12: "64px" },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04)",
      },
      fontFamily: {
        sans: ['"Noto Sans SC"', '"PingFang SC"', '"Microsoft YaHei"', '"Hiragino Sans GB"', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
```

### 13.4 其它注意

- 保留 `@media (prefers-reduced-motion: reduce)` 的降级规则，但去掉其中的像素 `transform` 清理（不再有弹跳动效）。
- `layout.tsx` 已加载 Noto Sans SC 400/500/600/700，字体无需改动；暗色可后续在 `layout.tsx` 加 `className` 切换（挂 `.dark`）。
- 迁移顺序建议：① `:root` token → ② 删除像素风整段（`globals.css:1493-1733`）→ ③ 逐组件替换 `--mission-*` / 散落色值 → ④ 收敛 `studio.css` → ⑤ 扩展 `tailwind.config.ts` → ⑥ 走查 6 个页面视觉与 `npm run build`。

---

## 附录 A：建议的 `:root` 变量块（可直接粘贴到 globals.css 顶部）

```css
:root {
  color-scheme: light;

  /* 背景层 */
  --bg: #fafafa;
  --bg-elevated: #f5f5f7;
  --surface: #ffffff;
  --surface-muted: #f5f5f7;
  --surface-hover: #f0f0f2;
  --surface-active: #e8e8ed;
  --surface-disabled: #f5f5f7;
  --overlay: rgba(0, 0, 0, 0.4);

  /* 文字 */
  --text-primary: #111111;
  --text-secondary: #3c3c43;
  --text-tertiary: #6e6e73;
  --text-quaternary: #8e8e93;
  --text-disabled: #c7c7cc;
  --text-inverse: #ffffff;

  /* 边框 */
  --border-strong: #d1d1d6;
  --border-medium: #e5e5ea;
  --border-weak: #f0f0f2;

  /* 交互 */
  --fill-selected: #111111;
  --fill-selected-hover: #2c2c2e;
  --fill-selected-active: #3c3c43;
  --focus-ring: #111111;

  /* 极少量语义色（例外） */
  --accent-danger: #d70015;
  --accent-danger-soft: #fff5f5;
  --accent-attention: #b25000;

  /* 圆角 */
  --radius-xs: 4px;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-pill: 999px;

  /* 间距 */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-8: 48px;
  --space-12: 64px;

  background: var(--bg);
  color: var(--text-primary);
  font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", sans-serif;
}

.dark {
  color-scheme: dark;
  --bg: #000000;
  --bg-elevated: #1c1c1e;
  --surface: #1c1c1e;
  --surface-muted: #2c2c2e;
  --surface-hover: #2c2c2e;
  --surface-active: #3a3a3c;
  --surface-disabled: #1c1c1e;
  --overlay: rgba(0, 0, 0, 0.6);
  --text-primary: #f5f5f7;
  --text-secondary: #d1d1d6;
  --text-tertiary: #8e8e93;
  --text-quaternary: #636366;
  --text-disabled: #48484a;
  --text-inverse: #000000;
  --border-strong: #48484a;
  --border-medium: #3a3a3c;
  --border-weak: #2c2c2e;
  --fill-selected: #f5f5f7;
  --fill-selected-hover: #ffffff;
  --fill-selected-active: #d1d1d6;
  --focus-ring: #f5f5f7;
  --accent-danger: #ff6961;
  --accent-danger-soft: #2c1415;
  --accent-attention: #ffa14a;
}
```

---

## 附录 B：迁移对照速查（旧 → 新）

| 旧 | 新 |
|---|---|
| `#f6f7f2` / `#f3efe5`（页面底） | `--bg` `#fafafa` |
| `#36563d` / `#3159b8`（主色） | `--fill-selected` `#111111` |
| `#e2f4e5` / `#dce6ff`（主色浅底） | `--surface-muted` `#f5f5f7` |
| `#d6dfd4` / `#e0e6de`（边框） | `--border-medium` `#e5e5ea` |
| `#edf1eb`（细边框） | `--border-weak` `#f0f0f2` |
| `#172019` / `#172033`（主文字） | `--text-primary` `#111111` |
| `#5d685f` / `#5c6475`（次文字） | `--text-tertiary` `#6e6e73` |
| `#9d2f24`（错误） | `--accent-danger` `#d70015`（仅错误/删除） |
| `#236333`（成功绿） | 实心黑徽章 + `✓` |
| `#785600`（警告黄） | 深描边加粗 / `--accent-attention` |
| `border-radius: 2px/3px` | `--radius-sm` 8px / `--radius-md` 12px |
| `box-shadow: 5px 5px 0` | 删除 / `--box-shadow-card` |
