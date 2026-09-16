# code-index-sync

An [Agent Skill](https://agentskills.io) that gives coding agents a **maintained, AI-readable code index** for your repo — so they locate files by reading a few small markdown tables instead of grepping the whole codebase on every task.

## The problem

Coding agents burn tokens and time on full-repo search ("where is X implemented?") on every single task. aider solves this with a dynamically computed repo map, but a dynamic map carries only *structure* (symbols, signatures) — never *semantics*: design intent, conventions, dependency rules, task routing. Hand-written docs carry semantics but silently rot.

**code-index-sync keeps a small hand-curated semantic layer and automates everything derivable from source, with a hard audit gate so the semantic layer can't rot unnoticed.**

## What it does

- **Scaffolds** a router index (`docs/code-index.md`) + per-area sub-indexes (`docs/index/<area>.md`). Each row = file path → one-line responsibility → key exports (auto-extracted for TS/TSX/Python; CSS marked `-`).
- **Enforces sync**: the skill contract requires the agent to update the matching sub-index *in the same task* that adds/renames/moves/deletes any source file — including files it just generated itself.
- **Audits drift** with `scripts/check_code_index.py`:
  1. *Coverage* — every managed non-test source file is registered in some sub-index
  2. *Stale* — every code filename referenced in the indexes still exists
  3. *Line budget* — no managed file exceeds `max_lines` (default 250 → split it)

  Exit 1 with a per-file report on any failure.
- **Refreshes the mechanical column**: `init_code_index.py refresh-exports` re-extracts exports and rewrites only the export column of existing rows. Human/AI-written one-line responsibilities are never touched.

## Layout

```
SKILL.md                        # the skill contract (for .trae/skills or .claude/skills)
references/maintenance.md       # deep rules: extraction, config keys, CI wiring
scripts/init_code_index.py      # scaffold / add-missing / refresh-exports / deps / install-hook
scripts/check_code_index.py     # drift audit
.code-index.json                # per-repo config, created by `init` (lives in YOUR repo)
```

## Quick start

```bash
# 1. In your repo root: scaffold config + indexes for your source dirs
#    (export + deps columns are auto-extracted; 职责 left as TODO)
python3 scripts/init_code_index.py init --dirs src packages/core/src services/api/app

# 2. Fill the TODO responsibility cells (one line per file) — the semantic part is human/AI work.
#    Also complete the router's task-routing table and dependency-direction diagram.

# 3. Audit — run at the end of every code task
python3 scripts/check_code_index.py
```

## Day-2 commands

```bash
python3 scripts/init_code_index.py add-missing       # new files → TODO rows (agent fills semantics after)
python3 scripts/init_code_index.py refresh-exports   # re-sync export+deps columns only, 职责 untouched
python3 scripts/init_code_index.py deps              # dump import graph JSON (feeds router's dep diagram)
python3 scripts/init_code_index.py install-hook      # pre-commit: source change w/o index change → blocked
```

Install the skill so your agent picks it up automatically:

```bash
# Trae
mkdir -p .trae/skills && cp -r <this-repo> .trae/skills/code-index-sync
# Claude Code
mkdir -p .claude/skills && cp -r <this-repo> .claude/skills/code-index-sync
```

## Keeping it fresh in CI / pre-commit

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: code-index
      entry: python3 path/to/scripts/check_code_index.py
      language: system
      pass_filenames: false
```

Or as a CI step: `python3 scripts/check_code_index.py && python3 scripts/init_code_index.py refresh-exports`.

## Config reference (`.code-index.json`)

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

Test files (`*.test.ts(x)`, `*.spec.ts(x)`, `test_*.py`, `conftest.py`, anything under `__tests__/`) are exempt from coverage/line checks and are described at directory level.

## Sub-index row format

```markdown
| `graph/normalize.ts` | Defensive normalization of any graph JSON | `normalizeGraph()` → `{graph, warnings}` |
```

One line per file; responsibilities ≤ ~30 words; group rows under `##` headings mirroring sub-folders or functional themes.

## When it fits (and when it doesn't)

- **Fits**: mid-size repos (tens to a few hundred source files) where semantic notes (conventions, dependency rules, "改 X 读哪份") pay off; teams using coding agents daily.
- **Doesn't fit**: monorepos with thousands of files (use aider-style dynamic maps instead), or repos where no agent ever reads the index.
- The line-budget check (default 250) is opinionated — set `max_lines` high or ignore check 3 if you don't want split enforcement.

## Credits & prior art

- [aider repo map](https://aider.chat/2023-10-22/repomap.html) — dynamic tree-sitter + PageRank structural index, computed per request.
- [llms.txt](https://llmstxt.org/) — standard for machine-readable site indexes; its "generate at build time so it can't rot" principle is what the audit gate approximates for hand-curated content.
- [repomix](https://repomix.com/) / [code2prompt](https://code2prompt.dev/) — one-shot whole-repo packing for LLM input.

This skill occupies the middle ground: **persistent semantic index + automated mechanical columns + hard drift gate**.

## License

MIT
