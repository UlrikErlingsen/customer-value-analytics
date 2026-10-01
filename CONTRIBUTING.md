# Contributing to Worth Signal

Thanks for your interest in improving Worth Signal! Contributions of all
kinds are welcome: bug reports, documentation fixes, new analyses, and
better explanations for non-specialists.

## Development setup

You need Python 3.10 or newer. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pytest
```

To start the app locally:

```bash
streamlit run app.py
```

## Running the tests

```bash
python -m pytest
```

Pytest picks up its configuration from `pyproject.toml` (it adds `src/` to
the import path and looks for tests in `tests/`). All tests must pass
before a change is merged; the same suite runs in CI on every push and
pull request.

## Project layout

```
app.py           Thin standalone entry point: page config, then render()
src/cva/         Pure computation modules (the actual models)
src/cva/ui/      Streamlit UI — all pages, widgets, and presentation;
                 render() is also the Signal Hub entry point
tests/           Pytest suite covering the computation modules and the app
docs/            Written guides and model documentation
examples/        Sample input files you can load into the app
```

The split matters: everything in `src/cva/` outside `src/cva/ui/` is plain
Python that can be imported and used **without Streamlit or Plotly** — no UI
imports, no session state, no side effects. A test enforces this. `src/cva/ui/`
is a thin presentation layer that calls into those modules and renders the
results. Every session-state and widget key there goes through `k()`, which
prefixes it with `worth:` so the app can share one Signal Hub session with the
other Signal apps. `src/cva/ui/signal_theme.py` and `src/cva/ui/assets/marks/`
are synced from Signal Hub; do not edit them here.

## Code style

- **Typed**: use type hints on function signatures.
- **Small pure functions**: each function takes inputs and returns
  outputs; avoid hidden state and module-level mutation.
- **Docstrings**: every public function gets a docstring that says what it
  computes and, where relevant, which published model it implements.
- **No behavior tied to the UI**: computation modules must never import
  Streamlit or depend on how results are displayed. If logic is worth
  having, it is worth being testable from a plain Python shell.

## Adding a new analysis

1. **Create a module** in `src/cva/` (for example `src/cva/my_model.py`)
   containing pure, typed functions that implement the computation. If
   the model comes from the literature, cite the paper in the module
   docstring.
2. **Add a page** function in `src/cva/ui/app.py` (and register it in
   `PAGES`) that collects inputs, calls your module, and presents the
   results. Give every widget an explicit `key=k("...")`.
3. **Write a test** in `tests/` that exercises the module directly —
   ideally against a worked example from the source paper or a hand-checked
   calculation.
4. Run `python -m pytest` and make sure the whole suite passes.

## Writing user-facing text

This app is meant to be usable by people who are not statisticians or
marketing scientists. Any text a user sees — page descriptions, input
labels, help text, result explanations — must be understandable by a
non-specialist. Prefer plain English over jargon; when a technical term
is unavoidable, explain it the first time it appears.

## Questions

Open an issue if anything here is unclear — confusing documentation is a
bug too.

For a vulnerability or privacy issue, follow [SECURITY.md](SECURITY.md) and
use GitHub's private security-advisory form. Never include real customer data
or credentials in a public issue.
