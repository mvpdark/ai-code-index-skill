# Maintenance reference (load only when needed)

## Export extraction rules

- TS/TSX: `export function/const/let/class/interface/type/enum NAME`, plus names inside `export { a, b as c }` (alias kept).
- Python: top-level `def`/`class`; leading-underscore names skipped.
- CSS and other extensions: export cell `-`.
- Deps cell: relative imports only (`./x`, `../pkg.y`), resolved to real files; unresolvable specs (external packages, broken paths) are dropped, never guessed.

## `.code-index.json` keys

```json
{
  "managed_dirs": ["packages/core/src", "services/api/app"],
  "managed_files": ["packages/app-web/vite.config.ts"],
  "index_dir": "docs/index",
  "router": "docs/code-index.md",
  "code_exts": [".ts", ".tsx", ".py", ".css"],
  "max_lines": 250,
  "skip_dirs": ["node_modules", ".venv", "dist", "build", "__pycache__", ".git"]
}
```

- `managed_dirs`: directories scanned for indexable source files.
- `managed_files`: individual files outside those dirs that still need registration.
- `code_exts`: extensions subject to coverage/refresh; `deps` resolution always covers ts/tsx/js/jsx/py.
- `max_lines`: line budget; set very high to disable split enforcement.

## Audit checks (check_code_index.py)

1. Coverage — every managed non-test file's basename appears in some `docs/index/*.md` or the router.
2. Stale — every backticked code filename in the indexes resolves to an existing file anywhere in the repo (skip_dirs honored).
3. Line budget — managed non-test files ≤ `max_lines`.

Test files exempt: `*.test.ts(x)`, `*.spec.ts(x)`, `test_*.py`, `conftest.py`, anything under `__tests__/`.

## CI / pre-commit wiring

`install-hook` writes `.git/hooks/pre-commit` that (a) blocks commits touching managed sources without touching index docs, and (b) runs the drift audit. For CI instead, add one step:

```yaml
- run: python3 scripts/check_code_index.py
```

Keep `add-missing` + `refresh-exports` out of CI (they write files); run them locally or in an auto-fix job that opens a PR.

## When NOT to use this skill

- Repos with thousands of source files: per-file semantic rows stop paying off; prefer aider-style dynamic maps.
- Repos where no agent reads the index: the maintenance cost is pure loss.
