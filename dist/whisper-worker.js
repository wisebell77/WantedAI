let transcriber;

async function getTranscriber() {
  if (transcriber) return transcriber;

  const { pipeline, env } = await import("https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1");
  env.allowLocalModels = false;
  transcriber = await pipeline(
    "automatic-speech-recognition",
    "Xenova/whisper-tiny",
    {
      progress_callback: (progress) => self.postMessage({ type: "progress", progress })
    }
  );
  return transcriber;
}

self.onmessage = async (event) => {
  try {
    if (event.data.type === "load") {
      await getTranscriber();
      self.postMessage({ type: "ready" });
      return;
    }

    if (event.data.type === "transcribe") {
      const whisper = await getTranscriber();
      self.postMessage({ type: "transcribing" });
      const result = await whisper(new Float32Array(event.data.audio), {
        language: "korean",
        task: "transcribe",
        chunk_length_s: 30,
        stride_length_s: 5
      });
      self.postMessage({ type: "complete", text: result.text || "" });
    }
  } catch (error) {
    self.postMessage({ type: "error", message: error instanceof Error ? error.message : "Whisper 전사에 실패했습니다." });
  }
};
