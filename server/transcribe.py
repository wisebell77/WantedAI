import json
import sys

from faster_whisper import WhisperModel


def main():
    # ponytail: loads the model per recording; use a persistent worker if latency becomes a measured problem.
    prompt = sys.argv[2] if len(sys.argv) > 2 else None
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    segments, info = model.transcribe(sys.argv[1], language="ko", beam_size=5, vad_filter=True, initial_prompt=prompt or None)
    items = [{"start": round(segment.start, 2), "end": round(segment.end, 2), "text": segment.text.strip()} for segment in segments]
    print(json.dumps({"text": " ".join(item["text"] for item in items).strip(), "segments": items, "model": "faster-whisper-medium", "beamSize": 5, "language": info.language}, ensure_ascii=False))


if __name__ == "__main__":
    main()
