use serde::Deserialize;
use serde_json::Value;

#[derive(Debug, Clone, Deserialize)]
pub(crate) struct ReadyPayload { pub status: String, pub pid: u32, pub host: String, pub port: u16, pub app_version: String, pub api_protocol_version: u32, pub schema_version: u32, pub run_mode: String }
#[derive(Debug, Clone, Deserialize)]
pub(crate) struct HealthPayload { pub status: String, pub app_version: String, pub api_protocol_version: u32, pub schema_version: u32, pub run_mode: String }
#[derive(Debug, Clone, Deserialize)]
struct VersionFile { app_version: String, api_protocol_version: u32, schema_version: u32 }

pub(crate) fn validate_ready(raw: &[u8], expected_pid: u32) -> Result<ReadyPayload, &'static str> {
    if raw.len() > 65_536 { return Err("ready file exceeds size limit"); }
    let value: Value = serde_json::from_slice(raw).map_err(|_| "ready file is not valid JSON")?;
    reject_sensitive_fields(&value)?;
    let ready: ReadyPayload = serde_json::from_value(value).map_err(|_| "ready payload has an invalid shape")?;
    if ready.status != "ready" || ready.pid != expected_pid || ready.host != "127.0.0.1" || ready.port == 0 || ready.run_mode != "desktop_production" { return Err("ready payload failed protocol validation"); }
    validate_versions(&ready.app_version, ready.api_protocol_version, ready.schema_version)?;
    Ok(ready)
}

pub(crate) fn validate_health(raw: &[u8]) -> Result<HealthPayload, &'static str> {
    if raw.len() > 65_536 { return Err("health response exceeds size limit"); }
    let health: HealthPayload = serde_json::from_slice(raw).map_err(|_| "health response is not valid JSON")?;
    if health.status != "ok" || health.run_mode != "desktop_production" { return Err("health response failed protocol validation"); }
    validate_versions(&health.app_version, health.api_protocol_version, health.schema_version)?;
    Ok(health)
}

#[derive(Debug, Clone, Deserialize)]
struct ShutdownPayload { status: String }

pub fn validate_shutdown(raw: &[u8]) -> Result<(), &'static str> {
    if raw.len() > 65_536 { return Err("shutdown response exceeds size limit"); }
    let shutdown: ShutdownPayload = serde_json::from_slice(raw).map_err(|_| "shutdown response is not valid JSON")?;
    if shutdown.status != "shutting_down" { return Err("shutdown response failed protocol validation"); }
    Ok(())
}
fn validate_versions(app: &str, api: u32, schema: u32) -> Result<(), &'static str> {
    let expected: VersionFile = serde_json::from_str(include_str!("../../version.json")).map_err(|_| "embedded version contract is invalid")?;
    if app != expected.app_version || api != expected.api_protocol_version || schema != expected.schema_version { return Err("sidecar version contract does not match"); }
    Ok(())
}

fn reject_sensitive_fields(value: &Value) -> Result<(), &'static str> {
    let object = value.as_object().ok_or("ready payload must be an object")?;
    if object.keys().any(|key| { let key = key.to_ascii_lowercase(); key.contains("token") || key.contains("database") || key.contains("user_data") }) { return Err("ready payload contains a sensitive field"); }
    Ok(())
}

#[cfg(test)]
mod tests { use super::*;
 fn ready() -> Vec<u8> { br#"{"status":"ready","pid":7,"host":"127.0.0.1","port":4567,"app_version":"0.1.0","api_protocol_version":1,"schema_version":1,"run_mode":"desktop_production"}"#.to_vec() }
 #[test] fn accepts_ready() { assert!(validate_ready(&ready(),7).is_ok()); }
 #[test] fn rejects_wrong_pid_and_sensitive_fields() { assert!(validate_ready(&ready(),8).is_err()); assert!(validate_ready(br#"{"token":"x"}"#,7).is_err()); }
 #[test] fn rejects_wrong_host() { let raw=String::from_utf8(ready()).unwrap().replace("127.0.0.1","0.0.0.0"); assert!(validate_ready(raw.as_bytes(),7).is_err()); }
 #[test] fn accepts_exact_shutdown_contract() { assert!(validate_shutdown(br#"{"status":"shutting_down"}"#).is_ok()); }
 #[test] fn rejects_shutdown_malformed_or_wrong_status() { assert!(validate_shutdown(b"not json").is_err()); assert!(validate_shutdown(br#"{"status":"ok"}"#).is_err()); assert!(validate_shutdown(&vec![b'x'; 65_537]).is_err()); }
}