//! Database configuration for normal environment-based Docker deployments.
use anyhow::{anyhow, Result};
use sqlx::postgres::{PgConnectOptions, PgSslMode};
use std::{env, str::FromStr};

pub fn options() -> Result<PgConnectOptions> {
    from_settings(|name| env::var(name).ok())
}

fn from_settings(get: impl Fn(&str) -> Option<String>) -> Result<PgConnectOptions> {
    // Preserve existing deployments and integrations that supply a full URL.
    if let Some(url) = get("DATABASE_URL").filter(|value| !value.is_empty()) {
        return PgConnectOptions::from_str(&url)
            .map_err(|_| anyhow!("Invalid DATABASE_URL; connection details omitted"));
    }
    let value = |name: &str, default: &str| get(name).filter(|v| !v.is_empty()).unwrap_or_else(|| default.to_owned());
    let mode = value("DATABASE_MODE", "local");
    if mode != "local" && mode != "external" {
        return Err(anyhow!("DATABASE_MODE must be local or external"));
    }
    let local = mode == "local";
    let host = if local { "db".to_owned() } else { value("POSTGRES_HOST", "").trim().to_owned() };
    let host = host.trim_start_matches('[').trim_end_matches(']');
    if host.is_empty() || host.chars().any(|c| c.is_whitespace() || "/@?#\\".contains(c)) {
        return Err(anyhow!("POSTGRES_HOST must be a hostname or IP address"));
    }
    if host.contains(':') && host.parse::<std::net::Ipv6Addr>().is_err() {
        return Err(anyhow!("POSTGRES_HOST must contain only a hostname or IP; set POSTGRES_PORT separately"));
    }
    let port = if local { 5432 } else {
        value("POSTGRES_PORT", "5432").parse::<u16>()
            .ok().filter(|port| *port > 0)
            .ok_or_else(|| anyhow!("POSTGRES_PORT must be between 1 and 65535"))?
    };
    let password = value("POSTGRES_PASSWORD", "");
    if password.is_empty() {
        return Err(anyhow!("POSTGRES_PASSWORD is required"));
    }
    let sslmode = if local { PgSslMode::Disable } else {
        PgSslMode::from_str(&value("POSTGRES_SSLMODE", "verify-full"))
            .map_err(|_| anyhow!("Invalid POSTGRES_SSLMODE"))?
    };
    let mut options = PgConnectOptions::new()
        .host(host).port(port)
        .username(&value("POSTGRES_USER", "relayix"))
        .database(&value("POSTGRES_DB", "relayix"))
        .password(&password).ssl_mode(sslmode);
    if !local {
        if let Some(ca) = get("POSTGRES_SSLROOTCERT").filter(|v| !v.is_empty()) {
            if !std::path::Path::new(&ca).is_file() {
                return Err(anyhow!("PostgreSQL CA certificate file is unavailable"));
            }
            options = options.ssl_root_cert(ca);
        }
    }
    Ok(options)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn settings(values: &[(&str, &str)]) -> Result<PgConnectOptions> {
        let values: HashMap<_, _> = values.iter().copied().collect();
        from_settings(|name| values.get(name).map(|v| v.to_string()))
    }

    #[test]
    fn modes_and_url_compatibility() {
        let local = settings(&[("POSTGRES_PASSWORD", "test-only"), ("POSTGRES_HOST", "ignored")]).unwrap();
        assert_eq!(local.get_host(), "db");
        assert!(matches!(local.get_ssl_mode(), PgSslMode::Disable));
        let remote = settings(&[("POSTGRES_PASSWORD", "test-only"), ("DATABASE_MODE", "external"),
            ("POSTGRES_HOST", "[::1]"), ("POSTGRES_PORT", "6543")]).unwrap();
        assert_eq!(remote.get_host(), "::1");
        assert_eq!(remote.get_port(), 6543);
        assert!(matches!(remote.get_ssl_mode(), PgSslMode::VerifyFull));
        let url = settings(&[("DATABASE_URL", "postgres://relayix@compat.example/relayix?sslmode=disable")]).unwrap();
        assert_eq!(url.get_host(), "compat.example");
    }

    #[test]
    fn invalid_settings_do_not_expose_credentials() {
        for (key, value) in [("DATABASE_MODE", "invalid"), ("POSTGRES_HOST", "https://invalid"),
            ("POSTGRES_PORT", "0"), ("POSTGRES_PORT", "65536"), ("POSTGRES_SSLMODE", "invalid"),
            ("POSTGRES_SSLROOTCERT", "/missing/relayix-test-ca.crt")] {
            let mut values = vec![("DATABASE_MODE", "external"), ("POSTGRES_HOST", "db.example"),
                ("POSTGRES_PASSWORD", "test-only")];
            values.retain(|(name, _)| *name != key);
            values.push((key, value));
            let error = settings(&values).unwrap_err().to_string();
            assert!(!error.contains("test-only"));
        }
    }
}
