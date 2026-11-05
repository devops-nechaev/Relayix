# Run Relayix with Docker Compose

Requirements: Docker Engine with Docker Compose v2. No source checkout, Python, Rust or Node.js is needed on the server. The published image includes the application and web UI.

## Bundled PostgreSQL

Download two files into an empty directory:

```bash
mkdir relayix && cd relayix
curl -fL https://github.com/devops-nechaev/Relayix/releases/download/v0.6.2/compose.yaml -o compose.yaml
curl -fL https://github.com/devops-nechaev/Relayix/releases/download/v0.6.2/relayix.env.example -o .env
```

Open `.env` in your preferred editor. Set these two values:

| Setting | What to enter |
| --- | --- |
| `POSTGRES_PASSWORD` | A new password for the bundled database |
| `ADMIN_PASSWORD` | Your Relayix login password: 12–128 characters, uppercase/lowercase letters, a number and a symbol |

Keep passwords inside single quotes, for example `ADMIN_PASSWORD='your own password here'`. Single quotes preserve `$`, `#` and spaces literally. Avoid a single quote inside a single-quoted value. Database passwords are URL-encoded automatically inside the container.

Start the service:

```bash
chmod 600 .env
docker compose up -d
```

Compose pulls the ready-made images, starts PostgreSQL, waits for it to become ready and starts Relayix. Open **`http://SERVER_IP:8080`** in your browser and sign in as **`admin`** with your `ADMIN_PASSWORD`. Schema migrations and the initial administrator account are created automatically. The first startup may take a few minutes while images download.

PostgreSQL is available only inside the Compose network. Its data persists in a named Docker volume.

## Existing external PostgreSQL

Create the database and login role on your PostgreSQL server first. The role must be able to create and alter objects in that database.

Download the external Compose file **as `compose.yaml`** into a new directory:

```bash
mkdir relayix && cd relayix
curl -fL https://github.com/devops-nechaev/Relayix/releases/download/v0.6.2/compose.external.yaml -o compose.yaml
curl -fL https://github.com/devops-nechaev/Relayix/releases/download/v0.6.2/relayix.env.example -o .env
```

In `.env`, set `ADMIN_PASSWORD` and your existing database connection settings:

| Setting | Example / purpose |
| --- | --- |
| `POSTGRES_HOST` | `postgres.example.org`, an IP address, or `host.docker.internal` for PostgreSQL on the Docker host |
| `POSTGRES_PORT` | `5432` |
| `POSTGRES_USER` | Existing database login role |
| `POSTGRES_DB` | Existing database name |
| `POSTGRES_PASSWORD` | That role's existing password |
| `POSTGRES_SSLMODE` | `verify-full` for verified TLS; explicitly set `disable` for a LAN database configured without TLS |

Enter a hostname or IP in `POSTGRES_HOST`, without a URL scheme or port. `localhost` refers to the app container; use `host.docker.internal` for the Docker host. A host database must listen on an interface reachable from Docker and allow the Docker subnet in its firewall and `pg_hba.conf`.

```bash
chmod 600 .env
docker compose up -d
```

Open `http://SERVER_IP:8080` and sign in as `admin`. This Compose file starts only Relayix; it creates no PostgreSQL container or database volume.

For a provider with a private CA, save its certificate as `postgres-ca.crt` in the same directory, readable by container user 10001, and download the optional overlay:

```bash
curl -fL https://github.com/devops-nechaev/Relayix/releases/download/v0.6.2/compose.tls.yaml -o compose.tls.yaml
docker compose -f compose.yaml -f compose.tls.yaml up -d
```

Keep `POSTGRES_SSLMODE=verify-full`; the hostname must match the certificate. Use both `-f` arguments for subsequent operations with this overlay.

## Optional settings

All settings go in `.env`; no JSON generator is needed.

| Setting | Default | Purpose |
| --- | --- | --- |
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
