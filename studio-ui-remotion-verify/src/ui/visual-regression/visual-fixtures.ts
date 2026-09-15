export type VisualFixtureName = "task-states" | "covers-84" | "voice-84" | "montage-84" | "publication-receipt" | "analytics-oauth-waiting" | "metadata-ready";

export function buildVisualFixture(
  base: NewsFlowSnapshot,
  fixtureName: string | null,
): NewsFlowSnapshot | null {
  if (!(["task-states", "covers-84", "voice-84", "montage-84", "publication-receipt", "analytics-oauth-waiting", "metadata-ready"] as const).includes(fixtureName as VisualFixtureName)) return null;

  const fixture = structuredClone(base);
  if (fixtureName === "analytics-oauth-waiting") {
    fixture.analyticsOAuth = { configured: true, mode: "cloudflare", serviceUrl: "https://visual-fixture.invalid/oauth", fileName: "visual-fixture-only" };
    fixture.channels = [{
      id: "visual-channel-1",
      name: "Визуальный канал OAuth",
      channel: "visual-channel",
      subscribers: "1 000",
      status: "Требует OAuth",
      oauthConnected: false,
      monetaryAccess: false,
      viewsHour: "—",
      views48h: "—",
    }];
    return fixture;
  }
  if (fixtureName === "publication-receipt") {
    fixture.publication.v2 = {
      items: {},
      counters: {},
      paused: false,
      uploadConcurrency: 1,
      channelRules: {},
      assignments: {},
      queue: [],
      receipts: {
        "visual-receipt-1": {
          productionItemId: "visual-production-1",
          title: "Визуальный receipt публикации",
          channelId: "visual-channel-1",
          requestedPublishAt: "2026-09-15T12:00:00Z",
          confirmedPublishAt: "2026-09-15T12:02:00Z",
          finalStatus: "DONE",
          totalDuration: "01:00",
          stages: { VIDEO_UPLOAD: "SUCCESS", TITLE: "SUCCESS", SCHEDULE: "SUCCESS" },
        },
      },
    };
    return fixture;
  }
  if (fixtureName === "metadata-ready") {
    fixture.seo = [{
      source_title: "Визуальная тема для metadata desk",
      script: "Изолированный текст сценария для визуальной проверки готового metadata-пакета.",
      status: "Готово",
      title: "Готовый SEO-пакет",
      description: "Готовое SEO-описание без вызова провайдера.",
      hashtags: ["#NewsFlow", "#Studio"],
      tags: ["newsflow", "production studio", "visual fixture"],
      tags_status: "Готово",
    }];
    return fixture;
  }
  if (fixtureName === "covers-84") {
    fixture.covers = Array.from({ length: 84 }, (_, index) => {
      const status = index < 64 ? "READY" : index < 72 ? "MISSING" : index < 78 ? "FAILED" : index < 82 ? "GENERATING" : "QUEUED";
      return {
        production_item_id: `visual-cover-${index + 1}`,
        scenario_index: index + 1,
        title: `Визуальная проверка обложки ${String(index + 1).padStart(2, "0")}`,
        status,
        progress: status === "READY" ? 100 : status === "GENERATING" ? 45 : 0,
        error: status === "FAILED" ? "Тестовая ошибка провайдера" : "",
      };
    });
    fixture.coverCounts = { total: 84, ready: 64, missing: 8, failed: 6, generating: 4, queued: 2 };
    fixture.counts = { ...fixture.counts, ideas: 84 };
    return fixture;
  }
  if (fixtureName === "voice-84" || fixtureName === "montage-84") {
    fixture.scenarios = Array.from({ length: 84 }, (_, index) => ({
      index,
      title: `Визуальная проверка сценария ${String(index + 1).padStart(2, "0")}`,
      state: "Готово",
      result: "Тестовый сценарий для изолированной визуальной проверки.",
      error: "",
    }));
    fixture.voiceItems = fixture.scenarios.map((scenario, index) => ({
      index: scenario.index,
      title: scenario.title,
      state: index < 64 ? "Готово" : "Ожидает",
      path: fixtureName === "montage-84" || index < 64 ? `C:/visual-fixture/voice-${index + 1}.mp3` : "",
      productionItemId: `visual-production-${index + 1}`,
      voiceProvider: "wproject",
      voiceName: "Новости",
      jobState: index < 64 ? "DONE" : "QUEUED",
      voiceStatus: index < 64 ? "Готово" : "В очереди",
      voiceProgress: index < 64 ? 100 : 0,
    }));
    if (fixtureName === "voice-84") {
      fixture.counts = { ...fixture.counts, scripts: 84, voice: 64 };
      return fixture;
    }
    fixture.montageTasks = fixture.scenarios.map((scenario, index) => ({
      index: scenario.index,
      title: scenario.title,
      status: index < 64 ? "Готово" : index < 72 ? "Рендер" : "В очереди",
      phase: index < 64 ? "Экспорт завершён" : index < 72 ? "Рендер" : "Ожидание",
      progress: index < 64 ? 100 : index < 72 ? 45 : 0,
      voicePath: `C:/visual-fixture/voice-${index + 1}.mp3`,
      outputPath: index < 64 ? `C:/visual-fixture/video-${index + 1}.mp4` : "",
      projectPath: `C:/visual-fixture/project-${index + 1}.newsflow`,
    }));
    fixture.counts = { ...fixture.counts, scripts: 84, voice: 84, montage: 64 };
    return fixture;
  }
  fixture.scenarios = [
    { index: 1, title: "Сценарий в работе", state: "RUNNING", result: "", error: "" },
  ];
  fixture.covers = [
    { scenario_index: 1, title: "Обложка требует внимания", status: "FAILED", progress: 42, error: "Сервис временно недоступен" },
  ];
  fixture.voiceItems = [
    { index: 1, title: "Озвучка ожидает провайдера", state: "", path: "", jobState: "WAITING_FOR_PROVIDER", voiceStatus: "Ожидание провайдера", voiceProgress: 60 },
  ];
  fixture.montageTasks = [
    { index: 1, title: "Монтаж готов", status: "READY", phase: "Экспорт завершён", progress: 100, outputPath: "C:/visual-fixture/output.mp4" },
  ];
  fixture.publication.v2 = {
    items: {},
    counters: {},
    paused: false,
    uploadConcurrency: 1,
    channelRules: {},
    assignments: {},
    queue: [
      {
        snapshotId: "visual-publication-1",
        productionItemId: "visual-production-1",
        title: "Публикация ожидает подтверждения",
        channelId: "visual-channel-1",
        privacy: "private",
        publishMode: "manual",
        currentStage: "Ожидание оператора",
        status: "PAUSED",
        active: true,
        completion: { completed: 2, total: 4 },
        steps: {},
      },
    ],
  };
  fixture.counts = { ideas: 0, scripts: 1, voice: 1, montage: 1 };
  return fixture;
}
