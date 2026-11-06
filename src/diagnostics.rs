//! Read-only connectivity checks. Never send messages or return provider response bodies.
use crate::*;
fn step(name:&str,status:&str,detail:impl ToString)->Value{json!({"name":name,"status":status,"detail":detail.to_string()})}
fn response(steps:Vec<Value>)->Json<Value>{Json(json!({"ok":!steps.iter().any(|s|s["status"]=="failed"),"steps":steps,"sent":false}))}
pub async fn channel(State(s):State<AppState>,h:HeaderMap,Path(id):Path<Uuid>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;
 let c=sqlx::query_as::<_,Channel>("SELECT * FROM channels WHERE id=$1").bind(id).fetch_optional(&s.db).await.map_err(db_error)?.ok_or_else(||err(StatusCode::NOT_FOUND,"Channel not found"))?;
 Ok(check(&s,&c).await)
}
#[derive(Deserialize)]
pub struct Draft {id:Option<Uuid>,kind:String,config:Value}
pub async fn draft(State(s):State<AppState>,h:HeaderMap,Json(mut draft):Json<Draft>)->ApiResult<Value>{
 auth::authenticated(&h,&s).await?;
 if !supported(&draft.kind){return Err(err(StatusCode::BAD_REQUEST,"Unsupported channel type"));}
 if let Some(id)=draft.id {
  let old:Option<(Value,)>=sqlx::query_as("SELECT config FROM channels WHERE id=$1").bind(id).fetch_optional(&s.db).await.map_err(db_error)?;
  let old=old.ok_or_else(||err(StatusCode::NOT_FOUND,"Channel not found"))?;
  restore_masked(&mut draft.config,&old.0);
 }
 let c=Channel{id:draft.id.unwrap_or_else(Uuid::new_v4),name:String::new(),kind:draft.kind,config:draft.config,enabled:true,created_at:Utc::now()};
 Ok(check(&s,&c).await)
}
async fn bot_call(client:&reqwest::Client,cfg:&Value,method:&str,payload:Value)->Result<Value>{
 let token=cfg["bot_token"].as_str().unwrap_or("");
 if token.is_empty()||!token.chars().all(|c|c.is_ascii_alphanumeric()||":_-".contains(c)){return Err(anyhow!("Invalid bot token"));}
 let result=client.post(format!("https://api.telegram.org/bot{token}/{method}")).json(&payload).send().await.map_err(|_|anyhow!("Telegram request failed; check connectivity and proxy settings"))?;
 let status=result.status();
 // Avoid retaining or reflecting provider errors containing tokens or identifiers.
 if status==reqwest::StatusCode::TOO_MANY_REQUESTS {return Err(anyhow!("Telegram rate limit; wait before retrying"));}
 if !status.is_success(){return Err(anyhow!("Telegram rejected the request (HTTP {})",status.as_u16()));}
 let data:Value=result.json().await.map_err(|_|anyhow!("Invalid Telegram response"))?;
 if data["ok"]!=true{return Err(anyhow!("Telegram rejected the request"));}
 Ok(data["result"].clone())
}
async fn check(s:&AppState,c:&Channel)->Json<Value>{
 let mut steps=vec![];
 if let Err(e)=valid_config(&c.kind,&c.config,s.allow_http){steps.push(step("configuration","failed",e));return response(steps);}
 steps.push(step("configuration","passed","Required channel settings are valid."));
 if c.kind!="telegram"{steps.push(step("connectivity","warning","Use Test to send a notification for this integration."));return response(steps);}
 if matches!(proxy::mode(&c.config),"mtproto"|"webproxy"){
  match telegram::transport(&c.config,"",Uuid::new_v4(),true,false).await {
   Ok(data)=>if let Some(items)=data["steps"].as_array(){steps.extend(items.iter().cloned());},
   Err(e)=>steps.push(step("transport","failed",e)),
  }
  return response(steps);
 }
 let client=match proxy::client(&s.client,&c.config){Ok(client)=>client,Err(e)=>{steps.push(step("transport","failed",e));return response(steps);}};
 match client.get("https://api.telegram.org").send().await {
  Ok(_)=>steps.push(step("transport","passed",if proxy::mode(&c.config)=="http"{"Telegram is reachable through the configured HTTP proxy."}else{"Telegram HTTPS is reachable."})),
  Err(_)=>{steps.push(step("transport","failed","Telegram HTTPS is unreachable; check DNS, TLS, firewall and proxy credentials. No direct fallback was attempted."));return response(steps);}
 }
 let bot=match bot_call(&client,&c.config,"getMe",json!({})).await {
  Ok(bot) if bot["is_bot"]==true=>{steps.push(step("credentials","passed","Telegram accepted the bot token."));bot},
  _=>{steps.push(step("credentials","failed","Bot authentication failed; check the token and Telegram rate limits."));return response(steps);}
 };
 let chat=match bot_call(&client,&c.config,"getChat",json!({"chat_id":c.config["chat_id"]})).await {
  Ok(chat)=>{steps.push(step("destination","passed","The bot can access the chat."));chat},
  Err(e)=>{steps.push(step("destination","failed",e));return response(steps);}
 };
 match bot_call(&client,&c.config,"getChatMember",json!({"chat_id":c.config["chat_id"],"user_id":bot["id"]})).await {
  Ok(member)=>{
   let status=member["status"].as_str().unwrap_or("");
   let denied=matches!(status,"left"|"kicked") || (status=="restricted" && (member["is_member"]!=true||member["can_send_messages"]!=true)) || (chat["type"]=="channel" && status!="creator" && (status!="administrator"||member["can_post_messages"]!=true));
   if denied {
    if let Some(destination)=steps.last_mut(){*destination=step("destination","failed","The bot cannot send to this chat; check membership and posting permissions.");}
   }
  }
  Err(_)=>{},
 }
 response(steps)
}
