---
name: new-function
description: Workflow for adding one analysis function (return, risk metric, scenario, simulation) to src/quant with a known-answer test first. Use whenever implementing a new public function.
---

Build exactly one function per pass, in this order:

1. **Question and assumptions.** In Portuguese, tell Bernardo in 3-5 lines what question the
   function answers, the formula, and its assumptions in plain words. Name the units
   (decimal/percent, daily/annual, currency).
2. **Known answer first.** Write the test before the code, in `tests/test_<module>.py`:
   - one case computed by hand or from a closed form / textbook (write the arithmetic in a
     comment so a reader can redo it);
   - one edge case (empty input, constant series, single asset, NaN);
   - if the function is indexed by time: change data after date t and assert results up to t
     are unchanged (look-ahead test).
   Run it and confirm it fails for the right reason.
3. **Implement** the smallest version that passes: full type hints, numpy-style docstring
   with Parameters, Returns, and an "Assumptions" section. No extra options "for later".
4. **Check:** `uv run python -m pytest -q`, `uv run ruff check .`, `uv run python -m pyright`.
   Show the output.
5. **Explain** the math in simple terms (what each step does and why), what is not tested,
   and the natural next function. Then stop; do not start the next one unasked.
