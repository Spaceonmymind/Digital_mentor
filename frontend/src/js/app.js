import {
  analysisSteps,
  documentParagraphs,
  documentRemarks,
  improvementDirections,
  mockMentorAnalysis,
  recommendationPlan,
} from "../mocks/mentorAnalysis.js";
import { getMentorAnswer, quickQuestions } from "../mocks/mentorChat.js";
import { FRONTEND_MOCK_MODE } from "./config.js";
import { renderIcons } from "./icons.js";
import { cancelAnalysis, createReport, getDetailedReportStatus, getPublicConfig, startDetailedReport } from "./api.js";
import { uploadDocument } from "./modules/upload.js";
import { runAnalysis } from "./modules/analysis.js";
import { askMentorApi } from "./modules/chat.js";
import { BrowserSpeechService, BrowserSttService, DisabledSpeechService, RemoteTtsSpeechService } from "./modules/speech.js";
import { MascotController } from "./modules/mascot.js";
import { addHistoryItem, getHistory, removeHistoryItem } from "./modules/history.js";
import { checkReadiness } from "./modules/readiness.js";
import { requestImprovementDirection } from "./modules/recommendations.js";

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
  publicConfig: { demo_mode: false, frontend_mock_mode: false, tts_mode: "browser" },
  speechToken: 0,
  uiState: "welcome",
  result: null,
  checkedRecommendations: new Set(),
  activeRecommendation: null,
  lastSpokenStep: "",
  detailedReport: null,
  detailedReportPoll: null,
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
  welcomeStage: document.getElementById("welcomeStage"),
  uploadStage: document.getElementById("uploadStage"),
  processingStage: document.getElementById("processingStage"),
  summaryStage: document.getElementById("summaryStage"),
  resultsStage: document.getElementById("resultsStage"),
  finalStage: document.getElementById("finalStage"),
  errorStage: document.getElementById("errorStage"),
  startDemoButton: document.getElementById("startDemoButton"),
  dropZone: document.getElementById("dropZone"),
  fileInput: document.getElementById("fileInput"),
  chooseFileButton: document.getElementById("chooseFileButton"),
  filePreview: document.getElementById("filePreview"),
  fileName: document.getElementById("fileName"),
  fileMeta: document.getElementById("fileMeta"),
  removeFileButton: document.getElementById("removeFileButton"),
  startAnalysisButton: document.getElementById("startAnalysisButton"),
  cancelAnalysisButton: document.getElementById("cancelAnalysisButton"),
  processingFileName: document.getElementById("processingFileName"),
  processingPercent: document.getElementById("processingPercent"),
  processingPhase: document.getElementById("processingPhase"),
  processingLiveStep: document.getElementById("processingLiveStep"),
  overallProgressBar: document.getElementById("overallProgressBar"),
  analysisSteps: document.getElementById("analysisSteps"),
  summaryScore: document.getElementById("summaryScore"),
  summaryVerdict: document.getElementById("summaryVerdict"),
  summaryStrengths: document.getElementById("summaryStrengths"),
  summaryImprovements: document.getElementById("summaryImprovements"),
  detailsButton: document.getElementById("detailsButton"),
  summaryReportButton: document.getElementById("summaryReportButton"),
  summaryResetButton: document.getElementById("summaryResetButton"),
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
  clearChatButton: document.getElementById("clearChatButton"),
  stopSpeechButton: document.getElementById("stopSpeechButton"),
  soundToggle: document.getElementById("soundToggle"),
  avatarSoundButton: document.getElementById("avatarSoundButton"),
  resetButton: document.getElementById("resetButton"),
  notification: document.getElementById("notification"),
  modeBanner: document.getElementById("modeBanner"),
  demoDocumentButton: document.getElementById("demoDocumentButton"),
  reportButton: document.getElementById("reportButton"),
  detailedReportStatusText: document.getElementById("detailedReportStatusText"),
  detailedReportFlow: document.getElementById("detailedReportFlow"),
  finishDemoButton: document.getElementById("finishDemoButton"),
  finalReportButton: document.getElementById("finalReportButton"),
  finalResetButton: document.getElementById("finalResetButton"),
  backToResultsButton: document.getElementById("backToResultsButton"),
  historyList: document.getElementById("historyList"),
  errorTitle: document.getElementById("errorTitle"),
  errorDescription: document.getElementById("errorDescription"),
  errorRequestId: document.getElementById("errorRequestId"),
  recommendationModal: document.getElementById("recommendationModal"),
  recommendationModalClose: document.getElementById("recommendationModalClose"),
  recommendationModalOk: document.getElementById("recommendationModalOk"),
  recommendationModalAccept: document.getElementById("recommendationModalAccept"),
  recommendationModalPriority: document.getElementById("recommendationModalPriority"),
  recommendationModalTitle: document.getElementById("recommendationModalTitle"),
  recommendationModalDescription: document.getElementById("recommendationModalDescription"),
  recommendationModalEffect: document.getElementById("recommendationModalEffect"),
  recommendationModalComplexity: document.getElementById("recommendationModalComplexity"),
  recommendationModalAction: document.getElementById("recommendationModalAction"),
  retryButton: document.getElementById("retryButton"),
  fullscreenButton: document.getElementById("fullscreenButton"),
  presenterPanel: document.getElementById("presenterPanel"),
  presenterCloseButton: document.getElementById("presenterCloseButton"),
  readinessTable: document.getElementById("readinessTable"),
};

let speechService = new BrowserSpeechService();
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
    greeting: "Приветствует",
    uploading: "Получает документ",
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
  const token = ++state.speechToken;
  speechService.speak(message, {
    force,
    onStart: () => {
      if (token === state.speechToken) mascot.setMascotState({ state: "speaking", message });
    },
    onEnd: () => {
      if (token === state.speechToken) {
        mascot.setMascotState({ state: state.uiState === "processing" ? "thinking" : state.analysisId ? "success" : "idle", message });
      }
    },
  });
}

function stopSpeech() {
  state.speechToken += 1;
  speechService.stop();
  sttService.stop();
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
  if (!state.analysisId && !FRONTEND_MOCK_MODE) {
    showNotification("Сначала завершите анализ, после этого можно задавать вопросы.");
    return;
  }

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
  [
    elements.welcomeStage,
    elements.uploadStage,
    elements.processingStage,
    elements.summaryStage,
    elements.resultsStage,
    elements.finalStage,
    elements.errorStage,
  ].forEach((stage) => {
    stage.classList.remove("is-visible");
  });
  elements[`${stageName}Stage`].classList.add("is-visible");
  state.uiState = stageName;
}

function showPage(section) {
  stopSpeech();
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

function setDetailedReportButtons(status = "not_started") {
  const buttons = [elements.reportButton, elements.summaryReportButton, elements.finalReportButton].filter(Boolean);
  const ready = status === "completed";
  const failed = status === "failed";
  const label = ready ? "Скачать подробный отчет" : failed ? "Повторить подготовку отчета" : "Отчет готовится";
  buttons.forEach((button) => {
    button.disabled = !ready && !failed;
    const icon = button.querySelector("[data-icon]");
    button.textContent = "";
    if (icon) button.append(icon);
    button.append(document.createTextNode(label));
  });
  if (elements.detailedReportStatusText) {
    const textByStatus = {
      not_started: "Подробный PDF появится после быстрого результата. Он будет собран из сохраненного анализа и извлеченного текста документа.",
      running: "Готовлю подробный отчет: вытаскиваю примеры из текста, собираю доказательства и оформляю рекомендации.",
      completed: "Подробный отчет готов. Его можно скачать без повторного запуска анализа.",
      failed: "Подробный отчет не собрался. Можно запустить подготовку еще раз.",
    };
    elements.detailedReportStatusText.textContent = textByStatus[status] || textByStatus.not_started;
  }
  if (elements.detailedReportFlow) {
    const items = [...elements.detailedReportFlow.querySelectorAll(".report-flow__item")];
    const activeIndex = status === "completed" ? items.length : status === "running" ? 2 : status === "failed" ? 0 : 1;
    items.forEach((item, index) => {
      item.classList.toggle("is-active", status === "running" && index === activeIndex);
      item.classList.toggle("is-complete", status === "completed" || (status === "running" && index < activeIndex));
      item.classList.toggle("is-failed", status === "failed" && index === 0);
    });
  }
}

async function refreshDetailedReportStatus() {
  if (!state.analysisId) return;
  const status = await getDetailedReportStatus(state.analysisId);
  state.detailedReport = status;
  setDetailedReportButtons(status.status);
  if (status.status === "completed" || status.status === "failed") {
    if (state.detailedReportPoll) {
      window.clearInterval(state.detailedReportPoll);
      state.detailedReportPoll = null;
    }
    showNotification(status.status === "completed" ? "Подробный отчет готов." : "Не удалось подготовить подробный отчет.");
  }
}

async function startDetailedReportLoading() {
  if (!state.analysisId || FRONTEND_MOCK_MODE) return;
  if (state.detailedReportPoll) {
    window.clearInterval(state.detailedReportPoll);
  }
  setDetailedReportButtons("running");
  try {
    state.detailedReport = await startDetailedReport(state.analysisId);
    setDetailedReportButtons(state.detailedReport.status);
    state.detailedReportPoll = window.setInterval(() => {
      refreshDetailedReportStatus().catch(() => {});
    }, 2500);
    await refreshDetailedReportStatus();
  } catch (error) {
    setDetailedReportButtons("failed");
    showNotification(error.message || "Не удалось запустить подготовку подробного отчета.");
  }
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
    showNotification("Выберите файл PDF или DOCX.");
    return;
  }

  state.file = file;
  elements.fileName.textContent = file.name;
  elements.fileMeta.textContent = `${extension} · ${formatFileSize(file.size)}`;
  elements.filePreview.hidden = false;
  elements.startAnalysisButton.disabled = true;
  setMentor("uploading", "Получаю документ и проверяю возможность обработки.");

  try {
    const documentMetadata = await uploadDocument(file);
    state.document = documentMetadata;
    elements.fileName.textContent = documentMetadata.name;
    elements.fileMeta.textContent = `${extension} · ${formatFileSize(documentMetadata.size)}`;
    elements.startAnalysisButton.disabled = false;
    setMentor("success", "Документ получен. Я готов приступить к анализу.");
  } catch (error) {
    state.document = null;
    elements.startAnalysisButton.disabled = true;
    setMentor("error", error.message || "Не удалось загрузить документ.");
    showNotification(error.message || "Не удалось загрузить документ.");
  }
}

async function useDemoDocument() {
  enableSpeech();
  try {
    const response = await fetch("/demo/sample-document.pdf");
    if (!response.ok) throw new Error("Пример работы не найден.");
    const blob = await response.blob();
    const file = new File([blob], "sample-document.pdf", { type: "application/pdf" });
    await setFile(file);
  } catch (error) {
    showNotification(error.message || "Не удалось загрузить пример работы.");
  }
}

function resetScenario() {
  stopSpeech();
  if (state.detailedReportPoll) {
    window.clearInterval(state.detailedReportPoll);
  }
  state.file = null;
  state.document = null;
  state.analysisId = null;
  state.result = null;
  state.remarks = documentRemarks;
  state.checkedRecommendations = new Set();
  state.activeRecommendation = null;
  state.lastSpokenStep = "";
  state.detailedReport = null;
  state.detailedReportPoll = null;
  setDetailedReportButtons("not_started");
  closeRecommendationModal();
  elements.fileInput.value = "";
  elements.filePreview.hidden = true;
  elements.startAnalysisButton.disabled = true;
  elements.processingPercent.textContent = "0%";
  elements.processingPhase.textContent = "Подготовка документа";
  elements.processingLiveStep.textContent = "Ожидаю запуск";
  elements.overallProgressBar.style.width = "0%";
  elements.directionResult.textContent = "Выберите направление улучшения.";
  elements.chatMessages.innerHTML = "";
  addMessage("mentor", "Загрузите работу, и я проведу комплексный анализ.");
  showStage("upload");
  setMentor("idle", "Загрузите работу, и я проведу комплексный анализ.");
  renderHistory();
}

const processingAgents = [
  { title: "Проблема", description: "проверяю актуальность и противоречие" },
  { title: "Экономика", description: "смотрю модель, расчеты и пороги" },
  { title: "Архитектура", description: "проверяю реализуемость решения" },
  { title: "Риски", description: "ищу слабые места и ограничения" },
  { title: "Итог", description: "собираю понятное заключение" },
];

function renderAnalysisSteps(activeIndex = -1, progress = 0) {
  elements.analysisSteps.innerHTML = processingAgents
    .map((agent, index) => {
      let status = "waiting";
      if (progress >= 100 || index < activeIndex) status = "complete";
      if (index === activeIndex) status = "running";
      if (activeIndex === 1 && index >= 0 && index <= 3) status = "running";
      if (activeIndex === 4 && index <= 3) status = "complete";
      const label = status === "complete" ? "готово" : status === "running" ? "в работе" : "ожидает";
      const indicator = status === "complete" ? '<span data-icon="check"></span>' : "";
      return `
        <div class="analysis-step is-${status}">
          <div class="analysis-step__indicator">${indicator}</div>
          <strong>${agent.title}</strong>
          <p>${agent.description}</p>
          <span class="analysis-step__state">${label}</span>
        </div>
      `;
    })
    .join("");
  renderIcons();
}

function processingAgentIndex(progress = 0, currentStep = "") {
  if (currentStep === "demo_final" || progress >= 88) return 4;
  if (currentStep === "demo_agents" || progress >= 25) return 1;
  return 0;
}

function processingStepLabel(progress = 0, currentStep = "") {
  if (progress >= 100 || currentStep === "completed") return "Завершено";
  if (currentStep === "demo_final" || progress >= 88) return "Формирование итогового вывода";
  if (currentStep === "demo_agents" || progress >= 25) return "Параллельная проверка ключевых разделов";
  if (currentStep === "extracting" || currentStep === "preparing") return "Подготовка текста";
  return "Запуск анализа";
}

function renderResults(result) {
  const normalized = normalizeResult(result);
  state.result = normalized;
  state.remarks = normalized.remarks.length ? normalized.remarks : documentRemarks;

  elements.criteriaList.innerHTML = normalized.criteria
    .map(
      ({ title, score, explanation }) => `
        <div class="criterion">
          <div class="criterion__head">
            <span>${title}</span>
            <strong>${normalized.isMentorReport ? `${score}/5` : normalized.isDemoReport ? `${score}/10` : `${score}%`}</strong>
          </div>
          <small>${explanation || getScoreLevel(score)}</small>
          <div class="progress"><span style="width: ${normalized.isMentorReport ? Math.round((score / 5) * 100) : normalized.isDemoReport ? Math.round((score / 10) * 100) : score}%"></span></div>
        </div>
      `,
    )
    .join("");

  document.querySelector(".score-card .eyebrow").textContent = normalized.isMentorReport ? "Текущая стадия" : normalized.isDemoReport ? "Demo-оценка" : "Итоговая оценка";
  document.querySelector(".score-card strong").textContent = normalized.isMentorReport ? normalized.currentStage : normalized.isDemoReport ? `${normalized.overall_score} / 60` : `${normalized.overall_score} / 100`;
  document.querySelector(".score-card > div span").textContent = normalized.verdict;
  const ring = document.querySelector(".score-ring");
  const scorePercent = normalized.isMentorReport ? 50 : normalized.isDemoReport ? Math.round((normalized.overall_score / 60) * 100) : normalized.overall_score;
  ring.textContent = normalized.isMentorReport ? normalized.currentStage : normalized.isDemoReport ? `${normalized.overall_score}/60` : normalized.overall_score;
  ring.style.setProperty("--score-angle", `${Math.max(0, Math.min(100, scorePercent)) * 3.6}deg`);
  renderList(elements.strengthsList, normalized.strengths);
  renderList(elements.improvementsList, normalized.improvements);
  renderList(elements.aiRiskList, normalized.aiRisk.factors);
  renderSummary(normalized);
  if (normalized.analysis_id) {
    addHistoryItem({
      analysis_id: normalized.analysis_id,
      document_name: state.document?.name || state.file?.name || "Документ",
      overall_score: normalized.overall_score,
      status: "completed",
    });
    renderHistory();
  }
}

function normalizeResult(result) {
  const extraBlocks = result.extra_blocks || {};
  const mentorReport = extraBlocks.mentor_report || result.report || null;
  if (mentorReport) {
    return normalizeMentorReportResult(result, mentorReport);
  }
  const demoReport = extraBlocks.demo_report || null;
  if (demoReport) {
    return normalizeDemoReportResult(result, demoReport);
  }
  const aiRisk = result.ai_risk || { factors: result.aiRiskFactors || [] };

  return {
    analysis_id: result.analysis_id || state.analysisId,
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
    aiRisk,
    recommendations: result.recommendations || recommendationPlan,
    isMentorReport: false,
    isDemoReport: false,
  };
}

function normalizeDemoReportResult(result, report) {
  return {
    analysis_id: result.analysis_id || state.analysisId,
    overall_score: report.overall_score,
    currentStage: null,
    verdict: report.conclusion,
    criteria: (report.criteria || []).map((item, index) => ({
      code: String(index + 1),
      title: item.name,
      score: item.score,
      max_score: 10,
      explanation: item.comment,
    })),
    strengths: report.strengths || [],
    improvements: report.remarks || [],
    remarks: (report.remarks || []).map((item, index) => ({
      title: item,
      quote: "",
      comment: item,
      recommendation: (report.recommendations || [])[index] || "Уточнить этот пункт.",
      severity: "medium",
    })),
    aiRisk: {
      level: "demo",
      factors: [
        "Demo-режим: короткий мультиагентный анализ",
        "Контекст сокращен до смысловых блоков",
        "Для защиты результата используйте standard/expert режим",
      ],
      disclaimer: "Demo-отчет предназначен для быстрой демонстрации и не заменяет полный expert-анализ.",
    },
    recommendations: (report.recommendations || []).map((item, index) => ({
      priority: String(index + 1),
      title: item,
      effect: "Улучшит демонстрационную оценку",
      complexity: "Средняя",
    })),
    spokenSummary: report.spoken_summary || report.conclusion,
    isMentorReport: false,
    isDemoReport: true,
  };
}

function normalizeMentorReportResult(result, report) {
  const objections = report.objections || [];
  const nextStep = report.one_next_step || {};
  const question = report.one_question || {};
  const stageItems = report.stage_assessments || [];
  const currentStage = report.header?.current_stage || "S?";
  const vetoFactors = report.veto?.is_active
    ? [
        "ВЕТО",
        `Причина: ${report.veto.reason}`,
        `Что нужно для снятия: ${report.veto.how_to_remove}`,
      ]
    : [];
  return {
    analysis_id: result.analysis_id || state.analysisId,
    overall_score: 0,
    currentStage,
    verdict: report.what_this_work_is || "Разбор сформирован.",
    criteria: stageItems.map((item) => ({
      title: `${item.stage_code} ${item.title}`,
      score: item.score,
      explanation: `${item.completed} До следующего уровня: ${item.next_level_requirement}`,
    })),
    strengths: report.what_survived || [],
    improvements: objections.map((item) => `${item.title}. Что не работает: ${item.what_does_not_work} Почему: ${item.why} Куда двигаться: ${item.where_to_move}`),
    remarks: objections.map((item, index) => ({
      title: item.title,
      quote: "",
      comment: `${item.what_does_not_work}\n\nПочему: ${item.why}`,
      recommendation: item.where_to_move,
      severity: index === 0 ? "high" : "medium",
    })),
    aiRisk: {
      level: "medium",
      factors: [
        ...vetoFactors,
        `Один вопрос: ${question.question || "не сформирован"}`,
        `Следующий шаг: ${nextStep.step || "не сформирован"}`,
        `Проверка результата шага: ${nextStep.check_result || "не указана"}`,
      ],
      disclaimer: "Разбор не является подписью человека и не заменяет решение научного руководителя или экспертного совета.",
    },
    recommendations: [
      {
        priority: "1",
        title: nextStep.step || "Сформулировать следующий проверяемый шаг.",
        effect: nextStep.check_result || "Появится проверяемое основание для следующей стадии.",
        complexity: "Средняя",
      },
    ],
    mentorReport: report,
    spokenSummary: report.spoken_summary || "",
    isMentorReport: true,
  };
}

function getScoreLevel(score) {
  if (score >= 90) return "Высокий";
  if (score >= 75) return "Достаточный";
  return "Требует внимания";
}

function renderSummary(result) {
  elements.summaryScore.textContent = result.isMentorReport ? result.currentStage : result.overall_score;
  const summaryScoreCaption = document.querySelector(".summary-score span");
  if (summaryScoreCaption) summaryScoreCaption.textContent = result.isMentorReport ? "текущая стадия" : result.isDemoReport ? "из 60" : "из 100";
  elements.summaryVerdict.textContent = result.spokenSummary || result.verdict;
  renderList(elements.summaryStrengths, result.strengths.slice(0, 3));
  renderList(elements.summaryImprovements, result.improvements.slice(0, 3));
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
  const quote = remark.quote?.trim();
  elements.remarkContent.innerHTML = `
    <span class="remark-meta">${remark.section || "Фрагмент документа"} · ${remark.severity || "важно"}</span>
    <h3>${remark.title || remark.comment || "Замечание"}</h3>
    ${quote ? `<blockquote>${quote}</blockquote>` : ""}
    <div class="remark-card__body">
      <div>
        <span>Что не так</span>
        <p>${remark.comment || remark.title || "Фрагмент требует уточнения."}</p>
      </div>
      <div>
        <span>Что сделать</span>
        <p>${remark.recommendation || "Уточнить этот пункт и добавить проверяемые основания."}</p>
      </div>
    </div>
  `;
  elements.remarkTabs.innerHTML = remarks
    .map(
      (_, index) =>
        `<button class="remark-tab ${index === state.activeRemark ? "is-active" : ""}" type="button" data-remark="${index}">${index + 1}</button>`,
    )
    .join("");
}

function getRecommendationNumber(priority) {
  return String(priority || "")
    .match(/\d+/)?.[0] || String(priority || "1");
}

function getRecommendationAction(item) {
  const title = item?.title || "Доработать выбранный пункт.";
  const normalized = title.toLowerCase();
  if (normalized.includes("методолог")) {
    return "Добавьте отдельный короткий подраздел: цель метода, выборка или объект анализа, критерии оценки и способ интерпретации результатов.";
  }
  if (normalized.includes("сравнитель")) {
    return "Соберите 3-5 аналогов, задайте единые критерии сравнения и покажите, чем предложенное решение отличается по ценности и применимости.";
  }
  if (normalized.includes("вывод")) {
    return "После ключевых разделов добавьте авторские выводы: что получилось доказать, какие ограничения есть и какой практический смысл имеет результат.";
  }
  if (normalized.includes("источник")) {
    return "Подберите дополнительные актуальные источники, свяжите каждый источник с конкретным тезисом и обновите список литературы.";
  }
  return "Сформулируйте конкретное изменение, добавьте подтверждающие материалы и проверьте, что доработка отражена в выводах.";
}

function openRecommendationModal(item) {
  if (!item) return;
  state.activeRecommendation = item;
  elements.recommendationModalPriority.textContent = getRecommendationNumber(item.priority);
  elements.recommendationModalTitle.textContent = item.title;
  elements.recommendationModalDescription.textContent =
    item.description || "Эта доработка поможет сделать работу убедительнее и понятнее для эксперта.";
  elements.recommendationModalEffect.textContent = item.effect || "Повысит качество работы";
  elements.recommendationModalComplexity.textContent = item.complexity || "Средняя";
  elements.recommendationModalAction.textContent = getRecommendationAction(item);
  elements.recommendationModal.hidden = false;
  document.body.classList.add("is-modal-open");
  elements.recommendationModalOk.focus();
}

function closeRecommendationModal() {
  elements.recommendationModal.hidden = true;
  document.body.classList.remove("is-modal-open");
}

function toggleRecommendationChecked(priority) {
  if (state.checkedRecommendations.has(priority)) {
    state.checkedRecommendations.delete(priority);
  } else {
    state.checkedRecommendations.add(priority);
  }
  renderRecommendationPlan(state.result?.recommendations || recommendationPlan);
}

function markRecommendationChecked(priority) {
  state.checkedRecommendations.add(priority);
  renderRecommendationPlan(state.result?.recommendations || recommendationPlan);
}


function renderRecommendationPlan(items = recommendationPlan) {
  elements.recommendationPlan.innerHTML = items
    .map(
      (item) => `
        <article class="recommendation-card ${state.checkedRecommendations.has(item.priority) ? "is-checked" : ""}">
          <div class="recommendation-card__top">
            <div class="recommendation-card__number">
              <strong>${getRecommendationNumber(item.priority)}</strong>
            </div>
            <h3>${item.title}</h3>
          </div>
          <p>${item.description || "Рекомендация поможет повысить качество итоговой работы."}</p>
          <div class="recommendation-card__meta">
            <span>${item.effect}</span>
            <span>${item.complexity}</span>
          </div>
          <div class="recommendation-card__actions">
            <button class="button button--ghost" type="button" data-detail="${item.priority}">Подробнее</button>
            <button class="button button--secondary" type="button" data-check-recommendation="${item.priority}">Учту</button>
          </div>
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
  if (!state.analysisId && !FRONTEND_MOCK_MODE) {
    showNotification("Сначала завершите анализ, затем задайте вопрос ментору.");
    return;
  }
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
    setMentor("error", error.message || "Не удалось получить ответ.");
    showNotification(error.message || "Не удалось получить ответ.");
  }
}

async function startAnalysis() {
  if (!state.document?.id) return;

  elements.processingFileName.textContent = state.document.name || state.file?.name || "Работа";
  elements.processingPercent.textContent = "0%";
  elements.processingPhase.textContent = "Подготовка документа";
  elements.processingLiveStep.textContent = "Запуск анализа";
  elements.overallProgressBar.style.width = "0%";
  showStage("processing");
  renderAnalysisSteps(0, 0);
  setMentor("thinking", analysisSteps[0].message);

  try {
    const result = await runAnalysis(state.document.id, (status) => {
      if (status.frontendStepIndex !== undefined) {
        renderAnalysisSteps(status.frontendStepIndex, status.progress || 0);
      } else {
        renderAnalysisSteps(processingAgentIndex(status.progress || 0, status.current_step || ""), status.progress || 0);
        state.analysisId = status.id || state.analysisId;
      }
      const progress = Math.max(0, Math.min(100, status.progress || 0));
      elements.processingPercent.textContent = `${progress}%`;
      elements.processingPhase.textContent = status.message || "Агенты анализируют документ";
      elements.processingLiveStep.textContent = processingStepLabel(progress, status.current_step || "");
      elements.overallProgressBar.style.width = `${progress}%`;
      const shouldSpeak = [20, 48, 72, 95].some((mark) => Math.abs(progress - mark) <= 3);
      const stepKey = status.current_step || status.message;
      if (shouldSpeak && stepKey !== state.lastSpokenStep) {
        state.lastSpokenStep = stepKey;
        setMentor("thinking", status.message || "Выполняю анализ документа.");
      } else {
        mascot.setMascotState({ state: "thinking", message: status.message || "Выполняю анализ документа." });
      }
    });

    state.analysisId = result.analysis_id || state.analysisId;
    elements.processingPercent.textContent = "100%";
    elements.processingPhase.textContent = "Быстрый анализ готов";
    elements.processingLiveStep.textContent = "Завершено";
    elements.overallProgressBar.style.width = "100%";
    renderAnalysisSteps(processingAgents.length, 100);
    renderResults(result);
    renderDocumentReview();
    renderRecommendationPlan(normalizeResult(result).recommendations);
    renderDirections();
    renderChat();
    startDetailedReportLoading();
    showStage("summary");
    const normalized = normalizeResult(result);
    setMentor("success", normalized.spokenSummary || `Анализ завершен. Текущая стадия работы: ${normalized.currentStage || "не определена"}.`);
  } catch (error) {
    showError("Не удалось обработать документ", error.message || "Проверьте, что файл не поврежден и содержит текстовый слой.", error.body?.error?.request_id);
  }
}

async function cancelCurrentAnalysis() {
  if (state.analysisId) {
    try {
      await cancelAnalysis(state.analysisId);
    } catch {
      // Best-effort cancellation for the demo interface.
    }
  }
  showStage("upload");
  setMentor("idle", "Анализ отменен. Можно выбрать другой документ.");
}

async function downloadReport() {
  if (!state.analysisId) {
    showNotification("Сначала завершите анализ документа.");
    return;
  }
  try {
    if (!FRONTEND_MOCK_MODE) {
      if (!state.detailedReport || state.detailedReport.status === "not_started" || state.detailedReport.status === "failed") {
        await startDetailedReportLoading();
      }
      if (state.detailedReport?.status !== "completed") {
        showNotification("Подробный отчет еще готовится.");
        return;
      }
      window.open(state.detailedReport.report_url, "_blank", "noopener");
      return;
    }
    const report = await createReport(state.analysisId);
    window.open(report.report_url, "_blank", "noopener");
    showNotification("Отчет сформирован.");
  } catch (error) {
    showNotification(error.message || "Не удалось сформировать отчет.");
  }
}

function showError(title, description, requestId) {
  elements.errorTitle.textContent = title;
  elements.errorDescription.textContent = description;
  elements.errorRequestId.textContent = requestId ? `request_id: ${requestId}` : "request_id не получен";
  showStage("error");
  setMentor("error", description);
}

function renderHistory() {
  const items = getHistory();
  elements.historyList.innerHTML = items.length
    ? items
        .map(
          (item) => `
            <article class="history-item">
              <div>
                <strong>${item.document_name}</strong>
                <span>${new Date(item.created_at).toLocaleString("ru-RU")} · ${item.overall_score || "—"} баллов · ${item.status}</span>
              </div>
              <button class="icon-button" type="button" aria-label="Удалить запись истории" data-remove-history="${item.analysis_id}">
                <span data-icon="trash-2"></span>
              </button>
            </article>
          `,
        )
        .join("")
    : "<p>Пока нет сохраненных проверок.</p>";
  renderIcons();
}

function openFullscreen() {
  const target = document.documentElement;
  if (!document.fullscreenEnabled || !target.requestFullscreen) {
    showNotification("Браузер не поддерживает полноэкранный режим.");
    return;
  }
  target.requestFullscreen().catch(() => showNotification("Не удалось включить полноэкранный режим."));
}

async function runReadinessCheck() {
  const checks = await checkReadiness({ mascotImage: elements.mascotImage });
  elements.readinessTable.innerHTML = `
    <table>
      <thead><tr><th>Компонент</th><th>Статус</th><th>Комментарий</th></tr></thead>
      <tbody>${checks.map((item) => `<tr><td>${item.component}</td><td>${item.status}</td><td>${item.comment}</td></tr>`).join("")}</tbody>
    </table>
  `;
}

function showPresenterPanel(show = true) {
  elements.presenterPanel.hidden = !show;
  renderIcons();
}

function beginWork() {
  enableSpeech();
  showStage("upload");
  setMentor(
    "greeting",
    "Добрый день! Я цифровой ментор. Загрузите работу, и я помогу определить ее сильные стороны и направления дальнейшего развития.",
  );
}

function configureSpeechService(ttsMode) {
  const browser = new BrowserSpeechService();
  if (ttsMode === "remote") {
    speechService = new RemoteTtsSpeechService({
      fallback: browser,
      onFallback: () => showNotification("Серверная озвучка недоступна, включен голос браузера."),
    });
  } else if (ttsMode === "disabled") {
    speechService = new DisabledSpeechService();
  } else {
    speechService = browser;
  }
}

async function loadPublicConfig() {
  try {
    const config = await getPublicConfig();
    state.publicConfig = config;
    window.__MENTOR_DEMO_MODE__ = Boolean(config.demo_mode);
    configureSpeechService(config.tts_mode);
    document.body.classList.toggle("is-presentation-mode", Boolean(config.presentation_mode));
    elements.demoDocumentButton.hidden = !(config.demo_mode || FRONTEND_MOCK_MODE);
    elements.modeBanner.hidden = !(config.frontend_mock_mode || FRONTEND_MOCK_MODE);
  } catch (error) {
    window.__MENTOR_DEMO_MODE__ = false;
    configureSpeechService("browser");
    elements.modeBanner.hidden = !FRONTEND_MOCK_MODE;
    elements.demoDocumentButton.hidden = !FRONTEND_MOCK_MODE;
  }
}

function bindEvents() {
  if (isSpeechSupported()) {
    loadVoices();
    window.speechSynthesis?.addEventListener?.("voiceschanged", loadVoices);
  }

  elements.navItems.forEach((item) => {
    item.addEventListener("click", () => {
      const section = item.dataset.section;
      showPage(section);
    });
  });

  elements.chooseFileButton.addEventListener("click", () => elements.fileInput.click());
  elements.startDemoButton.addEventListener("click", beginWork);
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
  elements.cancelAnalysisButton.addEventListener("click", cancelCurrentAnalysis);
  elements.resetButton.addEventListener("click", () => {
    enableSpeech();
    resetScenario();
  });
  elements.demoDocumentButton.addEventListener("click", useDemoDocument);
  elements.reportButton.addEventListener("click", downloadReport);
  elements.finishDemoButton.addEventListener("click", () => {
    showStage("final");
    setMentor("success", "Работа завершена. Отчет и рекомендации готовы к дальнейшей доработке.");
  });
  elements.summaryReportButton.addEventListener("click", downloadReport);
  elements.finalReportButton.addEventListener("click", downloadReport);
  elements.detailsButton.addEventListener("click", () => {
    showStage("results");
    setMentor("success", "Открываю подробный анализ работы.");
  });
  elements.summaryResetButton.addEventListener("click", resetScenario);
  elements.finalResetButton.addEventListener("click", resetScenario);
  elements.backToResultsButton.addEventListener("click", () => showStage("results"));
  elements.retryButton.addEventListener("click", resetScenario);
  elements.fullscreenButton.addEventListener("click", openFullscreen);
  elements.clearChatButton.addEventListener("click", () => renderChat());
  elements.stopSpeechButton.addEventListener("click", stopSpeech);

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

  elements.directionButtons.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-direction]");
    if (!button) return;
    const direction = improvementDirections[Number(button.dataset.direction)];
    elements.directionResult.textContent = "Ментор подбирает рекомендацию.";
    enableSpeech();
    const answer = await requestImprovementDirection({
      analysisId: state.analysisId,
      label: direction.label,
      fallbackText: direction.text,
    });
    elements.directionResult.textContent = answer;
    setMentor("speaking", answer);
  });

  elements.recommendationPlan.addEventListener("click", (event) => {
    const checkButton = event.target.closest("[data-check-recommendation]");
    if (checkButton) {
      toggleRecommendationChecked(checkButton.dataset.checkRecommendation);
      return;
    }
    const button = event.target.closest("[data-detail]");
    if (!button) return;
    const items = state.result?.recommendations || recommendationPlan;
    openRecommendationModal(items.find((item) => item.priority === button.dataset.detail));
  });

  elements.recommendationModalClose.addEventListener("click", closeRecommendationModal);
  elements.recommendationModalOk.addEventListener("click", closeRecommendationModal);
  elements.recommendationModal.addEventListener("click", (event) => {
    if (event.target === elements.recommendationModal) closeRecommendationModal();
  });
  elements.recommendationModalAccept.addEventListener("click", () => {
    if (state.activeRecommendation) {
      markRecommendationChecked(state.activeRecommendation.priority);
    }
    closeRecommendationModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !elements.recommendationModal.hidden) {
      closeRecommendationModal();
    }
  });

  elements.historyList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-history]");
    if (!button) return;
    removeHistoryItem(button.dataset.removeHistory);
    renderHistory();
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

  elements.presenterCloseButton.addEventListener("click", () => showPresenterPanel(false));
  elements.presenterPanel.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-presenter-action]");
    if (!button) return;
    const action = button.dataset.presenterAction;
    if (action === "reset") resetScenario();
    if (action === "upload") showStage("upload");
    if (action === "analysis") showStage("processing");
    if (action === "summary") showStage(state.result ? "summary" : "results");
    if (action === "mock") {
      window.localStorage.setItem("FRONTEND_MOCK_MODE", "true");
      elements.modeBanner.hidden = false;
      showNotification("Резервный режим включен для следующего сценария.");
    }
    if (action === "sound") {
      state.sound = !state.sound;
      updateSoundButton();
    }
    if (action === "ready") await runReadinessCheck();
    if (action === "fullscreen") openFullscreen();
  });

  window.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "d") {
      event.preventDefault();
      showPresenterPanel(elements.presenterPanel.hidden);
    }
  });
}

async function init() {
  await loadPublicConfig();
  renderIcons();
  renderAnalysisSteps();
  bindEvents();
  setSidebarCollapsed(true);
  updateSoundButton();
  updateMicButton();
  setDetailedReportButtons("not_started");
  renderHistory();
  showStage("welcome");
  setMentor(
    "greeting",
    "Добрый день! Я цифровой ментор. Загрузите работу, и я помогу определить ее сильные стороны и направления дальнейшего развития.",
  );
}

init();
