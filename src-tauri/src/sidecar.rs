use crate::sidecar_protocol::{validate_health, validate_ready};
use getrandom::fill;
use std::{
    fs,
    io::{BufRead, BufReader, Read, Write},
    net::TcpStream,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

const TOKEN_ENV: &str = "LOCAL_ENGLISH_TRAINER_STARTUP_TOKEN";
const READY_ENV: &str = "LOCAL_ENGLISH_TRAINER_READY_FILE";
const ROOT_ENV: &str = "LOCAL_ENGLISH_TRAINER_USER_DATA_ROOT";
const MODE_ENV: &str = "LOCAL_ENGLISH_TRAINER_MODE";
const PORT_ENV: &str = "LOCAL_ENGLISH_TRAINER_PORT";
const PREFIX: &str = "local-english-trainer-p2_5b-";
const MAX_DIAGNOSTIC_LINES: usize = 64;
const MAX_HTTP_RESPONSE_BYTES: usize = 65_536;
const MAX_HTTP_HEADER_BYTES: usize = 16_384;
const READ_BUFFER_BYTES: usize = 4_096;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SidecarState { NotStarted, Starting, Ready, Stopping, Stopped, Failed }

#[derive(Debug)]
struct LaunchConfig { exe: PathBuf, cwd: PathBuf, user_root: PathBuf, ready_file: PathBuf, token: String }

#[cfg(test)]
impl LaunchConfig {
    fn safe_summary(&self) -> String {
        format!("sidecar exe={} cwd={}", self.exe.file_name().unwrap_or_default().to_string_lossy(), self.cwd.file_name().unwrap_or_default().to_string_lossy())
    }
}

pub(crate) struct SidecarManager {
    state: SidecarState,
    child: Option<Child>,
    token: Option<String>,
    endpoint: Option<u16>,
    temporary_root: Option<PathBuf>,
    readers: Vec<thread::JoinHandle<()>>,
}

impl Default for SidecarManager {
    fn default() -> Self {
        Self { state: SidecarState::NotStarted, child: None, token: None, endpoint: None, temporary_root: None, readers: vec![] }
    }
}

impl SidecarManager {
    pub(crate) fn state(&self) -> SidecarState { self.state }

    pub(crate) fn start(&mut self, resource_dir: &Path) -> Result<(), &'static str> {
        if self.state != SidecarState::NotStarted { return Err("sidecar manager is not idle"); }
        self.state = SidecarState::Starting;
        let result = (|| {
            let (exe, cwd) = resolve_resource(resource_dir)?;
            let root = create_temp_root()?;
            self.temporary_root = Some(root.clone());
            let config = LaunchConfig {
                exe,
                cwd,
                user_root: root.join("user-data"),
                ready_file: root.join("runtime").join("sidecar-ready.json"),
                token: generate_token()?,
            };
            let mut child = build_command(&config).spawn().map_err(|_| "sidecar could not start")?;
            let pid = child.id();
            self.readers = drain(&mut child);
            self.child = Some(child);
            let port = wait_ready(&config.ready_file, pid, self.child.as_mut().unwrap())?;
            eprintln!("LOCAL_ENGLISH_TRAINER_SIDECAR_READY");
            health(port, &config.token)?;
            eprintln!("LOCAL_ENGLISH_TRAINER_SIDECAR_HEALTH_OK");
            self.endpoint = Some(port);
            self.token = Some(config.token);
            self.state = SidecarState::Ready;
            Ok(())
        })();
        if result.is_err() { self.state = SidecarState::Failed; let _ = self.stop(); }
        result
    }

    pub(crate) fn stop(&mut self) -> Result<(), &'static str> {
        self.state = SidecarState::Stopping;
        if let Some(mut child) = self.child.take() { let _ = child.kill(); let _ = child.wait(); }
        for reader in self.readers.drain(..) { let _ = reader.join(); }
        self.token = None;
        self.endpoint = None;
        if let Some(root) = self.temporary_root.take() { remove_temp_root(&root)?; }
        self.state = SidecarState::Stopped;
        Ok(())
    }
}

impl Drop for SidecarManager { fn drop(&mut self) { let _ = self.stop(); } }

pub(crate) fn run_startup_probe(resource_dir: &Path) -> Result<(), &'static str> {
    let mut manager = SidecarManager::default();
    manager.start(resource_dir)?;
    if manager.state() != SidecarState::Ready { return Err("sidecar did not reach ready state"); }
    manager.stop()?;
    eprintln!("LOCAL_ENGLISH_TRAINER_SIDECAR_CLEANUP_COMPLETE");
    Ok(())
}

fn resolve_resource(resource_dir: &Path) -> Result<(PathBuf, PathBuf), &'static str> {
    let root = fs::canonicalize(resource_dir.join("sidecar").join("local-english-trainer-api")).map_err(|_| "sidecar resource root is missing")?;
    let exe = root.join("local-english-trainer-api.exe");
    if !exe.is_file() || !root.join("_internal").is_dir() { return Err("sidecar resource tree is incomplete"); }
    let exe = fs::canonicalize(exe).map_err(|_| "sidecar executable is invalid")?;
    if !exe.starts_with(&root) { return Err("sidecar executable escapes resource root"); }
    Ok((exe, root))
}

fn create_temp_root() -> Result<PathBuf, &'static str> {
    let mut bytes = [0u8; 16];
    fill(&mut bytes).map_err(|_| "secure random source failed")?;
    let root = std::env::temp_dir().join(format!("{PREFIX}{}", hex(&bytes)));
    if root.exists() { return Err("temporary root collision"); }
    fs::create_dir_all(&root).map_err(|_| "temporary root creation failed")?;
    Ok(root)
}

fn remove_temp_root(root: &Path) -> Result<(), &'static str> {
    let temp = fs::canonicalize(std::env::temp_dir()).map_err(|_| "temp directory unavailable")?;
    let root = fs::canonicalize(root).map_err(|_| "temporary root unavailable")?;
    if !root.starts_with(&temp) || !root.file_name().unwrap_or_default().to_string_lossy().starts_with(PREFIX) { return Err("temporary root cleanup was rejected"); }
    fs::remove_dir_all(root).map_err(|_| "temporary root cleanup failed")
}

fn generate_token() -> Result<String, &'static str> {
    let mut bytes = [0u8; 32];
    fill(&mut bytes).map_err(|_| "secure random source failed")?;
    Ok(hex(&bytes))
}

fn hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for b in bytes { use std::fmt::Write as _; let _ = write!(out, "{b:02x}"); }
    out
}

fn build_command(config: &LaunchConfig) -> Command {
    let mut command = Command::new(&config.exe);
    command.current_dir(&config.cwd).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .env(MODE_ENV, "desktop_production").env(ROOT_ENV, &config.user_root).env(READY_ENV, &config.ready_file)
        .env(PORT_ENV, "0").env(TOKEN_ENV, &config.token);
    command
}

fn drain(child: &mut Child) -> Vec<thread::JoinHandle<()>> {
    let mut readers = vec![];
    if let Some(stdout) = child.stdout.take() { readers.push(thread::spawn(move || drain_reader(stdout))); }
    if let Some(stderr) = child.stderr.take() { readers.push(thread::spawn(move || drain_reader(stderr))); }
    readers
}

fn drain_reader<R: Read + Send + 'static>(reader: R) {
    let mut kept = 0;
    for line in BufReader::new(reader).lines() {
        if line.is_err() { break; }
        kept += 1;
        if kept > MAX_DIAGNOSTIC_LINES { kept = MAX_DIAGNOSTIC_LINES; }
    }
}

fn wait_ready(path: &Path, pid: u32, child: &mut Child) -> Result<u16, &'static str> {
    let deadline = Instant::now() + Duration::from_secs(15);
    while Instant::now() < deadline {
        if child.try_wait().map_err(|_| "sidecar status check failed")?.is_some() { return Err("sidecar exited before ready"); }
        if let Ok(metadata) = fs::metadata(path) {
            if metadata.len() > 65_536 { return Err("ready file exceeds size limit"); }
            return Ok(validate_ready(&fs::read(path).map_err(|_| "ready file read failed")?, pid)?.port);
        }
        thread::sleep(Duration::from_millis(75));
    }
    Err("sidecar ready timeout")
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum HealthHttpError {
    Timeout, ReadFailed, HeaderTooLarge, ResponseTooLarge, HeaderIncomplete, MalformedHead,
    UnexpectedStatus, Unauthorized, InvalidContentType, MalformedFraming, BodyTooLarge,
    PrematureEof, UnsupportedTransferEncoding,
}

impl HealthHttpError {
    fn message(&self) -> &'static str {
        match self {
            Self::Timeout => "health response timed out",
            Self::ReadFailed => "health response read failed",
            Self::HeaderTooLarge => "health response header exceeds size limit",
            Self::ResponseTooLarge => "health response exceeds size limit",
            Self::HeaderIncomplete => "health response header is incomplete",
            Self::MalformedHead => "health response header is malformed",
            Self::UnexpectedStatus => "health returned an unexpected status",
            Self::Unauthorized => "health returned unauthorized",
            Self::InvalidContentType => "health returned an invalid content type",
            Self::MalformedFraming => "health response framing is malformed",
            Self::BodyTooLarge => "health response body exceeds size limit",
            Self::PrematureEof => "health response ended before its declared body",
            Self::UnsupportedTransferEncoding => "health response transfer encoding is unsupported",
        }
    }
}

#[derive(Debug)]
struct HttpHead { status_line: String, header_names: Vec<String>, content_length: Option<usize>, transfer_encoding: Option<String> }

fn health(port: u16, token: &str) -> Result<(), &'static str> {
    let addr = format!("127.0.0.1:{port}");
    let mut stream = TcpStream::connect_timeout(&addr.parse().map_err(|_| "health endpoint invalid")?, Duration::from_secs(5)).map_err(|_| "health connection failed")?;
    stream.set_read_timeout(Some(Duration::from_secs(5))).map_err(|_| "health timeout setup failed")?;
    stream.set_write_timeout(Some(Duration::from_secs(5))).map_err(|_| "health timeout setup failed")?;
    stream.write_all(&build_health_request(token)).map_err(|_| "health request failed")?;
    let body = read_bounded_http_response(&mut stream).map_err(|error| error.message())?;
    validate_health(&body)?;
    Ok(())
}

fn build_health_request(token: &str) -> Vec<u8> {
    format!("GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Local-English-Trainer-Token: {token}\r\nAccept: application/json\r\nConnection: close\r\n\r\n").into_bytes()
}

fn read_bounded_http_response<R: Read>(reader: &mut R) -> Result<Vec<u8>, HealthHttpError> {
    let mut response = Vec::with_capacity(READ_BUFFER_BYTES);
    let mut scratch = [0u8; READ_BUFFER_BYTES];
    let mut parsed_head: Option<HttpHead> = None;
    let mut body_start = 0;
    loop {
        if let Some(head) = &parsed_head {
            if let Some(content_length) = head.content_length {
                let body_bytes = response.len().saturating_sub(body_start);
                if body_bytes == content_length { emit_http_diagnostic(head, "content-length", body_bytes); return Ok(response[body_start..].to_vec()); }
                if body_bytes > content_length { return Err(HealthHttpError::MalformedFraming); }
            }
        }
        let read = reader.read(&mut scratch).map_err(map_read_error)?;
        if read == 0 {
            if let Some(head) = &parsed_head {
                if head.content_length.is_some() { return Err(HealthHttpError::PrematureEof); }
                emit_http_diagnostic(head, "connection-close", response.len() - body_start);
                return Ok(response[body_start..].to_vec());
            }
            return Err(HealthHttpError::HeaderIncomplete);
        }
        if response.len().saturating_add(read) > MAX_HTTP_RESPONSE_BYTES { return Err(HealthHttpError::ResponseTooLarge); }
        response.extend_from_slice(&scratch[..read]);
        if parsed_head.is_none() {
            if let Some(header_end) = find_header_end(&response) {
                if header_end > MAX_HTTP_HEADER_BYTES { return Err(HealthHttpError::HeaderTooLarge); }
                let head = parse_http_head(&response[..header_end])?;
                body_start = header_end + 4;
                if response.len() - body_start > MAX_HTTP_RESPONSE_BYTES - body_start { return Err(HealthHttpError::BodyTooLarge); }
                if head.content_length.is_none() && head.transfer_encoding.is_some() { return Err(HealthHttpError::UnsupportedTransferEncoding); }
                parsed_head = Some(head);
            } else if response.len() > MAX_HTTP_HEADER_BYTES { return Err(HealthHttpError::HeaderTooLarge); }
        }
    }
}

fn map_read_error(error: std::io::Error) -> HealthHttpError {
    match error.kind() { std::io::ErrorKind::TimedOut | std::io::ErrorKind::WouldBlock => HealthHttpError::Timeout, _ => HealthHttpError::ReadFailed }
}

fn find_header_end(bytes: &[u8]) -> Option<usize> { bytes.windows(4).position(|window| window == b"\r\n\r\n") }

fn parse_http_head(bytes: &[u8]) -> Result<HttpHead, HealthHttpError> {
    if bytes.contains(&0) { return Err(HealthHttpError::MalformedHead); }
    let text = std::str::from_utf8(bytes).map_err(|_| HealthHttpError::MalformedHead)?;
    let mut lines = text.split("\r\n");
    let status_line = lines.next().ok_or(HealthHttpError::MalformedHead)?;
    let mut status_parts = status_line.split_ascii_whitespace();
    let version = status_parts.next().ok_or(HealthHttpError::MalformedHead)?;
    let code = status_parts.next().ok_or(HealthHttpError::MalformedHead)?;
    if !matches!(version, "HTTP/1.0" | "HTTP/1.1") || code.len() != 3 || !code.bytes().all(|byte| byte.is_ascii_digit()) { return Err(HealthHttpError::MalformedHead); }
    let status = code.parse::<u16>().map_err(|_| HealthHttpError::MalformedHead)?;
    if status == 401 { return Err(HealthHttpError::Unauthorized); }
    if status != 200 { return Err(HealthHttpError::UnexpectedStatus); }
    let mut header_names = Vec::new();
    let mut content_lengths = Vec::new();
    let mut transfer_encodings = Vec::new();
    let mut content_type = None;
    for line in lines {
        let (raw_name, raw_value) = line.split_once(':').ok_or(HealthHttpError::MalformedHead)?;
        if raw_name.is_empty() || !raw_name.bytes().all(is_header_name_byte) { return Err(HealthHttpError::MalformedHead); }
        let name = raw_name.to_ascii_lowercase();
        let value = raw_value.trim_matches([' ', '\t']);
        header_names.push(name.clone());
        match name.as_str() {
            "content-length" => { if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) { return Err(HealthHttpError::MalformedFraming); } content_lengths.push(value.parse::<usize>().map_err(|_| HealthHttpError::MalformedFraming)?); }
            "transfer-encoding" => transfer_encodings.push(value.to_ascii_lowercase()),
            "content-type" => content_type = Some(value.to_ascii_lowercase()),
            _ => {}
        }
    }
    if let Some(content_type) = content_type {
        let media_type = content_type.split(';').next().unwrap_or_default().trim();
        if media_type != "application/json" && !media_type.ends_with("+json") { return Err(HealthHttpError::InvalidContentType); }
    }
    let content_length = content_lengths.first().copied();
    if content_lengths.iter().any(|value| Some(*value) != content_length) { return Err(HealthHttpError::MalformedFraming); }
    if content_length.is_some_and(|value| value > MAX_HTTP_RESPONSE_BYTES) { return Err(HealthHttpError::BodyTooLarge); }
    let transfer_encoding = (!transfer_encodings.is_empty()).then(|| transfer_encodings.join(","));
    if content_length.is_some() && transfer_encoding.is_some() { return Err(HealthHttpError::MalformedFraming); }
    Ok(HttpHead { status_line: status_line.to_owned(), header_names, content_length, transfer_encoding })
}

fn is_header_name_byte(byte: u8) -> bool { byte.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&byte) }

fn emit_http_diagnostic(head: &HttpHead, framing: &str, body_bytes: usize) {
    let headers = head.header_names.join(",");
    let content_length = head.content_length.map(|value| value.to_string()).unwrap_or_else(|| "none".to_owned());
    eprintln!("LET_HEALTH_HTTP_DIAG status={} headers={} framing={} content_length={} body_bytes={}", head.status_line, headers, framing, content_length, body_bytes);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    const HEALTH: &str = r#"{"status":"ok","app_version":"0.1.0","api_protocol_version":1,"schema_version":1,"run_mode":"desktop_production"}"#;

    struct FragmentedReader { chunks: Vec<Vec<u8>>, next: usize }
    impl Read for FragmentedReader {
        fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
            if self.next == self.chunks.len() { return Ok(0); }
            let chunk = &self.chunks[self.next];
            self.next += 1;
            buffer[..chunk.len()].copy_from_slice(chunk);
            Ok(chunk.len())
        }
    }
    fn response(status: &str, headers: &[(&str, String)], body: &str) -> Vec<u8> {
        let mut out = format!("HTTP/1.1 {status}\r\n").into_bytes();
        for (name, value) in headers { out.extend_from_slice(format!("{name}: {value}\r\n").as_bytes()); }
        out.extend_from_slice(b"\r\n"); out.extend_from_slice(body.as_bytes()); out
    }
    fn valid_response() -> Vec<u8> { response("200 OK", &[("Content-Type", "application/json; charset=utf-8".into()), ("Content-Length", HEALTH.len().to_string())], HEALTH) }
    #[test] fn tokens_are_hex_and_unique() { let a = generate_token().unwrap(); let b = generate_token().unwrap(); assert_eq!(a.len(), 64); assert_ne!(a, b); }
    #[test] fn temp_root_is_under_temp() { let root = create_temp_root().unwrap(); assert!(root.starts_with(std::env::temp_dir())); remove_temp_root(&root).unwrap(); }
    #[test] fn command_keeps_token_out_of_args() { let root = std::env::temp_dir(); let config = LaunchConfig { exe: root.join("a.exe"), cwd: root.clone(), user_root: root.join("u"), ready_file: root.join("r"), token: "secret".into() }; assert!(!config.safe_summary().contains("secret")); }
    #[test] fn reads_valid_content_length_response_and_validates_json() { let mut reader = Cursor::new(valid_response()); let body = read_bounded_http_response(&mut reader).unwrap(); assert!(validate_health(&body).is_ok()); }
    #[test] fn accepts_case_insensitive_header_names() { let raw = response("200 OK", &[("cOnTeNt-LeNgTh", HEALTH.len().to_string())], HEALTH); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)).unwrap(), HEALTH.as_bytes()); }
    #[test] fn accepts_identical_repeated_content_lengths() { let raw = response("200 OK", &[("Content-Length", HEALTH.len().to_string()), ("Content-Length", HEALTH.len().to_string())], HEALTH); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)).unwrap(), HEALTH.as_bytes()); }
    #[test] fn rejects_json_with_trailing_body_garbage() { let body = format!("{HEALTH}x"); let raw = response("200 OK", &[("Content-Length", body.len().to_string())], &body); assert!(validate_health(&read_bounded_http_response(&mut Cursor::new(raw)).unwrap()).is_err()); }
    #[test] fn reads_header_delimiter_and_body_across_read_boundaries() {
        let raw = valid_response();
        let split = raw.windows(4).position(|part| part == b"\r\n\r\n").unwrap() + 3;
        let mut reader = FragmentedReader { chunks: vec![raw[..split].to_vec(), raw[split..split + 1].to_vec(), raw[split + 1..].to_vec()], next: 0 };
        assert_eq!(read_bounded_http_response(&mut reader).unwrap(), HEALTH.as_bytes());
    }
    #[test] fn maps_read_timeout_without_waiting_for_eof() { assert_eq!(map_read_error(std::io::Error::from(std::io::ErrorKind::TimedOut)), HealthHttpError::Timeout); }
    #[test] fn rejects_non_success_statuses_without_json_parsing() { let raw = response("500 Internal Server Error", &[("Content-Length", "2".into())], "{}"); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)), Err(HealthHttpError::UnexpectedStatus)); let raw = response("401 Unauthorized", &[("Content-Length", "2".into())], "{}"); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)), Err(HealthHttpError::Unauthorized)); }
    #[test] fn rejects_invalid_or_conflicting_content_length() { let raw = response("200 OK", &[("Content-Length", "x".into())], HEALTH); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)), Err(HealthHttpError::MalformedFraming)); let raw = response("200 OK", &[("Content-Length", "1".into()), ("Content-Length", "2".into())], "{}"); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)), Err(HealthHttpError::MalformedFraming)); }
    #[test] fn rejects_declared_length_mismatch_and_unsupported_framing() { let raw = response("200 OK", &[("Content-Length", "1".into())], "{}"); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)), Err(HealthHttpError::MalformedFraming)); let raw = response("200 OK", &[("Content-Length", "3".into())], "{}"); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)), Err(HealthHttpError::PrematureEof)); let raw = response("200 OK", &[("Transfer-Encoding", "chunked".into())], "0\r\n\r\n"); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)), Err(HealthHttpError::UnsupportedTransferEncoding)); let raw = response("200 OK", &[("Content-Length", "2".into()), ("Transfer-Encoding", "chunked".into())], "{}"); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)), Err(HealthHttpError::MalformedFraming)); }
    #[test] fn rejects_large_headers_and_bodies() { let raw = response("200 OK", &[("X-Fill", "x".repeat(MAX_HTTP_HEADER_BYTES))], ""); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)), Err(HealthHttpError::HeaderTooLarge)); let raw = response("200 OK", &[("Content-Length", (MAX_HTTP_RESPONSE_BYTES + 1).to_string())], ""); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)), Err(HealthHttpError::BodyTooLarge)); }
    #[test] fn rejects_invalid_content_type_and_invalid_health_json() { let raw = response("200 OK", &[("Content-Type", "text/plain".into()), ("Content-Length", "2".into())], "{}"); assert_eq!(read_bounded_http_response(&mut Cursor::new(raw)), Err(HealthHttpError::InvalidContentType)); assert!(validate_health(b"not json").is_err()); }
    #[test] fn rejects_health_contract_mismatch_and_request_does_not_leak_token() { assert!(validate_health(br#"{"status":"ok","app_version":"wrong","api_protocol_version":1,"schema_version":1,"run_mode":"desktop_production"}"#).is_err()); assert!(validate_health(br#"{"status":"ok","app_version":"0.1.0","api_protocol_version":1,"schema_version":1,"run_mode":"wrong"}"#).is_err()); let request = build_health_request("secret-token"); assert!(request.windows(b"X-Local-English-Trainer-Token: secret-token".len()).any(|part| part == b"X-Local-English-Trainer-Token: secret-token")); assert!(!HealthHttpError::Timeout.message().contains("secret-token")); }
}