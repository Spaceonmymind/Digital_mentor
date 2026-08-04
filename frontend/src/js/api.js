import { API_BASE_URL } from "./config.js";


async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const message = body?.error?.message || body?.message || "Ошибка запроса к серверу";
    const error = new Error(message);
    error.status = response.status;
    error.body = body;
    throw error;
  }

  return body;
}


export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append("upload", file);
  const response = await fetch(`${API_BASE_URL}/documents`, {
    method: "POST",
    body: formData,
  });
  return parseResponse(response);
}


export async function getPublicConfig() {
  const response = await fetch(`${API_BASE_URL}/config`);
  return parseResponse(response);
}


export async function getDocument(documentId) {
  const response = await fetch(`${API_BASE_URL}/documents/${documentId}`);
  return parseResponse(response);
}


export async function createAnalysis(payload) {
  const response = await fetch(`${API_BASE_URL}/analyses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}


export async function getAnalysis(analysisId) {
  const response = await fetch(`${API_BASE_URL}/analyses/${analysisId}`);
  return parseResponse(response);
}


export async function getAnalysisResult(analysisId) {
  const response = await fetch(`${API_BASE_URL}/analyses/${analysisId}/result`);
  return parseResponse(response);
}


export async function cancelAnalysis(analysisId) {
  const response = await fetch(`${API_BASE_URL}/analyses/${analysisId}/cancel`, {
    method: "POST",
  });
  return parseResponse(response);
}


export async function sendChatMessage(payload) {
  const response = await fetch(`${API_BASE_URL}/chat/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}


export async function synthesizeSpeech(payload) {
  const response = await fetch(`${API_BASE_URL}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}


export async function createReport(analysisId) {
  const response = await fetch(`${API_BASE_URL}/analyses/${analysisId}/reports`, {
    method: "POST",
  });
  return parseResponse(response);
}


export async function deleteDocument(documentId, { force = false } = {}) {
  const response = await fetch(`${API_BASE_URL}/documents/${documentId}?force=${force ? "true" : "false"}`, {
    method: "DELETE",
  });
  return parseResponse(response);
}
