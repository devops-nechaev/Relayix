# Upgrade Relayix to 0.6.1 Beta

The deployment uses Compose project `relayix`, PostgreSQL role/database `relayix`, and volume `relayix_db_data`. Users, channel credentials, route addresses and route keys must survive upgrades. Historical applied migrations remain unchanged; the new branding migration updates only the default failure-alert title and existing policies that still use that default.

Private configuration is now outside the checkout at `../private/relayix-config/deployment.json`. It contains the existing values as JSON strings. The local installation's former `.env` has already been moved to `../private/relayix-config/legacy.env` as a private migration backup. Do not put either file in Git.

For another existing installation, transfer the existing settings into an external JSON file before removing its old dotenv file. Preserve the database password, database role/name and project name exactly until a database transfer is complete. `POSTGRES_USER` and `POSTGRES_DB` in the external configuration can select an existing role/database. Do not regenerate credentials for an existing PostgreSQL volume. `config/deployment.example.json` contains only nonsecret defaults, not replacement credentials. Keep the private directory at 700 and files at 600.

Back up with the wrapper, which supplies the private settings without printing them:

```bash
mkdir -p ../private/relayix-backups
chmod 700 ../private/relayix-backups
umask 077
scripts/compose.sh exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "../private/relayix-backups/before-v061-$(date +%Y%m%d-%H%M%S).dump"
```

Set the external JSON's `RELAYIX_IMAGE` to `relayix:0.6.1` (or the matching published GHCR reference), then replace only the app:

```bash
scripts/compose.sh up -d --no-deps app
scripts/compose.sh ps
scripts/compose.sh logs --tail=30 app
curl --fail http://192.168.39.110:8080/healthz
```

Use `RELAYIX_CONFIG_FILE` to select an alternative external JSON file. The wrapper refuses a configuration file inside the source checkout and explicitly disables default `.env` discovery. Do not run `docker compose down -v` on an existing database.

The GitHub deployment workflow reads `production` environment Secrets, creates a private candidate outside the checkout, and uses `scripts/deploy.sh` to back up, pull, replace only the app and check health. Its candidate must retain the active database password. On failure the previous configuration/app is restored; rollback does not restore database data. See [GitHub setup](docs/GITHUB.md).

To roll back this release, select the retained `relayix:0.6.0` image in the private configuration and run `scripts/compose.sh up -d --no-deps app`.

## Rename an existing deployment

Changing a Compose project name selects a different volume. Stop the old application before taking a final `pg_dump -Fc` backup, then start only the target `db` service with project/role/database set to `relayix`. Restore the archive into the empty target database with `pg_restore --no-owner --no-acl --exit-on-error`. Do not start the new app until the restore completes. Compare record counts and configuration before enabling the worker, then check `/healthz`, login and existing routes.

Retain the original stopped containers, volume and private configuration backup until the transferred deployment is verified. A rollback after new writes requires preserving those new writes too; switching to the old volume alone would discard them. Never run `down -v` during this procedure.

The session cookie and local browser-storage keys now use `relayix`. Sign in again after upgrading. Saved account preferences remain in PostgreSQL. Historical migration files deliberately retain their original content because SQLx verifies their checksums.

## Debian Trixie and dependency refresh

The updated application uses Python 3.15.2 on Trixie, built with Rust 1.99.1 and Node.js 26.13.0 LTS. The database image is PostgreSQL 17.11 on Trixie. The PostgreSQL major version remains 17.

Before moving an existing cluster from another base distribution, take a final logical backup while the source app is stopped. Restore into an empty Trixie-initialized database, compare table contents and confirm that existing password hashes authenticate with the updated application. This rebuilds indexes using the target distribution's collation implementation. Keep the source volume and image for rollback rather than attaching the existing cluster to a different libc/locale implementation without checking collation versions.

Persist the transferred volume name in `RELAYIX_DB_VOLUME` and the selected database image in `POSTGRES_IMAGE` in the private JSON. A database rollback must restore the matching image, volume and application configuration together; preserve any writes accepted after cutover.
