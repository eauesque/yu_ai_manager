#[path = "external_editor_config.rs"]
mod config;
#[path = "external_editor_launch.rs"]
mod launch;
#[path = "external_editor_monitor.rs"]
mod monitor;

pub use config::{get_external_editor_config, set_external_editor_config, EditorConfig};
pub use launch::open_in_external_editor;
pub use monitor::MonitoredEditorFiles;

#[cfg(test)]
pub use config::{editor_config_path, load_editor_config, save_editor_config};
#[cfg(test)]
pub use monitor::{file_mtime, EditorClosedPayload};

#[cfg(test)]
#[path = "external_editor_tests.rs"]
mod tests;
