function errorDetail(error: unknown): string {
  return error instanceof Error ? error.message.trim() : "";
}

/**
 * Explain a failed startup snapshot without surfacing arbitrary Core stderr,
 * which could contain local paths or provider diagnostics.
 */
export function coreAvailabilityNotice(error: unknown): string {
  const detail = errorDetail(error);
  if (/maxbuffer/i.test(detail)) {
    return "Не удалось получить снимок: объём снимка проекта превысил лимит старой сборки. "
      + "Данные проекта не удалены. Установите обновлённую TEST-сборку и перезапустите NewsFlow.";
  }
  if (/не найдено актуальное ядро|ядро newsflow не найдено|ENOENT/i.test(detail)) {
    return "Ядро NewsFlow не найдено в этой сборке. Данные проекта не удалены; "
      + "переустановите или откройте целую TEST-сборку NewsFlow.";
  }
  if (/не удалось запустить ядро|не смог запустить ядро|нет доступа|EACCES|permission denied/i.test(detail)) {
    return "Ядро NewsFlow не удалось запустить. Данные проекта не удалены. "
      + "Закройте другие экземпляры NewsFlow и проверьте, что TEST-сборка распакована полностью и не заблокирована системой.";
  }
  return "Ядро NewsFlow временно недоступно: не удалось получить снимок проекта. "
    + "Данные проекта не удалены. Закройте NewsFlow, убедитесь, что предыдущий экземпляр завершён, и откройте TEST-сборку снова.";
}
