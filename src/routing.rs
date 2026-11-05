//! Shared webhook routing and diagnostics, including authenticated UI tests.
use crate::{auth, db_error, err, hash, ApiResult, AppState};
use axum::{extract::{Path, State}, http::{HeaderMap, StatusCode}, Json};
use serde::Serialize;
use serde_json::{json, Value};
use sqlx::FromRow;
use subtle::ConstantTimeEq;
use uuid::Uuid;

#[derive(FromRow)]
struct Endpoint {
    id: Uuid,
    name: String,
    enabled: bool,
    min_priority: i32,
    required_tag: Option<String>,
    token_hash: String,
}

struct Event {
    title: String,
    message: String,
    priority: i32,
    tags: Vec<String>,
}

fn parse_event(payload: &Value) -> Result<Event, &'static str> {
    if !payload.is_object() { return Err("Webhook payload must be a JSON object"); }
    let title = payload.get("title").and_then(Value::as_str)
        .or_else(|| payload.get("alertname").and_then(Value::as_str)).unwrap_or("Notification").to_owned();
    let message = payload.get("message").or_else(|| payload.get("body"))
        .and_then(Value::as_str).unwrap_or(&title).to_owned();
    let priority = match payload.get("priority") {
        None | Some(Value::Null) => 3,
        Some(value) => value.as_i64().ok_or("priority must be an integer")?.clamp(1, 5) as i32,
    };
    let tags = match payload.get("tags") {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::Array(values)) => values.iter().map(|value| {
            value.as_str().map(|tag| tag.trim().to_owned()).ok_or("tags must be an array of strings")
        }).collect::<Result<Vec<_>, _>>()?,
        _ => return Err("tags must be an array of strings or omitted"),
    };
    if title.len() > 256 || message.len() > 10000 { return Err("Title or message is too long"); }
    if tags.len() > 32 || tags.iter().any(|tag| tag.is_empty() || tag.len() > 64) {
        return Err("Use at most 32 nonempty tags, each at most 64 bytes");
    }
    Ok(Event { title, message, priority, tags })
}

#[derive(FromRow)]
struct Destination { id: Uuid, name: String, kind: String, enabled: bool }

#[derive(Serialize)]
struct Recipient {
    id: Uuid,
    name: String,
    kind: String,
    enabled: bool,
    queued: bool,
    reason: &'static str,
}

#[derive(Serialize)]
struct Report {
    route_id: Uuid,
    route_name: String,
    matched: bool,
    reason: &'static str,
    route_enabled: bool,
    priority: i32,
    min_priority: i32,
    priority_match: bool,
    required_tag: Option<String>,
    tags_match: bool,
    destinations: usize,
    active_destinations: usize,
    recipients: Vec<Recipient>,
}

fn report(endpoint: &Endpoint, event: &Event, destinations: Vec<Destination>) -> Report {
    let required = endpoint.required_tag.as_deref().map(str::trim).filter(|tag| !tag.is_empty());
    let priority_match = event.priority >= endpoint.min_priority;
    let tags_match = required.map(|required| event.tags.iter().any(|tag| tag == required)).unwrap_or(true);
    let matched = endpoint.enabled && priority_match && tags_match;
    let total = destinations.len();
    let active = destinations.iter().filter(|destination| destination.enabled).count();
    let reason = if !endpoint.enabled { "route_disabled" }
        else if !priority_match { "priority_below_minimum" }
        else if !tags_match { "tag_mismatch" }
        else if total == 0 { "no_destinations" }
        else if active == 0 { "no_active_destinations" }
        else { "queued" };
    let recipients = destinations.into_iter().map(|destination| {
        let queued = matched && destination.enabled;
        let recipient_reason = if !destination.enabled { "destination_disabled" }
            else if queued { "queued" } else { reason };
        Recipient { id: destination.id, name: destination.name, kind: destination.kind,
            enabled: destination.enabled, queued, reason: recipient_reason }
    }).collect();
    Report { route_id: endpoint.id, route_name: endpoint.name.clone(), matched, reason, route_enabled: endpoint.enabled, priority: event.priority,
        min_priority: endpoint.min_priority, priority_match, required_tag: required.map(str::to_owned),
        tags_match, destinations: total, active_destinations: active, recipients }
}

async fn enqueue(s: &AppState, endpoint: Endpoint, payload: Value, test: bool) -> ApiResult<Value> {
    let event = parse_event(&payload).map_err(|message| {
        tracing::warn!(route_id=%endpoint.id, reason="invalid_payload", error=message, test, "webhook payload rejected");
        err(StatusCode::BAD_REQUEST, message)
    })?;
    let mut tx = s.db.begin().await.map_err(db_error)?;
    let destinations = sqlx::query_as::<_, Destination>(
        "SELECT c.id,c.name,c.kind,c.enabled FROM channels c JOIN route_channels rc ON rc.channel_id=c.id WHERE rc.route_id=$1 ORDER BY c.created_at,c.id")
        .bind(endpoint.id).fetch_all(&mut *tx).await.map_err(db_error)?;
    let routing = report(&endpoint, &event, destinations);
    if !endpoint.enabled {
        tracing::info!(route_id=%endpoint.id, reason=routing.reason, test, "webhook routing rejected");
        return Err((StatusCode::FORBIDDEN, Json(json!({"error":"Route disabled","queued":0,"routing":routing}))));
    }
    let event_id = Uuid::new_v4();
    sqlx::query("INSERT INTO events(id,route_id,title,message,priority,tags,payload) VALUES($1,$2,$3,$4,$5,$6,$7)")
        .bind(event_id).bind(endpoint.id).bind(&event.title).bind(&event.message).bind(event.priority)
        .bind(json!(event.tags)).bind(payload).execute(&mut *tx).await.map_err(db_error)?;
    let mut queued = 0;
    for recipient in routing.recipients.iter().filter(|recipient| recipient.queued) {
        sqlx::query("INSERT INTO deliveries(id,event_id,channel_id) VALUES($1,$2,$3)")
            .bind(Uuid::new_v4()).bind(event_id).bind(recipient.id).execute(&mut *tx).await.map_err(db_error)?;
        queued += 1;
    }
    tx.commit().await.map_err(db_error)?;
    tracing::info!(%event_id, route_id=%endpoint.id, reason=routing.reason, matched=routing.matched,
        priority=event.priority, min_priority=endpoint.min_priority, tags_match=routing.tags_match,
        destinations=routing.destinations, active_destinations=routing.active_destinations, queued, test,
        "webhook routing evaluated");
    for recipient in routing.recipients.iter().filter(|recipient| !recipient.queued) {
        tracing::info!(%event_id, route_id=%endpoint.id, channel_id=%recipient.id,
            reason=recipient.reason, test, "webhook destination excluded");
    }
    Ok(Json(json!({"event_id":event_id,"queued":queued,"routing":routing})))
}

pub async fn ingest(State(s): State<AppState>, Path(slug): Path<String>, headers: HeaderMap,
                    Json(payload): Json<Value>) -> ApiResult<Value> {
    let endpoint = sqlx::query_as::<_, Endpoint>(
        "SELECT id,name,enabled,min_priority,required_tag,token_hash FROM routes WHERE slug=$1")
        .bind(slug).fetch_optional(&s.db).await.map_err(db_error)?
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "Unknown route"))?;
    let supplied = headers.get("x-relay-key").and_then(|value| value.to_str().ok()).unwrap_or("");
    if supplied.is_empty() || !bool::from(hash(supplied).as_bytes().ct_eq(endpoint.token_hash.as_bytes())) {
        return Err(err(StatusCode::UNAUTHORIZED, "Invalid route key"));
    }
    enqueue(&s, endpoint, payload, false).await
}

pub async fn test_route(State(s): State<AppState>, Path(id): Path<Uuid>, headers: HeaderMap,
                        Json(payload): Json<Value>) -> ApiResult<Value> {
    auth::authenticated(&headers, &s).await?;
    let endpoint = sqlx::query_as::<_, Endpoint>(
        "SELECT id,name,enabled,min_priority,required_tag,token_hash FROM routes WHERE id=$1")
        .bind(id).fetch_optional(&s.db).await.map_err(db_error)?
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "Route not found"))?;
    enqueue(&s, endpoint, payload, true).await
}

#[cfg(test)]
mod tests {
    use super::*;
    fn endpoint(tag: Option<&str>, minimum: i32) -> Endpoint {
        Endpoint { id: Uuid::new_v4(), name: "Test route".to_owned(), enabled: true, min_priority: minimum,
            required_tag: tag.map(str::to_owned), token_hash: String::new() }
    }
    #[test]
    fn optional_fields_and_configured_filters() {
        for payload in [json!({"title":"Test"}), json!({"priority":null,"tags":null}), json!({"tags":[]})] {
            let event = parse_event(&payload).unwrap();
            assert_eq!(event.priority, 3); assert!(event.tags.is_empty());
            assert!(report(&endpoint(None, 1), &event, vec![]).matched);
            assert!(report(&endpoint(Some("  "), 1), &event, vec![]).matched);
            assert_eq!(report(&endpoint(Some("prod"), 1), &event, vec![]).reason, "tag_mismatch");
            assert_eq!(report(&endpoint(None, 4), &event, vec![]).reason, "priority_below_minimum");
        }
        assert!(parse_event(&json!({"tags":"prod"})).is_err());
        assert!(parse_event(&json!({"tags":[1]})).is_err());
        assert!(parse_event(&json!({"priority":"high"})).is_err());
        assert!(report(&endpoint(Some("prod"), 3), &parse_event(&json!({"tags":[" prod "]})).unwrap(), vec![]).matched);
    }
}
