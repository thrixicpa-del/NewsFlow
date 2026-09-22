export type VisualFixtureName = "task-states" | "covers-84" | "voice-84" | "montage-84" | "publication-84" | "publication-receipt" | "analytics-oauth-waiting" | "metadata-ready";

export function buildVisualFixture(
  base: NewsFlowSnapshot,
  fixtureName: string | null,
): NewsFlowSnapshot | null {
  if (!(["task-states", "covers-84", "voice-84", "montage-84", "publication-84", "publication-receipt", "analytics-oauth-waiting", "metadata-ready"] as const).includes(fixtureName as VisualFixtureName)) return null;

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
  if (fixtureName === "publication-84") {
    fixture.channels = Array.from({ length: 8 }, (_, index) => ({
      id: `visual-channel-${index + 1}`,
      channel: `visual-channel-${index + 1}`,
      name: `Канал ${index + 1}`,
      subscribers: String(12500 + index * 1750),
      status: index === 7 ? "Требует OAuth" : "Подключён",
      oauthConnected: index !== 7,
      monetaryAccess: index < 4,
      viewsHour: "—",
      views48h: "—",
    }));

    const channelRules = Object.fromEntries(fixture.channels.map((channel, index) => {
      const channelId = String(channel.id);
      return [channelId, {
        channelId,
        enabled: true,
        quota: index < 4 ? 12 : 10,
        monetized: index < 4,
        distributionStrategy: index < 4 ? "longest_monetized" : "balanced",
        privacy: "private",
        publishMode: "schedule",
        timezone: "Europe/Minsk",
        firstPublishAt: "2026-11-15T04:00:00+03:00",
        intervalMinutes: index % 2 === 0 ? 15 : 30,
        allowedWeekdays: [0, 1, 2, 3, 4, 5, 6],
        publishWindowStart: "04:00",
        publishWindowEnd: "10:00",
        dailyCap: 16,
        minDurationSeconds: 0,
        maxDurationSeconds: 0,
        orderStart: 0,
        orderEnd: 0,
        automation: { upload: true, metadata: true, thumbnail: true, ads: true, post: true, cards: true, endScreen: true },
      }];
    }));

    const items: Record<string, any> = {};
    const assignments: Record<string, any> = {};
    const queue: any[] = [];
    for (let index = 0; index < 84; index += 1) {
      const number = index + 1;
      const productionItemId = `visual-publication-${String(number).padStart(3, "0")}`;
      const channelIndex = index % fixture.channels.length;
      const channelId = `visual-channel-${channelIndex + 1}`;
      const cycle = Math.floor(index / fixture.channels.length);
      const minuteOfDay = 4 * 60 + cycle * 15;
      const clock = `${String(Math.floor(minuteOfDay / 60)).padStart(2, "0")}:${String(minuteOfDay % 60).padStart(2, "0")}`;
      const publishAt = `2026-11-15T${clock}:00+03:00`;
      const durationSeconds = index % 3 === 0 ? 620 : index % 3 === 1 ? 455 : 780;
      const monetized = channelIndex < 4;
      const uploaded = index < 48;
      const failedAds = index === 13;
      const adsMode = monetized ? (durationSeconds >= 480 ? "AUTO+MANUAL_39S" : "AUTO_ONLY") : "NONE";
      const adsStatus = failedAds ? "FAILED" : monetized && uploaded ? "SUCCESS" : monetized ? "PENDING" : "NOT_REQUIRED";
      const overallStatus = failedAds ? "PARTIAL" : index < 24 ? "DONE" : uploaded ? "FORMATTING" : "WAITING";
      const currentStage = failedAds ? "ADS" : index < 24 ? "DONE" : uploaded ? "ADS" : "VIDEO_UPLOAD";
      const title = `Визуальный ролик ${String(number).padStart(2, "0")} — массовая публикация`;

      items[productionItemId] = {
        productionItemId,
        metadata: {
          index: number,
          title,
          seoTitle: `SEO: ${title}`,
          description: `Тестовое описание ролика ${number}.`,
          tags: ["newsflow", "visual", `video-${number}`],
          hashtags: ["#NewsFlow", "#Visual"],
          seoStatus: "Готово",
          tagsStatus: "Готово",
        },
        artifacts: {
          video: { path: `C:/visual-fixture/video-${number}.mp4`, exists: true, durationSeconds },
          thumbnail: { path: `C:/visual-fixture/cover-${number}.png`, exists: true },
        },
        durationSeconds,
        readiness: { state: "PUBLICATION_READY", videoReady: true, contentReady: true, publicationReady: true, reasons: [] },
      };
      assignments[productionItemId] = {
        productionItemId, channelId, publishAt, source: "auto", locked: false,
      };
      queue.push({
        snapshotId: `visual-snapshot-${number}`,
        productionItemId,
        title,
        channelId,
        publishAt,
        privacy: "private",
        publishMode: "schedule",
        youtubeVideoId: uploaded ? `visual-yt-${number}` : undefined,
        youtubeVideoUrl: uploaded ? `https://youtube.example/watch?v=visual-yt-${number}` : undefined,
        currentStage,
        status: overallStatus,
        active: index === 31,
        ads: { status: adsStatus, mode: adsStatus === "SUCCESS" || adsStatus === "NOT_REQUIRED" ? adsMode : "" },
        completion: { completed: index < 24 ? 12 : uploaded ? 7 : 0, total: 12 },
        steps: {
          AUTH_CHECK: { status: uploaded ? "SUCCESS" : "PENDING" },
          VIDEO_UPLOAD: { status: uploaded ? "SUCCESS" : "PENDING" },
          YOUTUBE_PROCESSING: { status: uploaded ? "SUCCESS" : "PENDING" },
          TITLE: { status: uploaded ? "SUCCESS" : "PENDING" },
          DESCRIPTION: { status: uploaded ? "SUCCESS" : "PENDING" },
          TAGS: { status: uploaded ? "SUCCESS" : "PENDING" },
          THUMBNAIL: { status: index < 30 ? "SUCCESS" : uploaded ? "PENDING" : "PENDING" },
          ADS: {
            status: adsStatus,
            providerResult: { mode: adsMode, automaticSlotsEnabled: monetized, manualSlotsSeconds: adsMode === "AUTO+MANUAL_39S" ? [39, 78, 117] : [] },
            error: failedAds ? { category: "RETRYABLE", message: "Тестовая ошибка Studio" } : undefined,
          },
          POST: { status: index < 24 ? "SUCCESS" : "PENDING" },
          CARDS: { status: index < 24 ? "SUCCESS" : "PENDING" },
          END_SCREEN: { status: index < 24 ? "SUCCESS" : "PENDING" },
          SCHEDULE: { status: index < 24 ? "SUCCESS" : "PENDING" },
        },
        timeline: [],
      });
    }

    fixture.publication.v2 = {
      items,
      counters: { total: 84, PUBLICATION_READY: 84, DONE: 24, FORMATTING: 23, PARTIAL: 1, WAITING: 36 },
      paused: false,
      uploadConcurrency: 6,
      channelRules,
      assignments,
      rulePresets: [],
      queue,
      receipts: {},
    };
    fixture.counts = { ...fixture.counts, scripts: 84, voice: 84, montage: 84 };
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
