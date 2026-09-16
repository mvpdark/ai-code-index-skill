#!/usr/bin/env python3
"""Scaffold + refresh AI code indexes (generic, config-driven via .code-index.json).

Commands:
  init             Create .code-index.json + docs/code-index.md + docs/index/<area>.md
                   with auto-extracted key exports; 职责 cells left as TODO.
  refresh-exports  Re-extract exports and rewrite ONLY the export column of existing
                   table rows (matched by backticked file name). Never touches 职责.

Usage:
  python3 init_code_index.py init --dirs packages/core/src services/api/app [--max-lines 250]
  python3 init_code_index.py refresh-exports [repo-root]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_EXTS = [".ts", ".tsx", ".py", ".css"]
SKIP_DIRS = {"node_modules", ".venv", "dist", "build", "__pycache__", ".git"}

TS_RE = re.compile(
    r"^export\s+(?:async\s+)?(?:function|const|let|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)|"
    r"^export\s*\{([^}]*)\}",
    re.M,
)
PY_RE = re.compile(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)|^class\s+([A-Za-z_]\w*)", re.M)


def is_test_file(p: Path) -> bool:
    return (
        p.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        or p.name.startswith("test_")
        or p.name == "conftest.py"
        or "__tests__" in p.parts
    )


def extract_exports(p: Path) -> str:
    """Return comma-joined key export names, or '-' for css/unknown."""
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


def source_files(root: Path, rel_dir: str) -> list[Path]:
    base = root / rel_dir
    exts = {".ts", ".tsx", ".py", ".css", ".js", ".jsx"}
    if not base.is_dir():
        return []
    return sorted(
        p
        for p in base.rglob("*")
        if p.is_file() and p.suffix in exts and p.name != "__init__.py"
        and not (SKIP_DIRS & set(p.parts))
    )


def area_name(rel_dir: str) -> str:
    return rel_dir.replace("/", "-").replace("\\", "-").strip("-").lower()


def gen_sub_index(root: Path, rel_dir: str) -> str:
    files = [p for p in source_files(root, rel_dir) if not is_test_file(p)]
    groups: dict[str, list[Path]] = {}
    for p in files:
        rel = p.relative_to(root / rel_dir)
        key = str(rel.parent) if str(rel.parent) != "." else "(root)"
        groups.setdefault(key, []).append(p)
    lines = [f"# 子索引：{rel_dir}", ""]
    for group in sorted(groups):
        lines += [f"## {group}/" if group != "(root)" else "## 根目录", "",
                  "| 文件 | 职责 | 关键导出 |", "|---|---|---|"]
        for p in groups[group]:
            rel = p.relative_to(root / rel_dir)
            lines.append(f"| `{rel}` | TODO | {extract_exports(p)} |")
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
        (idx_dir / f"{name}.md").write_text(gen_sub_index(root, d), encoding="utf-8")
        rows.append((d, name))
        print(f"✓ 生成 docs/index/{name}.md")
    router = ["# 代码索引（AI 优先读物）", "",
              "> 用途：任何代码任务先读本表定位文件，跳过全盘检索。按功能分子索引，只读需要的那份。",
              "> 维护规则：新增/改名/移动/删除源文件必须同步更新对应子索引；源文件 >%d 行须拆分。" % max_lines,
              "> 机器校验：`python3 scripts/check_code_index.py`（exit 1 = 索引漂移，必须修复后交付）。",
              "", "## 任务路由", "", "| 你要改什么 | 读哪份子索引 |", "|---|---|"]
    for d, name in rows:
        router.append(f"| （补一句该区域的职责描述） | [index/{name}.md](./index/{name}.md) |")
    router += ["", "## 依赖方向（单向，不得反转）", "", "```", "TODO：画出模块依赖图", "```", ""]
    (root / "docs" / "code-index.md").write_text("\n".join(router), encoding="utf-8")
    print("✓ 生成 docs/code-index.md（任务路由与依赖方向需人工补充语义）")
    print("下一步：把各子索引里的 TODO 职责列填上一句话说明，然后跑审计脚本。")
    return 0


EXPORT_CELL_RE = re.compile(r"(\| `[^`]*` \|[^\n|]*\|)([^\n|]*)(\|)")


def cmd_refresh(root: Path) -> int:
    cfg_path = root / ".code-index.json"
    if not cfg_path.is_file():
        sys.exit("未找到 .code-index.json，先运行 init")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    exts = set(cfg["code_exts"])
    # basename → exports
    table: dict[str, str] = {}
    for d in cfg["managed_dirs"]:
        for p in source_files(root, d):
            if p.suffix in exts:
                table[p.name] = extract_exports(p)
    changed = 0
    idx_dir = root / cfg["index_dir"]
    for f in sorted(idx_dir.glob("*.md")):
        lines = f.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            m = EXPORT_CELL_RE.search(line)
            if m:
                fname = Path(re.search(r"`([^`]*)`", line).group(1)).name
                if fname in table and m.group(2).strip() != table[fname].strip():
                    line = line[: m.start(2)] + " " + table[fname] + " " + line[m.end(2):]
                    changed += 1
            out.append(line)
        f.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"✓ 刷新完成，更新 {changed} 行的关键导出列（职责列未动）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--dirs", nargs="+", required=True)
    p_init.add_argument("--max-lines", type=int, default=250)
    p_ref = sub.add_parser("refresh-exports")
    p_ref.add_argument("root", nargs="?", default=None)
    args = ap.parse_args()

    if args.cmd == "init":
        return cmd_init(Path.cwd().resolve(), args.dirs, args.max_lines)
    cur = Path(args.root).resolve() if args.root else Path.cwd().resolve()
    for d in [cur, *cur.parents]:
        if (d / ".code-index.json").is_file():
            return cmd_refresh(d)
    sys.exit("未找到 .code-index.json")


if __name__ == "__main__":
    sys.exit(main())
