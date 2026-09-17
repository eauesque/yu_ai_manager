use ignore::WalkBuilder;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

pub struct WalkConfig {
    pub recursive: bool,
    /// 拡張子リスト（例: [".png", ".jpg"]）。空なら全ファイル。
    pub extensions: Vec<String>,
    /// 除外するディレクトリ名（パスコンポーネント単位）
    pub exclude_dirs: Vec<String>,
}

/// Python の iter_files 相当。シンボリックリンクを除外し、
/// stop_signal が true になったら即中断する。
pub fn iter_files<'a>(
    root: &'a Path,
    config: &'a WalkConfig,
    stop_signal: Option<Arc<AtomicBool>>,
) -> impl Iterator<Item = PathBuf> + 'a {
    let exts: Vec<String> = config
        .extensions
        .iter()
        .map(|e| e.to_ascii_lowercase())
        .collect();
    let exclude: std::collections::HashSet<String> = config.exclude_dirs.iter().cloned().collect();

    let walker = WalkBuilder::new(root)
        .hidden(false)
        .follow_links(false)
        .max_depth(if config.recursive { None } else { Some(1) })
        .build();

    walker.filter_map(move |entry| {
        if let Some(sig) = &stop_signal {
            if sig.load(Ordering::Relaxed) {
                return None;
            }
        }
        let entry = entry.ok()?;
        let path = entry.path().to_path_buf();
        if !path.is_file() || path.is_symlink() {
            return None;
        }
        // 除外ディレクトリチェック（先祖ディレクトリ名で判定）
        for ancestor in path.ancestors().skip(1) {
            if let Some(name) = ancestor.file_name() {
                if exclude.contains(name.to_string_lossy().as_ref()) {
                    return None;
                }
            }
        }
        let suffix = path
            .extension()
            .map(|e| format!(".{}", e.to_string_lossy().to_ascii_lowercase()))
            .unwrap_or_default();
        if exts.is_empty() || exts.contains(&suffix) {
            Some(path)
        } else {
            None
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn setup() -> TempDir {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("a.png"), b"x").unwrap();
        fs::write(dir.path().join("b.jpg"), b"x").unwrap();
        fs::write(dir.path().join("c.txt"), b"x").unwrap();
        let sub = dir.path().join("sub");
        fs::create_dir(&sub).unwrap();
        fs::write(sub.join("d.png"), b"x").unwrap();
        dir
    }

    #[test]
    fn test_ext_filter_non_recursive() {
        let dir = setup();
        let cfg = WalkConfig {
            recursive: false,
            extensions: vec![".png".into(), ".jpg".into()],
            exclude_dirs: vec![],
        };
        let mut paths: Vec<_> = iter_files(dir.path(), &cfg, None).collect();
        paths.sort();
        assert_eq!(paths.len(), 2);
        assert!(paths.iter().any(|p| p.ends_with("a.png")));
        assert!(paths.iter().any(|p| p.ends_with("b.jpg")));
    }

    #[test]
    fn test_recursive() {
        let dir = setup();
        let cfg = WalkConfig {
            recursive: true,
            extensions: vec![".png".into()],
            exclude_dirs: vec![],
        };
        let paths: Vec<_> = iter_files(dir.path(), &cfg, None).collect();
        assert_eq!(paths.len(), 2); // a.png + sub/d.png
    }

    #[test]
    fn test_exclude_dir() {
        let dir = setup();
        let cfg = WalkConfig {
            recursive: true,
            extensions: vec![".png".into()],
            exclude_dirs: vec!["sub".into()],
        };
        let paths: Vec<_> = iter_files(dir.path(), &cfg, None).collect();
        assert_eq!(paths.len(), 1); // a.png のみ
    }

    #[test]
    fn test_stop_signal() {
        let dir = setup();
        let stop = Arc::new(AtomicBool::new(true));
        let cfg = WalkConfig {
            recursive: true,
            extensions: vec![],
            exclude_dirs: vec![],
        };
        let paths: Vec<_> = iter_files(dir.path(), &cfg, Some(stop)).collect();
        assert_eq!(paths.len(), 0);
    }
}
