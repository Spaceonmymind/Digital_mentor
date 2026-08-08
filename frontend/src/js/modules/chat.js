import { sendChatMessage } from "../api.js";
import { FRONTEND_MOCK_MODE } from "../config.js";
import { getMentorAnswer } from "../../mocks/mentorChat.js";


export async function askMentorApi(analysisId, question) {
  if (FRONTEND_MOCK_MODE || !analysisId) {
    return { answer: getMentorAnswer(question), message_id: "frontend-mock-message" };
  }

  return sendChatMessage({ analysis_id: analysisId, message: question });
}
