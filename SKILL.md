---
name: "code-index-sync"
description: "Generate and maintain per-feature AI code indexes (router md + sub-index md), auto-synced on any source file add/rename/delete. Invoke when .code-index.json exists or user wants a code index."
---

# Code Index Sync

Maintain an **AI-readable code index** so coding agents can locate files by reading a few small markdown tables instead of searching the whole repo. The index is split by feature/module: one router (`docs/code-index.md`) plus per-area sub-indexes (`docs/index/<area>.md`). Each row = file path → one-line responsibility → key exports.

## Why this exists

- Full-repo grep/glob per task wastes tokens and time; a curated index answers "where is X" in one read.
- Semantic notes (responsibility, dependency direction, conventions) cannot be auto-generated — but **drift detection and export extraction can**. This skill automates the mechanical parts and forces the agent to maintain the semantic parts.

## Layout

```
.code-index.json          # config: managed dirs, extensions, line budget
docs/code-index.md        # router: task routing table + top-level structure + dependency direction
docs/index/<area>.md      # one sub-index per managed area
scripts/check_code_index.py    # drift audit (coverage / stale refs / line budget)
scripts/init_code_index.py     # scaffold + refresh-exports
```

## Core contract (MANDATORY for the agent)

Whenever a task **creates, renames, moves, or deletes** any source file under a managed dir — including files the agent itself just generated (new components, new modules, split-off files) — in the SAME task, before finishing:

1. Update the matching `docs/index/<area>.md`: add/remove/fix the row (path, one-line responsibility, key exports).
2. If a new area/dir appeared, add a row to the router's task-routing table.
3. Run `python3 <skill>/scripts/check_code_index.py` — it must exit 0. Non-zero = index drift = task NOT done; fix and re-run.

Never deliver code changes that leave the index stale. The audit script is the hard gate.

## Workflows

### First-time setup (no `.code-index.json`)

```bash
python3 scripts/init_code_index.py init \
  --dirs packages/core/src packages/app-web/src services/api/app
```

This writes `.code-index.json`, generates sub-indexes grouped by directory (one table section per sub-folder), auto-extracts key exports per file, and leaves `职责` cells as `TODO` for the agent/human to fill with one-line semantics. Then ask the AI (or hand-edit) to replace every TODO, and add the router's dependency-direction notes.

### Refresh key exports (mechanical column, fully automated)

```bash
python3 scripts/init_code_index.py refresh-exports
```

Re-parses every indexed source file and rewrites only the `关键导出` column of existing table rows. Run this after refactors that rename exports, or periodically. `职责` is never touched.

### Audit (run at the end of every code task)

```bash
python3 scripts/check_code_index.py
```

Checks: (1) every managed non-test source file is registered in some sub-index; (2) every code filename referenced in the index actually exists (no stale rows); (3) no managed source file exceeds `max_lines` (default 250 — split it). Exit 1 with a per-file report on any failure.

## Extracted-export rules

- TS/TSX: `export function/const/class/interface/type/enum NAME`, plus names inside `export { a, b }`.
- Python: top-level `def`/`class` (leading-underscore skipped).
- CSS and other files: cell set to `-`.
- Test files (`*.test.ts(x)`, `test_*.py`, `conftest.py`, `__tests__/`) are exempt from coverage/line checks and are described at directory level in the index.

## Config reference (`.code-index.json`)

```json
{
  "managed_dirs": ["packages/core/src", "services/api/app"],
  "managed_files": ["packages/app-web/vite.config.ts"],
  "index_dir": "docs/index",
  "router": "docs/code-index.md",
  "code_exts": [".ts", ".tsx", ".py", ".css"],
  "max_lines": 250,
  "skip_dirs": ["node_modules", ".venv", "dist", "build", "__pycache__"]
}
```

## Sub-index row format

```markdown
| `graph/normalize.ts` | Defensive normalization of any graph JSON | `normalizeGraph()` → `{graph, warnings}` |
```

Keep one line per file, responsibilities ≤ ~30 words. Group rows under `##` headings that mirror sub-folders or functional themes.
