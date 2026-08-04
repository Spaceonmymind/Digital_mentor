import { synthesizeSpeech } from "../api.js";


export class RemoteTtsSpeechService {
  constructor({ fallback, onFallback } = {}) {
    this.fallback = fallback;
    this.onFallback = onFallback;
    this.audio = null;
    this.failed = false;
    this.ready = false;
  }

  isAvailable() {
    return !this.failed || Boolean(this.fallback?.isAvailable());
  }

  enable() {
    this.ready = true;
    this.fallback?.enable();
  }

  loadVoices() {
    this.fallback?.loadVoices();
  }

  async speak(text, { force = false, onStart, onEnd } = {}) {
    if (!this.ready || this.failed) {
      return this.fallback?.speak(text, { force, onStart, onEnd });
    }
    this.stop();
    try {
      const result = await synthesizeSpeech({ text, voice_id: "mentor-default" });
      this.audio = new Audio(result.audio_url);
      this.audio.onplay = () => onStart?.();
      this.audio.onended = () => onEnd?.();
      this.audio.onerror = () => {
        this.failed = true;
        this.onFallback?.();
        this.fallback?.speak(text, { force: true, onStart, onEnd });
      };
      await this.audio.play();
    } catch (error) {
      this.failed = true;
      this.onFallback?.();
      return this.fallback?.speak(text, { force: true, onStart, onEnd });
    }
  }

  stop() {
    if (this.audio) {
      this.audio.pause();
      this.audio.currentTime = 0;
    }
    this.fallback?.stop();
  }
}


export class DisabledSpeechService {
  isAvailable() {
    return false;
  }

  enable() {}

  loadVoices() {}

  async speak() {}

  stop() {}
}


export class BrowserSpeechService {
  constructor() {
    this.ready = false;
    this.voices = [];
    this.selectedVoice = null;
    this.lastSpokenMessage = "";
  }

  isAvailable() {
    return "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  }

  enable() {
    this.ready = true;
    this.loadVoices();
  }

  loadVoices() {
    if (!this.isAvailable()) return;
    this.voices = window.speechSynthesis.getVoices();
    this.selectedVoice =
      this.voices.find((voice) => voice.lang.toLowerCase().startsWith("ru")) ||
      this.voices.find((voice) => /russian|рус/i.test(voice.name)) ||
      this.voices[0] ||
      null;
  }

  normalize(text) {
    return text
      .replace(/\s+/g, " ")
      .replace(/AI/gi, "эй ай")
      .replace(/ИИ/g, "искусственного интеллекта")
      .replace(/PDF/g, "пи ди эф")
      .replace(/DOCX/g, "док икс")
      .trim()
      .slice(0, 700);
  }

  async speak(text, { force = false, onStart, onEnd } = {}) {
    if (!this.ready || !this.isAvailable()) return;
    const normalized = this.normalize(text);
    if (!normalized || (!force && normalized === this.lastSpokenMessage)) return;

    this.lastSpokenMessage = normalized;
    this.stop();

    const utterance = new SpeechSynthesisUtterance(normalized);
    utterance.lang = "ru-RU";
    utterance.rate = 1.12;
    utterance.pitch = 1.08;
    utterance.volume = 0.95;
    utterance.onstart = () => onStart?.();
    utterance.onend = () => onEnd?.();
    utterance.onerror = () => onEnd?.();

    if (this.selectedVoice) {
      utterance.voice = this.selectedVoice;
    }

    window.speechSynthesis.speak(utterance);
    if (!this.voices.length) {
      window.setTimeout(() => {
        this.loadVoices();
        if (!window.speechSynthesis.speaking && this.ready) {
          window.speechSynthesis.speak(utterance);
        }
      }, 250);
    }
  }

  stop() {
    if (this.isAvailable()) {
      window.speechSynthesis.cancel();
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
