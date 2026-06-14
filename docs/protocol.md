# Chat-to-Codebase 协议说明

Chat-to-Codebase 使用 AUTO_SYNC 文本协议连接网页 AI 与本地 Bridge Server。

目标：

- 让网页 AI 负责思考和生成代码。
- 让本地脚本负责接收、写入、创建目录、删除、备份和提交。
- 避免复制粘贴多个文件时出错。
- 让聊天中的代码生成结果安全落地到本地代码库。

---

## 1. 名称关系

- 项目名：Chat-to-Codebase
- 协议名：AUTO_SYNC
- 本地服务：AUTO_SYNC Bridge Server

项目名负责表达整体工作流：从聊天到代码库。

协议名负责标识网页 AI 输出的同步块。

---

## 2. 封闭动作集合

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

重要规则：

- 不允许自创 ACTION。
- 即使只是追加一小段，也必须使用 `ACTION: write` 输出完整文件。
- 即使只是替换一小段，也必须使用 `ACTION: write` 输出完整文件。
- 即使只是修改一行，也必须使用 `ACTION: write` 输出完整文件。
- 修改已有文件前，AI 必须读取或拿到当前完整文件内容。
- 如果无法读取当前完整文件内容，不要凭印象重写，应先要求用户提供文件内容。

错误示例：

    START_MARK
    ACTION: append
    FILE: README.md
    追加内容
    END_MARK

    START_MARK
    ACTION: replace
    FILE: README.md
    替换内容
    END_MARK

正确做法：

    START_MARK
    ACTION: write
    FILE: README.md
    README.md 的完整新内容
    END_MARK

---

## 3. 权限边界

假设项目根目录是：

    D:/project/test

那么 Chat-to-Codebase 的权限边界是：

    D:/project/test/ 内部：允许控制
    D:/project/test/ 外部：禁止控制

也就是说，FILE 后面的路径必须永远是相对项目根目录的路径。

允许：

    index.html
    src/main.js
    clients/chatgpt/start_prompt.md
    old_folder/

禁止：

    ../other_project/file.js
    D:/project/other_project/file.js
    C:/Users/name/Desktop/file.txt
    /root/file.txt
    ~/file.txt

这些被禁止的路径不是因为路径本身特殊，而是因为它们越过了项目根目录边界。

---

## 4. 受保护路径

默认情况下，以下路径即使位于项目根目录内，也会被保护：

- `.git`
- `.env`
- `.env.*`
- 私钥文件
- 证书文件
- 密钥文件

其中 `.env.example` 允许操作。

如果确实需要解除保护，可以在 `.env` 中设置：

    AUTO_SYNC_ALLOW_PROTECTED_PATHS=true

不建议日常开启。

---

## 5. 基本结构

为了避免本文档被同步器误判，下面使用占位符描述协议。

写入文件的基本结构：

    START_MARK
    ACTION: write
    FILE: path/to/file.ext
    完整文件内容
    END_MARK

实际输出时：

- START_MARK 表示 AUTO_SYNC 开始标记。
- END_MARK 表示 AUTO_SYNC 结束标记。

真正写入时，必须把 START_MARK 和 END_MARK 替换成完整协议标记。

---

## 6. 写入文件

默认动作就是 write，因此 ACTION 可以省略。

省略 ACTION 的写法：

    START_MARK
    FILE: index.html
    完整 HTML 内容
    END_MARK

显式写 ACTION 的写法：

    START_MARK
    ACTION: write
    FILE: index.html
    完整 HTML 内容
    END_MARK

要求：

- FILE 后面必须是相对项目根目录路径。
- 文件内容必须完整。
- 不要写“其余不变”。
- 不要只输出 FILE 行。
- 不要使用 append / replace / patch / update / insert。

---

## 7. 创建目录

创建目录使用 `ACTION: mkdir`。

    START_MARK
    ACTION: mkdir
    FILE: src/components/
    END_MARK

说明：

- 如果目录已经存在，则不会重复创建。
- 如果同名文件已经存在，则会报错。

---

## 8. 删除文件或目录

删除文件使用 `ACTION: delete`。

    START_MARK
    ACTION: delete
    FILE: old_file.py
    END_MARK

删除目录同样使用 `ACTION: delete`。

    START_MARK
    ACTION: delete
    FILE: old_folder/
    END_MARK

说明：

- 删除前会根据配置自动备份。
- 如果路径不存在，则跳过删除并返回提示。
- 删除对象不明确时，AI 应先问用户，不要猜。

---

## 9. 多文件同步

一个文件或目录操作对应一个同步块。

示例：

    START_MARK
    FILE: index.html
    完整内容
    END_MARK

    START_MARK
    FILE: style.css
    完整内容
    END_MARK

    START_MARK
    ACTION: delete
    FILE: old_folder/
    END_MARK

不要把多个 FILE 混在同一个同步块里。

---

## 10. 路径规则

FILE 后面必须是相对项目根目录的路径。

允许：

    index.html
    src/main.js
    clients/chatgpt/tampermonkey.user.js
    docs/ai_context.md

禁止：

    C:/Users/name/project/file.txt
    /root/file.txt
    ../file.txt
    .env
    .git/config

本地接收器会拦截：

- 绝对路径
- Windows 盘符路径
- 上级目录路径
- 用户目录路径
- `.git`
- `.env`
- `.env.*`，但允许 `.env.example`
- SSH 私钥文件
- 证书和密钥文件

---

## 11. 输出建议

网页 AI 输出同步块时，建议把所有同步块包在 Markdown text 代码块里。

原因是 Python、YAML、Markdown 等文件对缩进敏感，直接裸输出可能被网页渲染破坏缩进。

尤其是 Python 文件、Markdown 文件、YAML 文件、JSON 文件，不要裸输出同步块。

---

## 12. 协作规则

如果用户只是讨论、分析、设计，不要输出同步块。

当用户明确表示：

- 写入项目
- 直接改进去
- 落地
- 按这个方案改
- 可以，直接写入项目

才输出同步块。

涉及删除、密钥、自动 push、核心配置时，建议先提醒用户风险。

---

## 13. AI Context 与阶段校准

Chat-to-Codebase 推荐每个项目维护：

    docs/ai_context.md

它用于让 AI 在新对话、长上下文截断、读取 GitHub 仓库校准时快速理解当前项目状态。

当改动影响以下内容时，应同步更新 docs/ai_context.md：

- 项目目标
- 技术栈
- 目录结构
- 核心模块职责
- 协议规则
- 已完成功能
- 当前阶段重点
- 下一步计划

更新 docs/ai_context.md 也必须使用 `ACTION: write` 输出完整文件，不要使用 append / replace。

当用户要求阶段校准时，AI 应只读检查 GitHub 仓库，不默认写入项目。如果没有实质问题，应明确说“当前无需修改”。