use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{collections::BTreeMap, io::Read};

pub const BUSINESS_RESPONSE_LIMIT_BYTES: usize = 8 * 1024 * 1024;
const BUSINESS_HEADER_LIMIT_BYTES: usize = 16 * 1024;
const READ_BUFFER_BYTES: usize = 4096;

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct ReadingPackSummary {
    pub pack_id: String,
    pub title: String,
    pub description: String,
    pub language: String,
    pub level: String,
    pub tags: Vec<String>,
    pub source: BTreeMap<String, Value>,
    pub passage_count: u32,
    pub question_count: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ProxyOperation {
    ListReadingPacks,
}

impl ProxyOperation {
    pub(crate) const fn method(self) -> &'static str {
        match self {
            Self::ListReadingPacks => "GET",
        }
    }

    pub(crate) const fn path(self) -> &'static str {
        match self {
            Self::ListReadingPacks => "/api/reading-packs",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProxyError {
    Unavailable,
    Timeout,
    ResponseTooLarge,
    InvalidResponse,
    UpstreamRejected,
}

impl ProxyError {
    pub const fn safe_message(self) -> &'static str {
        match self {
            Self::Unavailable => "The local learning service is unavailable.",
            Self::Timeout => "The local learning service timed out.",
            Self::ResponseTooLarge => "The local learning service returned too much data.",
            Self::InvalidResponse => "The local learning service returned an invalid response.",
            Self::UpstreamRejected => "The local learning service rejected the request.",
        }
    }
}

pub(crate) fn parse_reading_pack_list(body: &[u8]) -> Result<Vec<ReadingPackSummary>, ProxyError> {
    serde_json::from_slice(body).map_err(|_| ProxyError::InvalidResponse)
}

pub(crate) fn read_json_response<R: Read>(reader: &mut R) -> Result<Vec<u8>, ProxyError> {
    let mut response = Vec::with_capacity(READ_BUFFER_BYTES);
    let mut scratch = [0u8; READ_BUFFER_BYTES];
    let mut body_start = None;
    let mut content_length = None;

    loop {
        if let (Some(start), Some(length)) = (body_start, content_length) {
            let body_size = response.len().saturating_sub(start);
            if body_size == length {
                return Ok(response[start..].to_vec());
            }
            if body_size > length {
                return Err(ProxyError::InvalidResponse);
            }
        }

        let read = reader.read(&mut scratch).map_err(map_read_error)?;
        if read == 0 {
            return match (body_start, content_length) {
                (Some(start), None) => Ok(response[start..].to_vec()),
                _ => Err(ProxyError::InvalidResponse),
            };
        }
        if response.len().saturating_add(read) > BUSINESS_HEADER_LIMIT_BYTES + BUSINESS_RESPONSE_LIMIT_BYTES {
            return Err(ProxyError::ResponseTooLarge);
        }
        response.extend_from_slice(&scratch[..read]);

        if body_start.is_none() {
            if let Some(header_end) = find_header_end(&response) {
                if header_end > BUSINESS_HEADER_LIMIT_BYTES {
                    return Err(ProxyError::ResponseTooLarge);
                }
                let head = parse_response_head(&response[..header_end])?;
                let start = header_end + 4;
                if head.content_length.is_some_and(|length| length > BUSINESS_RESPONSE_LIMIT_BYTES)
                    || response.len().saturating_sub(start) > BUSINESS_RESPONSE_LIMIT_BYTES
                {
                    return Err(ProxyError::ResponseTooLarge);
                }
                body_start = Some(start);
                content_length = head.content_length;
            } else if response.len() > BUSINESS_HEADER_LIMIT_BYTES {
                return Err(ProxyError::ResponseTooLarge);
            }
        }
    }
}

struct ResponseHead {
    content_length: Option<usize>,
}

fn parse_response_head(raw: &[u8]) -> Result<ResponseHead, ProxyError> {
    if raw.contains(&0) {
        return Err(ProxyError::InvalidResponse);
    }
    let text = std::str::from_utf8(raw).map_err(|_| ProxyError::InvalidResponse)?;
    let mut lines = text.split("\r\n");
    let status_line = lines.next().ok_or(ProxyError::InvalidResponse)?;
    let mut status_parts = status_line.split_ascii_whitespace();
    let version = status_parts.next().ok_or(ProxyError::InvalidResponse)?;
    let status = status_parts.next().ok_or(ProxyError::InvalidResponse)?;
    if !matches!(version, "HTTP/1.0" | "HTTP/1.1")
        || status.len() != 3
        || !status.bytes().all(|byte| byte.is_ascii_digit())
    {
        return Err(ProxyError::InvalidResponse);
    }
    if status != "200" {
        return Err(ProxyError::UpstreamRejected);
    }

    let mut content_lengths = Vec::new();
    let mut has_transfer_encoding = false;
    let mut json_content_type = false;
    for line in lines {
        let (raw_name, raw_value) = line.split_once(':').ok_or(ProxyError::InvalidResponse)?;
        if raw_name.is_empty() || !raw_name.bytes().all(is_header_name_byte) {
            return Err(ProxyError::InvalidResponse);
        }
        let name = raw_name.to_ascii_lowercase();
        let value = raw_value.trim_matches([' ', '\t']);
        match name.as_str() {
            "content-length" => {
                if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
                    return Err(ProxyError::InvalidResponse);
                }
                content_lengths.push(value.parse::<usize>().map_err(|_| ProxyError::InvalidResponse)?);
            }
            "transfer-encoding" => has_transfer_encoding = true,
            "content-type" => {
                let media_type = value.to_ascii_lowercase();
                let media_type = media_type.split(';').next().unwrap_or_default().trim();
                json_content_type = media_type == "application/json" || media_type.ends_with("+json");
            }
            _ => {}
        }
    }
    let content_length = content_lengths.first().copied();
    if content_lengths.iter().any(|length| Some(*length) != content_length)
        || (content_length.is_some() && has_transfer_encoding)
        || has_transfer_encoding
        || !json_content_type
    {
        return Err(ProxyError::InvalidResponse);
    }
    Ok(ResponseHead { content_length })
}

fn find_header_end(bytes: &[u8]) -> Option<usize> {
    bytes.windows(4).position(|window| window == b"\r\n\r\n")
}

fn is_header_name_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&byte)
}

fn map_read_error(error: std::io::Error) -> ProxyError {
    match error.kind() {
        std::io::ErrorKind::TimedOut | std::io::ErrorKind::WouldBlock => ProxyError::Timeout,
        _ => ProxyError::Unavailable,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn response(status: &str, headers: &[(&str, String)], body: &[u8]) -> Vec<u8> {
        let mut output = format!("HTTP/1.1 {status}\r\n").into_bytes();
        for (name, value) in headers {
            output.extend_from_slice(format!("{name}: {value}\r\n").as_bytes());
        }
        output.extend_from_slice(b"\r\n");
        output.extend_from_slice(body);
        output
    }

    fn valid_body() -> &'static [u8] {
        br#"[{"pack_id":"pack-1","title":"Pack","description":"","language":"en","level":"B1","tags":["news"],"source":{"kind":"fixture"},"passage_count":1,"question_count":2}]"#
    }

    #[test]
    fn accepts_fixed_reading_pack_response() {
        let body = valid_body();
        let raw = response(
            "200 OK",
            &[("Content-Type", "application/json".into()), ("Content-Length", body.len().to_string())],
            body,
        );
        let parsed = read_json_response(&mut Cursor::new(raw)).unwrap();
        let packs = parse_reading_pack_list(&parsed).unwrap();
        assert_eq!(packs.len(), 1);
        assert_eq!(packs[0].pack_id, "pack-1");
    }

    #[test]
    fn rejects_non_success_malformed_and_oversized_responses() {
        let rejected = response("404 Not Found", &[("Content-Type", "application/json".into())], b"{}");
        assert_eq!(read_json_response(&mut Cursor::new(rejected)), Err(ProxyError::UpstreamRejected));
        let malformed = response("200 OK", &[("Content-Type", "text/plain".into())], b"{}");
        assert_eq!(read_json_response(&mut Cursor::new(malformed)), Err(ProxyError::InvalidResponse));
        let oversized = response(
            "200 OK",
            &[("Content-Type", "application/json".into()), ("Content-Length", (BUSINESS_RESPONSE_LIMIT_BYTES + 1).to_string())],
            b"",
        );
        assert_eq!(read_json_response(&mut Cursor::new(oversized)), Err(ProxyError::ResponseTooLarge));
    }

    #[test]
    fn rejects_invalid_json_and_does_not_expose_connection_secrets() {
        assert_eq!(parse_reading_pack_list(b"not json"), Err(ProxyError::InvalidResponse));
        for error in [ProxyError::Unavailable, ProxyError::Timeout, ProxyError::ResponseTooLarge, ProxyError::InvalidResponse, ProxyError::UpstreamRejected] {
            assert!(!error.safe_message().contains("secret-token"));
            assert!(!error.safe_message().contains("127.0.0.1:4567"));
        }
    }

    #[test]
    fn operation_is_structurally_fixed_to_the_business_allowlist() {
        let operation = ProxyOperation::ListReadingPacks;
        assert_eq!(operation.method(), "GET");
        assert_eq!(operation.path(), "/api/reading-packs");
        assert_ne!(operation.path(), "/health");
        assert_ne!(operation.path(), "/desktop/shutdown");
    }
}