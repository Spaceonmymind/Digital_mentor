import { createAnalysis, getAnalysis, getAnalysisResult } from "../api.js";
import { FRONTEND_MOCK_MODE } from "../config.js";
import { analysisSteps, mockMentorAnalysis } from "../../mocks/mentorAnalysis.js";


const POLL_INTERVAL = 1400;


export async function runAnalysis(documentId, onProgress) {
  if (FRONTEND_MOCK_MODE) {
    return mockMentorAnalysis((index) => {
      const step = analysisSteps[index];
      onProgress({
        status: "processing",
        progress: Math.round(((index + 1) / analysisSteps.length) * 100),
        current_step: step?.title,
        message: step?.message,
        frontendStepIndex: index,
      });
    });
  }

  const created = await createAnalysis({
    document_id: documentId,
    analysis_type: "mentor",
    methodology_id: "mentor-default",
    methodology_version: "draft",
  });

  let status = await getAnalysis(created.analysis_id);
  onProgress(status);

  while (!["completed", "failed", "cancelled"].includes(status.status)) {
    await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL));
    status = await getAnalysis(created.analysis_id);
    onProgress(status);
  }

  if (status.status === "failed") {
    throw new Error(status.error_message || "Анализ завершился с ошибкой");
  }
  if (status.status === "cancelled") {
    throw new Error("Анализ отменен");
  }

  return getAnalysisResult(created.analysis_id);
}
