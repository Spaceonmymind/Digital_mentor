import { mascotAssets } from "../config.js";


export class MascotController {
  constructor({ image, card, status, message, wave }) {
    this.image = image;
    this.card = card;
    this.status = status;
    this.message = message;
    this.wave = wave;
    this.currentState = "idle";
  }

  setMascotState({ state = "idle", label, message }) {
    this.currentState = state;
    this.card.dataset.status = state;
    this.status.textContent = label || this.status.textContent;
    if (message) {
      this.message.textContent = message;
    }
    this.wave.hidden = state !== "speaking";
    this.setImageForState(state);
  }

  setImageForState(state) {
    const candidates = [
      mascotAssets[state],
      mascotAssets.fallbackGif,
      mascotAssets.fallbackPng,
      mascotAssets.currentPng,
    ].filter(Boolean);
    this.tryImage(candidates, 0);
  }

  tryImage(candidates, index) {
    if (index >= candidates.length) return;
    const candidate = candidates[index];
    if (this.image.getAttribute("src") === candidate) return;
    const probe = new Image();
    probe.onload = () => {
      this.image.src = candidate;
    };
    probe.onerror = () => this.tryImage(candidates, index + 1);
    probe.src = candidate;
  }
}
