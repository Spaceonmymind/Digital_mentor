export const API_BASE_URL = window.__DIGITAL_MENTOR_CONFIG__?.apiBaseUrl || "/api/v1";

export const FRONTEND_MOCK_MODE =
  window.__DIGITAL_MENTOR_CONFIG__?.mockMode === true ||
  new URLSearchParams(window.location.search).get("mock") === "1" ||
  window.localStorage.getItem("FRONTEND_MOCK_MODE") === "true";

export const mascotAssets = {
  idle: "/src/assets/mascot/mascot-idle.gif",
  uploading: "/src/assets/mascot/mascot-thinking.gif",
  thinking: "/src/assets/mascot/mascot-thinking.gif",
  speaking: "/src/assets/mascot/mascot-speaking.gif",
  success: "/src/assets/mascot/mascot-success.gif",
  error: "/src/assets/mascot/mascot-error.gif",
  fallbackGif: "/src/assets/mascot/mascot-default.gif",
  fallbackPng: "/src/assets/mascot/mascot-default.png",
  currentPng: "/src/assets/mascot/finik-kosmonavt.png",
};
