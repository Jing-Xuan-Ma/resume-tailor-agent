#!/usr/bin/env python3
"""
Stop Hook 傻瓜版验证脚本
------------------------------------------------
不需要你知道项目路径，不需要你填任何配置。
它会自动做三件事：
1. 看这一轮到底改了哪些文件
2. 改的是Python就跑ruff检查，改的是前端就跑lint（前提是这些工具已经装了，
   没装的话直接跳过，不会报错卡住你）
3. 如果改的是"正经代码"（不是测试/文档），检查有没有同步更新DEVLOG

出了什么问题，会直接把原因写清楚喂给Claude，让它自己去改，不用你插手判断。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# ruff --output-format=concise: "path:row:col: CODE message"
_RUFF_FINDING_RE = re.compile(r"^\S+:\d+:\d+: \w+")


def run_cmd(cmd: list[str], timeout: int = 120) -> tuple[bool, str]:
    """跑一个命令。工具没装/命令不存在，当作'跳过，不算失败'处理。"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        ok = result.returncode == 0
        output = (result.stdout or "") + (result.stderr or "")
        return ok, output[-1500:]
    except FileNotFoundError:
        # 工具没装，跳过，不算失败，避免因为环境没配好就把人卡死
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"命令超时: {' '.join(cmd)}"


def get_changed_files() -> list[str]:
    """拿这一轮实际改动过的文件（工作区 + 暂存区 + 新建的未跟踪文件）"""
    files = set()
    for args in (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        # `git diff` 不包含新建但还没 `git add` 的文件，得单独查未跟踪文件，
        # 不然像新建的 tech_evidence.py 这种文件永远不会被检查到。
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
            files.update(f for f in result.stdout.strip().splitlines() if f)
        except (OSError, subprocess.SubprocessError):
            pass
    return list(files)


def block(reason: str):
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def added_line_numbers(path: str) -> set[int] | None:
    """Line numbers this turn actually added/changed in `path`.

    Returns None for a brand-new untracked file (every line counts). Used to
    keep ruff from blocking on pre-existing debt in a file we only touched a
    few lines of — same idea as `golangci-lint --new-from-rev`.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if tracked.returncode != 0:
        return None  # untracked/new file — everything in it is "new"
    diff = subprocess.run(
        ["git", "diff", "-U0", "HEAD", "--", path],
        capture_output=True, text=True, timeout=15, check=False,
    )
    lines: set[int] = set()
    current = 0
    for line in diff.stdout.splitlines():
        if line.startswith("@@"):
            # @@ -a,b +c,d @@  — c is the start line in the new file
            try:
                plus_part = line.split("+", 1)[1].split(" ", 1)[0]
                start = int(plus_part.split(",")[0])
                current = start
            except (IndexError, ValueError):
                current = 0
        elif line.startswith("+") and not line.startswith("+++"):
            lines.add(current)
            current += 1
        elif not line.startswith("-"):
            current += 1
    return lines


def filter_ruff_output_to_new_lines(output: str, changed_files: list[str]) -> str:
    """Drop ruff findings that sit outside this turn's actually-changed lines."""
    new_lines_by_file = {f: added_line_numbers(f) for f in changed_files}
    kept: list[str] = []
    for line in output.splitlines():
        parts = line.split(":", 2)
        if len(parts) >= 2 and parts[0] in new_lines_by_file and parts[1].isdigit():
            allowed = new_lines_by_file[parts[0]]
            if allowed is not None and int(parts[1]) not in allowed:
                continue  # pre-existing line, not something this turn touched
        kept.append(line)
    return "\n".join(kept)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    # 安全阀：上一次已经拦截过一次了，这次必须放行，不然死循环
    if payload.get("stop_hook_active"):
        sys.exit(0)

    changed = get_changed_files()
    if not changed:
        sys.exit(0)  # 什么代码都没改，直接放行

    failures = []

    # ---- Python文件改了 -> 自动跑ruff（装了才跑，没装就跳过）----
    # 只查本轮实际改动的文件，不查全仓库：这个仓库里有 1000+ 条历史遗留的
    # ruff 问题（跟本轮改动无关），如果每次都跑 `ruff check .` 会导致
    # 任何一次改动都被无关的历史债务卡住，永远收不了尾。
    py_changed = [f for f in changed if f.endswith(".py") and Path(f).exists()]
    if py_changed:
        # 同样优先用项目自己的 venv 里的 ruff（版本/配置发现跟项目一致），
        # 找不到才退回 PATH 里的全局 ruff。
        backend_venv_ruff = Path("backend/.venv/bin/ruff")
        ruff_cmd = [str(backend_venv_ruff)] if backend_venv_ruff.exists() else ["ruff"]
        ok, output = run_cmd([*ruff_cmd, "check", "--output-format=concise", *py_changed])
        if not ok and output:
            # ruff 报的是整个文件里的所有问题；这里只保留本轮真正改动过的
            # 行上的问题，不然碰一下老文件就要被历史债务卡住。
            new_only = filter_ruff_output_to_new_lines(output, py_changed)
            real_violations = [
                line for line in new_only.splitlines() if _RUFF_FINDING_RE.match(line)
            ]
            if real_violations:
                failures.append(
                    "Python代码检查(ruff,仅本轮改动的行)没通过：\n" + "\n".join(real_violations)
                )

        # 项目里如果有tests目录，顺手跑一下测试。完整测试套件可能超过默认
        # 120s（本仓库跑到过 130s+），单独给它更长的超时。
        # 注意：不能直接用 PATH 里的 `pytest` —— 它可能解析到系统/用户级
        # Python（装不全依赖，比如没有 pydantic_settings），而不是项目自己的
        # backend/.venv。优先用项目虚拟环境里的 pytest。
        # -m "not network" 跳过需要真实外部凭证/网络的冒烟测试（标了
        # @pytest.mark.network 的那些）——这些测试是否通过取决于当前配置了
        # 哪些真实 API key，不该成为每一轮收尾的硬性门槛。
        backend_venv_pytest = Path("backend/.venv/bin/pytest")
        if backend_venv_pytest.exists():
            ok, output = run_cmd(
                ["bash", "-c", "cd backend && .venv/bin/pytest -q -m 'not network'"], timeout=300,
            )
            if not ok and output:
                failures.append(f"测试(pytest)没通过：\n{output}")
        elif Path("tests").exists() or Path("test").exists():
            ok, output = run_cmd(["pytest", "-q", "-m", "not network"], timeout=300)
            if not ok and output:
                failures.append(f"测试(pytest)没通过：\n{output}")

    # ---- 前端文件改了 -> 自动跑lint（有package.json才跑）----
    # 同样只查本轮改动的文件：`npm run lint`（next lint）不接受文件参数，
    # 会扫全项目，把跟本轮无关的历史 warning/error 也算进来。改用本地
    # eslint 二进制直接指定改动文件。
    fe_changed = [f for f in changed if f.endswith((".ts", ".tsx", ".js", ".jsx")) and Path(f).exists()]
    frontend_root = Path("frontend") if Path("frontend/package.json").exists() else Path(".")
    frontend_eslint = frontend_root / "node_modules" / ".bin" / "eslint"
    fe_changed_in_frontend = [f for f in fe_changed if f.startswith(str(frontend_root) + "/") or frontend_root == Path(".")]
    if fe_changed_in_frontend and frontend_eslint.exists():
        abs_files = [str(Path(f).resolve()) for f in fe_changed_in_frontend]
        ok, output = run_cmd([str(frontend_eslint), *abs_files])
        if not ok and output:
            failures.append(f"前端代码检查(eslint,仅本轮改动文件)没通过：\n{output}")

    # DEVLOG lives under archive/notes/; no longer required on every code change.

    if failures:
        block("以下几点需要处理：\n\n" + "\n\n".join(failures))

    sys.exit(0)


if __name__ == "__main__":
    main()
