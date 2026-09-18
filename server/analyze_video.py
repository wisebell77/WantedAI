"""Server-side MediaPipe interview video analysis.

Reads one video file and prints JSON. Models are supplied through environment
variables so the web client never downloads or executes MediaPipe.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load_mediapipe():
    # Keep server inference headless/CPU-only (important on macOS without an
    # NSOpenGL context and on EC2 containers).
    os.environ.setdefault("MEDIAPIPE_DISABLE_GPU", "1")
    try:
        import av
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
    except ImportError as exc:
        raise RuntimeError("MEDIAPIPE_NOT_INSTALLED: install -r requirements-server.txt") from exc
    return av, mp, np, python, vision


def analyze(path: str) -> dict:
    av, mp, np, python, vision = _load_mediapipe()
    model_dir = Path(os.getenv("MEDIAPIPE_MODEL_DIR", Path(__file__).resolve().parent.parent / "models"))
    face_path = os.getenv("MEDIAPIPE_FACE_MODEL", str(model_dir / "face_landmarker.task"))
    gesture_path = os.getenv("MEDIAPIPE_GESTURE_MODEL", str(model_dir / "gesture_recognizer.task"))
    pose_path = os.getenv("MEDIAPIPE_POSE_MODEL", str(model_dir / "pose_landmarker.task"))
    missing = [p for p in (face_path, gesture_path, pose_path) if not Path(p).exists()]
    if missing:
        raise RuntimeError("MEDIAPIPE_MODELS_MISSING: " + ",".join(missing))

    face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=face_path, delegate=python.BaseOptions.Delegate.CPU),
        running_mode=vision.RunningMode.VIDEO, num_faces=1,
        output_face_blendshapes=True))
    gesture = vision.GestureRecognizer.create_from_options(vision.GestureRecognizerOptions(
        base_options=python.BaseOptions(model_asset_path=gesture_path, delegate=python.BaseOptions.Delegate.CPU),
        running_mode=vision.RunningMode.VIDEO, num_hands=2))
    pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=pose_path, delegate=python.BaseOptions.Delegate.CPU),
        running_mode=vision.RunningMode.VIDEO, num_poses=1))

    try:
        container = av.open(path)
        stream = container.streams.video[0]
    except Exception as exc:
        raise RuntimeError("VIDEO_DECODE_FAILED") from exc
    fps = float(stream.average_rate or 0) or 30.0
    stride = max(1, round(fps / float(os.getenv("MEDIAPIPE_FPS", "10"))))
    frames = faces = hands = poses = blinks = body_moves = 0
    frown_frames = shoulder_tilt_frames = shoulders_off_center_frames = arm_moves = 0
    gesture_counts = {}
    samples = []
    prev_shoulder = None
    prev_wrist = None
    last_blink = False
    first_ts = last_ts = None
    for index, frame in enumerate(container.decode(stream)):
        if index % stride:
            continue
        timestamp = int((float(frame.pts * frame.time_base) if frame.pts is not None else index / fps) * 1000)
        first_ts = timestamp if first_ts is None else first_ts
        last_ts = timestamp
        pixels = np.ascontiguousarray(frame.to_ndarray(format="rgb24"), dtype=np.uint8)
        image = mp.Image(mp.ImageFormat.SRGB, pixels)
        face_result = face.detect_for_video(image, timestamp)
        gesture_result = gesture.recognize_for_video(image, timestamp)
        pose_result = pose.detect_for_video(image, timestamp)
        frames += 1
        if face_result.face_landmarks:
            faces += 1
            blend = {c.category_name: c.score for c in (face_result.face_blendshapes[0] if face_result.face_blendshapes else [])}
            blink = (blend.get("eyeBlinkLeft", 0) + blend.get("eyeBlinkRight", 0)) / 2 > 0.45
            if blink and not last_blink:
                blinks += 1
            last_blink = blink
            if (blend.get("mouthFrownLeft", 0) + blend.get("mouthFrownRight", 0)) / 2 > 0.45:
                frown_frames += 1
        if gesture_result.hand_landmarks:
            hands += 1
        for labels in gesture_result.gestures or []:
            if labels:
                name = labels[0].category_name
                if name and name != "None":
                    gesture_counts[name] = gesture_counts.get(name, 0) + 1
        shoulder_tilt = False
        shoulders_off_center = False
        if pose_result.pose_landmarks:
            poses += 1
            points = pose_result.pose_landmarks[0]
            # MediaPipe pose indices 11/12 are shoulders; movement is normalized
            # by image coordinates and intentionally remains an observable cue.
            shoulder = ((points[11].x + points[12].x) / 2, (points[11].y + points[12].y) / 2)
            if prev_shoulder and ((shoulder[0] - prev_shoulder[0]) ** 2 + (shoulder[1] - prev_shoulder[1]) ** 2) ** 0.5 > 0.035:
                body_moves += 1
            prev_shoulder = shoulder
            shoulder_tilt = abs(points[11].y - points[12].y) > 0.055
            shoulders_off_center = abs(shoulder[0] - 0.5) > 0.22
            shoulder_tilt_frames += int(shoulder_tilt)
            shoulders_off_center_frames += int(shoulders_off_center)
            wrists = ((points[15].x + points[16].x) / 2, (points[15].y + points[16].y) / 2)
            if prev_wrist and ((wrists[0] - prev_wrist[0]) ** 2 + (wrists[1] - prev_wrist[1]) ** 2) ** 0.5 > 0.05:
                arm_moves += 1
            prev_wrist = wrists
        if len(samples) < 1800:
            def compact(landmarks):
                return [[round(point.x, 4), round(point.y, 4), round(getattr(point, "z", 0), 4)] for point in landmarks]
            samples.append({
                "time": round((timestamp - first_ts) / 1000, 2),
                "face": compact(face_result.face_landmarks[0]) if face_result.face_landmarks else [],
                "hands": [compact(hand) for hand in (gesture_result.hand_landmarks or [])],
                "pose": compact(pose_result.pose_landmarks[0]) if pose_result.pose_landmarks else [],
                "shoulderTilt": shoulder_tilt,
                "shouldersOffCenter": shoulders_off_center,
            })
    duration = max(0.0, ((last_ts or 0) - (first_ts or 0)) / 1000)
    face_rate = faces / frames if frames else 0
    result = {
        "model": "mediapipe-tasks-python",
        "sampleFps": round(frames / duration, 2) if duration else 0,
        "durationSeconds": round(duration, 2),
        "framesAnalyzed": frames,
        "faceCoverage": round(face_rate, 3),
        "handFrames": hands,
        "poseCoverage": round(poses / frames, 3) if frames else 0,
        "blinkCount": blinks,
        "upperBodyMovementEvents": body_moves,
        "armMovementEvents": arm_moves,
        "mouthFrownPercent": round(frown_frames / faces * 100, 1) if faces else 0,
        "shoulderTiltPercent": round(shoulder_tilt_frames / poses * 100, 1) if poses else 0,
        "shouldersOffCenterPercent": round(shoulders_off_center_frames / poses * 100, 1) if poses else 0,
        "gestures": gesture_counts,
        "samples": samples,
        "connections": {
            "face": [list(edge) for edge in mp.solutions.face_mesh.FACEMESH_TESSELATION],
            "pose": [list(edge) for edge in mp.solutions.pose.POSE_CONNECTIONS],
        },
        "note": "관찰 가능한 신호이며 채용 적합성·감정·성격을 판정하지 않습니다.",
    }
    face.close(); gesture.close(); pose.close(); container.close()
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(analyze(sys.argv[1]), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(2)
