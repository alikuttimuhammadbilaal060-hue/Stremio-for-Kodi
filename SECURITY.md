# Security Policy

## Supported versions

Security fixes target the latest stable Stremio for Kodi release. Update to the
latest release before checking whether a problem remains. Older releases and
unreleased branches do not receive separate security backports.

MKGA Connector is a separate addon. Include its version when a report involves
pairing, remote commands, or profile installation.

## Reporting a vulnerability

Use GitHub's [private vulnerability reporting form](https://github.com/0eroiQ/Stremio-for-Kodi/security/advisories/new)
for suspected security vulnerabilities. Reports submitted through this form are
visible to the repository maintainers rather than public issue readers.

Include the affected addon and Kodi versions, operating system, impact, and
minimal reproduction steps. Redact Stremio authentication tokens, MKGA access
and pairing tokens, provider URLs containing credentials, API keys, account
information, and device paths. Do not include live credentials in a report.

Avoid public issues for exploit details or sensitive diagnostics. Ordinary bugs
and feature requests belong in [GitHub Issues](https://github.com/0eroiQ/Stremio-for-Kodi/issues).

Maintainers will use the private report to clarify the impact, discuss a fix,
and coordinate disclosure. No fixed response time is currently guaranteed.
