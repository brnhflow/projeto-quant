# Setup log

What was installed or configured, why, and the source behind each decision.
Date of setup: 2026-11-23. Machine: Windows 11 with Smart App Control on.

## Machine facts that shaped the setup

- Already present: Python 3.14, uv 0.12, git 2.55, gh 2.103 (not logged in), Node 24.
  Missing: CMake and any C/C++ compiler.
- **Smart App Control blocks unsigned executables and DLLs.** Tested: `pytest.exe` (the
  launcher pip/uv generate) and mypy's compiled modules (`mypy`, `librt`, `ast-serialize`)
  are blocked; `uv`, `ruff`, Python itself, numpy 2.5, pandas 3.1 and scipy 1.18 load fine.
  Consequences: tools run as `python -m <tool>`; the type checker is pyright, not mypy.
- Project lives in `C:\Users\berna\projetos\projeto-quant`, outside OneDrive, so the
  `.venv` (thousands of files) is not synced to the cloud.

## Python toolchain

| Tool | Version | Why | Source |
|---|---|---|---|
| uv | 0.12 (already installed) | One tool for Python versions, venv, lockfile (`uv.lock`), build. Fast and reproducible. | docs.astral.sh/uv |
| hatchling | build backend | Simple, standard (PEP 517), supports src layout. | hatch.pypa.io |
| ruff | 0.17.6 | Lint + format in one fast tool, replaces flake8/isort/black. Rules include numpy (NPY) and pandas (PD) pitfalls and numpy-style docstrings. | docs.astral.sh/ruff |
| pyright | 1.1.414 | Strict static typing. Chosen over mypy only because of Smart App Control (above). Official Microsoft package, runs on Node. | github.com/microsoft/pyright |
| pytest + pytest-cov | 9.2 / 7.1 | Standard test runner; warnings are errors; branch coverage in CI. | docs.pytest.org |
| pre-commit (+ pre-commit-hooks v6.0.0) | 4.7 | Runs the same checks as CI before each commit, plus YAML/TOML checks, private-key detection and a 500 KB file limit. | pre-commit.com |
| GitHub Actions | checkout v7, setup-uv v10 | CI on Python 3.11 (minimum) and 3.14 (dev). Read-only token (`permissions: contents: read`). | docs.github.com/actions, github.com/astral-sh/setup-uv |

No runtime dependencies yet: numpy/pandas/scipy get added with the first function that needs them.

## Claude Code configuration (in `.claude/`, committed)

| Item | What it does | Source |
|---|---|---|
| `CLAUDE.md`, ~35 lines | Only what Claude cannot infer from code: exact commands, rules, how to work with me. Kept short because it loads into every session. | code.claude.com/docs/en/best-practices ("Keep CLAUDE.md short"), /costs ("Aim to keep CLAUDE.md under 200 lines") |
| `settings.json` permissions | Allow test/lint/type/git-read commands without prompts; **ask** before `uv add`, `git push`, `gh repo create`, releases; **deny** reading `.env` and `secrets/`. Deny rules hold in every permission mode. | code.claude.com/docs/en/settings, /best-practices ("Limit access with permission rules") |
| PostToolUse hook | After each Edit/Write of a `.py` file: ruff format + fix; unfixable lint errors go back to Claude (exit 2). | code.claude.com/docs/en/hooks |
| Stop hook | If there are uncommitted `.py` changes, Claude cannot finish while pyright or pytest fail (output trimmed to the tail to save tokens). Rules that must always hold belong in hooks, not in CLAUDE.md. | code.claude.com/docs/en/best-practices ("Enforce the check with a Stop hook") |
| `agents/reviewer.md` | Read-only (Read, Grep, Glob) Sonnet reviewer for financial correctness: look-ahead, units, known-answer tests. Fresh context, not biased by the conversation that wrote the code. | code.claude.com/docs/en/sub-agents, /best-practices ("Know what subagents cost") |
| `skills/new-function` | The one-function workflow (assumptions, known-answer test, code, checks, explanation). Loads only when used, so it costs nothing in other sessions. | code.claude.com/docs/en/skills, /costs ("Move instructions from CLAUDE.md to skills") |

## Token economy habits (no install needed)

From code.claude.com/docs/en/costs and /best-practices:
- `/clear` between unrelated tasks; `/compact <focus>` only when continuity matters.
- Sonnet for day-to-day work, Opus for design decisions (`/model`); plan mode (Shift+Tab)
  before multi-file changes; lower `/effort` for simple tasks.
- Specific prompts naming the file and function avoid broad scans.
- Prefer CLI tools (`gh`) over MCP servers: no per-tool listing in context.
- `/usage` shows which skills, subagents and MCP servers consume the plan.

## Connectors and MCP: what was and was not added

| Need | Decision | Benefit / token cost / risk |
|---|---|---|
| GitHub | **`gh` CLI, no MCP server.** Needs `gh auth login` by me. | Same capability; the docs say CLIs are more context-efficient than MCP. Risk: `gh` acts with my account, so `git push` and `gh repo create` are on "ask". |
| Library docs | **None.** Built-in WebFetch on official docs (numpy, pandas, scipy) when needed. | A docs MCP saves little at this size and adds a dependency. Revisit if API mistakes become frequent. |
| Web search | **Built-in** WebSearch/WebFetch. | No install, no key. |
| Market data | **No MCP.** The registry's finance servers are paid, company-data products, or brokers whose tools include account access and trading (Webull, Clear Street), which this project rules out. Data will be fetched by tested Python code with read-only, documented sources (decided in roadmap step 1). | Keeps data flow reproducible and testable instead of hidden in a chat tool. |
| C++ build | **Not installed yet** (CMake, MSVC Build Tools ~several GB, scikit-build-core, pybind11/nanobind). Only needed at roadmap step 9. Note: Smart App Control may block the compiled test binaries; WSL2 is the likely way out. | Avoids a large install with no use for months. |
| gitleaks (secret scanner) | **Not installed.** Its compiled binary would likely be blocked by Smart App Control; `.gitignore` + deny rules + `detect-private-key` cover the current risk. | Revisit before the repo goes public. |

## Market data (2026-11-23)

Tested live before choosing; no new dependency (HTTP with the standard library).

| Source | Use | Verdict |
|---|---|---|
| Yahoo Finance `/v8/finance/chart` | B3, European stocks and ETFs, crypto | Used. Unofficial; community reports 429 rate limits and endpoint changes in 2026, so: one request per asset, 0.5 s apart, retries with backoff, cache fallback. |
| Kraken public OHLC | Crypto | Used. Official, no key, 720-day limit. |
| Frankfurter (ECB reference rates) | FX | Used. Open source, no key, daily. |
| ECB Data Portal API | FX | Not reachable during testing (503 / connection failure). |
| Stooq CSV | Stocks | Rejected: now behind a JavaScript proof-of-work check. |
| brapi.dev | B3 | Rejected: free access without key only for a few test tickers. |
| Twelve Data, Marketstack, Alpha Vantage | Stocks | Not used: need a key, and free tiers are limited or US-only for live data. |
