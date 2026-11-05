# GitHub setup and delivery

The checkout is prepared for a repository named `relayix`. The workflows derive the registry name from `github.repository`; no owner name or registry password is stored in the source.

## First publication

The local origin is connected to https://github.com/devops-nechaev/Relayix.git and based on its existing LICENSE commit. Once the checks and review are complete, publish from this directory:

```bash
git remote -v  # origin: https://github.com/devops-nechaev/Relayix.git
git add .
git diff --cached --stat
git commit -m "Prepare Relayix 0.6.1 Beta"
git push -u origin main
```

Private configuration, local backups, dumps, image exports and generated outputs are ignored. Review staged files before the first commit. Relayix original source is Apache-2.0; preserve LICENSE, NOTICE, LICENSES and THIRD_PARTY_NOTICES.md when distributing. Review the third-party inventory and run the secret checks before publication.

In repository settings enable Actions and Packages. Protect `main` and require the `verify` job before merging. Enable private vulnerability reporting and secret scanning if available. Dependabot is configured for Rust, npm and Actions.

## Continuous integration

`Verify` runs on pull requests, pushes to `main` and manual dispatch. It builds the Docker image with `cargo test --locked --release`, compiles the React app using `npm ci`, and runs `scripts/check.sh --skip-app-build`. Tests use an isolated PostgreSQL, local SMTP/HTTP mocks and Chromium. Test resources are cleaned up even on failure. Screenshots and failure logs are uploaded for seven days. Fork PRs run without registry publishing credentials.

## Continuous delivery

When a tested version is ready:

```bash
git tag v0.6.1
git push origin v0.6.1
```

`Release Docker image` runs the complete CI again, checks that the tag agrees with both Cargo and npm versions, and publishes `ghcr.io/devops-nechaev/relayix:0.6.1` and `:beta`. It uses the repository-scoped `GITHUB_TOKEN` with `packages:write`; no personal token is required for publication. It includes source/revision labels, build provenance and an SBOM. Tags are beta releases; the pipeline deliberately does not label them `latest`.

Container package visibility is controlled in GitHub Packages. For anonymous pulls set the package public. For private pulls authenticate on the deployment host with a token allowed to read that package; do not commit the credential.

## Deployment configuration and GitHub Secrets

Create the `production` GitHub environment with required reviewers and restrict deployments to the default branch. Keep Compose project `relayix` and the data volume selected by `RELAYIX_DB_VOLUME` for an existing installation.

Store these **Secrets** in the production environment:

| Name | Existing private configuration field |
| --- | --- |
| `RELAYIX_POSTGRES_PASSWORD` | `POSTGRES_PASSWORD` |
| `RELAYIX_ADMIN_TOKEN` | `ADMIN_TOKEN` |
| `RELAYIX_ADMIN_PASSWORD` | `ADMIN_PASSWORD` (bootstrap credential) |

Use the current values. Do not generate a new database password for an existing database. With an authenticated GitHub CLI, `python3 scripts/sync_github_secrets.py` uploads these values directly from the external private configuration over stdin, without placing them in shell history or printing them. It preserves existing environment protection settings. This command needs access to manage environment Secrets; source preparation alone does not create them remotely.

Use **Variables** for nonsecret configuration:

- `RELAYIX_DEPLOY_DIR`: absolute source/deployment directory.
- `RELAYIX_CONFIG_FILE`: optional absolute private JSON path (default `../private/relayix-config/deployment.json` relative to the checkout).
- `RELAYIX_COMPOSE_PROJECT`: `relayix` for this existing installation.
- `RELAYIX_HEALTH_URL`: `http://192.168.39.110:8080/healthz` for this installation.
- Optional `RELAYIX_ADMIN_USERNAME`, `RELAYIX_BIND_ADDRESS`, `RELAYIX_PORT`, `RELAYIX_COOKIE_SECURE` override their existing nonsecret values.

`Deploy release` is a manual workflow on the default branch, targeting a dedicated Linux x64 runner labelled `relayix-deploy`. That trusted runner needs Docker Compose v2, Bash and Python 3 and access to the deployment host. Pull requests and CI run on GitHub-hosted runners, not that server.

The workflow renders a candidate JSON from Secrets/Variables in `RUNNER_TEMP`, then backs up the active private configuration/database, pulls the image, checks that the candidate database password agrees with the existing one, replaces only the app and verifies health. On failure it restores the previous app configuration. It removes the temporary candidate and registry login afterwards. Active private configuration remains outside the checkout for service restarts and backup operations.

For manual operation, use `scripts/compose.sh`; it loads the private JSON into the Docker process environment and disables dotenv discovery. There is no production `.env` in the repository. Deployment credentials must not be put into repository Variables, workflow YAML, image build arguments, test fixtures or CI artifacts.

After connection/publication, run CI once in GitHub to validate account/runner settings. See [publication checks](PUBLICATION.md). Source preparation and local tests do not publish files or configure remote Secrets automatically.

References: [GitHub Actions secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions), [GitHub container publishing](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images).

## Bundled or external PostgreSQL

The normal startup guide is [DEPLOYMENT.md](DEPLOYMENT.md). All database fields live in the private JSON. `DATABASE_MODE=local` selects the bundled database; `external` uses `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD` and TLS settings without creating a database service or volume. The workflow retains those fields from the active base configuration. `RELAYIX_POSTGRES_PASSWORD` must match the existing database password in either mode.

The deployment script backs up either database through the one-off `db-tools` client before replacing the app. Select `POSTGRES_CLIENT_IMAGE` for the external server's major version if needed. A candidate cannot silently change database mode/host/port/user/name; perform an explicit backup/restore transfer before changing the active destination. Optional `POSTGRES_SSLROOTCERT` paths refer to files already present on the deployment host, not on the GitHub-hosted build runner.
