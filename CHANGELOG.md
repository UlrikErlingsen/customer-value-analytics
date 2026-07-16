# Changelog

Notable changes to WorthSignal are documented here. This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/UlrikErlingsen/customer-value-analytics/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/UlrikErlingsen/customer-value-analytics/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/UlrikErlingsen/customer-value-analytics/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/UlrikErlingsen/customer-value-analytics/releases/tag/v1.0.0
