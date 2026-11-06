# Changelog

## 0.7.1 Beta — 2026-11-06

- Keep attempt counts in Attempts and move the Details action into its own column.
- Add account-persisted column visibility and click-to-sort headers to every table. Event/delivery/alert sorting runs on the server before result limits and pagination; default to newest first.
- Run Telegram diagnostics immediately from the channel or edit form and display compact inline stages with green/red icons; remove the separate dialog and redundant permissions warning. Known permission failures are reported as chat-access failures.
- Highlight fallback recipient settings in the route editor and explicitly describe the five-attempt trigger.

## 0.7.0 Beta — 2026-11-05

- Add searchable, paginated incoming webhook history, including accepted events with no queued deliveries and their original routing decisions.
- Preview route decisions without storing events or sending messages.
- Preserve delivery attempt counts and detailed attempt history across manual retries; show attempt errors, timings and fallback status.
- Configure explicit fallback recipients per route. After a primary delivery exhausts five attempts, queue each fallback once per event without recursive fallback.
- Support route-scoped Idempotency-Key headers with concurrent duplicate suppression and conflict detection for changed payloads.
- Add read-only Telegram diagnostics for proxy transport, credentials, destination access and permission checks, without sending messages or exposing credentials.
- Validate startup settings and report actionable database authentication, TLS, network and configuration errors without connection credentials.

## 0.6.4 Beta — 2026-11-05

- Distinguish plain MTProxy secrets from dd/ee markers by their full length and preserve raw keys beginning with those bytes; cover each prefix deterministically.

- Keep webhook priority and tags optional (default priority 3 and empty tags). Route tags are UI labels only and never gate delivery; history filters match route labels or message tags. Preserve the legacy required_tag API field as UI metadata.
- Return routing diagnostics with queue counts, matched filters and per-recipient exclusion reasons, and correlate routing decisions in service logs without exposing credentials or message bodies.
- Add Test webhook to Routes, with priority, optional comma-separated tags, JSON copying, real event submission and a link to delivery results.

- Focus the first editable field when opening a dialog and restore focus without scrolling when closing it. Use an explicit input line height for consistent caret alignment.
- Show page-level feedback in a fixed notification stack so manual refresh, failures and notification dismissal keep the page in place. Stabilize scrollbar space and the refresh timestamp width.
- Cover field focus and keyboard input at 150% scale, and verify page/header/scroll geometry during manual and automatic refresh.

## 0.6.3 Beta — 2026-11-05

- Use one root `compose.yaml` with only the application and optional PostgreSQL services. Select local/external PostgreSQL and TLS in `.env`.
- Read database settings natively in the application; remove inline Python, mode-specific overlays and the database-tools service.
- Name the containers `relayix-app` and `relayix-db` and their shared network `relayix-network`; preserve existing named database volumes.
- Align the README, setup guide and downloadable release bundle with the single Compose configuration.

- Preserve every byte of FakeTLS keys beginning with `dd` or `ee` when passing them to Telethon; cover both prefixes with deterministic wire tests.

## 0.6.2 Beta — 2026-11-05

- Distribute standalone Compose files and a blank environment template with the release: download, set two passwords and run `docker compose up -d`; no source build or host Python is needed.

- Use Debian Trixie throughout application, build and test images with Rust 1.99.1, Node.js 26.13.0 LTS, Python 3.15.2 and PostgreSQL 17.11.
- Update stable Rust and npm dependencies, regenerate Python locks for Python 3.15, and refresh dependency licenses and Playwright.
- Support bundled, external and host PostgreSQL through one private settings file, including custom CA certificates and database backup tools.
- Keep the application image in `compose.app.yaml`; update by changing its tag and recreating only the app. Preserve database settings and data volumes.
- Provide English-only setup and release documentation, presentation screenshots and tested local/external/TLS startup examples.
- Compact channel rows and use the official Mattermost logomark with its source notice.
- Configure Telegram application credentials once per server and resolve bot destinations without manually entered access hashes.
- Complete Relayix naming across Compose, database defaults, browser storage and session cookies while preserving applied migrations.

## 0.6.1 Beta — 2026-11-04

- Add real ee FakeTLS for MTProto with validated SNI, authenticated ClientHello/server HMAC, TLS record framing and explicit rejection without downgrade. WEB remains plain/dd.
- Remove deployment .env and .env.example from the checkout. Load an external owner-only JSON through a Compose wrapper; disable automatic dotenv discovery.
- Render deployment candidates from GitHub production Secrets and Variables, reject database-password mismatches, and retain backup/rollback behavior.
- Generate shared test admin/database/provider/proxy credentials for every run in a temporary external directory, mask them in GitHub logs, and remove them on cleanup. Remove fixed credentials from Python/Rust tests.

## 0.6.0 Beta — 2026-11-04

- Add per-channel authenticated HTTP proxies for HTTP integrations and SMTP CONNECT; preserve TLS verification and refuse silent direct fallback.
- Add Telegram MTProto (plain/dd) and WEB-proxy transport with in-memory bot sessions, per-attempt deadlines, API credentials, topic mapping and safe errors. Explicitly reject unsupported FakeTLS ee secrets and WEB base paths.
- Include destination service identity/icons in dashboard and delivery history.
- Move existing private backups outside the source checkout and keep schema migrations tracked.
- Add Apache-2.0 license metadata, NOTICE, collected dependency licenses and publication documentation.
- Add exact local-credential checks, Gitleaks source/history gates in CI and preserve a narrow public-placeholder exception.

## 0.5.1 Beta — 2026-11-04

- Add dismiss buttons to all success/error banners and a per-account auto-close timeout in My profile (8 seconds by default, 0 for manual dismissal); pause timers on hover/focus.
- Add a separate SMTP sender name with Unicode support, legacy From mailbox compatibility and control-character validation.
- Explain route priority levels, threshold behavior and the default message priority in route forms.
- Remove the sidebar description and login description/badges; keep sign-in compact.
- Rename the project directory to relayix while preserving the existing Compose project and PostgreSQL volume.
- Prepare GitHub CI with locked dependencies, Rust/API/SMTP/Chromium checks, test artifacts, and gated GHCR release delivery. Add contribution/security documentation and Dependabot.

## 0.5.0 Beta — 2026-11-04

- Rename the application to Relayix with a violet routing mark, new login branding, calmer light/dark surfaces and responsive route cards.
- Add seven account-persisted dashboard periods from five minutes to thirty days; apply the period to metrics, recent deliveries and linked history filters.
- Consolidate endpoints, key rotation, recipient details and a copyable tagged request example in Routes; remove the API Tokens page.
- Label route tags simply as Tag and show recipients in a dedicated block with service icons and delivery methods.
- Support Mattermost bot / personal access tokens for channel posts and direct messages, preserving webhook compatibility and masked credentials. Use the official Mattermost logomark.
- Preserve existing PostgreSQL volume, users, sessions, routes, webhook addresses, credentials and keys on upgrade.

## 0.4.1 Beta — 2026-11-04

- Store theme, refresh interval, delivery/tag filters, route tag filter, search and page size in account preferences; keep account and API-token preferences isolated.
- Add configurable 5–3600 second monitoring refresh and an off setting. Show save failures and support retrying them.
- Generate route webhook addresses automatically and preserve existing addresses when renaming routes.
- Show full selectable endpoints and display key/endpoint clipboard feedback inside the key dialog.
- Display actual delivery tags and route required-tag badges; add exact tag filters and suggestions.
- Add Beta branding on the login screen, application header and browser title.
- Remove the two dashboard callout cards.
- Remove image/source bundles, generated reports and screenshots from the source tree; keep build/test outputs outside the repository and retain Docker images in Docker.

## 0.4.0 — 2026-11-04

- Ship a versioned Docker image and image-only Compose deployment; provide native Docker image export for transfer.
- Add username/password authentication, Argon2id hashes, expiring HttpOnly sessions, login throttling, user management and administrator/member roles.
- Replace the avatar placeholder with an account menu, personal profile, password changes and session revocation.
- Make Refresh show progress, update time, success/errors and fetch uncached data. Update independent resources even if one request fails.
- Add dashboard failed/retrying counters and links to filtered delivery history.
- Add configurable failure rules with watched routes/channels, recipients, thresholds, minimum attempts, time windows, cooldown and editable warning text.
- Deliver failure warnings through a separate persistent queue with history/retries and protection against recursive warnings.
- Support optional Telegram topic IDs.
- Filter and paginate deliveries on the server by status, channel, route, dates and text; show attempts and expandable errors.
- Disable Templates UI, API and message expansion while retaining historical database rows.
- Preserve existing channel credentials, routes, webhook keys and PostgreSQL volume with an additive migration.

## 0.3.0 — 2026-11-04

- Add local SVG service icons to channel cards, integration selection and route recipients.
- Group all 13 integrations into Chat & Messaging, Push Notifications, Email and Other.
- Add Matrix delivery with bot access tokens, safe room path encoding and stable transaction IDs on retries. Refuse encrypted rooms.
- Add Email (SMTP) with STARTTLS, implicit TLS, optional authentication, sender and recipient configuration.
- Mask new credentials and Pushover user keys; preserve unchanged secrets when editing channels.
- Show server validation errors inside channel forms and expose channel deletion on cards.
- Include application version in `/healthz`, update upgrade instructions, and add Rust, HTTP/SMTP queue and browser checks.
- Keep existing database migrations, route URLs, keys and channel settings compatible with v0.1/v0.2.
