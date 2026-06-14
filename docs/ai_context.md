# AI Context

本文档用于让 AI 在新对话、长上下文截断、读取 GitHub 仓库校准时，快速理解 Chat-to-Codebase 当前项目状态。

它不是普通 README，也不是流水账 changelog。只有当改动影响项目目标、技术栈、目录结构、模块职责、协议规则、已完成功能、当前阶段重点或下一步计划时，才需要更新本文档。

README.md 给人快速上手看。docs/ai_context.md 给 AI 对齐项目状态看。

---

## 1. 项目定位

Chat-to-Codebase 是一个轻量级的网页 AI 自动同步桥。

核心模式：

- 网页大模型负责理解需求、规划方案、生成代码。
- 本地 Bridge Server 负责接收同步块、写入文件、创建目录、删除文件或目录、备份旧内容，并可选执行 Git commit / push。

它不是本地 AI Agent，也不接 Codex。当前主要面向 ChatGPT 网页端使用。

---

## 2. 当前稳定基线

当前项目已经形成 v0.1 级别的基础闭环：

1. ChatGPT 网页端输出 AUTO_SYNC 同步块。
2. Tampermonkey 脚本捕捉同步块。
3. 脚本把同步块发送到本地 `http://127.0.0.1:9999/sync`。
4. `bridge_server.py` 解析协议。
5. 本地项目根目录内执行 write / mkdir / delete。
6. 覆盖或删除前根据配置自动备份。
7. 可选执行 Git commit / push。
8. 通过 docs/ai_context.md 支持项目锚点和阶段校准。

---

## 3. 当前技术栈

- 本地服务：Python + Flask
- 网页脚本：Tampermonkey UserScript
- 同步协议：AUTO_SYNC 文本协议
- 配置方式：环境变量 / `.env`
- 版本管理：本地 Git，可选自动 commit / push
- 当前主要客户端：ChatGPT 网页端

---

## 4. 核心工作流

标准工作流：

1. 用户在目标项目根目录启动 `bridge_server.py`。
2. 浏览器安装并启用 `clients/chatgpt/tampermonkey.user.js`。
3. 新 ChatGPT 对话中粘贴 `clients/chatgpt/start_prompt.md`。
4. 用户描述需求。
5. 如果只是讨论、设计、分析，不输出 AUTO_SYNC 块。
6. 用户明确说“写入项目”“直接改进去”“落地”等时，ChatGPT 输出完整同步块。
7. Tampermonkey 捕捉同步块并发送到本地服务。
8. Bridge Server 在项目根目录内执行操作。
9. 用户本地测试后提交并推送。
10. 需要时让 AI 读取 GitHub 仓库做只读阶段校准。

---

## 5. AUTO_SYNC 封闭动作协议

AUTO_SYNC 是封闭动作协议，不是 patch 协议，也不是局部编辑协议。

当前只支持：

- `ACTION: write`
- `ACTION: mkdir`
- `ACTION: delete`

禁止使用：

- `ACTION: append`
- `ACTION: replace`
- `ACTION: patch`
- `ACTION: update`
- `ACTION: insert`

关键规则：

- 不允许自创 ACTION。
- 小范围改动也必须使用 `ACTION: write`。
- 追加一段内容也必须使用 `ACTION: write` 输出完整文件。
- 替换一小节也必须使用 `ACTION: write` 输出完整文件。
- 修改一行也必须使用 `ACTION: write` 输出完整文件。
- 修改已有文件前，AI 必须先读取或拿到当前完整文件内容。
- 如果无法读取当前完整文件内容，应要求用户提供，不要凭印象重写。
- 本地 Bridge Server 遇到不支持的 ACTION 会拒绝执行，并返回可复制给 AI 的错误说明。

这个规则用于防止长对话后 AI 出现协议漂移，误用 append / replace / patch 等不存在的动作。

---

## 6. 关键目录与文件

当前项目结构重点：

- `bridge_server.py`
  - 本地 Flask 接收器。
  - 提供 `/`、`/health`、`/sync`。
  - 负责解析 AUTO_SYNC、路径安全校验、写入、建目录、删除、备份、日志、可选 Git 操作。
  - 遇到不支持的 ACTION 时，会返回明确错误提示，提醒只能使用 write / mkdir / delete。

- `clients/chatgpt/tampermonkey.user.js`
  - ChatGPT 网页端脚本。
  - 捕捉最新助手回复中的 AUTO_SYNC 块。
  - 发送到本地 Bridge Server。
  - 提供右下角状态面板、暂停、重扫、清缓存。

- `clients/chatgpt/start_prompt.md`
  - 给新 ChatGPT 对话使用的启动提示词。
  - 规定协作边界、写入条件、路径权限、封闭动作集合、协议格式、AI Context 维护、阶段校准规则。

- `docs/protocol.md`
  - AUTO_SYNC 协议说明。
  - 说明封闭动作集合、write / mkdir / delete、路径规则、安全限制和输出建议。

- `docs/ai_context.md`
  - 当前文件。
  - 给 AI 读取仓库时对齐项目状态使用。

- `.env.example`
  - 环境变量示例。

- `.gitignore`
  - 忽略本地环境、日志、缓存、构建产物等。

---

## 7. 已完成功能

当前已完成：

- 本地 Bridge Server 启动和状态页。
- `/health` 健康检查。
- `/sync` 同步接口。
- AUTO_SYNC 块解析。
- `ACTION: write` 写入文件。
- `ACTION: mkdir` 创建目录。
- `ACTION: delete` 删除文件或目录。
- 拒绝不支持的 ACTION，并返回清晰错误说明。
- 明确禁止 append / replace / patch / update / insert。
- 项目根目录边界限制。
- 禁止绝对路径、盘符路径、用户目录路径、上级目录路径。
- 默认保护 `.git`、`.env`、私钥、证书等敏感路径。
- 覆盖或删除前自动备份。
- 同步日志写入 `.auto_sync_logs/`。
- 可选 Git 自动提交和推送。
- ChatGPT Tampermonkey 脚本。
- ChatGPT 启动提示词。
- 小白测试项目示例。
- GitHub 仓库锚点规则。
- docs/ai_context.md 自动维护规则。
- 只读阶段校准规则。

---

## 8. 当前协作规则

开发协作遵循：

- 讨论、设计、排查、解释时不输出 AUTO_SYNC 块。
- 用户明确要求落地时才输出 AUTO_SYNC 块。
- 涉及已有文件修改时，必须基于当前文件内容，不凭记忆重写。
- 路径不明确时先问用户，不猜。
- 删除对象不明确时先问用户，不猜。
- 不接触 Token、Cookie、密码、私钥、证书等敏感信息。
- 不操作项目根目录外路径。
- 不使用 append / replace / patch / update / insert 等未支持动作。

---

## 9. AI Context 维护规则

AI 在参与项目开发时，需要判断是否同步更新本文档。

需要更新的情况：

- 项目目标改变。
- 技术栈改变。
- 目录结构改变。
- 核心模块职责改变。
- AUTO_SYNC 协议规则改变。
- 新增或删除重要功能。
- 当前阶段重点改变。
- 下一步计划改变。
- 影响后续 AI 接手理解项目的关键约定改变。

不需要更新的情况：

- 单纯样式微调。
- 文案小改。
- 注释小改。
- 不影响结构和功能的小修复。
- 临时实验性说明。

维护原则：

- 不写流水账。
- 不混入其他业务项目上下文。
- 保持简洁、准确、可交接。
- 修改前应先读取当前内容。
- 如果必须整份重写，应保留项目定位、稳定基线、关键目录、安全规则和下一步计划。
- 更新本文档也必须使用 `ACTION: write` 输出完整文件，不要使用 append / replace。

---

## 10. 只读阶段校准规则

当用户说“阶段校准”“我已经提交了，你看下当前项目进度”“检查一下是否跑偏”等表达时，AI 应进入只读检查模式。

只读检查模式下：

1. 读取用户提供的 GitHub 仓库。
2. 优先查看 README.md、docs/ai_context.md、docs/protocol.md。
3. 判断项目是否偏离目标。
4. 判断项目结构是否混乱。
5. 判断文档和代码是否存在明显不一致。
6. 判断是否存在影响后续开发的实质问题。
7. 不输出 AUTO_SYNC 块。
8. 不默认修改项目。
9. 如果没有实质问题，明确说“当前无需修改”。

校准是判断，不是找事。不要为了显得有用而强行挑问题。

---

## 11. 不要随意改动的地方

以下内容属于当前稳定基础，非必要不要大改：

- `bridge_server.py` 的路径安全模型。
- 只允许项目根目录内部操作的权限边界。
- 默认保护 `.git`、`.env`、私钥、证书等敏感路径。
- AUTO_SYNC 完整开始和结束标记规则。
- 封闭动作集合：只支持 write / mkdir / delete。
- 一个文件或目录操作对应一个同步块的规则。
- 小范围修改也必须整文件 write 的规则。
- 真正写入时使用 Markdown text 代码块包裹同步块的规则。
- README 保持简洁的定位。
- 当前主要面向 ChatGPT 的使用方式。

---

## 12. 下一步计划

近期建议：

1. 持续验证长对话下 AI 是否仍会误用 append / replace。
2. 如果仍有误用，继续强化 start_prompt.md 的前置规则。
3. 保持 README 简洁，只作为人类快速入口。
4. 保持 docs/protocol.md 作为协议说明。
5. 持续维护 docs/ai_context.md，作为 AI 项目锚点。
6. 后续可考虑增强 `bridge_server.py` 的请求体大小限制、CORS 限制和更清晰的错误分类，但当前不是必须项。