import { getPublicConfig } from "../api.js";


export async function checkReadiness({ mascotImage }) {
  const checks = [];
  checks.push({ component: "Frontend", status: "Готов", comment: "Интерфейс загружен" });

  try {
    const ready = await fetch("/health/ready");
    checks.push({
      component: "Backend и БД",
      status: ready.ok ? "Готов" : "Требует внимания",
      comment: ready.ok ? "Сервис анализа доступен" : "Проверка готовности не прошла",
    });
  } catch {
    checks.push({ component: "Backend и БД", status: "Недоступен", comment: "Не удалось получить readiness" });
  }

  try {
    const demo = await fetch("/demo/sample-document.pdf", { method: "HEAD" });
    checks.push({
      component: "Demo-документ",
      status: demo.ok ? "Готов" : "Недоступен",
      comment: demo.ok ? "Файл доступен" : "Файл не найден",
    });
  } catch {
    checks.push({ component: "Demo-документ", status: "Недоступен", comment: "Не удалось проверить файл" });
  }

  try {
    const config = await getPublicConfig();
    checks.push({ component: "TTS-режим", status: "Определен", comment: config.tts_mode || "browser" });
  } catch {
    checks.push({ component: "TTS-режим", status: "Fallback", comment: "Будет использован голос браузера" });
  }

  checks.push({
    component: "Маскот",
    status: mascotImage?.complete ? "Готов" : "Проверяется",
    comment: mascotImage?.currentSrc || mascotImage?.src || "Используется fallback",
  });
  checks.push({ component: "PDF-отчет", status: "Готов", comment: "Формируется после завершения анализа" });

  return checks;
}
