use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    time::Duration,
};

use infer_core::engine::{TagPrediction, TagResult};
use tokio::{process::Command, time::timeout};

const NATIVE_VIDEO_EXTENSIONS: &[&str] = &["mp4", "webm", "avi", "mov", "mkv", "m4v", "ogv"];

pub(crate) fn is_native_video_format(path: &str) -> bool {
    Path::new(path)
        .extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| NATIVE_VIDEO_EXTENSIONS.contains(&extension.to_lowercase().as_str()))
        .unwrap_or(false)
}

async fn get_video_duration_ms(video_path: &Path) -> Option<i64> {
    let output = timeout(
        Duration::from_secs(10),
        Command::new("ffprobe")
            .args([
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
            ])
            .arg(video_path)
            .output(),
    )
    .await
    .ok()?
    .ok()?;

    if !output.status.success() {
        return None;
    }

    let raw = String::from_utf8_lossy(&output.stdout);
    let raw = raw.trim();
    if raw.is_empty() || raw == "N/A" {
        return None;
    }

    let duration_ms = raw.parse::<f64>().ok()? * 1000.0;
    if !duration_ms.is_finite() || duration_ms < i64::MIN as f64 || duration_ms > i64::MAX as f64 {
        return None;
    }
    Some(crate::num::sat_i64(duration_ms))
}

fn seconds_to_timestamp(seconds: f64) -> String {
    let h = crate::num::sat_i64(seconds / 3600.0);
    // Same conversion as the line above, so use the same helper: the bare cast
    // here had identical saturating semantics but did not say so, and left
    // this one line of the function outside the audited wrapper.
    let m = crate::num::sat_i64((seconds % 3600.0) / 60.0);
    let s = seconds % 60.0;
    format!("{:02}:{:02}:{:06.3}", h, m, s)
}

async fn extract_frame(video_path: &Path, out: &Path, timestamp: &str) -> bool {
    let output = timeout(
        Duration::from_secs(15),
        Command::new("ffmpeg")
            .args(["-ss", timestamp, "-i"])
            .arg(video_path)
            .args(["-vframes", "1", "-q:v", "2", "-pix_fmt", "yuvj420p", "-y"])
            .arg(out)
            .output(),
    )
    .await;

    matches!(output, Ok(Ok(output)) if output.status.success()) && out.exists()
}

/// Parses ffmpeg `showinfo` stderr for scene-change timestamps.
///
/// Split out from the ffmpeg call so the parsing and the max-scene thinning can
/// be tested without a video. Mirrors `_detect_scene_changes` in
/// `core/files_core/video_keyframes.py`, including its even-sampling step when
/// more scenes are found than `max_scenes`.
pub(crate) fn parse_scene_timestamps(stderr: &str, max_scenes: usize) -> Vec<f64> {
    let mut timestamps = Vec::new();
    let mut rest = stderr;
    while let Some(at) = rest.find("pts_time:") {
        rest = &rest[at + "pts_time:".len()..];
        let value: String = rest
            .trim_start()
            .chars()
            .take_while(|c| c.is_ascii_digit() || *c == '.')
            .collect();
        if let Ok(seconds) = value.parse::<f64>() {
            timestamps.push(seconds);
        }
    }
    if max_scenes > 0 && timestamps.len() > max_scenes {
        let step = timestamps.len() as f64 / max_scenes as f64;
        timestamps = (0..max_scenes)
            .map(|index| timestamps[crate::num::sat_usize(index as f64 * step)])
            .collect();
    }
    timestamps
}

async fn detect_scene_changes(video_path: &Path, threshold: f64, max_scenes: usize) -> Vec<f64> {
    let output = tokio::process::Command::new("ffmpeg")
        .arg("-i")
        .arg(video_path)
        .arg("-vf")
        .arg(format!("select='gt(scene,{threshold})',showinfo"))
        .arg("-f")
        .arg("null")
        .arg("-")
        .output()
        .await;
    match output {
        Ok(output) => parse_scene_timestamps(&String::from_utf8_lossy(&output.stderr), max_scenes),
        Err(error) => {
            tracing::debug!(%error, path = %video_path.display(), "scene detection failed");
            Vec::new()
        }
    }
}

pub(crate) async fn extract_keyframes(
    video_path: &Path,
    dir: &Path,
    count: u32,
    strategy: &str,
) -> Vec<PathBuf> {
    extract_keyframes_with_threshold(video_path, dir, count, strategy, 0.4).await
}

pub(crate) async fn extract_keyframes_with_threshold(
    video_path: &Path,
    dir: &Path,
    count: u32,
    strategy: &str,
    scene_threshold: f64,
) -> Vec<PathBuf> {
    let duration_ms = get_video_duration_ms(video_path).await;

    if strategy == "single" {
        let timestamp = match duration_ms {
            Some(duration_ms) if duration_ms >= 1000 => {
                seconds_to_timestamp(duration_ms as f64 / 1000.0 * 0.25)
            }
            _ => "00:00:00.000".to_string(),
        };
        let out = dir.join("frame_0.jpg");
        return if extract_frame(video_path, &out, &timestamp).await {
            vec![out]
        } else {
            Vec::new()
        };
    }

    // Python tries scene detection first and falls through to uniform when it
    // finds nothing (video_keyframes.py: "scene": ... fallback to uniform).
    if strategy == "scene" {
        let positions = detect_scene_changes(video_path, scene_threshold, count as usize).await;
        if !positions.is_empty() {
            let mut frames = Vec::new();
            for (index, position) in positions.iter().enumerate() {
                let timestamp = seconds_to_timestamp(*position);
                let out = dir.join(format!("frame_{index}.jpg"));
                if extract_frame(video_path, &out, &timestamp).await {
                    frames.push(out);
                }
            }
            if !frames.is_empty() {
                return frames;
            }
        }
    }

    match duration_ms {
        Some(duration_ms) if duration_ms >= 1000 => {
            let duration_s = duration_ms as f64 / 1000.0;
            let mut frames = Vec::new();
            for index in 0..count {
                let position = duration_s * index as f64 / count as f64;
                let timestamp = seconds_to_timestamp(position);
                let out = dir.join(format!("frame_{index}.jpg"));
                if extract_frame(video_path, &out, &timestamp).await {
                    frames.push(out);
                }
            }
            frames
        }
        _ => {
            let out = dir.join("frame_0.jpg");
            if extract_frame(video_path, &out, "00:00:00.000").await {
                vec![out]
            } else {
                Vec::new()
            }
        }
    }
}

pub(crate) fn merge_tag_results(mut results: Vec<TagResult>) -> TagResult {
    if results.is_empty() {
        return TagResult {
            tags: Vec::new(),
            rating: String::new(),
            path: String::new(),
            model_id: String::new(),
        };
    }
    if results.len() == 1 {
        return results.remove(0);
    }

    let model_id = results[0].model_id.clone();
    let path = results[0].path.clone();
    let mut tag_map: HashMap<(String, String), f32> = HashMap::new();
    for result in &results {
        for tag in &result.tags {
            let confidence = tag_map
                .entry((tag.tag.clone(), tag.category.clone()))
                .or_insert(tag.confidence);
            if tag.confidence > *confidence {
                *confidence = tag.confidence;
            }
        }
    }

    let mut tags = tag_map
        .into_iter()
        .map(|((tag, category), confidence)| TagPrediction {
            tag,
            confidence,
            category,
        })
        .collect::<Vec<_>>();
    tags.sort_by(|left, right| {
        right
            .confidence
            .partial_cmp(&left.confidence)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let mut best_rating = results[0].rating.clone();
    let mut best_rating_confidence = -1.0_f32;
    for result in &results {
        let max_rating_confidence = result
            .tags
            .iter()
            .filter(|tag| tag.category == "rating")
            .map(|tag| tag.confidence)
            .fold(None, |max, confidence| {
                Some(max.map_or(confidence, |max: f32| max.max(confidence)))
            });
        if let Some(max_rating_confidence) = max_rating_confidence {
            if max_rating_confidence > best_rating_confidence {
                best_rating_confidence = max_rating_confidence;
                best_rating = result.rating.clone();
            }
        }
    }

    TagResult {
        tags,
        rating: best_rating,
        path,
        model_id,
    }
}

#[cfg(test)]
mod tests {
    use super::{
        is_native_video_format, merge_tag_results, parse_scene_timestamps, seconds_to_timestamp,
    };
    use infer_core::engine::{TagPrediction, TagResult};

    fn prediction(tag: &str, confidence: f32, category: &str) -> TagPrediction {
        TagPrediction {
            tag: tag.to_string(),
            confidence,
            category: category.to_string(),
        }
    }

    fn result(tags: Vec<TagPrediction>, rating: &str, path: &str, model_id: &str) -> TagResult {
        TagResult {
            tags,
            rating: rating.to_string(),
            path: path.to_string(),
            model_id: model_id.to_string(),
        }
    }

    fn confidence_for(tags: &[TagPrediction], tag: &str, category: &str) -> Option<f32> {
        tags.iter()
            .find(|prediction| prediction.tag == tag && prediction.category == category)
            .map(|prediction| prediction.confidence)
    }

    #[test]
    fn scene_parsing_reads_every_pts_time_in_ffmpeg_showinfo_output() {
        let stderr = "\
[Parsed_showinfo_1 @ 0x1] n:0 pts:0 pts_time:0 duration:1\n\
[Parsed_showinfo_1 @ 0x1] n:1 pts:900 pts_time:1.25 duration:1\n\
[Parsed_showinfo_1 @ 0x1] n:2 pts:1800 pts_time:12.5 duration:1\n";
        assert_eq!(parse_scene_timestamps(stderr, 8), vec![0.0, 1.25, 12.5]);
    }

    #[test]
    fn scene_parsing_thins_to_max_scenes_by_even_sampling() {
        // Mirrors Python's `step = len(timestamps) / max_scenes` indexing, which
        // keeps the first element and strides from there -- not a head-take.
        let stderr: String = (0..10)
            .map(|index| format!("pts_time:{index}.0 \n"))
            .collect();
        let thinned = parse_scene_timestamps(&stderr, 4);
        assert_eq!(thinned, vec![0.0, 2.0, 5.0, 7.0]);
    }

    #[test]
    fn scene_parsing_returns_empty_when_ffmpeg_found_no_scenes() {
        assert!(parse_scene_timestamps("no matches here", 8).is_empty());
        assert!(parse_scene_timestamps("", 8).is_empty());
    }

    #[test]
    fn scene_parsing_keeps_everything_when_under_the_cap() {
        let stderr = "pts_time:1.5 pts_time:2.5 ";
        assert_eq!(parse_scene_timestamps(stderr, 8), vec![1.5, 2.5]);
    }

    #[test]
    fn formats_timestamps_like_python() {
        assert_eq!(seconds_to_timestamp(0.0), "00:00:00.000");
        assert_eq!(seconds_to_timestamp(5.25), "00:00:05.250");
        assert_eq!(seconds_to_timestamp(65.5), "00:01:05.500");
        assert_eq!(seconds_to_timestamp(3661.25), "01:01:01.250");
    }

    #[test]
    fn recognizes_native_video_extensions() {
        for path in [
            "video.mp4",
            "video.MP4",
            "video.webm",
            "video.avi",
            "video.mov",
            "video.mkv",
            "video.m4v",
            "video.ogv",
        ] {
            assert!(is_native_video_format(path), "{path}");
        }

        for path in ["image.png", "notes.txt", "no-extension", ""] {
            assert!(!is_native_video_format(path), "{path}");
        }
    }

    #[test]
    fn merging_empty_results_returns_default_result() {
        let merged = merge_tag_results(Vec::new());

        assert!(merged.tags.is_empty());
        assert!(merged.rating.is_empty());
        assert!(merged.path.is_empty());
        assert!(merged.model_id.is_empty());
    }

    #[test]
    fn merging_one_result_returns_it_unchanged() {
        let merged = merge_tag_results(vec![result(
            vec![prediction("cat", 0.9, "general")],
            "general",
            "frame.jpg",
            "model-a",
        )]);

        assert_eq!(merged.tags.len(), 1);
        assert_eq!(confidence_for(&merged.tags, "cat", "general"), Some(0.9));
        assert_eq!(merged.rating, "general");
        assert_eq!(merged.path, "frame.jpg");
        assert_eq!(merged.model_id, "model-a");
    }

    #[test]
    fn merging_keeps_higher_later_confidence() {
        let merged = merge_tag_results(vec![
            result(
                vec![prediction("cat", 0.5, "general")],
                "general",
                "a.jpg",
                "model-a",
            ),
            result(
                vec![prediction("cat", 0.9, "general")],
                "general",
                "b.jpg",
                "model-b",
            ),
        ]);

        assert_eq!(merged.tags.len(), 1);
        assert_eq!(confidence_for(&merged.tags, "cat", "general"), Some(0.9));
        assert_eq!(merged.path, "a.jpg");
        assert_eq!(merged.model_id, "model-a");
    }

    #[test]
    fn merging_does_not_overwrite_with_lower_confidence() {
        let merged = merge_tag_results(vec![
            result(
                vec![prediction("cat", 0.9, "general")],
                "general",
                "a.jpg",
                "model-a",
            ),
            result(
                vec![prediction("cat", 0.5, "general")],
                "general",
                "b.jpg",
                "model-b",
            ),
        ]);

        assert_eq!(confidence_for(&merged.tags, "cat", "general"), Some(0.9));
    }

    #[test]
    fn merging_distinguishes_categories() {
        let merged = merge_tag_results(vec![
            result(
                vec![prediction("cat", 0.9, "general")],
                "general",
                "a.jpg",
                "model-a",
            ),
            result(
                vec![prediction("cat", 0.8, "character")],
                "general",
                "b.jpg",
                "model-a",
            ),
        ]);

        assert_eq!(merged.tags.len(), 2);
        assert_eq!(confidence_for(&merged.tags, "cat", "general"), Some(0.9));
        assert_eq!(confidence_for(&merged.tags, "cat", "character"), Some(0.8));
    }

    #[test]
    fn merging_uses_rating_from_the_first_frame_with_rating_predictions() {
        let merged = merge_tag_results(vec![
            result(
                vec![prediction("cat", 0.9, "general")],
                "general",
                "a.jpg",
                "model-a",
            ),
            result(
                vec![prediction("safe", 0.6, "rating")],
                "safe",
                "b.jpg",
                "model-a",
            ),
        ]);

        assert_eq!(merged.rating, "safe");
    }

    #[test]
    fn merging_uses_rating_from_highest_confidence_rating_prediction() {
        let merged = merge_tag_results(vec![
            result(
                vec![prediction("safe", 0.9, "rating")],
                "safe",
                "a.jpg",
                "model-a",
            ),
            result(
                vec![prediction("questionable", 0.8, "rating")],
                "questionable",
                "b.jpg",
                "model-a",
            ),
        ]);

        assert_eq!(merged.rating, "safe");
    }
}
