mod providers;
mod proxy;
mod telegram;
mod mattermost;
mod message;
mod preferences;
mod auth;
mod alerts;
mod database;
mod routing;
mod operations;
mod diagnostics;
mod table;
mod delivery_groups;
#[cfg(test)]
mod tests;
use std::{env, sync::Arc, time::Duration};
use anyhow::{anyhow, Result};
use axum::{extract::{Path, Query, State, DefaultBodyLimit}, http::{HeaderMap, StatusCode}, routing::{get, post}, Json, Router};
use chrono::{DateTime, Utc};
use rand::{distr::Alphanumeric, RngExt};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use sqlx::{PgPool, FromRow};
use subtle::ConstantTimeEq;
use tower_http::{services::{ServeDir, ServeFile}, trace::TraceLayer};
use uuid::Uuid;

#[derive(Clone)]
struct AppState { db: PgPool, admin: Arc<String>, client: reqwest::Client, allow_http: bool, secure_cookies: bool, dummy_password_hash: Arc<String>, retry_seconds: i32 }
type ApiResult<T> = std::result::Result<Json<T>, (StatusCode, Json<Value>)>;
fn err(code: StatusCode, msg: impl ToString) -> (StatusCode, Json<Value>) { (code, Json(json!({"error":msg.to_string()}))) }
fn unauthorized() -> (StatusCode, Json<Value>) { err(StatusCode::UNAUTHORIZED, "Invalid credentials or expired session") }
fn db_error(e: sqlx::Error) -> (StatusCode, Json<Value>) { tracing::error!(error=%e, "database error"); err(StatusCode::INTERNAL_SERVER_ERROR, "Database error") }
fn hash(v: &str) -> String { hex::encode(Sha256::digest(v.as_bytes())) }
fn key() -> String { rand::rng().sample_iter(&Alphanumeric).take(48).map(char::from).collect() }

#[derive(Serialize, FromRow)]
struct Channel { id: Uuid, name: String, kind: String, config: Value, enabled: bool, created_at: DateTime<Utc> }
#[derive(Deserialize)]
struct ChannelInput { name: String, kind: String, config: Value, enabled: Option<bool> }
fn supported(kind: &str) -> bool { matches!(kind, "telegram" | "mattermost" | "slack" | "discord" | "teams" | "google_chat" | "rocket_chat" | "webhook" | "ntfy" | "gotify" | "pushover" | "matrix" | "smtp") }
fn valid_config(kind: &str, cfg: &Value, allow_http: bool) -> Result<()> {
    if !cfg.is_object() { return Err(anyhow!("Channel config must be an object")); }
    let required: &[&str] = match kind {
        "telegram" => &["bot_token", "chat_id"], "ntfy" => &["url", "topic"],
        "gotify" => &["url", "token"], "pushover" => &["token", "user"],
        "mattermost" if mattermost::is_bot(cfg) => &["url", "bot_token"],
        "matrix" => &["url", "room_id", "access_token"], "smtp" => &["host", "from", "to"], _ => &["url"]
    };
    for field in required { if cfg.get(field).and_then(Value::as_str).unwrap_or("").trim().is_empty() { return Err(anyhow!("Missing {field}")); } }
    if matches!(kind, "ntfy" | "gotify" | "mattermost" | "slack" | "discord" | "teams" | "google_chat" | "rocket_chat" | "webhook" | "matrix") {
        let raw = cfg["url"].as_str().unwrap_or("");
        let url = url::Url::parse(raw).map_err(|_| anyhow!("Invalid destination URL"))?;
        if url.scheme() != "https" && !(allow_http && url.scheme() == "http") { return Err(anyhow!("HTTPS required (or explicitly enable ALLOW_INSECURE_HTTP)")); }
        if url.host_str().is_none() || !url.username().is_empty() || url.password().is_some() { return Err(anyhow!("Invalid URL")); }
    }
    proxy::validate(kind,cfg)?;
    if kind == "mattermost" { mattermost::validate(cfg)?; }
    if kind == "telegram" { telegram_thread(cfg)?; }
    if kind == "smtp" { providers::valid_smtp(cfg, allow_http)?; }
    if kind == "matrix" {
        let room = cfg["room_id"].as_str().unwrap();
        if !room.starts_with('!') || !room.contains(':') || room.chars().any(char::is_whitespace) {
            return Err(anyhow!("Matrix room ID must look like !room:example.org (room aliases are not supported)"));
        }
        let url = url::Url::parse(cfg["url"].as_str().unwrap())?;
        if url.query().is_some() || url.fragment().is_some() { return Err(anyhow!("Matrix homeserver URL must not include a query or fragment")); }
    }
    Ok(())
}
async fn channels(State(s): State<AppState>, h: HeaderMap) -> ApiResult<Vec<Channel>> {
    auth::authenticated(&h, &s).await?;
    let mut result = sqlx::query_as::<_,Channel>("SELECT * FROM channels ORDER BY created_at DESC").fetch_all(&s.db).await.map_err(db_error)?;
    for c in &mut result { mask(&mut c.config); }
    Ok(Json(result))
}
fn mask(config: &mut Value) { for &key in providers::SECRET_FIELDS { if config.get(key).is_some() { config[key] = json!("********"); } } }
fn restore_masked(config: &mut Value, old: &Value) {
    for &key in providers::SECRET_FIELDS {
        if config.get(key).and_then(Value::as_str) == Some("********") {
            if let Some(value) = old.get(key) { config[key] = value.clone(); }
        }
    }
}
async fn create_channel(State(s): State<AppState>, h: HeaderMap, Json(input): Json<ChannelInput>) -> ApiResult<Value> {
    auth::authenticated(&h,&s).await?;
    if !supported(&input.kind) {return Err(err(StatusCode::BAD_REQUEST,"Unsupported channel type"));}
    valid_config(&input.kind,&input.config,s.allow_http).map_err(|e| err(StatusCode::BAD_REQUEST,e))?;
    let id=Uuid::new_v4();
    sqlx::query("INSERT INTO channels (id,name,kind,config,enabled) VALUES ($1,$2,$3,$4,$5)")
        .bind(id).bind(input.name).bind(input.kind).bind(input.config).bind(input.enabled.unwrap_or(true)).execute(&s.db).await.map_err(db_error)?;
    Ok(Json(json!({"id":id})))
}
async fn update_channel(State(s): State<AppState>, h: HeaderMap, Path(id): Path<Uuid>, Json(mut input): Json<ChannelInput>) -> ApiResult<Value> {
    auth::authenticated(&h,&s).await?;
    if !supported(&input.kind) {return Err(err(StatusCode::BAD_REQUEST,"Unsupported type"));}
    let old: Option<(Value,)> = sqlx::query_as("SELECT config FROM channels WHERE id=$1").bind(id).fetch_optional(&s.db).await.map_err(db_error)?;
    let old=old.ok_or_else(||err(StatusCode::NOT_FOUND,"Channel not found"))?.0;
    restore_masked(&mut input.config, &old);
    valid_config(&input.kind,&input.config,s.allow_http).map_err(|e|err(StatusCode::BAD_REQUEST,e))?;
    sqlx::query("UPDATE channels SET name=$2,kind=$3,config=$4,enabled=$5 WHERE id=$1").bind(id).bind(input.name).bind(input.kind).bind(input.config).bind(input.enabled.unwrap_or(true)).execute(&s.db).await.map_err(db_error)?;
    Ok(Json(json!({"ok":true})))
}
async fn delete_channel(State(s):State<AppState>, h:HeaderMap,Path(id):Path<Uuid>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;sqlx::query("DELETE FROM channels WHERE id=$1").bind(id).execute(&s.db).await.map_err(db_error)?;Ok(Json(json!({"ok":true})))
}

#[derive(Serialize,FromRow)]
struct Route { id:Uuid, name:String,slug:String,enabled:bool,min_priority:i32, required_tag:Option<String>,created_at:DateTime<Utc> }
#[derive(Serialize)]
struct RouteResponse { #[serde(flatten)] route:Route, channels:Vec<Uuid>, fallback_channel_ids:Vec<Uuid> }
#[derive(Deserialize)]
struct RouteInput { name:String,slug:Option<String>,enabled:Option<bool>, min_priority:Option<i32>,required_tag:Option<String>, channel_ids:Vec<Uuid>, #[serde(default)] fallback_channel_ids:Vec<Uuid> }
fn slug_valid(s:&str)->bool { !s.is_empty() && s.len()<=80 && s.bytes().all(|b|b.is_ascii_lowercase() || b.is_ascii_digit() || b==b'-') }
fn generated_slug(name:&str,id:Uuid)->String {
 let mut prefix=String::new();
 for ch in name.chars() {if ch.is_ascii_alphanumeric(){prefix.push(ch.to_ascii_lowercase())}else if !prefix.is_empty()&&!prefix.ends_with('-'){prefix.push('-')}if prefix.len()>=40{break;}}
 let prefix=prefix.trim_matches('-');format!("{}-{}",if prefix.is_empty(){"route"}else{prefix},id.simple())
}
fn valid_route(input:&RouteInput)->Result<()> {
 if input.channel_ids.len()>100 || input.fallback_channel_ids.len()>100 {return Err(anyhow!("Use at most 100 primary and 100 fallback recipients"));}
 if input.fallback_channel_ids.iter().any(|id|input.channel_ids.contains(id)) {return Err(anyhow!("Primary and fallback recipients must be different"));}
 if input.channel_ids.iter().collect::<std::collections::HashSet<_>>().len()!=input.channel_ids.len() || input.fallback_channel_ids.iter().collect::<std::collections::HashSet<_>>().len()!=input.fallback_channel_ids.len() {return Err(anyhow!("Duplicate recipients are not allowed"));}
 if input.name.trim().is_empty()||input.name.len()>100 {return Err(anyhow!("Route name is required (maximum 100 characters)"));}
 if input.required_tag.as_ref().map(|tag|tag.trim().len()>64).unwrap_or(false) {return Err(anyhow!("Tag must be at most 64 characters"));}
 Ok(())
}
async fn routes(State(s):State<AppState>,h:HeaderMap)->ApiResult<Vec<RouteResponse>>{
 auth::authenticated(&h,&s).await?;
 let rows=sqlx::query_as::<_,Route>("SELECT id,name,slug,enabled,min_priority,required_tag,created_at FROM routes ORDER BY created_at DESC").fetch_all(&s.db).await.map_err(db_error)?;
 let mut out=Vec::new();
 for route in rows {let ids:Vec<(Uuid,)> = sqlx::query_as("SELECT channel_id FROM route_channels WHERE route_id=$1").bind(route.id).fetch_all(&s.db).await.map_err(db_error)?;let fallback:Vec<(Uuid,)>=sqlx::query_as("SELECT channel_id FROM route_fallback_channels WHERE route_id=$1 ORDER BY channel_id").bind(route.id).fetch_all(&s.db).await.map_err(db_error)?;out.push(RouteResponse{route,channels:ids.into_iter().map(|x|x.0).collect(),fallback_channel_ids:fallback.into_iter().map(|x|x.0).collect()});}
 Ok(Json(out))
}
async fn create_route(State(s):State<AppState>,h:HeaderMap,Json(input):Json<RouteInput>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;valid_route(&input).map_err(|e|err(StatusCode::BAD_REQUEST,e))?;
 let id=Uuid::new_v4();let slug=input.slug.as_deref().filter(|s|!s.is_empty()).map(str::to_owned).unwrap_or_else(||generated_slug(&input.name,id));
 if !slug_valid(&slug){return Err(err(StatusCode::BAD_REQUEST,"Invalid route endpoint"));}
 let token=key(); let mut tx=s.db.begin().await.map_err(db_error)?;
 let inserted=sqlx::query("INSERT INTO routes(id,name,slug,token_hash,enabled,min_priority,required_tag) VALUES($1,$2,$3,$4,$5,$6,$7)")
 .bind(id).bind(input.name.trim()).bind(&slug).bind(hash(&token)).bind(input.enabled.unwrap_or(true)).bind(input.min_priority.unwrap_or(1).clamp(1,5)).bind(input.required_tag.map(|t|t.trim().to_owned()).filter(|t|!t.is_empty())).execute(&mut *tx).await;
 if inserted.is_err(){return Err(err(StatusCode::CONFLICT,"Route slug already exists or invalid input"));}
 for cid in input.channel_ids {sqlx::query("INSERT INTO route_channels(route_id,channel_id) VALUES($1,$2)").bind(id).bind(cid).execute(&mut *tx).await.map_err(db_error)?;}
 for cid in input.fallback_channel_ids {sqlx::query("INSERT INTO route_fallback_channels(route_id,channel_id) VALUES($1,$2)").bind(id).bind(cid).execute(&mut *tx).await.map_err(db_error)?;}
 tx.commit().await.map_err(db_error)?;
 Ok(Json(json!({"id":id,"token":token,"slug":slug,"route_name":input.name,"endpoint":format!("/h/{slug}")})))
}
async fn update_route(State(s):State<AppState>,h:HeaderMap,Path(id):Path<Uuid>,Json(input):Json<RouteInput>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;valid_route(&input).map_err(|e|err(StatusCode::BAD_REQUEST,e))?;
 let old:Option<(String,)>=sqlx::query_as("SELECT slug FROM routes WHERE id=$1").bind(id).fetch_optional(&s.db).await.map_err(db_error)?;
 let old=old.ok_or_else(||err(StatusCode::NOT_FOUND,"Route not found"))?.0;
 if input.slug.as_ref().map(|slug|slug!=&old).unwrap_or(false){return Err(err(StatusCode::BAD_REQUEST,"Existing webhook endpoints cannot be changed"));}
 let mut tx=s.db.begin().await.map_err(db_error)?;
 sqlx::query("UPDATE routes SET name=$2,enabled=$3,min_priority=$4,required_tag=$5 WHERE id=$1")
 .bind(id).bind(input.name.trim()).bind(input.enabled.unwrap_or(true)).bind(input.min_priority.unwrap_or(1).clamp(1,5)).bind(input.required_tag.map(|t|t.trim().to_owned()).filter(|t|!t.is_empty())).execute(&mut *tx).await.map_err(db_error)?;
 sqlx::query("DELETE FROM route_channels WHERE route_id=$1").bind(id).execute(&mut *tx).await.map_err(db_error)?;
 for cid in input.channel_ids {sqlx::query("INSERT INTO route_channels(route_id,channel_id) VALUES($1,$2)").bind(id).bind(cid).execute(&mut *tx).await.map_err(db_error)?;}
 sqlx::query("DELETE FROM route_fallback_channels WHERE route_id=$1").bind(id).execute(&mut *tx).await.map_err(db_error)?;
 for cid in input.fallback_channel_ids {sqlx::query("INSERT INTO route_fallback_channels(route_id,channel_id) VALUES($1,$2)").bind(id).bind(cid).execute(&mut *tx).await.map_err(db_error)?;}
 tx.commit().await.map_err(db_error)?;Ok(Json(json!({"ok":true})))
}
async fn delete_route(State(s):State<AppState>,h:HeaderMap,Path(id):Path<Uuid>)->ApiResult<Value>{auth::authenticated(&h,&s).await?;sqlx::query("DELETE FROM routes WHERE id=$1").bind(id).execute(&s.db).await.map_err(db_error)?;Ok(Json(json!({"ok":true})))}
async fn rotate_route(State(s):State<AppState>,h:HeaderMap,Path(id):Path<Uuid>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;let token=key();
 let result:Option<(String,String)>=sqlx::query_as("UPDATE routes SET token_hash=$2 WHERE id=$1 RETURNING slug,name").bind(id).bind(hash(&token)).fetch_optional(&s.db).await.map_err(db_error)?;
 let (slug,name)=result.ok_or_else(||err(StatusCode::NOT_FOUND,"Route not found"))?;
 Ok(Json(json!({"token":token,"route_name":name,"endpoint":format!("/h/{slug}")})))
}

#[derive(Serialize,FromRow)]
struct Delivery { id:Uuid,event_id:Uuid,route_id:Uuid,channel_id:Uuid,channel_name:String,channel_kind:String,route_name:String,title:String,tags:Value,route_tag:Option<String>,status:String,attempts:i32,is_fallback:bool,error:Option<String>,created_at:DateTime<Utc>,sent_at:Option<DateTime<Utc>>,message:String,has_title:bool,#[serde(skip)] payload:Value,#[serde(skip)] event_created_at:DateTime<Utc> }
const DELIVERY_SELECT:&str="SELECT d.id,d.event_id,e.route_id,d.channel_id,c.name AS channel_name,c.kind AS channel_kind,r.name AS route_name,e.title,e.tags,NULLIF(BTRIM(r.required_tag),'') AS route_tag,d.status,d.attempts,d.is_fallback,d.error,d.created_at,d.sent_at,e.message,FALSE AS has_title,e.payload,e.created_at AS event_created_at";
#[derive(Deserialize,Default)]
struct DeliveryQuery {
 status:Option<String>,channel_id:Option<Uuid>,route_id:Option<Uuid>,event_id:Option<Uuid>,from:Option<DateTime<Utc>>,to:Option<DateTime<Utc>>,
 group_events:Option<bool>,search:Option<String>,tag:Option<String>,period:Option<String>,page:Option<i64>,page_size:Option<i64>,#[serde(flatten)] sort:table::Sort,
}
async fn deliveries(State(s):State<AppState>,h:HeaderMap,Query(mut filter):Query<DeliveryQuery>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;
 if filter.status.as_deref().map(|v|!matches!(v,"sent"|"failed"|"queued"|"processing"|"retrying")).unwrap_or(false) {return Err(err(StatusCode::BAD_REQUEST,"Invalid delivery status"));}
 if filter.from.zip(filter.to).map(|(from,to)|from>to).unwrap_or(false) {return Err(err(StatusCode::BAD_REQUEST,"Start date must precede end date"));}
 if let Some(period)=filter.period.as_deref().filter(|p|!p.is_empty()) {
  let duration=monitoring_period(period).ok_or_else(||err(StatusCode::BAD_REQUEST,"Invalid monitoring period"))?;let to=Utc::now();let from=to-duration;
  filter.from=Some(filter.from.map(|old|old.max(from)).unwrap_or(from));filter.to=Some(filter.to.map(|old|old.min(to)).unwrap_or(to));
 }
 if filter.search.as_ref().map(|v|v.len()>250).unwrap_or(false) {return Err(err(StatusCode::BAD_REQUEST,"Search is too long"));}
 if filter.tag.as_ref().map(|v|v.len()>64).unwrap_or(false){return Err(err(StatusCode::BAD_REQUEST,"Tag is too long"));}
 let page=filter.page.unwrap_or(1).clamp(1,1000000);let page_size=filter.page_size.unwrap_or(50).clamp(1,100);
 let search=filter.search.as_ref().filter(|v|!v.is_empty()).map(|v|format!("%{v}%"));
 let condition=" FROM deliveries d JOIN events e ON e.id=d.event_id JOIN channels c ON c.id=d.channel_id JOIN routes r ON r.id=e.route_id WHERE ($1::text IS NULL OR d.status=$1 OR ($1='retrying' AND d.status='queued' AND d.error IS NOT NULL)) AND ($2::uuid IS NULL OR d.channel_id=$2) AND ($3::uuid IS NULL OR e.route_id=$3) AND ($4::timestamptz IS NULL OR d.created_at>=$4) AND ($5::timestamptz IS NULL OR d.created_at<=$5) AND ($6::text IS NULL OR e.title ILIKE $6 OR e.message ILIKE $6 OR c.name ILIKE $6 OR r.name ILIKE $6 OR COALESCE(d.error,'') ILIKE $6) AND ($7::text IS NULL OR e.tags @> jsonb_build_array($7::text) OR NULLIF(BTRIM(r.required_tag),'')=$7::text) AND ($8::uuid IS NULL OR e.id=$8)";
 if filter.group_events.unwrap_or(false){return delivery_groups::list(&s.db,&filter,&condition.replace("d.created_at","e.created_at").replace("d.status=$1","(d.status=$1 AND ($1<>'queued' OR d.error IS NULL))"),&search,page,page_size).await;}
 let order=table::order("deliveries",&filter.sort)?;
 let mut count_sql=sqlx::QueryBuilder::<sqlx::Postgres>::new("SELECT COUNT(*)");count_sql.push(condition);
 let (total,):(i64,)=count_sql.build_query_as::<(i64,)>().bind(&filter.status).bind(filter.channel_id).bind(filter.route_id).bind(filter.from).bind(filter.to).bind(&search).bind(filter.tag.as_deref().filter(|t|!t.is_empty())).bind(filter.event_id).fetch_one(&s.db).await.map_err(db_error)?;
 let mut rows_sql=sqlx::QueryBuilder::<sqlx::Postgres>::new(DELIVERY_SELECT);rows_sql.push(condition).push(order).push(" LIMIT $9 OFFSET $10");
 let mut items=rows_sql.build_query_as::<Delivery>().bind(&filter.status).bind(filter.channel_id).bind(filter.route_id).bind(filter.from).bind(filter.to).bind(&search).bind(filter.tag.as_deref().filter(|t|!t.is_empty())).bind(filter.event_id).bind(page_size).bind((page-1)*page_size).fetch_all(&s.db).await.map_err(db_error)?;
 for row in &mut items {
  let title=message::event_title(&row.payload);row.has_title=!title.is_empty();
 }
 Ok(Json(json!({"items":items,"total":total,"page":page,"page_size":page_size})))
}
async fn retry(State(s):State<AppState>,h:HeaderMap,Path(id):Path<Uuid>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;
 let result=sqlx::query("UPDATE deliveries SET status='queued',next_attempt_at=NOW(),locked_at=NULL,error=NULL,cycle_attempts=0,last_error_at=NULL WHERE id=$1 AND (status='failed' OR (status='queued' AND error IS NOT NULL))").bind(id).execute(&s.db).await.map_err(db_error)?;
 if result.rows_affected()==0 {return Err(err(StatusCode::CONFLICT,"Only failed or retrying deliveries can be retried"));}
 Ok(Json(json!({"ok":true})))
}
fn telegram_thread(cfg:&Value)->Result<Option<i64>> {
 let Some(value)=cfg.get("message_thread_id").filter(|v|!v.is_null() && v.as_str()!=Some("")) else{return Ok(None);};
 let id=value.as_i64().or_else(||value.as_str().and_then(|v|v.parse().ok())).filter(|id|*id>0 && *id<=i32::MAX as i64).ok_or_else(||anyhow!("Telegram topic ID must be a positive integer"))?;
 Ok(Some(id))
}
fn telegram_payload(cfg:&Value,text:&str)->Result<Value> {
 let mut payload=json!({"chat_id":cfg["chat_id"],"text":text});
 payload["parse_mode"]=json!("HTML");
 if let Some(id)=telegram_thread(cfg)? {payload["message_thread_id"]=json!(id);}
 Ok(payload)
}
async fn test_channel(State(s):State<AppState>,h:HeaderMap,Path(id):Path<Uuid>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;
 let c=sqlx::query_as::<_,Channel>("SELECT * FROM channels WHERE id=$1").bind(id).fetch_optional(&s.db).await.map_err(db_error)?.ok_or_else(||err(StatusCode::NOT_FOUND,"Channel not found"))?;
 send(&s.client,&c,"Relayix test","Test notification from Relayix",3,s.allow_http,Uuid::new_v4()).await.map_err(|e|err(StatusCode::BAD_GATEWAY,e))?;
 Ok(Json(json!({"ok":true})))
}

async fn send(client:&reqwest::Client,c:&Channel,title:&str,message:&str,priority:i32,allow_http:bool,delivery_id:Uuid)->Result<()> {
 let cfg=&c.config;
 valid_config(&c.kind,cfg,allow_http)?;
 let rendered=message::render(&c.kind,cfg,title,message);
 let text=rendered.text;
 if c.kind=="telegram"&&matches!(proxy::mode(cfg),"mtproto"|"webproxy"){return telegram::send(cfg,&text,delivery_id,rendered.html).await;}
 let client=proxy::client(client,cfg)?;
 if c.kind == "mattermost" && mattermost::is_bot(cfg) {return mattermost::send(&client,cfg,&text).await;}
 if c.kind == "smtp" { return providers::send_smtp(cfg,title,message).await; }
 if c.kind == "matrix" { return providers::send_matrix(&client,cfg,&text,delivery_id).await; }
 let response=match c.kind.as_str() {
 "telegram"=>{
   let token=cfg["bot_token"].as_str().unwrap();
   if !token.chars().all(|ch|ch.is_ascii_alphanumeric() || ch==':' || ch=='_' || ch=='-') {return Err(anyhow!("Invalid bot token"));}
   client.post(format!("https://api.telegram.org/bot{token}/sendMessage")).json(&telegram_payload(cfg,&text)?).send().await.map_err(|e|anyhow!(e.without_url()))?
 },
 "ntfy"=>{
   let server=cfg["url"].as_str().unwrap().trim_end_matches('/');
   let topic=cfg["topic"].as_str().unwrap();
   if !topic.chars().all(|x|x.is_ascii_alphanumeric()||x=='-'||x=='_'){return Err(anyhow!("Invalid topic"));}
   client.post(format!("{server}/{topic}")).header("Title",title).header("Priority",priority.to_string()).body(message.to_owned()).send().await.map_err(|e|anyhow!(e.without_url()))?
 },
 "gotify"=> client.post(format!("{}/message",cfg["url"].as_str().unwrap().trim_end_matches('/'))).query(&[("token",cfg["token"].as_str().unwrap())]).json(&json!({"title":title,"message":message,"priority":priority})).send().await.map_err(|e|anyhow!(e.without_url()))?,
 "pushover"=>client.post("https://api.pushover.net/1/messages.json").form(&[("token",cfg["token"].as_str().unwrap()),("user",cfg["user"].as_str().unwrap()),("title",title),("message",message)]).send().await.map_err(|e|anyhow!(e.without_url()))?,
 "discord"=>client.post(cfg["url"].as_str().unwrap()).json(&json!({"content":text})).send().await.map_err(|e|anyhow!(e.without_url()))?,
 "teams"=>client.post(cfg["url"].as_str().unwrap()).json(&json!({"text":text})).send().await.map_err(|e|anyhow!(e.without_url()))?,
 "google_chat"=>client.post(cfg["url"].as_str().unwrap()).json(&json!({"text":text})).send().await.map_err(|e|anyhow!(e.without_url()))?,
 "slack" | "mattermost" | "rocket_chat"=>client.post(cfg["url"].as_str().unwrap()).json(&json!({"text":text})).send().await.map_err(|e|anyhow!(e.without_url()))?,
 "webhook"=>client.post(cfg["url"].as_str().unwrap()).json(&json!({"title":title,"message":message,"priority":priority,"source":"relayix"})).send().await.map_err(|e|anyhow!(e.without_url()))?,
 _=>return Err(anyhow!("Unsupported channel"))
 };
 let status=response.status();
 if !status.is_success(){return Err(anyhow!("Remote server returned {status}"));}
 Ok(())
}

fn monitoring_period(period:&str)->Option<chrono::Duration> {
 Some(match period {"5m"=>chrono::Duration::minutes(5),"15m"=>chrono::Duration::minutes(15),"30m"=>chrono::Duration::minutes(30),"1h"=>chrono::Duration::hours(1),"24h"=>chrono::Duration::days(1),"7d"=>chrono::Duration::days(7),"30d"=>chrono::Duration::days(30),_=>return None})
}
#[derive(Deserialize)]
struct StatsQuery {period:Option<String>}
async fn stats(State(s):State<AppState>,h:HeaderMap,Query(query):Query<StatsQuery>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;
 let period=query.period.as_deref().unwrap_or("30d");let duration=monitoring_period(period).ok_or_else(||err(StatusCode::BAD_REQUEST,"Invalid monitoring period"))?;
 let to=Utc::now();let from=to-duration;
 let (total,sent,failed,pending,retrying):(i64,i64,i64,i64,i64)=sqlx::query_as("SELECT COUNT(*),COUNT(*) FILTER (WHERE status='sent'),COUNT(*) FILTER (WHERE status='failed'),COUNT(*) FILTER (WHERE status IN ('queued','processing')),COUNT(*) FILTER (WHERE status='queued' AND error IS NOT NULL) FROM deliveries WHERE created_at>=$1 AND created_at<=$2").bind(from).bind(to).fetch_one(&s.db).await.map_err(db_error)?;
 let (total30,sent30,failed30):(i64,i64,i64)=sqlx::query_as("SELECT COUNT(*),COUNT(*) FILTER (WHERE status='sent'),COUNT(*) FILTER (WHERE status='failed') FROM deliveries WHERE created_at>=NOW()-INTERVAL '30 days'").fetch_one(&s.db).await.map_err(db_error)?;
 Ok(Json(json!({"period":period,"from":from,"to":to,"total":total,"sent":sent,"failed":failed,"pending":pending,"retrying":retrying,"last_30_days":total30,"sent_30_days":sent30,"failed_30_days":failed30})))
}
async fn tags(State(s):State<AppState>,h:HeaderMap)->ApiResult<Vec<String>> {
 auth::authenticated(&h,&s).await?;
 let tags:Vec<(String,)>=sqlx::query_as("SELECT tag FROM (SELECT required_tag AS tag FROM routes WHERE required_tag IS NOT NULL AND required_tag<>'' UNION SELECT jsonb_array_elements_text(tags) AS tag FROM events) all_tags ORDER BY tag LIMIT 500").fetch_all(&s.db).await.map_err(db_error)?;
 Ok(Json(tags.into_iter().map(|(tag,)|tag).collect()))
}
async fn health()->Json<Value>{Json(json!({"status":"ok","name":"Relayix","version":env!("CARGO_PKG_VERSION"),"stage":"beta"}))}

async fn no_store(request:axum::extract::Request,next:axum::middleware::Next)->axum::response::Response {
 let mut response=next.run(request).await;
 response.headers_mut().insert(axum::http::header::CACHE_CONTROL,axum::http::HeaderValue::from_static("no-store"));
 response
}

#[tokio::main]
async fn main()->Result<()> {
 tracing_subscriber::fmt().with_env_filter(tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_|"relayix=info".into())).init();
 let admin_token=env::var("ADMIN_TOKEN").unwrap_or_default();
 if !admin_token.is_empty() && (admin_token.len()<32 || admin_token.starts_with("CHANGE_ME")) {return Err(anyhow!("Set a random ADMIN_TOKEN of at least 32 chars"));}
 let port=env::var("PORT").unwrap_or_else(|_|"8080".to_owned()).parse::<u16>().ok().filter(|p|*p>0).ok_or_else(||anyhow!("PORT must be between 1 and 65535"))?;
 for name in ["ALLOW_INSECURE_HTTP","COOKIE_SECURE"] {if env::var(name).is_ok_and(|v|!matches!(v.as_str(),""|"true"|"false")){return Err(anyhow!("{name} must be true or false"));}}
 if env::var("RETRY_BASE_SECONDS").is_ok_and(|v|v.parse::<i32>().map(|n|!(1..=900).contains(&n)).unwrap_or(true)){return Err(anyhow!("RETRY_BASE_SECONDS must be between 1 and 900"));}
 let api_id=env::var("TELEGRAM_API_ID").unwrap_or_default();let api_hash=env::var("TELEGRAM_API_HASH").unwrap_or_default();
 if !api_id.is_empty()||!api_hash.is_empty(){
  if api_id.parse::<i32>().ok().filter(|id|*id>0).is_none(){return Err(anyhow!("TELEGRAM_API_ID must be a positive integer; set it together with TELEGRAM_API_HASH"));}
  if api_hash.len()!=32||!api_hash.bytes().all(|b|b.is_ascii_hexdigit()){return Err(anyhow!("TELEGRAM_API_HASH must contain 32 hexadecimal characters"));}
 }else{tracing::info!("Telegram MTProto/WEB unavailable until TELEGRAM_API_ID and TELEGRAM_API_HASH are configured; direct/HTTP Bot API remains available");}
 let db=database::connect().await?;
 sqlx::migrate!().run(&db).await.map_err(|_|anyhow!("Database migration failed; check schema permissions, migration history and database server logs"))?;
 auth::bootstrap(&db).await?;
 let dummy_password_hash=Arc::new(auth::dummy_hash().await?);
 let client=reqwest::Client::builder().timeout(Duration::from_secs(12)).redirect(reqwest::redirect::Policy::none()).build()?;
 let s=AppState{db,admin:Arc::new(admin_token),client,allow_http:env::var("ALLOW_INSECURE_HTTP").unwrap_or_default()=="true",secure_cookies:env::var("COOKIE_SECURE").unwrap_or_default()=="true",dummy_password_hash,retry_seconds:env::var("RETRY_BASE_SECONDS").ok().and_then(|v|v.parse::<i32>().ok()).unwrap_or(15).clamp(1,900)};
 tokio::spawn(operations::worker(s.clone()));
 tokio::spawn(alerts::worker(s.clone()));
 let api=Router::new()
 .route("/auth/login",post(auth::login))
 .route("/auth/logout",post(auth::logout))
 .route("/auth/me",get(auth::me))
 .route("/auth/preferences",axum::routing::put(preferences::update))
 .route("/tags",get(tags))
 .route("/auth/profile",axum::routing::put(auth::profile))
 .route("/users",get(auth::users).post(auth::create_user))
 .route("/users/{id}",axum::routing::put(auth::update_user).delete(auth::delete_user))
 .route("/alert-policies",get(alerts::list).post(alerts::create))
 .route("/alert-policies/{id}",axum::routing::put(alerts::update).delete(alerts::delete))
 .route("/alert-policies/{id}/test",post(alerts::test))
 .route("/alert-deliveries",get(alerts::history))
 .route("/alert-deliveries/{id}/retry",post(alerts::retry))
 .route("/channels",get(channels).post(create_channel))
 .route("/channels/diagnose",post(diagnostics::draft))
 .route("/stats",get(stats))
 .route("/channels/{id}",axum::routing::put(update_channel).delete(delete_channel))
 .route("/channels/{id}/test",post(test_channel))
 .route("/channels/{id}/diagnose",post(diagnostics::channel))
 .route("/routes",get(routes).post(create_route))
 .route("/routes/{id}",axum::routing::put(update_route).delete(delete_route))
 .route("/routes/{id}/rotate",post(rotate_route))
 .route("/routes/{id}/test",post(routing::test_route))
 .route("/routes/{id}/preview",post(routing::preview_route))
 .route("/events",get(operations::events))
 .route("/deliveries/{id}/attempts",get(operations::attempts))
 .route("/deliveries",get(deliveries))
 .route("/deliveries/{id}/retry",post(retry))
 .fallback(||async{(StatusCode::NOT_FOUND,Json(json!({"error":"Unknown API endpoint"})))})
 .layer(axum::middleware::from_fn(no_store));
 let app=Router::new()
 .route("/healthz",get(health))
 .route("/h/{slug}",post(routing::ingest))
 .nest("/api",api)
 .fallback_service(ServeDir::new("web/dist").not_found_service(ServeFile::new("web/dist/index.html")))
 .layer(DefaultBodyLimit::max(64*1024))
 .layer(TraceLayer::new_for_http())
 .with_state(s);
 let listener=tokio::net::TcpListener::bind(format!("0.0.0.0:{port}")).await?;
 tracing::info!(%port,"Relayix started");
 axum::serve(listener,app).await?;Ok(())
}
