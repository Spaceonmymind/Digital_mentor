import { getDocument, uploadDocument as uploadDocumentRequest } from "../api.js";
import { FRONTEND_MOCK_MODE } from "../config.js";


export async function uploadDocument(file, onStatus = () => {}) {
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

  let document = await uploadDocumentRequest(file);
  onStatus(document.extraction_status || "pending");
  const deadline = Date.now() + 120000;
  while (document.extraction_status === "pending") {
    if (Date.now() >= deadline) throw new Error("Обработка документа заняла слишком много времени. Попробуйте файл меньшего размера.");
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    document = await getDocument(document.id);
    onStatus(document.extraction_status || "pending");
  }
  if (document.extraction_status === "failed") throw new Error("Не удалось извлечь текст документа.");
  return document;
}
