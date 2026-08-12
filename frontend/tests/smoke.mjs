import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import assert from "node:assert/strict";

const root = resolve(import.meta.dirname, "..");
const html = readFileSync(resolve(root, "index.html"), "utf8");
const app = readFileSync(resolve(root, "src/js/app.js"), "utf8");
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
  "recommendationModal",
]) {
  assert(html.includes(`id="${id}"`), `Missing ${id}`);
}

assert(html.includes("Использовать пример работы"), "Missing sample document button");
assert(!html.includes("Демонстрационный автономный режим"), "Mock mode banner must stay hidden from the main UI");
assert(app.includes("Ctrl") || app.includes("ctrlKey"), "Missing presenter keyboard shortcut");
assert(app.includes("requestImprovementDirection"), "Improvement direction must use a service");
assert(app.includes("addHistoryItem"), "Missing local history save");
assert(speech.includes("RemoteTtsSpeechService"), "Missing remote TTS service");
assert(speech.includes("BrowserSpeechService"), "Missing browser TTS fallback");
assert(speech.includes("DisabledSpeechService"), "Missing disabled speech service");
assert(app.includes('response.answer, { remoteText: true }'), "Mentor chat must request remote TTS");
assert(app.includes("speechService.hasPrerecorded?.(message)"), "Remote TTS must allow prerecorded standard phrases");
assert(speech.includes("PRERECORDED_SPEECH"), "Missing prerecorded speech mapping");
assert(speech.includes("/src/assets/audio/greeting.mp3"), "Missing prerecorded greeting mapping");
for (const audioFile of speech.matchAll(/\/src\/assets\/audio\/([^"']+\.mp3)/g)) {
  assert(existsSync(resolve(root, "src/assets/audio", audioFile[1])), `Missing prerecorded audio ${audioFile[1]}`);
}
assert(mascot.includes("fallbackGif"), "Missing mascot GIF fallback");
assert(mascot.includes("is-mascot-placeholder"), "Missing mascot CSS placeholder fallback");
assert(existsSync(resolve(root, "../demo/sample-document.pdf")), "Missing sample PDF");
assert(existsSync(resolve(root, "../demo/sample-document.docx")), "Missing sample DOCX");

console.log("frontend smoke checks passed");
