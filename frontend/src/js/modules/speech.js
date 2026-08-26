const PRERECORDED_SPEECH = new Map([
  ["greeting", "/src/assets/audio/greeting.wav"],
  ["uploading", "/src/assets/audio/uploading.wav"],
  ["analysis", "/src/assets/audio/analysis.wav"],
  ["completed", "/src/assets/audio/completed.wav"],
]);


export class PrerecordedSpeechService {
  constructor() {
    this.audio = null;
    this.ready = false;
  }

  isAvailable() {
    return typeof Audio !== "undefined";
  }

  enable() {
    this.ready = true;
  }

  loadVoices() {}

  hasCue(cue) {
    return PRERECORDED_SPEECH.has(cue);
  }

  async speak(_text, { cue, onStart, onEnd, onUnavailable } = {}) {
    const prerecordedUrl = PRERECORDED_SPEECH.get(cue);
    if (!this.ready || !prerecordedUrl) return;
    this.stop();
    try {
      this.audio = new Audio(prerecordedUrl);
      this.audio.onplay = () => onStart?.();
      this.audio.onended = () => onEnd?.();
      this.audio.onerror = () => onUnavailable?.();
      await this.audio.play();
    } catch {
      onUnavailable?.();
    }
  }

  stop() {
    if (this.audio) {
      this.audio.pause();
      this.audio.currentTime = 0;
    }
  }
}


export class BrowserSttService {
  constructor({ onStart, onResult, onFinal, onError, onEnd } = {}) {
    this.recognition = null;
    this.listening = false;
    this.handlers = { onStart, onResult, onFinal, onError, onEnd };
  }

  getConstructor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  isAvailable() {
    return Boolean(this.getConstructor());
  }

  ensureRecognition() {
    if (this.recognition || !this.isAvailable()) return this.recognition;

    const Recognition = this.getConstructor();
    const recognition = new Recognition();
    recognition.lang = "ru-RU";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.addEventListener("start", () => {
      this.listening = true;
      this.handlers.onStart?.();
    });
    recognition.addEventListener("result", (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript || "")
        .join(" ")
        .trim();
      this.handlers.onResult?.(transcript);
      const lastResult = event.results[event.results.length - 1];
      if (lastResult?.isFinal && transcript) {
        recognition.stop();
        this.handlers.onFinal?.(transcript);
      }
    });
    recognition.addEventListener("error", (event) => {
      this.handlers.onError?.(event.error);
    });
    recognition.addEventListener("end", () => {
      this.listening = false;
      this.handlers.onEnd?.();
    });

    this.recognition = recognition;
    return recognition;
  }

  start() {
    const recognition = this.ensureRecognition();
    if (!recognition) return false;
    if (this.listening) {
      recognition.stop();
      return true;
    }
    recognition.start();
    return true;
  }

  stop() {
    this.recognition?.stop();
  }
}
