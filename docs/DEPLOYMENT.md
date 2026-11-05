# Run Relayix with Docker Compose

Requirements: Docker Engine with Docker Compose v2.20 or newer. No source checkout, Python, Rust or Node.js is needed on the server. The published image includes the application and web UI.

## Bundled PostgreSQL

Download two files into an empty directory:

```bash
mkdir relayix && cd relayix
curl -fL https://github.com/devops-nechaev/Relayix/releases/download/v0.6.3/compose.yaml -o compose.yaml
curl -fL https://github.com/devops-nechaev/Relayix/releases/download/v0.6.3/relayix.env.example -o .env
```

Open `.env` in your preferred editor. Set these two values:

| Setting | What to enter |
| --- | --- |
| `POSTGRES_PASSWORD` | A new password for the bundled database |
| `ADMIN_PASSWORD` | Your Relayix login password: 12–128 characters, uppercase/lowercase letters, a number and a symbol |

Keep passwords inside single quotes, for example `ADMIN_PASSWORD='your own password here'`. Single quotes preserve `$`, `#` and spaces literally. Avoid a single quote inside a single-quoted value. The application accepts database passwords as written, including URL-reserved characters.

Start the service:

```bash
chmod 600 .env
docker compose up -d
```

Compose pulls the ready-made images, starts PostgreSQL, waits for it to become ready and starts Relayix. Open **`http://SERVER_IP:8080`** in your browser and sign in as **`admin`** with your `ADMIN_PASSWORD`. Schema migrations and the initial administrator account are created automatically. The first startup may take a few minutes while images download.

The containers are named `relayix-app` and `relayix-db` and share `relayix-network`. PostgreSQL is available only inside that network. Its data persists in a named Docker volume.

## Existing external PostgreSQL

Create the database and login role on your PostgreSQL server first. The role must be able to create and alter objects in that database.

Use the **same `compose.yaml` and `.env` downloaded above**. Set `DATABASE_MODE=external` in `.env`; no additional Compose files are needed.

In `.env`, set `ADMIN_PASSWORD` and your existing database connection settings:

| Setting | Example / purpose |
| --- | --- |
| `DATABASE_MODE` | `external` to disable the bundled PostgreSQL service |
| `POSTGRES_HOST` | `postgres.example.org`, an IP address, or the Docker host's LAN IP for PostgreSQL on the Docker host |
| `POSTGRES_PORT` | `5432` |
| `POSTGRES_USER` | Existing database login role |
| `POSTGRES_DB` | Existing database name |
| `POSTGRES_PASSWORD` | That role's existing password |
| `POSTGRES_SSLMODE` | `verify-full` for verified TLS; explicitly set `disable` for a LAN database configured without TLS |

Enter a hostname or IP in `POSTGRES_HOST`, without a URL scheme or port. `localhost` refers to the app container; use the Docker host's LAN IP for the Docker host. A host database must listen on an interface reachable from Docker and allow the Docker subnet in its firewall and `pg_hba.conf`.

```bash
chmod 600 .env
docker compose up -d
```

Open `http://SERVER_IP:8080` and sign in as `admin`. In external mode, only Relayix starts; the bundled PostgreSQL service is disabled.

### TLS and a private CA

Set these values in the same `.env` file:

```dotenv
POSTGRES_SSLMODE=verify-full
POSTGRES_CA_PATH=/srv/relayix/postgres-ca.crt
```

`POSTGRES_CA_PATH` is the path to the CA certificate **on the Docker host**; a relative path such as `./postgres-ca.crt` also works. The file must exist and be readable by container user 10001. Compose mounts it read-only; no overlay file or extra command-line flags are needed. The database hostname must match the server certificate.

Leave `POSTGRES_CA_PATH` empty to use the image's system trust store. For a LAN database configured without TLS, explicitly set `POSTGRES_SSLMODE=disable` and leave the CA path empty.

Apply either configuration with:

```bash
docker compose up -d
```

## Optional settings

All settings go in `.env`; no JSON generator is needed.

| Setting | Default | Purpose |
| --- | --- | --- |
| `DATABASE_MODE` | `local` | `local` starts bundled PostgreSQL; `external` uses your existing server |
| `POSTGRES_CA_PATH` | Empty | Optional host path to a PostgreSQL CA certificate |
| `ADMIN_USERNAME` | `admin` | Initial administrator username |
| `BIND_ADDRESS` | `0.0.0.0` | Listen on all host interfaces; use `127.0.0.1` for host-only access |
| `PORT` | `8080` | Web UI and webhook port on the Docker host |
| `COOKIE_SECURE` | `false` | Set `true` when serving the UI behind HTTPS |
| `ADMIN_TOKEN` | Empty | Optional administrator API token for automation |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | Empty | Only needed for Telegram MTProto / WEB proxies; ordinary Bot API delivery does not need them |
| `ALLOW_INSECURE_HTTP` | `false` | Allow HTTP notification destinations and unencrypted SMTP when explicitly enabled |
| `RUST_LOG` | `relayix=info` | Application log filter |

`ADMIN_PASSWORD` bootstraps a new account. Change an existing account's password in the UI. Changing `POSTGRES_PASSWORD` in `.env` does not change the password in an initialized PostgreSQL database.

The `.env` file contains credentials. Keep it on the deployment host and outside source control. The repository ignores `.env` files; the downloadable template contains no credentials.

## Existing installations using the previous standalone files

Replace your downloaded `compose.yaml` with the current release download and keep your existing `.env`, passwords and project directory. Add these lines to `.env`:

```dotenv
DATABASE_MODE=local
COMPOSE_PROFILES=${DATABASE_MODE}
```

For an existing external database, use `DATABASE_MODE=external` and retain its connection settings. Replace the former TLS overlay with `POSTGRES_CA_PATH` in `.env`. Then run `docker compose up -d` with no `-f` flags. The bundled database keeps its existing named volume. Switching database locations does not copy data between them.

## Updating

Change the app image tag in your `compose.yaml`, then run:

```bash
docker compose pull app
docker compose up -d --no-deps app
```

Migrations run automatically. Keep `.env`, the directory/project name and database volume unchanged. Updating the app does not require changing the PostgreSQL image.

## Logs and status

```bash
docker compose ps
docker compose logs -f app
```

After editing `.env`, run `docker compose up -d` to apply changes. To stop containers, use `docker compose stop`; `docker compose up -d` starts them again. Do not use `docker compose down -v` when retaining database data.

Existing private-JSON installations and GitHub-hosted deployment settings are documented in [the advanced deployment guide](DEPLOYMENT_ADVANCED.md) and [GitHub delivery](GITHUB.md). They continue to use their existing configuration and volume; downloading a new Compose file does not migrate data between installations.
