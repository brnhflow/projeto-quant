# projeto-quant (working title)

Personal portfolio analysis: risk, scenarios, decision support. Never order execution.
Plan of work: docs/ROADMAP.md. Tool choices and why: SETUP_LOG.md.

## Commands (Windows: always `python -m`, Smart App Control blocks tool .exe launchers)
- Install / update env: `uv sync` · app: `uv run python -m quant app`
- All tests: `uv run python -m pytest` · one file: `uv run python -m pytest tests/test_x.py -q`
- Lint + format: `uv run ruff check --fix . && uv run ruff format .`
- Types (strict): `uv run python -m pyright`
- Everything CI runs: `uv run python -m pre_commit run --all-files`

## Rules
- Python >=3.11, src layout (`src/quant`), full type hints, numpy-style docstrings.
- One function at a time: test with a known answer first (hand calculation, closed form,
  textbook value), then the implementation, then run the checks. Use the `new-function` skill.
- No look-ahead: a value dated t may use only data available at t. Any time-indexed function
  gets a test that changes future data and asserts past outputs do not move.
- Every model states its assumptions in plain language in the docstring ("Assumptions").
- Units explicit in names or docstrings: decimal vs percent, daily vs annual, currency.
- Not done until tests, ruff and pyright pass; show the command output as evidence and say
  what was not tested.
- No new dependency without saying why (`uv add` asks for approval).
- Decision support only: read-only data sources; never code that sends orders or holds
  broker credentials with trading rights.
- Personal data stays in `data/private/` (git-ignored); tests use synthetic or public data.

## Working with me
- Talk to me (Bernardo) in Portuguese, short; I am learning, so explain the math behind each
  step simply. Code, comments, commits and docs in English, human tone, no hype.
- Commits: small, local, message explains why. Never push or create a GitHub repo without my OK.
- After a big change, ask the `reviewer` subagent to check correctness before saying done.
