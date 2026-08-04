import { askMentorApi } from "./chat.js";
import { getMentorAnswer } from "../../mocks/mentorChat.js";


export async function requestImprovementDirection({ analysisId, label, fallbackText }) {
  if (!analysisId) {
    return fallbackText;
  }
  try {
    const response = await askMentorApi(analysisId, label);
    return response.answer;
  } catch {
    return getMentorAnswer(label) || fallbackText;
  }
}
