"""
AUTO_SYNC Bridge Server

定位：
    网页大模型负责思考和生成代码。
    本地脚本负责接收、写入、创建目录、删除、备份、提交。

权限模型：
    项目根目录内部：允许完整控制。
    项目根目录外部：绝对禁止。
    默认保护 .git、.env、私钥、证书等敏感路径。

运行：
    python bridge_server.py

默认地址：
    http://127.0.0.1:9999

环境变量：
    AUTO_SYNC_PROJECT_ROOT             项目根目录，默认当前目录
    AUTO_SYNC_HOST                     默认 127.0.0.1
    AUTO_SYNC_PORT                     默认 9999
    AUTO_SYNC_GIT_ENABLED              true/false，默认 false
    AUTO_SYNC_GIT_PUSH                 true/false，默认 false
    AUTO_SYNC_BACKUP_ENABLED           true/false，默认 true
    AUTO_SYNC_LOG_DIR                  默认 .auto_sync_logs
    AUTO_SYNC_ALLOW_PROTECTED_PATHS    true/false，默认 false

说明：
    这个服务只建议在本机 127.0.0.1 使用，不要暴露到公网。
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from flask import Flask, Response, jsonify, request


START_MARK = "###=== AUTO" + "_SYNC ===###"
END_MARK = "###=== END" + "_SYNC ===###"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9999
DEFAULT_LOG_DIR = ".auto_sync_logs"

SUPPORTED_ACTIONS = {"write", "mkdir", "delete"}
SUPPORTED_ACTION_TEXT = "ACTION: write、ACTION: mkdir、ACTION: delete"
FORBIDDEN_ACTION_TEXT = "ACTION: append、ACTION: replace、ACTION: patch、ACTION: update、ACTION: insert"


@dataclass
class BridgeConfig:
    project_root: Path
    host: str
    port: int
    git_enabled: bool
    git_push: bool
    backup_enabled: bool
    allow_protected_paths: bool
    log_dir: Path


@dataclass
class SyncBlock:
    action: str
    file_path: str
    content: str


class SyncError(Exception):
    pass


def load_dotenv_if_exists() -> None:
    env_path = Path(".env")

    if not env_path.exists():
        return

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if not key:
            continue

        if key not in os.environ:
            os.environ[key] = value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_file_text() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def load_config() -> BridgeConfig:
    load_dotenv_if_exists()

    root_raw = os.getenv("AUTO_SYNC_PROJECT_ROOT", "").strip()

    if root_raw:
        root = Path(root_raw).expanduser().resolve()
    else:
        root = Path(".").resolve()

    host = os.getenv("AUTO_SYNC_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST

    try:
        port = int(os.getenv("AUTO_SYNC_PORT", str(DEFAULT_PORT)))
    except ValueError:
        port = DEFAULT_PORT

    log_dir_raw = os.getenv("AUTO_SYNC_LOG_DIR", DEFAULT_LOG_DIR).strip() or DEFAULT_LOG_DIR
    log_dir = (root / log_dir_raw).resolve()

    return BridgeConfig(
        project_root=root,
        host=host,
        port=port,
        git_enabled=env_bool("AUTO_SYNC_GIT_ENABLED", False),
        git_push=env_bool("AUTO_SYNC_GIT_PUSH", False),
        backup_enabled=env_bool("AUTO_SYNC_BACKUP_ENABLED", True),
        allow_protected_paths=env_bool("AUTO_SYNC_ALLOW_PROTECTED_PATHS", False),
        log_dir=log_dir,
    )


CONFIG = load_config()
app = Flask(__name__)


def ensure_runtime_dirs() -> None:
    CONFIG.project_root.mkdir(parents=True, exist_ok=True)
    CONFIG.log_dir.mkdir(parents=True, exist_ok=True)
    (CONFIG.log_dir / "backups").mkdir(parents=True, exist_ok=True)


def write_log(event: dict[str, Any]) -> None:
    ensure_runtime_dirs()

    log_file = CONFIG.log_dir / "sync.log.jsonl"

    payload = {
        "time": now_text(),
        **event,
    }

    with log_file.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_request_text() -> str:
    if request.is_json:
        data = request.get_json(silent=True) or {}

        if isinstance(data, dict):
            for key in ("text", "content", "block", "data"):
                value = data.get(key)

                if isinstance(value, str):
                    return value

        raise SyncError("JSON 请求中没有找到 text/content/block/data 字段。")

    raw = request.get_data(as_text=True)

    if not raw:
        raise SyncError("请求体为空。")

    return raw


def extract_raw_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    search_from = 0

    while True:
        start_index = text.find(START_MARK, search_from)

        if start_index == -1:
            break

        end_index = text.find(END_MARK, start_index)

        if end_index == -1:
            break

        block_end = end_index + len(END_MARK)
        blocks.append(text[start_index:block_end])
        search_from = block_end

    if blocks:
        return blocks

    stripped = text.strip()

    if stripped.startswith("FILE:") or stripped.startswith("ACTION:"):
        return [START_MARK + "\n" + stripped + "\n" + END_MARK]

    raise SyncError("没有找到同步协议块。")


def unsupported_action_message(action: str) -> str:
    return (
        f"不支持的 ACTION：{action}。\n"
        f"当前 AUTO_SYNC 是封闭动作协议，只支持：{SUPPORTED_ACTION_TEXT}。\n"
        f"禁止使用：{FORBIDDEN_ACTION_TEXT}。\n"
        "AUTO_SYNC 不是 patch/append/replace 协议。\n"
        "如果只是追加一小段、替换一小段、修改一行，也必须先读取当前完整文件内容，"
        "然后使用 ACTION: write 输出完整文件。"
    )


def parse_block(raw_block: str) -> SyncBlock:
    inner = raw_block.strip()

    if inner.startswith(START_MARK):
        inner = inner[len(START_MARK):]

    if inner.endswith(END_MARK):
        inner = inner[: -len(END_MARK)]

    inner = inner.strip("\r\n")
    lines = inner.splitlines()

    action = "write"
    file_line_index = -1
    file_path = ""

    for index, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("ACTION:"):
            action_value = stripped.split("ACTION:", 1)[1].strip().lower()

            if action_value:
                action = action_value

            continue

        if stripped.startswith("FILE:"):
            file_line_index = index
            file_path = stripped.split("FILE:", 1)[1].strip()
            break

    if action not in SUPPORTED_ACTIONS:
        raise SyncError(unsupported_action_message(action))

    if file_line_index == -1:
        raise SyncError("协议块中没有找到 FILE: 行。")

    if not file_path:
        raise SyncError("FILE: 后面的路径为空。")

    content_lines = lines[file_line_index + 1:]
    content = "\n".join(content_lines)

    return SyncBlock(action=action, file_path=file_path, content=content)


def is_protected_path(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/").strip().strip("/")
    lower = normalized.lower()
    parts = [part.lower() for part in lower.split("/") if part]
    name = Path(normalized).name.lower()

    if not parts:
        return False

    if parts[0] == ".git":
        return True

    if lower == ".env":
        return True

    if lower.startswith(".env.") and lower != ".env.example":
        return True

    sensitive_names = {
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "known_hosts",
    }

    if name in sensitive_names:
        return True

    sensitive_suffixes = {
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        ".crt",
    }

    for suffix in sensitive_suffixes:
        if name.endswith(suffix):
            return True

    return False


def normalize_relative_path(relative_path: str) -> str:
    raw_path = relative_path.strip().replace("\\", "/")

    if not raw_path:
        raise SyncError("路径为空。")

    if "\x00" in raw_path:
        raise SyncError("路径包含非法空字符。")

    if raw_path.startswith("/") or raw_path.startswith("~"):
        raise SyncError(f"禁止使用绝对路径或用户目录路径：{relative_path}")

    if len(raw_path) >= 2 and raw_path[1] == ":":
        raise SyncError(f"禁止使用 Windows 盘符路径：{relative_path}")

    parts: list[str] = []

    for part in raw_path.split("/"):
        if part in {"", "."}:
            continue

        if part == "..":
            raise SyncError(f"禁止使用上级目录路径：{relative_path}")

        parts.append(part)

    if not parts:
        raise SyncError("路径无效。")

    normalized = "/".join(parts)

    if is_protected_path(normalized) and not CONFIG.allow_protected_paths:
        raise SyncError(
            f"安全拦截：默认禁止操作受保护路径：{relative_path}。"
            "如确实需要，请手动设置 AUTO_SYNC_ALLOW_PROTECTED_PATHS=true。"
        )

    return normalized


def resolve_safe_target(relative_path: str) -> tuple[str, Path]:
    normalized = normalize_relative_path(relative_path)
    target = (CONFIG.project_root / normalized).resolve()

    try:
        target.relative_to(CONFIG.project_root)
    except ValueError as exc:
        raise SyncError(f"目标路径越过项目根目录：{relative_path}") from exc

    return normalized, target


def backup_existing_path(target: Path, relative_path: str) -> Optional[str]:
    if not CONFIG.backup_enabled:
        return None

    if not target.exists():
        return None

    safe_name = relative_path.replace("\\", "/").strip("/").replace("/", "__")
    backup_name = f"{now_file_text()}__{safe_name}"
    backup_path = CONFIG.log_dir / "backups" / backup_name
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    if target.is_dir():
        shutil.copytree(target, backup_path)
    else:
        shutil.copy2(target, backup_path)

    return str(backup_path)


def write_file(block: SyncBlock) -> dict[str, Any]:
    normalized_path, target = resolve_safe_target(block.file_path)

    if target.exists() and target.is_dir():
        raise SyncError(f"写入失败：目标路径是目录，不是文件：{block.file_path}")

    target.parent.mkdir(parents=True, exist_ok=True)

    backup_path = backup_existing_path(target, normalized_path)

    old_content = None

    if target.exists() and target.is_file():
        old_content = target.read_text(encoding="utf-8", errors="replace")

    target.write_text(block.content, encoding="utf-8", newline="\n")

    changed = old_content != block.content

    result = {
        "action": "write",
        "file": normalized_path,
        "target": str(target),
        "changed": changed,
        "backup": backup_path,
        "bytes": len(block.content.encode("utf-8")),
    }

    write_log(
        {
            "type": "write_file",
            "ok": True,
            "file": normalized_path,
            "changed": changed,
            "backup": backup_path,
        }
    )

    return result


def make_directory(block: SyncBlock) -> dict[str, Any]:
    normalized_path, target = resolve_safe_target(block.file_path)

    if target.exists() and target.is_file():
        raise SyncError(f"创建目录失败：目标路径已存在同名文件：{block.file_path}")

    changed = not target.exists()
    target.mkdir(parents=True, exist_ok=True)

    result = {
        "action": "mkdir",
        "file": normalized_path,
        "target": str(target),
        "changed": changed,
    }

    write_log(
        {
            "type": "mkdir",
            "ok": True,
            "file": normalized_path,
            "changed": changed,
        }
    )

    return result


def delete_path(block: SyncBlock) -> dict[str, Any]:
    normalized_path, target = resolve_safe_target(block.file_path)

    if not target.exists():
        result = {
            "action": "delete",
            "file": normalized_path,
            "target": str(target),
            "changed": False,
            "message": "路径不存在，跳过删除。",
        }

        write_log(
            {
                "type": "delete_path",
                "ok": True,
                "file": normalized_path,
                "changed": False,
                "message": "not exists",
            }
        )

        return result

    backup_path = backup_existing_path(target, normalized_path)

    if target.is_dir():
        shutil.rmtree(target)
        deleted_type = "directory"
    else:
        target.unlink()
        deleted_type = "file"

    result = {
        "action": "delete",
        "file": normalized_path,
        "target": str(target),
        "changed": True,
        "deleted_type": deleted_type,
        "backup": backup_path,
    }

    write_log(
        {
            "type": "delete_path",
            "ok": True,
            "file": normalized_path,
            "changed": True,
            "deleted_type": deleted_type,
            "backup": backup_path,
        }
    )

    return result


def apply_block(block: SyncBlock) -> dict[str, Any]:
    if block.action == "delete":
        return delete_path(block)

    if block.action == "mkdir":
        return make_directory(block)

    return write_file(block)


def run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )

    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def git_is_available() -> bool:
    result = run_command(["git", "--version"], CONFIG.project_root)
    return result["returncode"] == 0


def git_commit_and_push(changed_files: list[str]) -> dict[str, Any]:
    if not CONFIG.git_enabled:
        return {
            "enabled": False,
            "message": "Git 自动提交未启用。设置 AUTO_SYNC_GIT_ENABLED=true 后启用。",
        }

    if not git_is_available():
        return {
            "enabled": True,
            "ok": False,
            "message": "系统没有找到 git 命令。",
        }

    git_dir = CONFIG.project_root / ".git"

    if not git_dir.exists():
        return {
            "enabled": True,
            "ok": False,
            "message": "当前项目根目录不是 Git 仓库。",
        }

    commands: list[dict[str, Any]] = []

    for file_path in changed_files:
        commands.append(run_command(["git", "add", "-A", "--", file_path], CONFIG.project_root))

    status_result = run_command(["git", "status", "--porcelain"], CONFIG.project_root)
    commands.append(status_result)

    if not status_result["stdout"].strip():
        return {
            "enabled": True,
            "ok": True,
            "message": "没有检测到需要提交的变更。",
            "commands": commands,
        }

    commit_message = "AUTO_SYNC: update " + ", ".join(changed_files[:3])

    if len(changed_files) > 3:
        commit_message += f" and {len(changed_files) - 3} more"

    commit_result = run_command(["git", "commit", "-m", commit_message], CONFIG.project_root)
    commands.append(commit_result)

    if commit_result["returncode"] != 0:
        return {
            "enabled": True,
            "ok": False,
            "message": "git commit 失败。",
            "commands": commands,
        }

    if CONFIG.git_push:
        push_result = run_command(["git", "push"], CONFIG.project_root)
        commands.append(push_result)

        if push_result["returncode"] != 0:
            return {
                "enabled": True,
                "ok": False,
                "message": "git push 失败。",
                "commands": commands,
            }

    return {
        "enabled": True,
        "ok": True,
        "pushed": CONFIG.git_push,
        "message": "Git 自动提交流程完成。",
        "commands": commands,
    }


@app.after_request
def add_cors_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/", methods=["GET"])
def index() -> Response:
    html = f"""
<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>AUTO_SYNC Bridge Server</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
            max-width: 920px;
            margin: 40px auto;
            line-height: 1.7;
            color: #222;
        }}
        h1 {{
            margin-bottom: 8px;
        }}
        code {{
            background: #f2f2f2;
            padding: 2px 6px;
            border-radius: 5px;
        }}
        .ok {{
            color: #15803d;
            font-weight: 700;
        }}
        .box {{
            border: 1px solid #ddd;
            border-radius: 12px;
            padding: 16px 20px;
            background: #fafafa;
            margin-top: 16px;
        }}
        .warn {{
            color: #b45309;
        }}
    </style>
</head>
<body>
    <h1>AUTO_SYNC Bridge Server</h1>
    <p class="ok">服务正在运行。</p>
    <div class="box">
        <p><b>项目根目录：</b><code>{CONFIG.project_root}</code></p>
        <p><b>权限边界：</b><code>仅允许操作项目根目录内部</code></p>
        <p><b>同步接口：</b><code>POST /sync</code></p>
        <p><b>健康检查：</b><code>GET /health</code></p>
        <p><b>支持动作：</b><code>write / delete / mkdir</code></p>
        <p><b>Git 自动提交：</b><code>{CONFIG.git_enabled}</code></p>
        <p><b>Git 自动推送：</b><code>{CONFIG.git_push}</code></p>
        <p><b>备份：</b><code>{CONFIG.backup_enabled}</code></p>
        <p><b>受保护路径开关：</b><code>{CONFIG.allow_protected_paths}</code></p>
        <p><b>日志目录：</b><code>{CONFIG.log_dir}</code></p>
    </div>
    <p class="warn">提示：本服务只建议在本机 127.0.0.1 使用，不要暴露到公网。</p>
</body>
</html>
"""
    return Response(html, mimetype="text/html; charset=utf-8")


@app.route("/health", methods=["GET"])
def health() -> Response:
    return jsonify(
        {
            "status": "ok",
            "service": "AUTO_SYNC Bridge Server",
            "time": now_text(),
            "project_root": str(CONFIG.project_root),
            "permission_boundary": "project_root_only",
            "git_enabled": CONFIG.git_enabled,
            "git_push": CONFIG.git_push,
            "backup_enabled": CONFIG.backup_enabled,
            "allow_protected_paths": CONFIG.allow_protected_paths,
            "log_dir": str(CONFIG.log_dir),
            "actions": ["write", "delete", "mkdir"],
        }
    )


@app.route("/sync", methods=["OPTIONS"])
def sync_options() -> Response:
    return jsonify({"ok": True})


@app.route("/sync", methods=["POST"])
def sync() -> Response:
    try:
        text = normalize_request_text()
        raw_blocks = extract_raw_blocks(text)
        parsed_blocks = [parse_block(raw_block) for raw_block in raw_blocks]

        results = []
        changed_files = []

        for block in parsed_blocks:
            result = apply_block(block)
            results.append(result)

            if result.get("changed"):
                changed_files.append(result["file"])

        if changed_files:
            git_result = git_commit_and_push(changed_files)
        else:
            git_result = {
                "enabled": CONFIG.git_enabled,
                "message": "文件内容没有变化，跳过 Git 流程。",
            }

        response_payload = {
            "ok": True,
            "message": "AUTO_SYNC 同步完成。",
            "count": len(results),
            "files": results,
            "git": git_result,
        }

        write_log(
            {
                "type": "sync",
                "ok": True,
                "count": len(results),
                "changed_files": changed_files,
                "git": git_result,
            }
        )

        return jsonify(response_payload)

    except Exception as exc:
        error_message = str(exc)

        write_log(
            {
                "type": "sync",
                "ok": False,
                "error": error_message,
            }
        )

        return jsonify(
            {
                "ok": False,
                "message": error_message,
            }
        ), 400


def print_startup_info() -> None:
    print("=" * 72)
    print("AUTO_SYNC Bridge Server 已启动")
    print("-" * 72)
    print(f"服务地址: http://{CONFIG.host}:{CONFIG.port}")
    print(f"同步接口: http://{CONFIG.host}:{CONFIG.port}/sync")
    print(f"健康检查: http://{CONFIG.host}:{CONFIG.port}/health")
    print(f"项目根目录: {CONFIG.project_root}")
    print("权限边界: 仅允许操作项目根目录内部")
    print(f"日志目录: {CONFIG.log_dir}")
    print(f"Git 自动提交: {CONFIG.git_enabled}")
    print(f"Git 自动推送: {CONFIG.git_push}")
    print(f"备份旧内容: {CONFIG.backup_enabled}")
    print(f"允许受保护路径: {CONFIG.allow_protected_paths}")
    print("支持动作: write / delete / mkdir")
    print("=" * 72)


if __name__ == "__main__":
    ensure_runtime_dirs()
    print_startup_info()
    app.run(host=CONFIG.host, port=CONFIG.port, debug=False)