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

const state = {
  file: null,
  sound: true,
  activeRemark: 0,
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

function setMentor(status, message) {
  const statusLabels = {
    idle: "Ожидает документ",
    speaking: "Формирует ответ",
    thinking: "Анализирует работу",
    success: "Анализ завершен",
    error: "Требуется действие",
  };
  elements.avatarCard.dataset.status = status;
  elements.mentorStatus.textContent = statusLabels[status] || statusLabels.idle;
  elements.mentorMessage.textContent = message;
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

function setFile(file) {
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
  elements.startAnalysisButton.disabled = false;
  setMentor("idle", "Файл выбран. Можно запускать комплексный анализ.");
}

function resetScenario() {
  state.file = null;
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
  elements.criteriaList.innerHTML = result.criteria
    .map(
      ([label, score]) => `
        <div class="criterion">
          <span>${label}</span>
          <div class="progress"><span style="width: ${score}%"></span></div>
          <strong>${score}%</strong>
        </div>
      `,
    )
    .join("");

  renderList(elements.strengthsList, result.strengths);
  renderList(elements.improvementsList, result.improvements);
  renderList(elements.aiRiskList, result.aiRiskFactors);
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
  const remark = documentRemarks[state.activeRemark];
  elements.remarkContent.innerHTML = `
    <h3>${remark.title}</h3>
    <p><strong>Замечание:</strong> ${remark.quote}</p>
    <p><strong>Рекомендация:</strong> ${remark.recommendation}</p>
  `;
  elements.remarkTabs.innerHTML = documentRemarks
    .map(
      (_, index) =>
        `<button class="remark-tab ${index === state.activeRemark ? "is-active" : ""}" type="button" data-remark="${index}">${index + 1}</button>`,
    )
    .join("");
}

function renderRecommendationPlan() {
  elements.recommendationPlan.innerHTML = recommendationPlan
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

function askMentor(question) {
  addMessage("user", question);
  setMentor("speaking", "Формирую ответ на ваш вопрос.");
  const typing = addMessage("mentor", "Ментор формирует ответ.", "is-typing");

  window.setTimeout(() => {
    typing.remove();
    const answer = getMentorAnswer(question);
    addMessage("mentor", answer);
    setMentor("success", answer);
  }, 850);
}

async function startAnalysis() {
  if (!state.file) return;

  showStage("processing");
  renderAnalysisSteps(0);
  setMentor("thinking", analysisSteps[0].message);

  const result = await mockMentorAnalysis((index) => {
    renderAnalysisSteps(index);
    setMentor("thinking", analysisSteps[index].message);
  });

  renderAnalysisSteps(analysisSteps.length);
  renderResults(result);
  renderDocumentReview();
  renderRecommendationPlan();
  renderDirections();
  renderChat();
  showStage("results");
  setMentor("success", "Анализ завершен. Я подготовил оценку, замечания и план улучшения.");
}

function bindEvents() {
  elements.navItems.forEach((item) => {
    item.addEventListener("click", () => {
      const section = item.dataset.section;
      showPage(section);
    });
  });

  elements.chooseFileButton.addEventListener("click", () => elements.fileInput.click());
  elements.sidebarToggle.addEventListener("click", () => setSidebarCollapsed(!state.sidebarCollapsed));
  elements.fileInput.addEventListener("change", () => setFile(elements.fileInput.files[0]));
  elements.removeFileButton.addEventListener("click", () => resetScenario());
  elements.startAnalysisButton.addEventListener("click", startAnalysis);
  elements.resetButton.addEventListener("click", resetScenario);

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
    askMentor(button.dataset.question);
  });

  elements.chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = elements.chatInput.value.trim();
    if (!question) return;
    elements.chatInput.value = "";
    askMentor(question);
  });

  elements.micButton.addEventListener("click", () => showNotification("Голосовой ввод будет подключен на следующем этапе."));

  [elements.soundToggle, elements.avatarSoundButton].forEach((button) => {
    button.addEventListener("click", () => {
      state.sound = !state.sound;
      elements.avatarSoundButton.innerHTML = `<span data-icon="volume2"></span>${state.sound ? "Озвучивание включено" : "Озвучивание выключено"}`;
      renderIcons();
      showNotification(state.sound ? "Звук включен." : "Звук выключен.");
    });
  });
}

renderIcons();
renderAnalysisSteps();
bindEvents();
setSidebarCollapsed(true);
resetScenario();
