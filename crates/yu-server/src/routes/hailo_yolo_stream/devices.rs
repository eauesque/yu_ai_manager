use std::{fs, io, path::PathBuf};

use serde::Serialize;
use thiserror::Error;

use super::source_task::Resolution;

#[cfg(test)]
tokio::task_local! {
    static ENUMERATE_OBSERVER: std::sync::Arc<std::sync::atomic::AtomicUsize>;
}

#[cfg(test)]
pub(crate) async fn observe_enumerate_calls<T>(
    observer: std::sync::Arc<std::sync::atomic::AtomicUsize>,
    future: impl std::future::Future<Output = T>,
) -> T {
    ENUMERATE_OBSERVER.scope(observer, future).await
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct Device {
    pub(crate) index: u32,
    pub(crate) name: String,
    pub(crate) resolution: Option<Resolution>,
}

#[derive(Debug, Error)]
pub(crate) enum DeviceError {
    #[error("device detection failed")]
    Detection(#[source] io::Error),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Platform {
    Linux,
    Windows,
    MacOs,
    Other,
}

impl Platform {
    fn current() -> Self {
        if cfg!(target_os = "linux") {
            Self::Linux
        } else if cfg!(target_os = "windows") {
            Self::Windows
        } else if cfg!(target_os = "macos") {
            Self::MacOs
        } else {
            Self::Other
        }
    }
}

trait DeviceIo {
    fn video_devices(&self) -> io::Result<Vec<(u32, PathBuf)>>;
    fn canonicalize(&self, path: &std::path::Path) -> io::Result<PathBuf>;
    fn read_to_string(&self, path: &std::path::Path) -> io::Result<String>;

    #[allow(dead_code)]
    fn open_device(&self, path: &std::path::Path) -> io::Result<()>;
}

struct SystemIo;

impl DeviceIo for SystemIo {
    fn video_devices(&self) -> io::Result<Vec<(u32, PathBuf)>> {
        let mut devices = Vec::new();
        for entry in fs::read_dir("/dev")? {
            let entry = entry?;
            let name = entry.file_name();
            let Some(index) = name
                .to_str()
                .and_then(|name| name.strip_prefix("video"))
                .filter(|index| {
                    !index.is_empty() && index.bytes().all(|byte| byte.is_ascii_digit())
                })
                .and_then(|index| index.parse().ok())
            else {
                continue;
            };
            devices.push((index, entry.path()));
        }
        Ok(devices)
    }

    fn canonicalize(&self, path: &std::path::Path) -> io::Result<PathBuf> {
        path.canonicalize()
    }

    fn read_to_string(&self, path: &std::path::Path) -> io::Result<String> {
        fs::read_to_string(path)
    }

    fn open_device(&self, path: &std::path::Path) -> io::Result<()> {
        fs::File::open(path).map(drop)
    }
}

pub(crate) fn enumerate_devices() -> Result<Vec<Device>, DeviceError> {
    enumerate_devices_with(&SystemIo, Platform::current())
}

pub(crate) async fn enumerate_devices_async() -> Result<Vec<Device>, DeviceError> {
    #[cfg(test)]
    let _ = ENUMERATE_OBSERVER
        .try_with(|observer| observer.fetch_add(1, std::sync::atomic::Ordering::SeqCst));
    tokio::task::spawn_blocking(enumerate_devices)
        .await
        .map_err(|_| DeviceError::Detection(io::Error::other("device enumeration worker failed")))?
}

fn enumerate_devices_with(
    io: &dyn DeviceIo,
    platform: Platform,
) -> Result<Vec<Device>, DeviceError> {
    if platform != Platform::Linux {
        return Ok(Vec::new());
    }

    let mut candidates = io.video_devices().map_err(DeviceError::Detection)?;
    candidates.sort_by_key(|(index, _)| *index);
    let mut devices = Vec::new();
    for (index, _device_path) in candidates {
        let sysfs_path = PathBuf::from(format!("/sys/class/video4linux/video{index}"));
        let real_path = io
            .canonicalize(&sysfs_path)
            .map_err(DeviceError::Detection)?;
        if !real_path
            .to_string_lossy()
            .to_ascii_lowercase()
            .contains("usb")
        {
            continue;
        }
        let name = io
            .read_to_string(&sysfs_path.join("name"))
            .map_err(DeviceError::Detection)?
            .trim()
            .to_string();
        devices.push(Device {
            index,
            name,
            resolution: None,
        });
    }
    Ok(devices)
}

#[cfg(test)]
mod tests {
    use std::{
        collections::HashMap,
        sync::atomic::{AtomicUsize, Ordering},
    };

    use serde_json::json;

    use super::*;

    struct FixtureIo {
        candidates: io::Result<Vec<(u32, PathBuf)>>,
        real_paths: HashMap<PathBuf, PathBuf>,
        names: HashMap<PathBuf, String>,
        list_calls: AtomicUsize,
        open_calls: AtomicUsize,
    }

    impl FixtureIo {
        fn devices() -> Self {
            let usb = PathBuf::from("/sys/class/video4linux/video2");
            let non_usb = PathBuf::from("/sys/class/video4linux/video7");
            Self {
                candidates: Ok(vec![
                    (7, PathBuf::from("/dev/video7")),
                    (2, PathBuf::from("/dev/video2")),
                ]),
                real_paths: HashMap::from([
                    (
                        usb.clone(),
                        PathBuf::from("/sys/devices/pci0000:00/usb1/video4linux/video2"),
                    ),
                    (
                        non_usb.clone(),
                        PathBuf::from("/sys/devices/platform/csi/video4linux/video7"),
                    ),
                ]),
                names: HashMap::from([
                    (usb.join("name"), " Fixture Camera\n".to_string()),
                    (non_usb.join("name"), "CSI Camera\n".to_string()),
                ]),
                list_calls: AtomicUsize::new(0),
                open_calls: AtomicUsize::new(0),
            }
        }

        fn failure() -> Self {
            Self {
                candidates: Err(io::Error::new(io::ErrorKind::PermissionDenied, "injected")),
                real_paths: HashMap::new(),
                names: HashMap::new(),
                list_calls: AtomicUsize::new(0),
                open_calls: AtomicUsize::new(0),
            }
        }
    }

    impl DeviceIo for FixtureIo {
        fn video_devices(&self) -> io::Result<Vec<(u32, PathBuf)>> {
            self.list_calls.fetch_add(1, Ordering::SeqCst);
            self.candidates
                .as_ref()
                .map(Clone::clone)
                .map_err(|error| io::Error::new(error.kind(), error.to_string()))
        }

        fn canonicalize(&self, path: &std::path::Path) -> io::Result<PathBuf> {
            self.real_paths
                .get(path)
                .cloned()
                .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, path.display().to_string()))
        }

        fn read_to_string(&self, path: &std::path::Path) -> io::Result<String> {
            self.names
                .get(path)
                .cloned()
                .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, path.display().to_string()))
        }

        fn open_device(&self, _path: &std::path::Path) -> io::Result<()> {
            self.open_calls.fetch_add(1, Ordering::SeqCst);
            Ok(())
        }
    }

    #[test]
    fn linux_fixture_lists_only_named_usb_devices_without_opening_them() {
        let io = FixtureIo::devices();

        let devices = enumerate_devices_with(&io, Platform::Linux).unwrap();

        assert_eq!(
            devices,
            vec![Device {
                index: 2,
                name: "Fixture Camera".to_string(),
                resolution: None,
            }]
        );
        assert_eq!(io.open_calls.load(Ordering::SeqCst), 0);
        assert_eq!(
            serde_json::to_value(&devices).unwrap()[0]["resolution"],
            json!(null)
        );
    }

    #[test]
    fn windows_and_macos_return_no_devices_without_touching_io() {
        for platform in [Platform::Windows, Platform::MacOs] {
            let io = FixtureIo::devices();
            assert_eq!(enumerate_devices_with(&io, platform).unwrap(), Vec::new());
            assert_eq!(io.list_calls.load(Ordering::SeqCst), 0);
            assert_eq!(io.open_calls.load(Ordering::SeqCst), 0);
        }
    }

    #[test]
    fn enumeration_failure_remains_a_device_domain_error() {
        assert!(matches!(
            enumerate_devices_with(&FixtureIo::failure(), Platform::Linux),
            Err(DeviceError::Detection(error)) if error.kind() == io::ErrorKind::PermissionDenied
        ));
    }

    #[test]
    fn platform_support_matches_numeric_index_validation() {
        let numeric_index_is_valid = super::super::input::validate_source("0", &json!({})).is_ok();
        assert_eq!(
            numeric_index_is_valid,
            Platform::current() == Platform::Linux
        );
    }

    #[test]
    fn stream_ui_guards_nullable_resolution_and_empty_devices() {
        // Read at run time, not `include_str!`: the template lives in the
        // Python extension tree outside this crate, and a compile-time include
        // would make the crate unbuildable once yu-server is split out. When
        // the extension is absent the guard cannot be checked, so skip rather
        // than fail — the assertions below still run in this repository.
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../extensions");
        if !root.is_dir() {
            // Crate built outside this repository: nothing to check against.
            eprintln!("skipped: extension tree not present at {}", root.display());
            return;
        }
        let path =
            root.join("builtin_hailo_yolo_detect/templates/hailo_yolo_detect/_yolo_stream_ui.html");
        // Present-but-moved must fail, not skip — a silent skip would let the
        // guard rot away unnoticed.
        let template = std::fs::read_to_string(&path)
            .unwrap_or_else(|e| panic!("stream UI template missing at {}: {e}", path.display()));
        assert!(template.contains("var devices = data.devices || [];"));
        assert!(template.contains("if (devices.length === 0)"));
        assert!(template.contains("(d.resolution ? ' (' + d.resolution.width"));
    }

    #[cfg(target_os = "linux")]
    #[test]
    #[ignore = "release gate: observe enumeration on a Linux host with real video devices"]
    fn linux_real_os_device_smoke() {
        let devices = enumerate_devices().unwrap();
        assert!(devices.iter().all(|device| device.resolution.is_none()));
    }

    #[cfg(target_os = "windows")]
    #[test]
    #[ignore = "release gate: observe the empty device contract on a Windows host"]
    fn windows_real_os_device_smoke() {
        assert_eq!(enumerate_devices().unwrap(), Vec::new());
        assert!(super::super::input::validate_source("0", &json!({})).is_err());
    }

    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "release gate: observe the empty device contract on a macOS host"]
    fn macos_real_os_device_smoke() {
        assert_eq!(enumerate_devices().unwrap(), Vec::new());
        assert!(super::super::input::validate_source("0", &json!({})).is_err());
    }
}
