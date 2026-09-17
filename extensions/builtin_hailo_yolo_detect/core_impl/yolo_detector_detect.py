import contextlib
import os


def detect_archive_video(detector, full_path: str, conf_threshold: float, frame_interval: float) -> list:
    import tempfile

    from .yolo_preprocess import _read_image_bytes

    ext = os.path.splitext(full_path)[1].lower()
    video_bytes = _read_image_bytes(full_path)
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name
    try:
        return detect_video(detector, tmp_path, conf_threshold, frame_interval)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


def detect_image(detector, path: str, conf_threshold: float) -> list:
    from .yolo_preprocess import preprocess_image_yolo

    image, scale_info = preprocess_image_yolo(path, detector.input_size)
    return detector.detect(image, scale_info, conf_threshold)


def detect_video(detector, path: str, conf_threshold: float, frame_interval: float) -> list:
    import cv2

    from .yolo_preprocess import preprocess_frame_yolo
    from .yolo_video import aggregate_video_detections, video_detection_frames

    with video_detection_frames(path, interval_sec=frame_interval, target_size=detector.input_size) as frame_paths:
        if not frame_paths:
            return []
        per_frame = []
        for frame_path in frame_paths:
            frame_bgr = cv2.imread(frame_path)
            if frame_bgr is None:
                continue
            image, scale_info = preprocess_frame_yolo(frame_bgr, detector.input_size)
            per_frame.append(detector.detect(image, scale_info, conf_threshold))
        return aggregate_video_detections(per_frame)
