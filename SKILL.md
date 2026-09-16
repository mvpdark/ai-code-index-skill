---
name: "ai-code-index-skill"
description: "Generate and maintain per-feature AI code indexes (router md + sub-index md), auto-synced on any source file add/rename/delete. Invoke when .code-index.json exists or user wants a code index for a repo."
---

# AI Code Index

Maintain an **AI-readable code index** so coding agents locate files by reading small markdown tables instead of searching the whole repo. Layout: one router (`docs/code-index.md`) + per-area sub-indexes (`docs/index/<area>.md`). Each row = file → one-line responsibility → key exports → deps (export/deps columns auto-extracted; responsibility is the only human/AI-written cell).

## Core contract (MANDATORY)

Whenever a task **creates, renames, moves, or deletes** any managed source file — including files you just generated — before finishing:

1. Run `python3 scripts/init_code_index.py add-missing` (auto-appends TODO rows with exports+deps for unregistered files), then replace each `TODO` responsibility cell with a one-line description and move the row out of `## 待归类` into the right section. Deleted/renamed files: remove/fix their rows.
2. New area or new sub-index file → add a row to the router's task-routing table.
3. Run `python3 scripts/check_code_index.py` — must exit 0. Non-zero = task NOT done.

**Failure paths:** audit fails 3× in a row on the same error → stop and ask the user; don't rewrite the index to trick the checker. Index edited by a concurrent task → re-run `add-missing` + audit before delivering. Never delete a stale row by editing the checker's rules.

## Commands

```bash
python3 scripts/init_code_index.py init --dirs src/core services/api/app   # first-time scaffold
python3 scripts/init_code_index.py add-missing                             # register new files as TODO rows
python3 scripts/init_code_index.py refresh-exports                         # re-sync export+deps columns only
python3 scripts/init_code_index.py deps                                    # dump import graph JSON (for router diagram)
python3 scripts/init_code_index.py install-hook                            # pre-commit gate: source change w/o index change → blocked
python3 scripts/check_code_index.py                                        # drift audit: coverage / stale refs / line budget
```

Scripts are zero-dependency Python 3; they locate the repo root by walking up from cwd for `.code-index.json`.

## Row format

```markdown
| `graph/normalize.ts` | Defensive normalization of any graph JSON | `normalizeGraph()` | `types.ts`, `coerce.ts` |
```

Responsibilities ≤ ~30 words. Group rows under `##` headings mirroring sub-folders or functional themes. Test files are exempt from checks; describe them at directory level.

Deeper rules (extraction regexes, config keys, CI wiring): read [references/maintenance.md](references/maintenance.md) only when needed.
