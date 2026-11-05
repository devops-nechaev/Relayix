# Contributing to Relayix

Use a feature branch and describe the problem, final behavior and relevant validation in the pull request. Keep the English UI consistent across light/dark themes and mobile widths.

Run `python3 tests/deploy.py` to verify backup/rollback using fake Docker, then `scripts/check.sh` with Docker and Docker Compose v2. It builds the locked Rust/React application and runs API, queue, SMTP and Chromium checks against temporary databases and local mock providers. It never uses production credentials or sends to real channels. Screenshots and failure logs go to `/tmp/relayix-test-artifacts`.

Database migrations must be additive. Never edit applied migrations, rotate existing route keys or rename existing database volumes as part of a branding change. Preserve existing mailbox and provider configuration formats.

Commit Cargo.lock and web/package-lock.json. Keep private deployment JSON, dotenv files, temporary test credentials, backups, database dumps, credentials, build outputs and browser screenshots out of source control. See [GitHub setup](docs/GITHUB.md) for CI and releases.
