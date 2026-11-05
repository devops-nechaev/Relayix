# Reporting security issues

Do not include live tokens, webhook keys, channel configurations or database dumps in public issues. Use the repository's private vulnerability reporting feature when enabled, or contact its maintainer privately.

Administrators should retain database backups before upgrades, use HTTPS for public deployments and configure `COOKIE_SECURE=true` behind HTTPS. Keep PostgreSQL private and the external deployment JSON readable only by its owner. Production credentials belong in GitHub environment Secrets and external private runtime configuration; test credentials must be generated per run. The Docker image runs as an unprivileged user.
