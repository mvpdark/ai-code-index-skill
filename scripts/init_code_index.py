#!/usr/bin/env python3
"""Scaffold + maintain AI code indexes (generic, config-driven via .code-index.json).

Commands:
  init             Create .code-index.json + docs/code-index.md + docs/index/<area>.md
                   with auto-extracted key exports; 职责 cells left as TODO.
  refresh-exports  Re-extract exports/deps and rewrite ONLY the export/deps columns of
                   existing table rows (matched by backticked file name). 职责 untouched.
  add-missing      Append a TODO row for every managed file not yet in any sub-index
                   (into the matching area file, under a `## 待归类` section).
  deps             Print the auto-extracted import dependency graph (JSON) for review.
  install-hook     Write a pre-commit hook that fails when managed sources changed
                   but index docs did not, and run the drift audit.

Usage:
  python3 init_code_index.py init --dirs src/core src/api [--max-lines 250]
  python3 init_code_index.py refresh-exports [repo-root]
  python3 init_code_index.py add-missing [repo-root]
  python3 init_code_index.py deps [repo-root]
  python3 init_code_index.py install-hook [repo-root]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

DEFAULT_EXTS = [".ts", ".tsx", ".py", ".css"]
SKIP_DIRS = {"node_modules", ".venv", "dist", "build", "__pycache__", ".git"}
ALL_CODE_EXTS = {".ts", ".tsx", ".py", ".css", ".js", ".jsx"}

TS_RE = re.compile(
    r"^export\s+(?:async\s+)?(?:function|const|let|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)|"
    r"^export\s*\{([^}]*)\}",
    re.M,
)
PY_RE = re.compile(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)|^class\s+([A-Za-z_]\w*)", re.M)
TS_IMPORT_RE = re.compile(r"from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]")
PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([.\w]+))", re.M)


def is_test_file(p: Path) -> bool:
    return (
        p.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        or p.name.startswith("test_")
        or p.name == "conftest.py"
        or "__tests__" in p.parts
    )


def extract_exports(p: Path) -> str:
    """Comma-joined key export names, or '-' for css/unknown."""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "-"
    names: list[str] = []
    if p.suffix in {".ts", ".tsx"}:
        for m in TS_RE.finditer(text):
            if m.group(1):
                names.append(m.group(1))
            elif m.group(2):
                for part in m.group(2).split(","):
                    part = part.strip().split(" as ")[-1].strip()
                    if part and part != "type":
                        names.append(part)
    elif p.suffix == ".py":
        for m in PY_RE.finditer(text):
            name = m.group(1) or m.group(2)
            if not name.startswith("_"):
                names.append(name)
    else:
        return "-"
    seen: list[str] = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return ", ".join(f"`{n}`" for n in seen) if seen else "-"


def extract_deps(p: Path, root: Path, cfg: dict) -> str:
    """Resolve local import specifiers to repo-relative file names; '-' if none."""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "-"
    specs: list[str] = []
    if p.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        for m in TS_IMPORT_RE.finditer(text):
            spec = m.group(1) or m.group(2)
            if spec.startswith("."):
                specs.append(spec)
    elif p.suffix == ".py":
        for m in PY_IMPORT_RE.finditer(text):
            spec = m.group(1) or m.group(2) or ""
            if spec.startswith("."):
                specs.append(spec)
    deps: list[str] = []
    for spec in specs:
        target = resolve_spec(p, spec, root, cfg)
        if target and target.name not in deps:
            deps.append(target.name)
    return ", ".join(f"`{d}`" for d in deps) if deps else "-"


def resolve_spec(p: Path, spec: str, root: Path, cfg: dict) -> Path | None:
    """Resolve a relative import spec to an actual managed file, or None."""
    if p.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        base = (p.parent / spec).resolve()
        for cand in (base, base.with_suffix(".ts"), base.with_suffix(".tsx"),
                     base.with_suffix(".js"), base / "index.ts"):
            if cand.is_file() and cand.suffix in ALL_CODE_EXTS:
                return cand
    elif p.suffix == ".py":
        # relative level = leading dots
        level = len(spec) - len(spec.lstrip("."))
        mod = spec.lstrip(".").replace(".", "/")
        base = p.parent
        for _ in range(level - 1):
            base = base.parent
        for cand in (base / f"{mod}.py", base / mod / "__init__.py"):
            if cand.is_file():
                return cand
    return None


def load_cfg(root: Path) -> dict:
    cfg_path = root / ".code-index.json"
    if not cfg_path.is_file():
        sys.exit("未找到 .code-index.json，先运行 init")
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def find_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    cur = Path.cwd().resolve()
    for d in [cur, *cur.parents]:
        if (d / ".code-index.json").is_file():
            return d
    sys.exit("未找到 .code-index.json（在仓库根运行，或传仓库根路径）")


def source_files(root: Path, rel_dir: str) -> list[Path]:
    base = root / rel_dir
    if not base.is_dir():
        return []
    return sorted(
        p for p in base.rglob("*")
        if p.is_file() and p.suffix in ALL_CODE_EXTS and p.name != "__init__.py"
        and not (SKIP_DIRS & set(p.parts))
    )


def area_name(rel_dir: str) -> str:
    return rel_dir.replace("/", "-").replace("\\", "-").strip("-").lower()


# ---------- init ----------

def gen_sub_index(root: Path, rel_dir: str, cfg: dict) -> str:
    files = [p for p in source_files(root, rel_dir) if not is_test_file(p)]
    groups: dict[str, list[Path]] = {}
    for p in files:
        rel = p.relative_to(root / rel_dir)
        key = str(rel.parent) if str(rel.parent) != "." else "(root)"
        groups.setdefault(key, []).append(p)
    lines = [f"# 子索引：{rel_dir}", ""]
    for group in sorted(groups):
        lines += [f"## {group}/" if group != "(root)" else "## 根目录", "",
                  "| 文件 | 职责 | 关键导出 | 依赖 |", "|---|---|---|---|"]
        for p in groups[group]:
            rel = p.relative_to(root / rel_dir)
            lines.append(
                f"| `{rel}` | TODO | {extract_exports(p)} | {extract_deps(p, root, cfg)} |"
            )
        lines.append("")
    return "\n".join(lines)


def cmd_init(root: Path, dirs: list[str], max_lines: int) -> int:
    cfg = {
        "managed_dirs": dirs,
        "managed_files": [],
        "index_dir": "docs/index",
        "router": "docs/code-index.md",
        "code_exts": DEFAULT_EXTS,
        "max_lines": max_lines,
        "skip_dirs": sorted(SKIP_DIRS),
    }
    (root / ".code-index.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    idx_dir = root / "docs" / "index"
    idx_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in dirs:
        name = area_name(d)
        (idx_dir / f"{name}.md").write_text(gen_sub_index(root, d, cfg), encoding="utf-8")
        rows.append((d, name))
        print(f"✓ 生成 docs/index/{name}.md")
    router = ["# 代码索引（AI 优先读物）", "",
              "> 用途：任何代码任务先读本表定位文件，跳过全盘检索。按功能分子索引，只读需要的那份。",
              f"> 维护规则：新增/改名/移动/删除源文件必须同步更新对应子索引；源文件 >{max_lines} 行须拆分。",
              "> 机器校验：`python3 scripts/check_code_index.py`（exit 1 = 索引漂移，必须修复后交付）。",
              "", "## 任务路由", "", "| 你要改什么 | 读哪份子索引 |", "|---|---|"]
    for d, name in rows:
        router.append(f"| （补一句该区域的职责描述） | [index/{name}.md](./index/{name}.md) |")
    router += ["", "## 依赖方向（单向，不得反转）", "", "```", "TODO：画出模块依赖图", "```", ""]
    (root / "docs" / "code-index.md").write_text("\n".join(router), encoding="utf-8")
    print("✓ 生成 docs/code-index.md（任务路由与依赖方向需人工补充语义）")
    print("下一步：把各子索引里的 TODO 职责列填上一句话说明，然后跑审计脚本。")
    return 0


# ---------- row rewriting (shared by refresh-exports / add-missing) ----------

ROW_RE = re.compile(r"^\|\s*`([^`]*)`\s*\|")


def split_row(line: str) -> list[str]:
    """Split a markdown table row into cells (assumes no escaped pipes)."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def refresh_cells(root: Path, cfg: dict) -> tuple[int, int]:
    """Rewrite export+deps columns of existing rows. Returns (export_changes, deps_changes)."""
    exts = set(cfg["code_exts"])
    exports: dict[str, str] = {}
    deps: dict[str, str] = {}
    for d in cfg["managed_dirs"]:
        for p in source_files(root, d):
            if p.suffix in exts:
                exports[p.name] = extract_exports(p)
                deps[p.name] = extract_deps(p, root, cfg)
    e_changed = d_changed = 0
    idx_dir = root / cfg["index_dir"]
    for f in sorted(idx_dir.glob("*.md")):
        lines = f.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            m = ROW_RE.match(line)
            if m:
                fname = Path(m.group(1)).name
                cells = split_row(line)
                if fname in exports and len(cells) >= 4:
                    if cells[2] != exports[fname]:
                        cells[2] = exports[fname]
                        e_changed += 1
                    if cells[3] != deps[fname]:
                        cells[3] = deps[fname]
                        d_changed += 1
                    line = "| " + " | ".join(cells) + " |"
                elif fname in exports and len(cells) == 3:  # 旧三列格式：补依赖列
                    cells.append(deps[fname])
                    line = "| " + " | ".join(cells) + " |"
                    d_changed += 1
            out.append(line)
        f.write_text("\n".join(out) + "\n", encoding="utf-8")
    return e_changed, d_changed


def cmd_refresh(root: Path) -> int:
    cfg = load_cfg(root)
    e, d = refresh_cells(root, cfg)
    print(f"✓ 刷新完成：关键导出列更新 {e} 行，依赖列更新 {d} 行（职责列未动）")
    return 0


def cmd_add_missing(root: Path) -> int:
    cfg = load_cfg(root)
    exts = set(cfg["code_exts"])
    idx_dir = root / cfg["index_dir"]
    text = "\n".join(f.read_text(encoding="utf-8") for f in sorted(idx_dir.glob("*.md"))) \
        if idx_dir.is_dir() else ""
    added = 0
    for d in cfg["managed_dirs"]:
        area_file = idx_dir / f"{area_name(d)}.md"
        if not area_file.is_file():
            continue
        missing = [
            p for p in source_files(root, d)
            if p.suffix in exts and not is_test_file(p) and p.name not in text
        ]
        if not missing:
            continue
        lines = area_file.read_text(encoding="utf-8").rstrip().splitlines()
        lines += ["", "## 待归类", "", "| 文件 | 职责 | 关键导出 | 依赖 |", "|---|---|---|---|"]
        for p in missing:
            rel = p.relative_to(root / d)
            lines.append(
                f"| `{rel}` | TODO | {extract_exports(p)} | {extract_deps(p, root, cfg)} |"
            )
            added += 1
        area_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"✓ {area_file.relative_to(root)} 追加 {len(missing)} 行（职责列待人工/AI 补语义）")
    if added == 0:
        print("✓ 没有未登记文件")
    return 0


def cmd_deps(root: Path) -> int:
    cfg = load_cfg(root)
    graph: dict[str, list[str]] = {}
    for d in cfg["managed_dirs"]:
        for p in source_files(root, d):
            cell = extract_deps(p, root, cfg)
            if cell != "-":
                graph[str(p.relative_to(root))] = [
                    c.strip("`") for c in cell.split(", ")
                ]
    print(json.dumps(graph, indent=2, ensure_ascii=False))
    return 0


# ---------- install-hook ----------

HOOK = """#!/bin/sh
# ai-code-index-skill pre-commit gate (installed by init_code_index.py install-hook)
STAGED=$(git diff --cached --name-only)
CODE=$(echo "$STAGED" | grep -E '\\.(ts|tsx|py|css|js|jsx)$' || true)
DOC=$(echo "$STAGED" | grep -E '^(docs/index/|docs/code-index\\.md)' || true)
if [ -n "$CODE" ] && [ -z "$DOC" ]; then
  echo "✗ 本次提交改动了源码但没有同步更新代码索引（docs/index/ 或 docs/code-index.md）"
  echo "  先运行: python3 scripts/init_code_index.py add-missing && 补职责列"
  exit 1
fi
python3 "$(dirname "$0")/../../scripts/check_code_index.py" 2>/dev/null \\
  || python3 scripts/check_code_index.py
"""


def cmd_install_hook(root: Path) -> int:
    hooks = root / ".git" / "hooks"
    if not hooks.is_dir():
        sys.exit("未找到 .git/hooks —— 请在 git 仓库根运行")
    target = hooks / "pre-commit"
    if target.exists() and "ai-code-index-skill" not in target.read_text(encoding="utf-8"):
        sys.exit(f"已存在自定义 {target}，为避免覆盖请手动合并本 skill 的门禁逻辑")
    target.write_text(HOOK, encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print("✓ 已安装 .git/hooks/pre-commit（源码改动未同步索引 → 拦截；并跑漂移审计）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--dirs", nargs="+", required=True)
    p_init.add_argument("--max-lines", type=int, default=250)
    for name in ("refresh-exports", "add-missing", "deps", "install-hook"):
        sp = sub.add_parser(name)
        sp.add_argument("root", nargs="?", default=None)
    args = ap.parse_args()

    if args.cmd == "init":
        return cmd_init(Path.cwd().resolve(), args.dirs, args.max_lines)
    root = find_root(args.root)
    return {
        "refresh-exports": cmd_refresh,
        "add-missing": cmd_add_missing,
        "deps": cmd_deps,
        "install-hook": cmd_install_hook,
    }[args.cmd](root)


if __name__ == "__main__":
    sys.exit(main())
