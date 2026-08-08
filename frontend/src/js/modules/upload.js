import { uploadDocument as uploadDocumentRequest } from "../api.js";
import { FRONTEND_MOCK_MODE } from "../config.js";


export async function uploadDocument(file) {
  if (FRONTEND_MOCK_MODE) {
    return {
      id: "frontend-mock-document",
      name: file.name,
      mime_type: file.type || "application/octet-stream",
      size: file.size,
      status: "uploaded",
      created_at: new Date().toISOString(),
    };
  }

  return uploadDocumentRequest(file);
}
