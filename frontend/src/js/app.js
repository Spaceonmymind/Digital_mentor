import {
  analysisSteps,
  documentParagraphs,
  documentRemarks,
  improvementDirections,
  mockMentorAnalysis,
  recommendationPlan,
} from "../mocks/mentorAnalysis.js";
import { getMentorAnswer, quickQuestions } from "../mocks/mentorChat.js";
import { renderIcons } from "./icons.js";
import { uploadDocument } from "./modules/upload.js";
import { runAnalysis } from "./modules/analysis.js";
import { askMentorApi } from "./modules/chat.js";
import { BrowserSpeechService, BrowserSttService } from "./modules/speech.js";
import { MascotController } from "./modules/mascot.js";

const state = {
  file: null,
  document: null,
  analysisId: null,
  sound: false,
  speechReady: false,
  isListening: false,
  activeRemark: 0,
  remarks: documentRemarks,
  sidebarCollapsed: true,
};

const elements = {
  appShell: document.getElementById("appShell"),
  sidebarToggle: document.getElementById("sidebarToggle"),
  navItems: document.querySelectorAll(".nav-item"),
  pages: {
    mentor: document.getElementById("mentorPage"),
    about: document.getElementById("aboutPage"),
  },
  avatarCard: document.querySelector(".avatar-card"),
  mascotImage: document.querySelector(".mascot-image"),
  voiceWave: document.querySelector(".voice-wave"),
  mentorStatus: document.getElementById("mentorStatus"),
  mentorMessage: document.getElementById("mentorMessage"),
  uploadStage: document.getElementById("uploadStage"),
  processingStage: document.getElementById("processingStage"),
  resultsStage: document.getElementById("resultsStage"),
  dropZone: document.getElementById("dropZone"),
  fileInput: document.getElementById("fileInput"),
  chooseFileButton: document.getElementById("chooseFileButton"),
  filePreview: document.getElementById("filePreview"),
  fileName: document.getElementById("fileName"),
  fileMeta: document.getElementById("fileMeta"),
  removeFileButton: document.getElementById("removeFileButton"),
  startAnalysisButton: document.getElementById("startAnalysisButton"),
  analysisSteps: document.getElementById("analysisSteps"),
  criteriaList: document.getElementById("criteriaList"),
  strengthsList: document.getElementById("strengthsList"),
  improvementsList: document.getElementById("improvementsList"),
  documentText: document.getElementById("documentText"),
  remarkContent: document.getElementById("remarkContent"),
  remarkTabs: document.getElementById("remarkTabs"),
  aiRiskList: document.getElementById("aiRiskList"),
  recommendationPlan: document.getElementById("recommendationPlan"),
  directionButtons: document.getElementById("directionButtons"),
  directionResult: document.getElementById("directionResult"),
  quickQuestions: document.getElementById("quickQuestions"),
  chatMessages: document.getElementById("chatMessages"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  micButton: document.getElementById("micButton"),
  soundToggle: document.getElementById("soundToggle"),
  avatarSoundButton: document.getElementById("avatarSoundButton"),
  resetButton: document.getElementById("resetButton"),
  notification: document.getElementById("notification"),
};

const speechService = new BrowserSpeechService();
const sttService = new BrowserSttService({
  onStart: () => {
    state.isListening = true;
    updateMicButton();
    elements.chatInput.placeholder = "Слушаю вопрос...";
    showNotification("Говорите, я слушаю.");
  },
  onResult: (transcript) => {
    if (transcript) {
      elements.chatInput.value = transcript;
    }
  },
  onFinal: (transcript) => {
    elements.chatInput.value = "";
    enableSpeech();
    askMentor(transcript);
  },
  onError: (errorCode) => {
    const messages = {
      "not-allowed": "Браузер не получил доступ к микрофону.",
      "no-speech": "Речь не распознана. Попробуйте еще раз.",
      "audio-capture": "Микрофон не найден или недоступен.",
      network: "Сервис распознавания речи недоступен.",
    };
    showNotification(messages[errorCode] || "Не удалось распознать голос.");
  },
  onEnd: () => {
    state.isListening = false;
    updateMicButton();
    elements.chatInput.placeholder = "Задайте вопрос ментору";
  },
});

const mascot = new MascotController({
  image: elements.mascotImage,
  card: elements.avatarCard,
  status: elements.mentorStatus,
  message: elements.mentorMessage,
  wave: elements.voiceWave,
});

function setMentor(status, message) {
  const statusLabels = {
    idle: "Ожидает документ",
    speaking: "Формирует ответ",
    thinking: "Анализирует работу",
    success: "Анализ завершен",
    error: "Требуется действие",
  };
  mascot.setMascotState({ state: status, label: statusLabels[status] || statusLabels.idle, message });
  speakMentor(message);
}

function isSpeechSupported() {
  return speechService.isAvailable();
}

function loadVoices() {
  speechService.loadVoices();
}

function enableSpeech() {
  state.speechReady = true;
  speechService.enable();
}

function speakMentor(message, force = false) {
  if (!state.sound || !state.speechReady || !isSpeechSupported()) return;
  speechService.speak(message, {
    force,
    onStart: () => mascot.setMascotState({ state: "speaking", message }),
    onEnd: () => mascot.setMascotState({ state: state.analysisId ? "success" : "idle", message }),
  });
}

function stopSpeech() {
  speechService.stop();
  mascot.setMascotState({ state: state.analysisId ? "success" : "idle" });
}

function updateSoundButton() {
  elements.avatarSoundButton.innerHTML = `<span data-icon="volume2"></span>${state.sound ? "Озвучивание включено" : "Озвучивание выключено"}`;
  elements.soundToggle.classList.toggle("is-active", state.sound);
  renderIcons();
}

function getSpeechRecognitionConstructor() {
  return sttService.getConstructor();
}

function isVoiceInputSupported() {
  return sttService.isAvailable();
}

function updateMicButton() {
  elements.micButton.classList.toggle("is-active", state.isListening);
  elements.micButton.setAttribute("aria-label", state.isListening ? "Остановить голосовой ввод" : "Голосовой ввод");
  elements.micButton.title = state.isListening ? "Остановить голосовой ввод" : "Голосовой ввод";
}

function startVoiceInput() {
  if (!isVoiceInputSupported()) {
    showNotification("Голосовой ввод не поддерживается этим браузером. Лучше открыть в Chrome или Edge.");
    return;
  }

  stopSpeech();
  try {
    sttService.start();
  } catch (error) {
    showNotification("Голосовой ввод уже запускается.");
  }
}

function showStage(stageName) {
  [elements.uploadStage, elements.processingStage, elements.resultsStage].forEach((stage) => {
    stage.classList.remove("is-visible");
  });
  elements[`${stageName}Stage`].classList.add("is-visible");
}

function showPage(section) {
  Object.values(elements.pages).forEach((page) => page.classList.remove("is-visible"));
  elements.pages[section].classList.add("is-visible");

  elements.navItems.forEach((item) => {
    item.classList.toggle("is-active", item.dataset.section === section);
  });
}

function showNotification(text) {
  elements.notification.textContent = text;
  elements.notification.classList.add("is-visible");
  window.setTimeout(() => elements.notification.classList.remove("is-visible"), 2600);
}

function setSidebarCollapsed(collapsed) {
  state.sidebarCollapsed = collapsed;
  elements.appShell.classList.toggle("is-sidebar-collapsed", collapsed);
  elements.sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
  elements.sidebarToggle.setAttribute("aria-label", collapsed ? "Раскрыть меню" : "Свернуть меню");
  elements.sidebarToggle.title = collapsed ? "Раскрыть меню" : "Свернуть меню";
}

function formatFileSize(size) {
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} КБ`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} МБ`;
}

function getFileExtension(fileName) {
  const extension = fileName.split(".").pop() || "";
  return extension.toUpperCase();
}

async function setFile(file) {
  if (!file) return;

  const extension = getFileExtension(file.name);
  if (!["PDF", "DOCX"].includes(extension)) {
    showNotification("Для демонстрации выберите файл PDF или DOCX.");
    return;
  }

  state.file = file;
  elements.fileName.textContent = file.name;
  elements.fileMeta.textContent = `${extension} · ${formatFileSize(file.size)}`;
  elements.filePreview.hidden = false;
  elements.startAnalysisButton.disabled = true;
  setMentor("uploading", "Загружаю документ на сервер.");

  try {
    const documentMetadata = await uploadDocument(file);
    state.document = documentMetadata;
    elements.fileName.textContent = documentMetadata.name;
    elements.fileMeta.textContent = `${extension} · ${formatFileSize(documentMetadata.size)}`;
    elements.startAnalysisButton.disabled = false;
    setMentor("success", "Файл загружен. Можно запускать комплексный анализ.");
  } catch (error) {
    state.document = null;
    elements.startAnalysisButton.disabled = true;
    setMentor("error", error.message || "Не удалось загрузить документ.");
    showNotification(error.message || "Не удалось загрузить документ.");
  }
}

function resetScenario() {
  state.file = null;
  state.document = null;
  state.analysisId = null;
  state.remarks = documentRemarks;
  elements.fileInput.value = "";
  elements.filePreview.hidden = true;
  elements.startAnalysisButton.disabled = true;
  elements.directionResult.textContent = "Выберите направление улучшения.";
  elements.chatMessages.innerHTML = "";
  addMessage("mentor", "Загрузите работу, и я проведу комплексный анализ.");
  showStage("upload");
  setMentor("idle", "Загрузите работу, и я проведу комплексный анализ.");
}

function renderAnalysisSteps(activeIndex = -1) {
  elements.analysisSteps.innerHTML = analysisSteps
    .map((step, index) => {
      const status = index < activeIndex ? "complete" : index === activeIndex ? "running" : "waiting";
      const label = status === "complete" ? "Завершен" : status === "running" ? "Выполняется" : "Ожидает";
      const indicator = status === "complete" ? '<span data-icon="check"></span>' : "";
      return `
        <div class="analysis-step is-${status}">
          <div class="analysis-step__indicator">${indicator}</div>
          <strong>${step.title}</strong>
          <span class="analysis-step__state">${label}</span>
        </div>
      `;
    })
    .join("");
  renderIcons();
}

function renderResults(result) {
  const normalized = normalizeResult(result);
  state.remarks = normalized.remarks.length ? normalized.remarks : documentRemarks;

  elements.criteriaList.innerHTML = normalized.criteria
    .map(
      ({ title, score }) => `
        <div class="criterion">
          <span>${title}</span>
          <div class="progress"><span style="width: ${score}%"></span></div>
          <strong>${score}%</strong>
        </div>
      `,
    )
    .join("");

  document.querySelector(".score-card strong").textContent = `${normalized.overall_score} / 100`;
  document.querySelector(".score-card > div span").textContent = normalized.verdict;
  document.querySelector(".score-ring").textContent = normalized.overall_score;
  renderList(elements.strengthsList, normalized.strengths);
  renderList(elements.improvementsList, normalized.improvements);
  renderList(elements.aiRiskList, normalized.aiRisk.factors);
}

function normalizeResult(result) {
  return {
    overall_score: result.overall_score ?? 87,
    verdict: result.verdict ?? "Работа выполнена на хорошем уровне",
    criteria: (result.criteria || []).map((criterion) => {
      if (Array.isArray(criterion)) {
        return { title: criterion[0], score: criterion[1] };
      }
      return criterion;
    }),
    strengths: result.strengths || [],
    improvements: result.improvements || [],
    remarks: result.remarks || [],
    aiRisk: result.ai_risk || { factors: result.aiRiskFactors || [] },
    recommendations: result.recommendations || recommendationPlan,
  };
}

function renderList(container, items) {
  container.innerHTML = items.map((item) => `<li>${item}</li>`).join("");
}

function renderDocumentReview() {
  const [first, ...rest] = documentParagraphs;
  elements.documentText.innerHTML = `
    <h3>${first.title}</h3>
    <p>${first.text}</p>
    ${rest.map((paragraph) => `<p class="${paragraph.highlighted ? "is-highlighted" : ""}">${paragraph.text}</p>`).join("")}
  `;
  renderRemark();
}

function renderRemark() {
  const remarks = state.remarks || documentRemarks;
  const remark = remarks[state.activeRemark] || remarks[0];
  elements.remarkContent.innerHTML = `
    <h3>${remark.title}</h3>
    <p><strong>Замечание:</strong> ${remark.quote}</p>
    <p><strong>Рекомендация:</strong> ${remark.recommendation}</p>
  `;
  elements.remarkTabs.innerHTML = remarks
    .map(
      (_, index) =>
        `<button class="remark-tab ${index === state.activeRemark ? "is-active" : ""}" type="button" data-remark="${index}">${index + 1}</button>`,
    )
    .join("");
}

function renderRecommendationPlan(items = recommendationPlan) {
  elements.recommendationPlan.innerHTML = items
    .map(
      (item) => `
        <article class="recommendation-card">
          <strong>${item.priority}</strong>
          <h3>${item.title}</h3>
          <p>Ожидаемый эффект: ${item.effect}</p>
          <p>Сложность: ${item.complexity}</p>
          <button class="button button--ghost" type="button" data-detail="${item.priority}">Подробнее</button>
        </article>
      `,
    )
    .join("");
}

function renderDirections() {
  elements.directionButtons.innerHTML = improvementDirections
    .map((item, index) => `<button type="button" data-direction="${index}">${item.label}</button>`)
    .join("");
}

function addMessage(author, text, extraClass = "") {
  const message = document.createElement("div");
  message.className = `chat-message is-${author} ${extraClass}`.trim();
  message.textContent = text;
  elements.chatMessages.append(message);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
  return message;
}

function renderChat() {
  elements.quickQuestions.innerHTML = quickQuestions
    .map((question) => `<button type="button" data-question="${question}">${question}</button>`)
    .join("");
  elements.chatMessages.innerHTML = "";
  addMessage("mentor", "Готов обсудить результаты анализа и помочь выбрать первые правки.");
}

async function askMentor(question) {
  addMessage("user", question);
  setMentor("speaking", "Формирую ответ на ваш вопрос.");
  const typing = addMessage("mentor", "Ментор формирует ответ.", "is-typing");

  try {
    const response = await askMentorApi(state.analysisId, question);
    typing.remove();
    addMessage("mentor", response.answer);
    setMentor("success", response.answer);
  } catch (error) {
    typing.remove();
    const answer = getMentorAnswer(question);
    addMessage("mentor", answer);
    setMentor("error", error.message || "Не удалось получить ответ от backend.");
    showNotification(error.message || "Не удалось получить ответ от backend.");
  }
}

async function startAnalysis() {
  if (!state.document?.id) return;

  showStage("processing");
  renderAnalysisSteps(0);
  setMentor("thinking", analysisSteps[0].message);

  try {
    const result = await runAnalysis(state.document.id, (status) => {
      if (status.frontendStepIndex !== undefined) {
        renderAnalysisSteps(status.frontendStepIndex);
      } else {
        const index = Math.min(
          analysisSteps.length - 1,
          Math.max(0, Math.floor((status.progress || 0) / (100 / analysisSteps.length))),
        );
        renderAnalysisSteps(index);
        state.analysisId = status.id || state.analysisId;
      }
      setMentor("thinking", status.message || "Выполняю анализ документа.");
    });

    state.analysisId = result.analysis_id || state.analysisId;
    renderAnalysisSteps(analysisSteps.length);
    renderResults(result);
    renderDocumentReview();
    renderRecommendationPlan(normalizeResult(result).recommendations);
    renderDirections();
    renderChat();
    showStage("results");
    setMentor("success", "Анализ завершен. Я подготовил оценку, замечания и план улучшения.");
  } catch (error) {
    setMentor("error", error.message || "Анализ завершился с ошибкой.");
    showNotification(error.message || "Анализ завершился с ошибкой.");
  }
}

function bindEvents() {
  if (isSpeechSupported()) {
    loadVoices();
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
  }

  elements.navItems.forEach((item) => {
    item.addEventListener("click", () => {
      const section = item.dataset.section;
      showPage(section);
    });
  });

  elements.chooseFileButton.addEventListener("click", () => elements.fileInput.click());
  elements.sidebarToggle.addEventListener("click", () => setSidebarCollapsed(!state.sidebarCollapsed));
  elements.fileInput.addEventListener("change", () => {
    enableSpeech();
    setFile(elements.fileInput.files[0]);
  });
  elements.removeFileButton.addEventListener("click", () => {
    enableSpeech();
    resetScenario();
  });
  elements.startAnalysisButton.addEventListener("click", () => {
    enableSpeech();
    startAnalysis();
  });
  elements.resetButton.addEventListener("click", () => {
    enableSpeech();
    resetScenario();
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    elements.dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.dropZone.querySelector(".drop-area").classList.add("is-over");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    elements.dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.dropZone.querySelector(".drop-area").classList.remove("is-over");
    });
  });

  elements.dropZone.addEventListener("drop", (event) => {
    enableSpeech();
    setFile(event.dataTransfer.files[0]);
  });

  elements.remarkTabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remark]");
    if (!button) return;
    state.activeRemark = Number(button.dataset.remark);
    renderRemark();
  });

  elements.directionButtons.addEventListener("click", (event) => {
    const button = event.target.closest("[data-direction]");
    if (!button) return;
    const direction = improvementDirections[Number(button.dataset.direction)];
    elements.directionResult.textContent = direction.text;
    enableSpeech();
    setMentor("speaking", direction.text);
  });

  elements.recommendationPlan.addEventListener("click", (event) => {
    const button = event.target.closest("[data-detail]");
    if (!button) return;
    showNotification(`${button.dataset.detail}: подробная карточка будет подключена на следующем этапе.`);
  });

  elements.quickQuestions.addEventListener("click", (event) => {
    const button = event.target.closest("[data-question]");
    if (!button) return;
    enableSpeech();
    askMentor(button.dataset.question);
  });

  elements.chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = elements.chatInput.value.trim();
    if (!question) return;
    enableSpeech();
    elements.chatInput.value = "";
    askMentor(question);
  });

  elements.micButton.addEventListener("click", () => {
    enableSpeech();
    startVoiceInput();
  });

  [elements.soundToggle, elements.avatarSoundButton].forEach((button) => {
    button.addEventListener("click", () => {
      enableSpeech();
      state.sound = !state.sound;
      updateSoundButton();
      if (state.sound) {
        if (!isSpeechSupported()) {
          showNotification("Браузер не поддерживает встроенную озвучку.");
          return;
        }
        state.lastSpokenMessage = "";
        showNotification("Звук включен. Сейчас Финик произнесет реплику.");
        speakMentor(elements.mentorMessage.textContent, true);
      } else {
        stopSpeech();
        showNotification("Звук выключен.");
      }
    });
  });
}

renderIcons();
renderAnalysisSteps();
bindEvents();
setSidebarCollapsed(true);
updateSoundButton();
updateMicButton();
resetScenario();
