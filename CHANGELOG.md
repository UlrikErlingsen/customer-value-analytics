# Changelog

Notable changes to Worth Signal are documented here. This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.2.0] - 2026-10-02

Signal brand refresh and Signal Hub entry point. No calculation, data contract or export format changed.

### Brand

- Display name written **Worth Signal** (with a space) in the app, README, docs, issue templates, launchers and metadata. The distribution `customer-value-analytics`, the import package `cva`, `CVA_*` environment variables, the Docker tag and user and file names stay unchanged.
- The app uses the shared `signal_theme` module (Organic Signal design, Customer family colour `#aa5d83`, Figtree): sidebar lockup, masthead, hero, notes, footer, the per-app Plotly template on every chart and the mark as favicon replace the pasted styles.
- New banner, social preview and marks in `assets/`; the old banner and social SVGs and the old mark PNG are removed. `.streamlit/config.toml` uses the family colours and the shared Signal settings, which lower the standalone Streamlit upload limit to 50 MB (the parser limit `CVA_MAX_UPLOAD_MB` still defaults to 200 MB; raise both to accept larger files).
- README follows the Signal template; the issue templates use the new name.

### Signal Hub contract

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
