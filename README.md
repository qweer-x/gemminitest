# Chat-to-Codebase

Chat-to-Codebase 是一个轻量级的网页 AI 自动同步桥。

它让你可以在网页 AI 对话中描述需求，由网页 AI 生成代码，再通过本地 Bridge Server 自动写入项目代码库。

核心模式：

    网页大模型负责思考和生成代码
    本地脚本负责接收、写入、删除、备份和提交

它不是本地 AI Agent，也不接 Codex。

它只负责把网页 AI 的代码输出，安全地落地到本地项目中。

---

## 工作流程

    ChatGPT / 网页 AI
            ↓
    输出 AUTO_SYNC 同步块
            ↓
    Tampermonkey 脚本捕捉
            ↓
    发送到 http://127.0.0.1:9999/sync
            ↓
    bridge_server.py 写入本地项目
            ↓
    可选 Git commit / push

---

## 快速开始

### 1. 安装依赖

在项目目录执行：

    pip install -r requirements.txt

### 2. 启动本地接收器

在目标项目根目录运行：

    python bridge_server.py

启动后打开：

    http://127.0.0.1:9999

看到状态页，说明本地接收器已经启动成功。

### 3. 安装 ChatGPT 网页脚本

1. 浏览器安装 Tampermonkey。
2. 新建脚本。
3. 复制 `clients/chatgpt/tampermonkey.user.js` 的内容。
4. 保存并启用。
5. 打开 `chatgpt.com`。
6. 右下角出现 `Chat-to-Codebase` 面板，即表示脚本运行成功。

### 4. 开启一个新的 ChatGPT 对话

复制：

    clients/chatgpt/start_prompt.md

把里面的内容发给 ChatGPT。

之后你就可以自然协作：

    先设计一下，不要写入。

确认方案后再说：

    可以，直接写入项目。

ChatGPT 输出同步块后，网页脚本会自动发送到本地接收器。

---

## 项目结构

    bridge_server.py
    requirements.txt
    .env.example
    .gitignore
    README.md

    clients/
    └─ chatgpt/
       ├─ tampermonkey.user.js
       └─ start_prompt.md

    docs/
    ├─ ai_context.md
    └─ protocol.md

以后要支持其他网页模型，可以继续添加：

    clients/
    ├─ chatgpt/
    ├─ gemini/
    ├─ claude/
    ├─ grok/
    └─ openrouter/

每个模型目录里放自己的网页脚本和启动提示词。

当前主要使用 ChatGPT，其他模型目录只是预留扩展。