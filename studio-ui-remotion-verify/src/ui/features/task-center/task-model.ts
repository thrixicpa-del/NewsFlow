export type TaskState = "QUEUED" | "PREPARING" | "RUNNING" | "WAITING" | "PAUSED" | "RETRYING" | "READY" | "FAILED" | "CANCELLED";
export type TaskSource = "scenario" | "cover" | "voice" | "montage" | "publication";

export type TaskCenterEntry = {
  id: string;
  source: TaskSource;
  title: string;
  status: TaskState;
  detail: string;
  progress?: number;
};

const stateFromBackend = (value: unknown): TaskState => {
  const raw = String(value || "").trim().toUpperCase();
  if (/(RETRY|ПОВТОР)/.test(raw)) return "RETRYING";
  if (/(CANCEL|ОСТАНОВ)/.test(raw)) return "CANCELLED";
  if (/(PAUSE|ПАУЗ|НУЖНО ДЕЙСТВИЕ|ACTION_REQUIRED)/.test(raw)) return "PAUSED";
  if (/(FAIL|ERROR|ОШИБ|AUTH_REQUIRED|QUOTA_BLOCKED|USER_ACTION_REQUIRED)/.test(raw)) return "FAILED";
  if (/(READY|ГОТОВ|SUCCESS|SUCCEEDED|PUBLISH)/.test(raw)) return "READY";
  if (/(WAIT(?:ING)?(?:_FOR_PROVIDER)?|ОЖИДАНИЕ.*ПРОВАЙДЕР)/.test(raw)) return "WAITING";
  if (/(PREPAR|ПОДГОТОВ|ПЛАНИР)/.test(raw)) return "PREPARING";
  if (/(RUNNING|ACTIVE|В ОБРАБОТКЕ|ГЕНЕР|ПЛАНИР|РЕНДЕР|СИНТЕЗ|ЗАГРУЗ|PROCESSING|ПОДБОР)/.test(raw)) return "RUNNING";
  return "QUEUED";
};

const voiceTaskState = (item: NewsFlowSnapshot["voiceItems"][number]): TaskState => {
  // item.state belongs to the source script, not the voice worker.
  if (item.voiceError) return "FAILED";
  const state = stateFromBackend(item.jobState || item.voiceStatus || (item.path ? "READY" : "QUEUED"));
  if (item.jobState) return state;
  const label = String(item.voiceStatus || "").trim().toUpperCase();
  const providerLabel = label.replace(/^(?:API|LUMEAN|VOICEGEN|WPROJECT):\s*/, "");
  // These provider messages still describe pending work; "готовый MP3"
  // describes the awaited file, including when an older output exists.
  if (/^ОЖИДАЕМ (?:ГОТОВЫЙ MP3|КНОПКУ СКАЧИВАНИЯ В ИСТОРИИ)$/.test(providerLabel)) return "WAITING";
  if (/^СКАЧИВАЕМ (?:ГОТОВЫЙ )?MP3$/.test(providerLabel)) return "RUNNING";
  if (/(?:^|:\s*)ГОТОВИМ(?:\s|$)/.test(label)) return "PREPARING";
  if (state === "QUEUED" && /ВЫПОЛНЯ|СОЗДА[ЁЕ]Т|ОТПРАВЛЯ|СОХРАНЯ/.test(label)) return "RUNNING";
  return state;
};

export function buildTaskCenterEntries(data: NewsFlowSnapshot): TaskCenterEntry[] {
  const scenarios = data.scenarios.map((item) => ({
    id: `scenario-${item.index}`,
    source: "scenario" as const,
    title: item.title,
    status: stateFromBackend(item.state),
    detail: item.error || (item.lengthStatus ? `Длина: ${item.lengthStatus}` : item.state),
  }));
  const covers = data.covers.map((item, index) => ({
    id: `cover-${item.scenario_index ?? index}`,
    source: "cover" as const,
    title: item.title,
    status: stateFromBackend(item.status),
    detail: item.error || item.status || "Ожидает генерации",
    progress: item.progress,
  }));
  const voice = data.voiceItems.map((item) => ({
    id: `voice-${item.productionItemId || item.index}`,
    source: "voice" as const,
    title: item.title,
    status: voiceTaskState(item),
    detail: item.voiceError || item.voiceStatus || item.jobState || "Ожидает озвучки",
    progress: item.voiceProgress,
  }));
  const montage = data.montageTasks.map((item) => ({
    id: `montage-${item.scenarioIndex ?? item.index}`,
    source: "montage" as const,
    title: item.title,
    status: stateFromBackend(item.status),
    detail: item.error || item.detail || item.phase || item.status || "Ожидает монтажа",
    progress: item.progress,
  }));
  const publication = (data.publication.v2?.queue || []).map((item) => ({
    id: `publication-${item.snapshotId}`,
    source: "publication" as const,
    title: item.title || item.productionItemId,
    status: stateFromBackend(item.status),
    detail: item.currentStage || item.status,
    progress: item.completion.total ? Math.round((item.completion.completed / item.completion.total) * 100) : undefined,
  }));
  return [...scenarios, ...covers, ...voice, ...montage, ...publication];
}
