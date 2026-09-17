use std::{ffi::OsString, path::PathBuf};

use serde_json::Value;
use thiserror::Error;
use url::Url;

const REMOTE_PROTOCOLS: &[&str] = &[
    "crypto", "data", "rtp", "udp", "tcp", "tls", "http", "https", "rtsp",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum SourceKind {
    UsbIndex(u32),
    LocalFile(PathBuf),
    Remote(String),
}

#[derive(Debug, Error, PartialEq, Eq)]
pub(crate) enum ValidationError {
    #[error("source must not start with '-'")]
    LeadingDash,
    #[error("USB index is invalid")]
    InvalidUsbIndex,
    #[error("USB sources are not supported on this platform")]
    UnsupportedUsb,
    #[error("protocol is not allowed: {0}")]
    UnsupportedProtocol(String),
    #[error("file URL is invalid")]
    InvalidFileUrl,
    #[error("local file does not exist or is not a regular file: {0}")]
    InvalidLocalFile(PathBuf),
    #[error("local file is outside configured scan roots: {0}")]
    OutsideScanRoots(PathBuf),
}

pub(crate) fn classify_source(source: &str) -> Result<SourceKind, ValidationError> {
    let source = source.trim();
    if !source.is_empty() && source.bytes().all(|byte| byte.is_ascii_digit()) {
        return source
            .parse()
            .map(SourceKind::UsbIndex)
            .map_err(|_| ValidationError::InvalidUsbIndex);
    }

    #[cfg(target_os = "linux")]
    if let Some(index) = source.strip_prefix("/dev/video") {
        if !index.is_empty() && index.bytes().all(|byte| byte.is_ascii_digit()) {
            return index
                .parse()
                .map(SourceKind::UsbIndex)
                .map_err(|_| ValidationError::InvalidUsbIndex);
        }
    }

    // A bare Windows drive path ("C:\foo\video.mp4") is a one-letter "scheme"
    // followed by an opaque body as far as the `url` crate is concerned, so
    // `Url::parse` below would misclassify it as a Remote source with scheme
    // "c" rather than a local file. Only real `file://...` URLs should reach
    // the Url::parse branch.
    if cfg!(windows) && is_windows_drive_path(source) {
        return Ok(SourceKind::LocalFile(PathBuf::from(source)));
    }

    if let Ok(url) = Url::parse(source) {
        if url.scheme() == "file" {
            return url
                .to_file_path()
                .map(SourceKind::LocalFile)
                .map_err(|()| ValidationError::InvalidFileUrl);
        }
        return Ok(SourceKind::Remote(source.to_string()));
    }

    Ok(SourceKind::LocalFile(PathBuf::from(source)))
}

fn is_windows_drive_path(source: &str) -> bool {
    let bytes = source.as_bytes();
    bytes.len() >= 3
        && bytes[0].is_ascii_alphabetic()
        && bytes[1] == b':'
        && matches!(bytes[2], b'\\' | b'/')
}

pub(crate) fn validate_source(source: &str, config: &Value) -> Result<SourceKind, ValidationError> {
    let source = source.trim();
    if source.starts_with('-') {
        return Err(ValidationError::LeadingDash);
    }

    match classify_source(source)? {
        SourceKind::LocalFile(path) => validate_local_file(path, config).map(SourceKind::LocalFile),
        SourceKind::Remote(remote) => {
            let scheme = Url::parse(&remote)
                .expect("remote sources were parsed during classification")
                .scheme()
                .to_string();
            if REMOTE_PROTOCOLS.contains(&scheme.as_str()) {
                Ok(SourceKind::Remote(remote))
            } else {
                Err(ValidationError::UnsupportedProtocol(scheme))
            }
        }
        usb @ SourceKind::UsbIndex(_) => {
            if cfg!(target_os = "linux") {
                Ok(usb)
            } else {
                Err(ValidationError::UnsupportedUsb)
            }
        }
    }
}

fn validate_local_file(path: PathBuf, config: &Value) -> Result<PathBuf, ValidationError> {
    let canonical = path
        .canonicalize()
        .map_err(|_| ValidationError::InvalidLocalFile(path.clone()))?;
    if !canonical
        .metadata()
        .is_ok_and(|metadata| metadata.is_file())
    {
        return Err(ValidationError::InvalidLocalFile(path));
    }

    let inside = crate::ext_config::global_scan_roots(config)
        .iter()
        .filter_map(|root| PathBuf::from(root).canonicalize().ok())
        .any(|root| crate::path_guard::path_is_within(&canonical, &root));
    if inside {
        Ok(canonical)
    } else {
        Err(ValidationError::OutsideScanRoots(canonical))
    }
}

pub(crate) fn ffmpeg_input_args(source: &SourceKind) -> Result<Vec<OsString>, ValidationError> {
    match source {
        #[cfg(target_os = "linux")]
        SourceKind::UsbIndex(index) => Ok(["-f", "v4l2", "-i"]
            .into_iter()
            .map(OsString::from)
            .chain([OsString::from(format!("/dev/video{index}"))])
            .collect()),
        #[cfg(not(target_os = "linux"))]
        SourceKind::UsbIndex(_) => Err(ValidationError::UnsupportedUsb),
        SourceKind::LocalFile(path) => Ok(vec![OsString::from("-i"), path.as_os_str().into()]),
        SourceKind::Remote(url) => Ok(vec![OsString::from("-i"), url.into()]),
    }
}

#[cfg(test)]
mod tests {
    use std::fs;

    use serde_json::json;
    use tempfile::tempdir;

    use super::*;

    fn config(root: &std::path::Path) -> Value {
        json!({"scan_roots": [{"path": root, "enabled": true}]})
    }

    #[test]
    fn accepts_real_files_inside_enabled_scan_roots() {
        let directory = tempdir().unwrap();
        let file = directory.path().join("video.mp4");
        fs::write(&file, b"video").unwrap();

        assert_eq!(
            validate_source(file.to_str().unwrap(), &config(directory.path())),
            Ok(SourceKind::LocalFile(file.canonicalize().unwrap()))
        );

        let file_url = Url::from_file_path(&file).unwrap().to_string();
        assert!(validate_source(&file_url, &config(directory.path())).is_ok());
    }

    #[test]
    fn rejects_files_outside_scan_roots() {
        let directory = tempdir().unwrap();
        let root = directory.path().join("root");
        fs::create_dir(&root).unwrap();
        let outside = directory.path().join("outside.mp4");
        fs::write(&outside, b"video").unwrap();

        assert!(matches!(
            validate_source(outside.to_str().unwrap(), &config(&root)),
            Err(ValidationError::OutsideScanRoots(_))
        ));
    }

    #[cfg(unix)]
    #[test]
    fn rejects_symlinks_that_escape_scan_roots() {
        use std::os::unix::fs::symlink;

        let directory = tempdir().unwrap();
        let root = directory.path().join("root");
        fs::create_dir(&root).unwrap();
        let outside = directory.path().join("outside.mp4");
        fs::write(&outside, b"video").unwrap();
        let link = root.join("escape.mp4");
        symlink(&outside, &link).unwrap();

        assert!(matches!(
            validate_source(link.to_str().unwrap(), &config(&root)),
            Err(ValidationError::OutsideScanRoots(_))
        ));
    }

    #[test]
    fn rejects_missing_files_and_directories() {
        let directory = tempdir().unwrap();
        let missing = directory.path().join("missing.mp4");

        assert!(matches!(
            validate_source(missing.to_str().unwrap(), &config(directory.path())),
            Err(ValidationError::InvalidLocalFile(_))
        ));
        assert!(matches!(
            validate_source(
                directory.path().to_str().unwrap(),
                &config(directory.path())
            ),
            Err(ValidationError::InvalidLocalFile(_))
        ));
    }

    #[test]
    fn rejects_files_inside_disabled_scan_roots() {
        let directory = tempdir().unwrap();
        let file = directory.path().join("video.mp4");
        fs::write(&file, b"video").unwrap();
        let config = json!({
            "scan_roots": [{"path": directory.path(), "enabled": false}]
        });

        assert!(matches!(
            validate_source(file.to_str().unwrap(), &config),
            Err(ValidationError::OutsideScanRoots(_))
        ));
    }

    #[test]
    fn rejects_leading_dash() {
        assert_eq!(
            validate_source("  -i", &json!({})),
            Err(ValidationError::LeadingDash)
        );
    }

    #[test]
    fn rejects_concat_pipe_and_unknown_protocols() {
        for source in ["concat:one|two", "pipe:0", "ftp://example.test/video"] {
            assert!(matches!(
                validate_source(source, &json!({})),
                Err(ValidationError::UnsupportedProtocol(_))
            ));
        }
    }

    #[test]
    fn accepts_allowlisted_remote_protocols() {
        for source in [
            "crypto:file.enc",
            "data:text/plain,video",
            "rtp://example.test/video",
            "udp://example.test:5000",
            "tcp://example.test:5000",
            "tls://example.test:443",
            "http://example.test/video",
            "https://example.test/video",
            "rtsp://example.test/video",
        ] {
            assert_eq!(
                validate_source(source, &json!({})),
                Ok(SourceKind::Remote(source.to_string()))
            );
        }
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn linux_numeric_usb_index_produces_v4l2_args() {
        let source = validate_source("0", &json!({})).unwrap();
        assert_eq!(
            ffmpeg_input_args(&source).unwrap(),
            ["-f", "v4l2", "-i", "/dev/video0"]
                .map(OsString::from)
                .to_vec()
        );
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn linux_device_path_is_the_same_usb_source() {
        assert_eq!(
            validate_source("/dev/video0", &json!({})),
            Ok(SourceKind::UsbIndex(0))
        );
    }

    #[cfg(not(target_os = "linux"))]
    #[test]
    fn non_linux_numeric_usb_index_is_rejected() {
        assert_eq!(
            validate_source("0", &json!({})),
            Err(ValidationError::UnsupportedUsb)
        );
    }
}
