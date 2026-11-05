use crate::*;

#[derive(Serialize,FromRow)]
pub struct Policy {
    id:Uuid,name:String,enabled:bool,watch_channel_ids:Vec<Uuid>,watch_route_ids:Vec<Uuid>,destination_ids:Vec<Uuid>,
    failure_threshold:i32,min_attempts:i32,window_minutes:i32,cooldown_minutes:i32,title:String,body:String,
    last_triggered_at:Option<DateTime<Utc>>,created_at:DateTime<Utc>,
}
#[derive(Deserialize)]
pub struct PolicyInput {
    name:String,enabled:bool,#[serde(default)] watch_channel_ids:Vec<Uuid>,#[serde(default)] watch_route_ids:Vec<Uuid>,
    destination_ids:Vec<Uuid>,failure_threshold:i32,min_attempts:i32,window_minutes:i32,cooldown_minutes:i32,title:String,body:String,
}
async fn validate(s:&AppState,input:&PolicyInput)->std::result::Result<(),(StatusCode,Json<Value>)> {
    if input.name.trim().is_empty() || input.name.len()>100 || input.title.trim().is_empty() || input.title.len()>256
        || input.body.trim().is_empty() || input.body.len()>5000 || !(1..=100).contains(&input.failure_threshold)
        || !(1..=5).contains(&input.min_attempts) || !(1..=1440).contains(&input.window_minutes)
        || !(1..=1440).contains(&input.cooldown_minutes) || input.destination_ids.is_empty()
        || input.destination_ids.len()>100 || input.watch_channel_ids.len()>100 || input.watch_route_ids.len()>100 {
        return Err(err(StatusCode::BAD_REQUEST,"Provide a name, alert text, at least one recipient, and valid threshold/window/cooldown values"));
    }
    for ids in [&input.destination_ids,&input.watch_channel_ids] {
        let count:(i64,)=sqlx::query_as("SELECT COUNT(*) FROM channels WHERE id=ANY($1)").bind(ids).fetch_one(&s.db).await.map_err(db_error)?;
        if count.0!=ids.len() as i64 {return Err(err(StatusCode::BAD_REQUEST,"Unknown or duplicate channel"));}
    }
    let count:(i64,)=sqlx::query_as("SELECT COUNT(*) FROM routes WHERE id=ANY($1)").bind(&input.watch_route_ids).fetch_one(&s.db).await.map_err(db_error)?;
    if count.0!=input.watch_route_ids.len() as i64 {return Err(err(StatusCode::BAD_REQUEST,"Unknown or duplicate route"));}
    Ok(())
}
pub async fn list(State(s):State<AppState>,h:HeaderMap)->ApiResult<Vec<Policy>> {
    auth::require_admin(&h,&s).await?;
    Ok(Json(sqlx::query_as::<_,Policy>("SELECT * FROM alert_policies ORDER BY created_at").fetch_all(&s.db).await.map_err(db_error)?))
}
pub async fn create(State(s):State<AppState>,h:HeaderMap,Json(input):Json<PolicyInput>)->ApiResult<Value> {
    auth::require_admin(&h,&s).await?;validate(&s,&input).await?;let id=Uuid::new_v4();
    sqlx::query("INSERT INTO alert_policies(id,name,enabled,watch_channel_ids,watch_route_ids,destination_ids,failure_threshold,min_attempts,window_minutes,cooldown_minutes,title,body) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)")
        .bind(id).bind(input.name.trim()).bind(input.enabled).bind(input.watch_channel_ids).bind(input.watch_route_ids).bind(input.destination_ids)
        .bind(input.failure_threshold).bind(input.min_attempts).bind(input.window_minutes).bind(input.cooldown_minutes).bind(input.title).bind(input.body)
        .execute(&s.db).await.map_err(db_error)?;
    Ok(Json(json!({"id":id})))
}
pub async fn update(State(s):State<AppState>,h:HeaderMap,Path(id):Path<Uuid>,Json(input):Json<PolicyInput>)->ApiResult<Value> {
    auth::require_admin(&h,&s).await?;validate(&s,&input).await?;
    let result=sqlx::query("UPDATE alert_policies SET name=$2,enabled=$3,watch_channel_ids=$4,watch_route_ids=$5,destination_ids=$6,failure_threshold=$7,min_attempts=$8,window_minutes=$9,cooldown_minutes=$10,title=$11,body=$12 WHERE id=$1")
        .bind(id).bind(input.name.trim()).bind(input.enabled).bind(input.watch_channel_ids).bind(input.watch_route_ids).bind(input.destination_ids)
        .bind(input.failure_threshold).bind(input.min_attempts).bind(input.window_minutes).bind(input.cooldown_minutes).bind(input.title).bind(input.body)
        .execute(&s.db).await.map_err(db_error)?;
    if result.rows_affected()==0 {return Err(err(StatusCode::NOT_FOUND,"Alert rule not found"));}
    Ok(Json(json!({"ok":true})))
}
pub async fn delete(State(s):State<AppState>,h:HeaderMap,Path(id):Path<Uuid>)->ApiResult<Value> {
    auth::require_admin(&h,&s).await?;
    sqlx::query("DELETE FROM alert_policies WHERE id=$1").bind(id).execute(&s.db).await.map_err(db_error)?;
    Ok(Json(json!({"ok":true})))
}
pub async fn test(State(s):State<AppState>,h:HeaderMap,Path(id):Path<Uuid>)->ApiResult<Value> {
    auth::require_admin(&h,&s).await?;
    let policy=sqlx::query_as::<_,Policy>("SELECT * FROM alert_policies WHERE id=$1").bind(id).fetch_optional(&s.db).await.map_err(db_error)?.ok_or_else(||err(StatusCode::NOT_FOUND,"Alert rule not found"))?;
    let mut tx=s.db.begin().await.map_err(db_error)?;
    let channels:Vec<(Uuid,)>=sqlx::query_as("SELECT id FROM channels WHERE id=ANY($1) AND enabled=true").bind(&policy.destination_ids).fetch_all(&mut *tx).await.map_err(db_error)?;
    if channels.is_empty() {return Err(err(StatusCode::BAD_REQUEST,"No enabled alert recipients"));}
    for (cid,) in &channels {
        sqlx::query("INSERT INTO alert_deliveries(id,policy_id,channel_id,title,message) VALUES($1,$2,$3,$4,$5)")
            .bind(Uuid::new_v4()).bind(id).bind(cid).bind("Relayix: failure alert test").bind(format!("Test of alert rule '{}'. This is a test notification.",policy.name)).execute(&mut *tx).await.map_err(db_error)?;
    }
    tx.commit().await.map_err(db_error)?;Ok(Json(json!({"queued":channels.len()})))
}

#[derive(Serialize,FromRow)]
pub struct AlertDelivery {id:Uuid,policy_name:Option<String>,channel_name:String,status:String,attempts:i32,error:Option<String>,title:String,created_at:DateTime<Utc>,sent_at:Option<DateTime<Utc>>}
pub async fn history(State(s):State<AppState>,h:HeaderMap)->ApiResult<Vec<AlertDelivery>> {
    auth::require_admin(&h,&s).await?;
    Ok(Json(sqlx::query_as::<_,AlertDelivery>("SELECT a.id,p.name AS policy_name,c.name AS channel_name,a.status,a.attempts,a.error,a.title,a.created_at,a.sent_at FROM alert_deliveries a LEFT JOIN alert_policies p ON p.id=a.policy_id JOIN channels c ON c.id=a.channel_id ORDER BY a.created_at DESC LIMIT 100").fetch_all(&s.db).await.map_err(db_error)?))
}
pub async fn retry(State(s):State<AppState>,h:HeaderMap,Path(id):Path<Uuid>)->ApiResult<Value> {
    auth::require_admin(&h,&s).await?;
    let result=sqlx::query("UPDATE alert_deliveries SET status='queued',attempts=0,error=NULL,locked_at=NULL,next_attempt_at=NOW() WHERE id=$1 AND status='failed'").bind(id).execute(&s.db).await.map_err(db_error)?;
    if result.rows_affected()==0 {return Err(err(StatusCode::CONFLICT,"Only failed alerts can be retried"));}
    Ok(Json(json!({"ok":true})))
}

fn render(pattern:&str,channel:&str,route:&str,error:&str,title:&str,count:usize)->String {
    // Single pass: provider text cannot inject additional placeholder expansions.
    let replacements=[("channel",channel.to_owned()),("route",route.to_owned()),("error",error.to_owned()),("title",title.to_owned()),("failures",count.to_string())];
    let mut output=String::new();let mut rest=pattern;
    while let Some(start)=rest.find('{') {
        output.push_str(&rest[..start]);rest=&rest[start..];
        if let Some(end)=rest.find('}') {
            let key=&rest[1..end];
            if let Some((_,value))=replacements.iter().find(|(name,_)|*name==key) {output.push_str(value);}else{output.push_str(&rest[..=end]);}
            rest=&rest[end+1..];
        }else{break;}
    }
    output.push_str(rest);output
}

async fn schedule(s:&AppState)->Result<()> {
    let policies:Vec<(Uuid,)>=sqlx::query_as("SELECT id FROM alert_policies WHERE enabled=true").fetch_all(&s.db).await?;
    for (pid,) in policies {
        let mut tx=s.db.begin().await?;
        let policy=sqlx::query_as::<_,Policy>("SELECT * FROM alert_policies WHERE id=$1 AND enabled=true AND (last_triggered_at IS NULL OR last_triggered_at<=NOW()-cooldown_minutes*INTERVAL '1 minute') FOR UPDATE SKIP LOCKED")
            .bind(pid).fetch_optional(&mut *tx).await?;
        let Some(policy)=policy else{continue;};
        let failures:Vec<(Uuid,String,String,String,String)>=sqlx::query_as("SELECT d.id,c.name,r.name,d.error,e.title FROM deliveries d JOIN channels c ON c.id=d.channel_id JOIN events e ON e.id=d.event_id JOIN routes r ON r.id=e.route_id WHERE d.status IN ('queued','failed') AND d.error IS NOT NULL AND d.attempts>=$1 AND d.last_error_at>=NOW()-$2::int*INTERVAL '1 minute' AND (CARDINALITY($3::uuid[])=0 OR d.channel_id=ANY($3)) AND (CARDINALITY($4::uuid[])=0 OR e.route_id=ANY($4)) AND NOT EXISTS(SELECT 1 FROM alert_incidents i WHERE i.policy_id=$5 AND i.delivery_id=d.id) ORDER BY d.last_error_at DESC LIMIT 1000")
            .bind(policy.min_attempts).bind(policy.window_minutes).bind(&policy.watch_channel_ids).bind(&policy.watch_route_ids).bind(pid).fetch_all(&mut *tx).await?;
        if failures.len()<policy.failure_threshold as usize {continue;}
        let destinations:Vec<(Uuid,)>=sqlx::query_as("SELECT id FROM channels WHERE id=ANY($1) AND enabled=true").bind(&policy.destination_ids).fetch_all(&mut *tx).await?;
        if destinations.is_empty() {continue;}
        let (source,channel,route,error,event_title)=&failures[0];
        let title=render(&policy.title,channel,route,error,event_title,failures.len()).chars().take(256).collect::<String>();
        let message=render(&policy.body,channel,route,error,event_title,failures.len()).chars().take(8000).collect::<String>();
        for (id,_,_,_,_) in &failures {sqlx::query("INSERT INTO alert_incidents(policy_id,delivery_id) VALUES($1,$2) ON CONFLICT DO NOTHING").bind(pid).bind(id).execute(&mut *tx).await?;}
        for (cid,) in destinations {
            sqlx::query("INSERT INTO alert_deliveries(id,policy_id,source_delivery_id,channel_id,title,message) VALUES($1,$2,$3,$4,$5,$6)")
                .bind(Uuid::new_v4()).bind(pid).bind(source).bind(cid).bind(&title).bind(&message).execute(&mut *tx).await?;
        }
        sqlx::query("UPDATE alert_policies SET last_triggered_at=NOW() WHERE id=$1").bind(pid).execute(&mut *tx).await?;
        tx.commit().await?;
    }
    Ok(())
}

async fn send_next(s:&AppState)->Result<bool> {
    let mut tx=s.db.begin().await?;
    let row:Option<(Uuid,Uuid,String,String)>=sqlx::query_as("SELECT id,channel_id,title,message FROM alert_deliveries WHERE (status='queued' AND next_attempt_at<=NOW()) OR (status='processing' AND locked_at<NOW()-INTERVAL '2 minutes') ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1").fetch_optional(&mut *tx).await?;
    let Some((id,cid,title,message))=row else{return Ok(false);};
    sqlx::query("UPDATE alert_deliveries SET status='processing',locked_at=NOW(),attempts=attempts+1 WHERE id=$1").bind(id).execute(&mut *tx).await?;tx.commit().await?;
    let channel=sqlx::query_as::<_,Channel>("SELECT * FROM channels WHERE id=$1").bind(cid).fetch_optional(&s.db).await?;
    let result=match channel {Some(c) if c.enabled=>send(&s.client,&c,&title,&message,4,s.allow_http,id).await,_=>Err(anyhow!("Alert recipient removed or disabled"))};
    match result {
        Ok(())=>{sqlx::query("UPDATE alert_deliveries SET status='sent',sent_at=NOW(),error=NULL,locked_at=NULL WHERE id=$1").bind(id).execute(&s.db).await?;},
        Err(error)=>{sqlx::query("UPDATE alert_deliveries SET status=CASE WHEN attempts>=5 THEN 'failed' ELSE 'queued' END,error=$2,locked_at=NULL,next_attempt_at=NOW()+POWER(2,LEAST(attempts,8))::int*$3::int*INTERVAL '1 second' WHERE id=$1").bind(id).bind(error.to_string().chars().take(512).collect::<String>()).bind(s.retry_seconds).execute(&s.db).await?;}
    }
    Ok(true)
}
pub async fn worker(s:AppState) {
    let mut last_schedule=tokio::time::Instant::now()-Duration::from_secs(10);
    loop {
        if last_schedule.elapsed()>=Duration::from_secs(5) {
            if let Err(error)=schedule(&s).await {tracing::error!(%error,"failure alert scheduling");}
            last_schedule=tokio::time::Instant::now();
        }
        match send_next(&s).await {
            Ok(true)=>{},
            Ok(false)=>tokio::time::sleep(Duration::from_millis(800)).await,
            Err(error)=>{tracing::error!(%error,"failure alert worker");tokio::time::sleep(Duration::from_secs(3)).await;}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn alert_placeholders_are_not_recursively_expanded() {
        assert_eq!(render("{failures}: {error}; {unknown}","channel","route","{channel}","title",2),"2: {channel}; {unknown}");
        assert_eq!(render("unfinished {error","c","r","e","t",1),"unfinished {error");
    }
}
