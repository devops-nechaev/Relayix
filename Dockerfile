FROM node:26.13.0-trixie-slim AS web-builder
WORKDIR /web
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM rust:1.99.1-trixie AS rust-builder
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src src
COPY migrations migrations
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/app/target \
    cargo test --locked --release && cargo build --locked --release && cp target/release/relayix /app/relayix

FROM python:3.15.2-slim-trixie
RUN apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin relayix
COPY transport/requirements.txt /app/transport/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /app/transport/requirements.txt
COPY transport/telegram_send.py transport/faketls.py /app/transport/
COPY transport/vendor /app/transport/vendor
COPY --from=rust-builder /app/relayix /usr/local/bin/relayix
COPY --from=web-builder /web/dist /app/web/dist
COPY LICENSE NOTICE THIRD_PARTY_NOTICES.md /usr/share/doc/relayix/
COPY LICENSES /usr/share/doc/relayix/licenses/
WORKDIR /app
USER 10001
LABEL org.opencontainers.image.title="Relayix" org.opencontainers.image.version="0.6.3" org.opencontainers.image.licenses="Apache-2.0"
EXPOSE 8080
CMD ["/usr/local/bin/relayix"]
