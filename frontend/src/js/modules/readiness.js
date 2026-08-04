import { getPublicConfig } from "../api.js";


export async function checkReadiness({ mascotImage }) {
  const checks = [];
  checks.push({ component: "Интерфейс", status: "Готов", comment: "Страница загружена" });

  try {
    const ready = await fetch("/health/ready");
    checks.push({
      component: "Сервис анализа",
      status: ready.ok ? "Готов" : "Требует внимания",
      comment: ready.ok ? "Сервис анализа доступен" : "Проверка готовности не прошла",
    });
  } catch {
    checks.push({ component: "Сервис анализа", status: "Недоступен", comment: "Не удалось выполнить проверку" });
  }

  try {
    const demo = await fetch("/demo/sample-document.pdf", { method: "HEAD" });
    checks.push({
      component: "Пример работы",
      status: demo.ok ? "Готов" : "Недоступен",
      comment: demo.ok ? "Файл доступен" : "Файл не найден",
    });
  } catch {
    checks.push({ component: "Пример работы", status: "Недоступен", comment: "Не удалось проверить файл" });
  }

  try {
    const config = await getPublicConfig();
    checks.push({ component: "Голос", status: "Готов", comment: config.tts_mode || "browser" });
  } catch {
    checks.push({ component: "Голос", status: "Резерв", comment: "Будет использован голос браузера" });
  }

  checks.push({
    component: "Маскот",
    status: mascotImage?.complete ? "Готов" : "Проверяется",
    comment: mascotImage?.currentSrc || mascotImage?.src || "Используется резервное изображение",
  });
  checks.push({ component: "PDF-отчет", status: "Готов", comment: "Формируется после завершения анализа" });

  return checks;
}
