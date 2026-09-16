#!/usr/bin/env python3
"""Code-index drift audit (generic, config-driven via .code-index.json).

Checks, exit 1 on any failure:
1. Coverage : every managed non-test source file name appears in some sub-index under index_dir.
2. Stale    : every code filename referenced in backticks in the indexes exists in the repo.
3. Lines    : no managed non-test source file exceeds max_lines.

Usage: python3 check_code_index.py [repo-root]   (default: search cwd upward for .code-index.json)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

DEFAULTS = {
    "managed_dirs": [],
    "managed_files": [],
    "index_dir": "docs/index",
    "router": "docs/code-index.md",
    "code_exts": [".ts", ".tsx", ".py", ".css"],
    "max_lines": 250,
    "skip_dirs": ["node_modules", ".venv", "dist", "build", "__pycache__", ".git"],
}


def find_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    cur = Path.cwd().resolve()
    for d in [cur, *cur.parents]:
        if (d / ".code-index.json").is_file():
            return d
    sys.exit("未找到 .code-index.json（请在仓库根运行，或传仓库根路径为参数）")


def load_cfg(root: Path) -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(json.loads((root / ".code-index.json").read_text(encoding="utf-8")))
    return cfg


def is_test_file(p: Path) -> bool:
    return (
        p.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        or p.name.startswith("test_")
        or p.name == "conftest.py"
        or "__tests__" in p.parts
    )


def walk_files(root: Path, cfg: dict) -> list[Path]:
    exts = set(cfg["code_exts"])
    skip = set(cfg["skip_dirs"])
    out: list[Path] = []
    for d in cfg["managed_dirs"]:
        base = root / d
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if (
                p.is_file()
                and p.suffix in exts
                and p.name != "__init__.py"
                and not (skip & set(p.parts))
            ):
                out.append(p)
    out.extend(root / f for f in cfg["managed_files"] if (root / f).is_file())
    return sorted(set(out))


def index_text(root: Path, cfg: dict) -> str:
    parts = []
    idx = root / cfg["index_dir"]
    if idx.is_dir():
        for f in sorted(idx.glob("*.md")):
            parts.append(f.read_text(encoding="utf-8"))
    router = root / cfg["router"]
    if router.is_file():
        parts.append(router.read_text(encoding="utf-8"))
    if not parts:
        sys.exit(f"索引不存在：{idx} 或 {router} —— 先运行 init_code_index.py init")
    return "\n".join(parts)


def referenced_code_files(text: str, exts: set[str]) -> set[str]:
    refs = set()
    for m in re.finditer(r"`([^`\s]+)`", text):
        token = m.group(1).rstrip(".,;")
        if Path(token).suffix in exts:
            refs.add(Path(token).name)
    return refs


def main() -> int:
    root = find_root(sys.argv[1] if len(sys.argv) > 1 else None)
    cfg = load_cfg(root)
    exts = set(cfg["code_exts"])
    text = index_text(root, cfg)
    sources = walk_files(root, cfg)
    skip = set(cfg["skip_dirs"])
    exist_names: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for f in filenames:
            if Path(f).suffix in exts:
                exist_names.add(f)
    errors: list[str] = []

    for p in sources:
        if is_test_file(p):
            continue
        if p.name not in text:
            errors.append(f"未登记：{p.relative_to(root)} 未出现在任何子索引中")

    for name in sorted(referenced_code_files(text, exts)):
        if name not in exist_names:
            errors.append(f"陈旧引用：索引提到的 {name} 在仓库源码中不存在")

    for p in sources:
        if is_test_file(p):
            continue
        n = sum(1 for _ in p.open(encoding="utf-8", errors="replace"))
        if n > cfg["max_lines"]:
            errors.append(f"超行数：{p.relative_to(root)} 共 {n} 行（>{cfg['max_lines']}），须拆分")

    if errors:
        print("索引表与源码存在漂移：")
        for e in errors:
            print(f"  ✗ {e}")
        print("\n请更新 docs/index/ 下对应子索引（或拆分文件）后重跑本脚本。")
        return 1
    print(f"✓ 索引与源码一致：{len(sources)} 个受管源文件全部登记，无陈旧引用，无超行数文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
