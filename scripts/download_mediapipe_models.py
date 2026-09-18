"""Download the three server-side MediaPipe task models used by the MVP."""
import ssl
from pathlib import Path
from urllib.request import urlopen

try:
    import certifi
    # Keep the platform trust store (including managed-network CAs) and add
    # certifi roots instead of replacing the former with the latter.
    SSL_CONTEXT = ssl.create_default_context()
    SSL_CONTEXT.load_verify_locations(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "models"
MODELS = {
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
    "gesture_recognizer.task": "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/latest/gesture_recognizer.task",
    "pose_landmarker.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
}

OUT.mkdir(exist_ok=True)
for name, url in MODELS.items():
    target = OUT / name
    if not target.exists():
        print(f"downloading {name}")
        partial = target.with_suffix(target.suffix + ".part")
        try:
            with urlopen(url, context=SSL_CONTEXT) as response, partial.open("wb") as output:
                output.write(response.read())
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
    else:
        print(f"exists {name}")
