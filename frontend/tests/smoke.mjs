import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import assert from "node:assert/strict";

const root = resolve(import.meta.dirname, "..");
const html = readFileSync(resolve(root, "index.html"), "utf8");
const app = readFileSync(resolve(root, "src/js/app.js"), "utf8");
const css = readFileSync(resolve(root, "src/styles/global.css"), "utf8");
const speech = readFileSync(resolve(root, "src/js/modules/speech.js"), "utf8");
const mascot = readFileSync(resolve(root, "src/js/modules/mascot.js"), "utf8");

for (const id of [
  "welcomeStage",
  "uploadStage",
  "processingStage",
  "summaryStage",
  "resultsStage",
  "finalStage",
  "presenterPanel",
  "historyList",
  "historyModal",
  "metricsModal",
  "documentModal",
  "documentModalTitle",
  "documentPageImage",
  "documentPageHighlight",
  "recommendationProgressBar",
  "recommendationModal",
]) {
  assert(html.includes(`id="${id}"`), `Missing ${id}`);
}

assert(html.includes("Использовать пример работы"), "Missing sample document button");
assert(html.includes("Цифровой консилиум"), "About page must explain the multi-agent system");
assert(html.includes("От документа до решения"), "About page must show the analysis pipeline");
assert(html.includes("Три модели — три класса задач"), "About page must explain model roles");
assert(html.includes('class="about-agents"'), "About page must include the agent team");
assert(!html.includes("Демонстрационный автономный режим"), "Mock mode banner must stay hidden from the main UI");
assert(app.includes("Ctrl") || app.includes("ctrlKey"), "Missing presenter keyboard shortcut");
assert(app.includes("requestImprovementDirection"), "Improvement direction must use a service");
assert(app.includes("getAnalysisHistory"), "History must load from the backend");
assert(app.includes("data-open-history"), "History items must reopen saved analyses");
assert(app.includes("Предварительная оценка цифрового ментора"), "Missing preliminary mentor score label");
assert(app.includes('`${score}/10`'), "Demo criteria must render X/10");
assert(app.includes('`${normalized.overall_score} / 60`'), "Demo overall score must render XX/60");
assert(app.includes("criterion__details"), "Demo criteria must provide compact details");
assert(app.includes("Подробнее"), "Demo criteria must include the details control");
assert(app.includes("truncateToSentence"), "Report previews must truncate at sentence boundaries");
assert(app.includes("report-list-item__icon"), "Report lists must render a separate icon element");
assert(app.includes("report-list-item__text"), "Report lists must render text separately from the icon");
assert(html.includes("Что требует доработки"), "Report issue heading must stay compact");
const chatSectionIndex = html.indexOf("Диалог с цифровым ментором");
const directionsSectionIndex = html.indexOf("Как вы хотите улучшить работу?");
const inlineHistoryIndex = html.indexOf("История анализов", directionsSectionIndex);
const nextStepSectionIndex = html.indexOf("Один вопрос и следующий шаг");
assert(chatSectionIndex < directionsSectionIndex, "Mentor chat must appear before improvement directions");
assert(directionsSectionIndex < inlineHistoryIndex, "Improvement directions must appear before inline history");
assert(inlineHistoryIndex < nextStepSectionIndex, "One question and next step must appear after inline history");
assert(app.includes("data-detail"), "Recommendation details control must remain available");
assert(html.includes("recommendationProgressBar"), "Recommendation planning progress must remain available");
assert(html.includes('class="recommendation-modal__content"'), "Recommendation modal must separate its scrollable content");
assert(/#resultsStage \.recommendation-grid\s*\{[^}]*overflow:\s*visible/s.test(css), "Recommendation cards must remain fully visible in page flow");
assert(/#recommendationModal \.recommendation-modal__content\s*\{[^}]*overflow-y:\s*auto/s.test(css), "Recommendation modal content must scroll vertically");
assert(/#recommendationModal \.modal-card\s*\{[^}]*max-height:\s*90vh[^}]*display:\s*flex/s.test(css), "Recommendation modal must stay within the viewport");
assert(app.includes('querySelector(".recommendation-modal__content").scrollTop = 0'), "Recommendation modal must open at the beginning of long content");
assert(!/function closeRecommendationModal\(\)[\s\S]*?scrollTo\(/.test(app), "Closing the recommendation modal must preserve page scroll position");
assert(app.includes("requestAnimationFrame"), "Progress must use smooth visual interpolation");
assert(app.includes("visualProgressCeiling"), "Visual progress must have safe stage ceilings");
assert(app.includes("getAnalysisMetrics"), "Metrics modal must use saved backend metrics");
assert(app.includes("data-evidence-index"), "Evidence navigation control is missing");
assert(app.includes('documentModalTitle: document.getElementById("documentModalTitle")'), "Evidence modal title must be registered before opening fragments");
assert(app.includes("Фрагменты исходного документа"), "Source evidence must be visible in the objections section");
assert(app.includes("data-evidence-index"), "PDF evidence buttons must open from the objections section");
assert(app.includes("bindEvidenceButtons"), "Evidence controls must receive direct click handlers");
assert(app.includes("state.evidence.indexOf(item)"), "Evidence buttons must use stable global indexes");
assert(app.includes("Фрагмент не найден. Обновите результаты анализа."), "Broken evidence links must show a visible error");
assert(app.includes("criterion__evidence-button"), "Criterion evidence must use compact controls");
assert(app.includes("evidence.slice(0, 2)"), "Criterion details must limit evidence previews");
assert(app.includes('classList.toggle("is-fragment"'), "DOCX evidence must use the compact fragment modal");
assert(/#documentModal\.is-fragment \.document-viewer\s*\{[^}]*width:\s*min\(560px/s.test(css), "DOCX fragment modal must stay compact");
assert(app.includes("getDocumentPagePreviewUrl"), "PDF evidence must use a rendered source page");
assert(app.includes("item.bbox"), "PDF evidence highlight must use extraction bbox");
assert(app.includes("DIGITAL_MENTOR_RECOMMENDATIONS"), "Recommendation state must persist in localStorage");
assert(app.includes("saveRecommendationState"), "Recommendation changes must be persisted");
assert(app.includes("source_type === \"pdf\""), "PDF-only viewer behavior is missing");
assert(!app.includes("setMentor(voiceWillPlay ? \"speaking\" : \"success\", response.answer"), "Full chat answer must not be copied into mascot bubble");
assert(speech.includes("PrerecordedSpeechService"), "Missing prerecorded speech service");
assert(!speech.includes("RemoteTtsSpeechService"), "Remote TTS must not be used by the frontend");
assert(!speech.includes("BrowserSpeechService"), "Browser text-to-speech must be disabled");
assert(!speech.includes("SpeechSynthesisUtterance"), "Arbitrary browser speech must be disabled");
assert(!app.includes("synthesizeAnalysisSpeech"), "Analysis TTS generation must not run");
assert(!app.includes("remoteText"), "Chat and recommendations must stay silent");
assert(!app.includes("await speakMentor(response.answer"), "Chat answers must not be spoken");
assert(app.includes('cue: "greeting"'), "Greeting cue is missing");
const beginWorkBody = app.slice(app.indexOf("function beginWork"), app.indexOf("function configureSpeechService"));
assert(!beginWorkBody.includes('cue: "greeting"'), "Begin work must not repeat the greeting cue");
assert(app.includes('cue: "uploading"'), "Upload cue is missing");
assert(app.includes('cue: "analysis"'), "Analysis cue is missing");
assert(app.includes('cue: "completed"'), "Completion cue is missing");
assert(app.includes("if (options.silent) return;"), "Mentor speech must support silent UI transitions");
assert(speech.includes("PRERECORDED_SPEECH"), "Missing prerecorded speech mapping");
assert.equal([...speech.matchAll(/\/src\/assets\/audio\/([^"']+\.wav)/g)].length, 4, "Exactly four WAV cues must remain");
for (const audioFile of speech.matchAll(/\/src\/assets\/audio\/([^"']+\.wav)/g)) {
  assert(existsSync(resolve(root, "src/assets/audio", audioFile[1])), `Missing prerecorded audio ${audioFile[1]}`);
}
assert(mascot.includes("fallbackGif"), "Missing mascot GIF fallback");
assert(mascot.includes("is-mascot-placeholder"), "Missing mascot CSS placeholder fallback");
assert(existsSync(resolve(root, "../demo/sample-document.pdf")), "Missing sample PDF");
assert(existsSync(resolve(root, "../demo/sample-document.docx")), "Missing sample DOCX");

console.log("frontend smoke checks passed");
