# WorthSignal privacy notes

WorthSignal is designed to run locally and does not include user accounts, advertising, product analytics, telemetry, or a customer-data database.

## When you run it on your computer

- Uploaded files are read by the Streamlit process running on that computer.
- Analyses operate in memory and create downloads only when you request them.
- WorthSignal does not intentionally send uploaded customer data to the project maintainer or any third-party API.
- Your original source file is never modified.

The launchers may connect to Python package indexes on first use to install open-source dependencies. That installation traffic does not include your uploaded customer data.

## When someone hosts it

A hosted deployment changes the trust boundary: uploaded files travel to and are processed by the chosen server. The deployment operator, not this repository, controls that server and is responsible for:

- authentication and access control;
- transport security;
- infrastructure and application logs;
- backups, retention, deletion, and incident response;
- notices, consent, contracts, and applicable privacy law.

The WorthSignal code does not add persistent customer-data storage, but a host or its surrounding infrastructure may. Do not upload confidential, personal, or regulated data to a hosted instance unless you trust its operator and understand its controls.

## Reporting a privacy or security concern

Email [code.modular578@passmail.net](mailto:code.modular578@passmail.net) with the subject
`[WorthSignal privacy]`. If GitHub private vulnerability reporting is enabled, its
[private security advisory form](https://github.com/UlrikErlingsen/customer-value-analytics/security/advisories/new)
is also suitable. Do not put sensitive data or an exploitable report in a public issue.
