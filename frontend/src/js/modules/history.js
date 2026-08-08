const HISTORY_KEY = "DIGITAL_MENTOR_HISTORY";
const LIMIT = 5;


export function getHistory() {
  try {
    return JSON.parse(window.localStorage.getItem(HISTORY_KEY) || "[]").slice(0, LIMIT);
  } catch {
    return [];
  }
}


export function addHistoryItem(item) {
  const next = [
    {
      analysis_id: item.analysis_id,
      document_name: item.document_name,
      created_at: new Date().toISOString(),
      overall_score: item.overall_score,
      status: item.status || "completed",
    },
    ...getHistory().filter((entry) => entry.analysis_id !== item.analysis_id),
  ].slice(0, LIMIT);
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  return next;
}


export function removeHistoryItem(analysisId) {
  const next = getHistory().filter((entry) => entry.analysis_id !== analysisId);
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  return next;
}
