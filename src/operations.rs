//! Incoming history, delivery attempts and bounded fallback dispatch.
use crate::*;

#[derive(Deserialize)]
pub struct EventQuery {route_id:Option<Uuid>,reason:Option<String>,search:Option<String>,page:Option<i64>,page_size:Option<i64>}
pub async fn events(State(s):State<AppState>,h:HeaderMap,Query(q):Query<EventQuery>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;
 if q.search.as_ref().is_some_and(|v|v.len()>250)||q.reason.as_ref().is_some_and(|v|v.len()>64){return Err(err(StatusCode::BAD_REQUEST,"History filter is too long"));}
 let page=q.page.unwrap_or(1).clamp(1,1000000);let size=q.page_size.unwrap_or(25).clamp(1,100);
 let search=q.search.filter(|v|!v.is_empty()).map(|v|format!("%{v}%"));
 let condition=" FROM events e JOIN routes r ON r.id=e.route_id WHERE ($1::uuid IS NULL OR e.route_id=$1) AND ($2::text IS NULL OR COALESCE(e.routing->>'reason','legacy')=$2) AND ($3::text IS NULL OR e.title ILIKE $3 OR e.message ILIKE $3 OR r.name ILIKE $3)";
 let mut count=sqlx::QueryBuilder::<sqlx::Postgres>::new("SELECT COUNT(*)");count.push(condition);
 let (total,):(i64,)=count.build_query_as().bind(q.route_id).bind(q.reason.as_deref().filter(|v|!v.is_empty())).bind(&search).fetch_one(&s.db).await.map_err(db_error)?;
 let mut rows=sqlx::QueryBuilder::<sqlx::Postgres>::new("SELECT jsonb_build_object('id',e.id,'route_id',e.route_id,'route_name',r.name,'title',e.title,'message',e.message,'priority',e.priority,'tags',e.tags,'routing',e.routing,'created_at',e.created_at,'deliveries',(SELECT COUNT(*) FROM deliveries d WHERE d.event_id=e.id),'sent',(SELECT COUNT(*) FROM deliveries d WHERE d.event_id=e.id AND d.status='sent'))");
 rows.push(condition).push(" ORDER BY e.created_at DESC,e.id DESC LIMIT $4 OFFSET $5");
 let items:Vec<(Value,)>=rows.build_query_as().bind(q.route_id).bind(q.reason.as_deref().filter(|v|!v.is_empty())).bind(search).bind(size).bind((page-1)*size).fetch_all(&s.db).await.map_err(db_error)?;
 Ok(Json(json!({"items":items.into_iter().map(|r|r.0).collect::<Vec<_>>(),"total":total,"page":page,"page_size":size})))
}
pub async fn attempts(State(s):State<AppState>,h:HeaderMap,Path(id):Path<Uuid>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;
 let delivery:Option<(i32,String,bool,Option<String>)>=sqlx::query_as("SELECT attempts,status,is_fallback,error FROM deliveries WHERE id=$1").bind(id).fetch_optional(&s.db).await.map_err(db_error)?;
 let (total,status,is_fallback,error)=delivery.ok_or_else(||err(StatusCode::NOT_FOUND,"Delivery not found"))?;
 let items:Vec<(Value,)>=sqlx::query_as("SELECT jsonb_build_object('number',number,'started_at',started_at,'finished_at',finished_at,'status',status,'error',error) FROM delivery_attempts WHERE delivery_id=$1 ORDER BY number DESC LIMIT 100").bind(id).fetch_all(&s.db).await.map_err(db_error)?;
 Ok(Json(json!({"delivery_id":id,"attempts":total,"status":status,"is_fallback":is_fallback,"items":items.into_iter().map(|r|r.0).collect::<Vec<_>>(),"history_limit":100,"can_retry":status=="failed"||(status=="queued"&&error.is_some())})))
}

async fn claim(s:&AppState)->Result<Option<(Uuid,String,String,i32,Uuid,i32)>> {
 let mut tx=s.db.begin().await?;
 let row:Option<(Uuid,String,String,i32,Uuid,i32)>=sqlx::query_as(
  "SELECT d.id,e.title,e.message,e.priority,d.channel_id,d.attempts+1 FROM deliveries d JOIN events e ON e.id=d.event_id WHERE (d.status='queued' AND d.next_attempt_at<=NOW()) OR (d.status='processing' AND d.locked_at<NOW()-INTERVAL '2 minutes') ORDER BY d.created_at FOR UPDATE OF d SKIP LOCKED LIMIT 1").fetch_optional(&mut *tx).await?;
 if let Some((id,_,_,_,_,number))=&row {
  sqlx::query("UPDATE delivery_attempts SET status='interrupted',finished_at=NOW(),error='Worker lease expired; outcome unknown' WHERE delivery_id=$1 AND status='processing'").bind(id).execute(&mut *tx).await?;
  sqlx::query("UPDATE deliveries SET status='processing',locked_at=NOW(),attempts=attempts+1,cycle_attempts=cycle_attempts+1 WHERE id=$1").bind(id).execute(&mut *tx).await?;
  sqlx::query("INSERT INTO delivery_attempts(delivery_id,number) VALUES($1,$2)").bind(id).bind(number).execute(&mut *tx).await?;
 }
 tx.commit().await?;Ok(row)
}
async fn finish(s:&AppState,id:Uuid,number:i32,result:Result<()>)->Result<()> {
 let mut tx=s.db.begin().await?;
 let row:Option<(Uuid,bool,i32)>=sqlx::query_as("SELECT event_id,is_fallback,cycle_attempts FROM deliveries WHERE id=$1 AND attempts=$2 AND status='processing' FOR UPDATE").bind(id).bind(number).fetch_optional(&mut *tx).await?;
 let Some((event_id,is_fallback,cycle_attempts))=row else{return Ok(());};
 let error=result.err().map(|e|e.to_string().chars().take(512).collect::<String>());
 let status=if error.is_none(){"sent"}else if cycle_attempts>=5{"failed"}else{"queued"};
 sqlx::query("UPDATE delivery_attempts SET status=$3,error=$4,finished_at=NOW() WHERE delivery_id=$1 AND number=$2").bind(id).bind(number).bind(if error.is_none(){"sent"}else{"failed"}).bind(&error).execute(&mut *tx).await?;
 sqlx::query("UPDATE deliveries SET status=$2,error=$3,locked_at=NULL,sent_at=CASE WHEN $2='sent' THEN NOW() ELSE NULL END,last_error_at=CASE WHEN $3::text IS NULL THEN NULL ELSE NOW() END,next_attempt_at=NOW()+(POWER(2,LEAST(cycle_attempts,8))::int * $4::int * INTERVAL '1 second') WHERE id=$1").bind(id).bind(status).bind(error).bind(s.retry_seconds).execute(&mut *tx).await?;
 if status=="failed"&&!is_fallback {
  let targets:Vec<(Uuid,)>=sqlx::query_as("SELECT f.channel_id FROM event_fallback_channels f JOIN channels c ON c.id=f.channel_id WHERE f.event_id=$1 AND c.enabled ORDER BY f.channel_id").bind(event_id).fetch_all(&mut *tx).await?;
  for (cid,) in targets {
   let result=sqlx::query("INSERT INTO deliveries(id,event_id,channel_id,is_fallback) VALUES($1,$2,$3,TRUE) ON CONFLICT(event_id,channel_id) DO NOTHING").bind(Uuid::new_v4()).bind(event_id).bind(cid).execute(&mut *tx).await?;
   if result.rows_affected()>0 {tracing::info!(%event_id,channel_id=%cid,failed_delivery_id=%id,"fallback delivery queued");}
  }
 }
 tx.commit().await?;Ok(())
}
pub async fn worker(s:AppState) {
 loop {
  match claim(&s).await {
   Ok(Some((id,title,message,priority,cid,number)))=>{
    let channel=sqlx::query_as::<_,Channel>("SELECT * FROM channels WHERE id=$1").bind(cid).fetch_optional(&s.db).await;
    let result=match channel {Ok(Some(c)) if c.enabled=>send(&s.client,&c,&title,&message,priority,s.allow_http,id).await,Ok(Some(_))=>Err(anyhow!("Channel disabled")),Ok(None)=>Err(anyhow!("Channel removed")),Err(_)=>Err(anyhow!("Channel lookup failed"))};
    if let Err(e)=finish(&s,id,number,result).await {tracing::error!(%e,%id,"worker result update failed");tokio::time::sleep(Duration::from_secs(3)).await;}
   }
   Ok(None)=>tokio::time::sleep(Duration::from_millis(800)).await,
   Err(e)=>{tracing::warn!(%e,"worker poll error");tokio::time::sleep(Duration::from_secs(3)).await;}
  }
 }
}
