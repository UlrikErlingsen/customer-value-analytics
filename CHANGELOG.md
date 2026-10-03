# Changelog

Notable changes to Worth Signal are documented here. This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.3.0] - 2026-10-03

### Larger datasets

- **Larger datasets: no built-in data limits when run locally** (was 200 MB per file via `CVA_MAX_UPLOAD_MB`, 50 MB for JSON, 400 MB of unpacked Excel, 1,000,000 rows per table and 10,000,000 cells). File size, rows and cells are limited only by memory; running out of memory (including Arrow allocation failures) is reported as a plain `DataProblem` / message. A public demo (`SIGNAL_PUBLIC=1`) keeps the old values as demo caps, all in the new `cva.limits` module, and its messages say the downloaded app has none. The `MAX_*` size constants in `cva.io` are gone; every public function keeps its name and signature (Freddo CRM compatible).
- BG/NBD and BG/BB pool customers with identical histories (their sufficient statistics) before fitting, an exact identity: results are unchanged, and BG/BB, whose likelihood loops per history in Python, now costs per distinct history instead of per customer. `score_bgbb` scores each distinct history once and maps the scores back.
- `complaint_summary` is vectorized (no Python loop over customers) with identical output; the RFM segment label is built without a row-wise `apply`.
- Exports scale: `results_to_excel` streams rows (openpyxl write-only) and continues a table on further sheets ("Customer scores (2)", …) beyond Excel's 1,048,575-row limit instead of failing; `results_to_json` writes compactly with pandas above 100,000 rows; new `results_to_csv_zip`. Results above 200,000 rows get CSV-zip, Excel and JSON downloads that are built on click. Every format holds every row.
- Charts with more than 20,000 customers show a fixed random sample with a note; the complaint-summary preview shows the first 1,000 customers. Scores and downloads cover everyone.
- Measured on this machine (5,000,000 transactions, 128 MB CSV, about 1 million customers): load 2 s, RFM inputs 5 s, RFM scores 2 s, BG/NBD summaries 7 s, BG/NBD fit and scores 40 s, CSV zip 8 s, JSON 1 s, Excel 55 s; peak memory 1.4 GB.
- Launchers pass `CVA_MAX_UPLOAD_MB` (default 10000) to `--server.maxUploadSize`; the Dockerfile sets `STREAMLIT_SERVER_MAX_UPLOAD_SIZE=10000`. Hub mode (`SIGNAL_HUB=1`) is unchanged.
- New `tests/test_large_data.py` (local mode accepts input above the demo caps, `SIGNAL_PUBLIC=1` enforces each cap, out-of-memory message, Excel sheet split, CSV zip and compact JSON, pooling leaves the fits unchanged, launcher/Docker/config caps); the old 50 MB JSON and row-limit tests are replaced.

### Suite

- Suite: Rival, Reach, Learn and Blueprint Signal added to the suite table; the synced Signal config raises `maxUploadSize` to 10000.

## [1.2.0] - 2026-10-02

Signal brand refresh and Signal Hub entry point. No calculation, data contract or export format changed.

### Brand

- Display name written **Worth Signal** (with a space) in the app, README, docs, issue templates, launchers and metadata. The distribution `customer-value-analytics`, the import package `cva`, `CVA_*` environment variables, the Docker tag and user and file names stay unchanged.
- The app uses the shared `signal_theme` module (Organic Signal design, Customer family colour `#aa5d83`, Figtree): sidebar lockup, masthead, hero, notes, footer, the per-app Plotly template on every chart and the mark as favicon replace the pasted styles.
- New banner, social preview and marks in `assets/`; the old banner and social SVGs and the old mark PNG are removed. `.streamlit/config.toml` uses the family colours and the shared Signal settings; the upload limits are unchanged.
- README follows the Signal template; the issue templates use the new name.
- Embedded Figtree font, no Google Fonts request: the shared theme ships the font as `signal_font.py` and uses a per-family contrast order for chart colours.

### Signal Hub contract

- Opens with the fictional demo preloaded: the generated test workbook (one example sheet per analysis, the same as `examples/quick_test.xlsx`) loads on first run, so every page works without an upload. An upload replaces it; removing the upload returns to the demo. The RFM data-layout choice now defaults to the layout of the chosen sheet.
- `cva.ui` exposes `APP_INFO` and `render()`, so Signal Hub can embed the app; `app.py` is now a thin standalone entry point.
- All session-state and widget keys are namespaced `worth:` (including the page selector). Pages no longer call `st.stop()`.
- `streamlit` and `plotly` moved to a `ui` extra (also in `test`); the analysis core installs without them. `requirements.txt` still lists everything.
- New tests: no Streamlit/Plotly import outside `cva.ui`, the core imports in a fresh interpreter, `render()` runs from a script without a page config and from the packaged files alone (no repo-root `examples/`, `docs/` or `assets/`), every widget key is namespaced, and the shared brand (README template, theme, family colour).

## [1.1.2] - 2026-10-01

A pin point for downstream users (Freddo CRM, the Signal Hub): no change to any calculation.

### Changed

- plotly 7 is allowed (requirement now `>=5.18,<8`).
- CI runs on `actions/setup-python` 7.

### Documentation

- The README links the new sibling apps TagSignal, TraceSignal and TrackSignal.

## [1.1.1] - 2026-07-16

### Security

- Uploads are now size-checked before parsing (200 MB default, 50 MB for JSON, 400 MB unpacked Excel, plus row and cell caps), and the default Streamlit upload limit dropped from 1 GB to 200 MB.
- Excel exports neutralize formula-like text in cell values and column headers, and defusedxml hardens workbook XML parsing.

## [1.1.0] - 2026-07-12

### Added

- WorthSignal product identity, visual system, logo, and repository banner.
- Clear local-versus-hosted privacy guidance.
- Public security policy, changelog, citation metadata, and GitHub contribution templates.

### Changed

- Reworked the first-run experience and public README around practical marketer questions.
- Replaced an unsourced marketing-measurement statistic with precise model-use guidance.
- Updated launchers, package metadata, documentation, and Docker packaging for the WorthSignal brand.
- Raised the per-file upload limit to 1 GB and documented how to handle very large customer files.

## [1.0.0] - 2026-07-11

- Initial open-source-ready customer-value analytics application.
- Excel, CSV, and JSON import; guided templates; Windows and macOS launchers.
- Nine analysis areas, downloadable results, model documentation, examples, and automated tests.
- AGPL-3.0-or-later license.

[Unreleased]: https://github.com/UlrikErlingsen/customer-value-analytics/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/UlrikErlingsen/customer-value-analytics/compare/v1.1.2...v1.2.0
[1.1.2]: https://github.com/UlrikErlingsen/customer-value-analytics/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/UlrikErlingsen/customer-value-analytics/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/UlrikErlingsen/customer-value-analytics/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/UlrikErlingsen/customer-value-analytics/releases/tag/v1.0.0
