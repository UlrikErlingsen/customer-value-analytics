# Security policy

## Supported version

Security fixes are made on the latest `main` branch. The project does not currently maintain older release branches.

## Report a vulnerability privately

Email [code.modular578@passmail.net](mailto:code.modular578@passmail.net) with the subject
`[WorthSignal security]`. If GitHub private vulnerability reporting is enabled for the public
repository, you may instead use its [private security advisory form](https://github.com/UlrikErlingsen/customer-value-analytics/security/advisories/new).
Please include:

- the affected version or commit;
- clear reproduction steps;
- the expected impact;
- a suggested fix, if you have one.

Please do not open a public issue for an unpatched vulnerability and never attach real customer data, credentials, or other secrets. Reports will be reviewed on a best-effort basis; this volunteer project does not promise a formal response-time SLA.

## Deployment responsibility

WorthSignal is local-first. If you expose it over a network, you are responsible for authentication, TLS, network controls, dependency updates, data handling, and server hardening. Read [PRIVACY.md](PRIVACY.md) before accepting uploads on a hosted deployment.
