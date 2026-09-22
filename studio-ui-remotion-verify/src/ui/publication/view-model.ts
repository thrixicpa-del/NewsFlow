import type { ChannelRow, ChannelRule, PublicationStatus, PublicationViewModel, QueueRow, ReceiptRow, VideoRow } from "./types";

const record = (value: unknown): Record<string, any> => value && typeof value === "object" ? value as Record<string, any> : {};
const text = (value: unknown) => String(value || "").trim();
const titleKey = (value: string) => value.trim().toLocaleLowerCase("ru-RU");
const channelId = (channel: NewsFlowSnapshot["channels"][number], index: number) => text(channel.id || channel.channel || channel.name || `channel-${index}`);

export function defaultRule(id: string, saved: Record<string, any> = {}): ChannelRule {
  const rawAutomation = record(saved.automation);
  return {
    channelId: id,
    enabled: saved.enabled !== false,
    quota: Math.max(0, Number(saved.quota) || 0),
    monetized: Boolean(saved.monetized),
    distributionStrategy: saved.distributionStrategy === "longest_monetized" ? "longest_monetized" : "balanced",
    privacy: ["private", "unlisted", "public"].includes(text(saved.privacy)) ? text(saved.privacy) as ChannelRule["privacy"] : "private",
    publishMode: saved.publishMode === "schedule" ? "schedule" : "publish_now",
    timezone: text(saved.timezone) || "Europe/Minsk",
    firstPublishAt: text(saved.firstPublishAt),
    intervalMinutes: Math.max(15, Math.round((Number(saved.intervalMinutes) || 180) / 15) * 15),
    allowedWeekdays: Array.isArray(saved.allowedWeekdays) ? saved.allowedWeekdays.map(Number).filter((day) => day >= 0 && day <= 6) : [0, 1, 2, 3, 4, 5, 6],
    publishWindowStart: text(saved.publishWindowStart),
    publishWindowEnd: text(saved.publishWindowEnd),
    dailyCap: Math.max(0, Number(saved.dailyCap) || 0),
    minDurationSeconds: Math.max(0, Number(saved.minDurationSeconds) || 0),
    maxDurationSeconds: Math.max(0, Number(saved.maxDurationSeconds) || 0),
    orderStart: Math.max(0, Number(saved.orderStart) || 0),
    orderEnd: Math.max(0, Number(saved.orderEnd) || 0),
    channelPriority: Number(saved.channelPriority) || 0,
    maxVideosPerHour: Math.max(0, Number(saved.maxVideosPerHour) || 0),
    topicCooldownMinutes: Math.max(0, Number(saved.topicCooldownMinutes) || 0),
    includeKeywords: Array.isArray(saved.includeKeywords) ? saved.includeKeywords.map(text).filter(Boolean) : [],
    excludeKeywords: Array.isArray(saved.excludeKeywords) ? saved.excludeKeywords.map(text).filter(Boolean) : [],
    automation: {
      upload: rawAutomation.upload !== false,
      metadata: rawAutomation.metadata !== false,
      thumbnail: rawAutomation.thumbnail !== false,
      ads: rawAutomation.ads !== false,
      post: rawAutomation.post !== false,
      cards: rawAutomation.cards !== false,
      endScreen: rawAutomation.endScreen !== false,
    },
  };
}

function statusFor(row: { mp4Ready: boolean; channelId: string; queue?: QueueRow; readiness: string }): PublicationStatus {
  if (!row.mp4Ready) return "Требует внимания";
  const status = text(row.queue?.status).toUpperCase();
  if (["FAILED", "AUTH_REQUIRED", "QUOTA_BLOCKED", "USER_ACTION_REQUIRED", "PARTIAL"].includes(status)) return "Требует внимания";
  if (status === "UPLOADING") return "Загружается";
  if (["YOUTUBE_PROCESSING", "PROCESSING"].includes(status)) return "Оформляется";
  if (["DONE", "SCHEDULED"].includes(status)) return status === "DONE" ? "Готово" : "Запланирован";
  if (!row.channelId) return "Требует канала";
  return row.queue ? "Назначен" : "Готов";
}

export function buildPublicationView(data: NewsFlowSnapshot): PublicationViewModel {
  const rawV2 = record(data.publication.v2);
  const rawItems = record(rawV2.items);
  const queue = (Array.isArray(rawV2.queue) ? rawV2.queue : []).map((item) => ({
    ...record(item),
    ads: record(record(item).ads),
    completion: record(record(item).completion),
    steps: record(record(item).steps),
    timeline: Array.isArray(record(item).timeline) ? record(item).timeline : [],
  })) as QueueRow[];
  const queueByProduction = new Map(queue.map((item) => [item.productionItemId, item]));
  const assignments = record(rawV2.assignments);
  const channels = data.channels.map((channel, index) => ({ channel, id: channelId(channel, index) }));
  const rules = record(rawV2.channelRules);
  const names = new Map(channels.map(({ channel, id }) => [id, channel.name || channel.channel || id]));

  const coverByProduction = new Map(
    (data.covers || [])
      .filter((cover) => text((cover as any).production_item_id || (cover as any).productionItemId))
      .map((cover) => [text((cover as any).production_item_id || (cover as any).productionItemId), cover]),
  );
  const seoByProduction = new Map(
    (data.seo || [])
      .filter((item) => text((item as any).production_item_id || (item as any).productionItemId))
      .map((item) => [text((item as any).production_item_id || (item as any).productionItemId), item]),
  );
  const voiceByProduction = new Map(
    (data.voiceItems || [])
      .filter((voice) => text((voice as any).productionItemId || (voice as any).production_item_id))
      .map((voice) => [text((voice as any).productionItemId || (voice as any).production_item_id), voice]),
  );

  const legacyCoverByTitle = new Set(
    (data.covers || [])
      .filter((cover) => ["Готово", "Готово с текстом"].includes(text(cover.status)) && Boolean(cover.selected_path || cover.path || cover.paths?.length))
      .map((cover) => titleKey(text(cover.title))),
  );
  const legacySeoByTitle = new Map((data.seo || []).map((item) => [titleKey(text(item.source_title)), item]));
  const legacyVoiceByTitle = new Set(
    (data.voiceItems || []).filter((voice) => Boolean(voice.path)).map((voice) => titleKey(text(voice.title))),
  );

  const videoRows: VideoRow[] = Object.entries(rawItems).map(([id, raw], index) => {
    const item = record(raw);
    const metadata = record(item.metadata);
    const artifacts = record(item.artifacts);
    const video = record(artifacts.video);
    const thumbnail = record(artifacts.thumbnail);
    const audio = record(artifacts.audio);
    const readiness = record(item.readiness);
    const title = text(metadata.title) || id;
    const assignment = record(assignments[id]);
    const execution = queueByProduction.get(id);
    const assignedChannel = text(execution?.channelId || assignment.channelId);
    const isLegacy = id.startsWith("legacy-") || id.startsWith("legacy-montage:");

    const currentSeo = record(seoByProduction.get(id));
    const legacySeo = isLegacy ? record(legacySeoByTitle.get(titleKey(title))) : {};
    const seo = Object.keys(currentSeo).length ? currentSeo : legacySeo;
    const currentCover = record(coverByProduction.get(id));
    const currentVoice = record(voiceByProduction.get(id));

    const mp4Ready = Boolean(readiness.videoReady ?? video.exists ?? video.path);
    const coverReady = Boolean(
      thumbnail.exists
      || (text(thumbnail.path) && thumbnail.exists !== false)
      || currentCover.selected_path
      || currentCover.path
      || (Array.isArray(currentCover.paths) && currentCover.paths.length)
      || (isLegacy && legacyCoverByTitle.has(titleKey(title)))
    );
    const seoReady = Boolean(
      readiness.contentReady
      || text(metadata.seoStatus) === "Готово"
      || text(seo.status) === "Готово"
      || metadata.description
      || seo.description
    );
    const mp3Ready = Boolean(
      audio.exists
      || audio.path
      || currentVoice.path
      || (isLegacy && legacyVoiceByTitle.has(titleKey(title)))
    );
    const metadataReady = Boolean(
      metadata.title
      && (metadata.description || seo.description)
      && ((Array.isArray(metadata.tags) && metadata.tags.length) || (Array.isArray(seo.tags) && seo.tags.length))
    );
    const row = {
      id,
      number: Number(metadata.index) || index + 1,
      title,
      duration: text(video.durationSeconds || video.duration || item.durationSeconds || metadata.duration || "—"),
      mp4Ready,
      coverReady,
      seoReady,
      mp3Ready,
      metadataReady,
      channelId: assignedChannel,
      channelName: names.get(assignedChannel) || (assignedChannel ? assignedChannel : "—"),
      publishAt: text(execution?.publishAt || assignment.publishAt),
      assignmentType: assignment.locked ? "LOCKED" : text(assignment.source || (execution ? "AUTO" : "—")),
      readiness: text(readiness.state),
      queue: execution,
    };
    return { ...row, status: statusFor(row) };
  }).sort((a, b) => a.number - b.number);

  const channelRows: ChannelRow[] = channels.map(({ channel, id }) => ({
    ...defaultRule(id, record(rules[id])),
    name: channel.name || channel.channel || id,
    oauthConnected: Boolean(channel.oauthConnected),
    subscribers: channel.subscribers || "—",
    assigned: videoRows.filter((video) => video.channelId === id).length,
  }));
  const receiptsRaw = record(rawV2.receipts);
  const receipts: ReceiptRow[] = Object.entries(receiptsRaw).map(([snapshotId, raw]) => {
    const receipt = record(raw);
    const id = text(receipt.productionItemId);
    const row = videoRows.find((video) => video.id === id);
    const stages = record(receipt.stages);
    return {
      snapshotId,
      productionItemId: id,
      title: text(receipt.title) || row?.title || id,
      channelId: text(receipt.channelId),
      channelName: names.get(text(receipt.channelId)) || text(receipt.channelId),
      youtubeVideoId: text(receipt.youtubeVideoId),
      youtubeVideoUrl: text(receipt.youtubeVideoUrl),
      requestedPublishAt: text(receipt.requestedPublishAt),
      confirmedPublishAt: text(receipt.confirmedPublishAt),
      finalStatus: text(receipt.finalStatus),
      completion: `${Object.values(stages).filter((state) => ["SUCCESS", "SKIPPED", "NOT_REQUIRED"].includes(text(state))).length}/${Object.keys(stages).length}`,
      duration: text(receipt.totalDuration || "—"),
      ads: {
        status: text(record(receipt.ads).status),
        mode: text(record(receipt.ads).mode),
        automatic: Boolean(record(receipt.ads).automatic),
        manualSlotsSeconds: Array.isArray(record(receipt.ads).manualSlotsSeconds) ? record(receipt.ads).manualSlotsSeconds.map(Number) : [],
        confirmedManualSlotsSeconds: Array.isArray(record(receipt.ads).confirmedManualSlotsSeconds) ? record(receipt.ads).confirmedManualSlotsSeconds.map(Number) : [],
      },
      stages: Object.fromEntries(Object.entries(stages).map(([key, value]) => [key, text(value)])),
    };
  });
  const rulePresets = (Array.isArray(rawV2.rulePresets) ? rawV2.rulePresets : [])
    .map((value) => {
      const preset = record(value);
      return { name: text(preset.name), rules: record(preset.rules), updatedAt: text(preset.updatedAt) };
    })
    .filter((preset) => preset.name);
  return {
    videos: videoRows,
    channels: channelRows,
    queue,
    receipts,
    rulePresets,
    uploadConcurrency: Math.max(1, Number(rawV2.uploadConcurrency || data.publication.uploadConcurrency) || 1),
    paused: Boolean(rawV2.paused),
    counters: record(rawV2.counters) as Record<string, number>,
  };
}

export function stageLabel(stage: string) { return ({ WAITING: "Ожидает", AUTH_CHECK: "Проверка OAuth", VIDEO_UPLOAD: "Загрузка MP4", YOUTUBE_PROCESSING: "YouTube обрабатывает", TITLE: "Заголовок", DESCRIPTION: "Описание", TAGS: "Теги", THUMBNAIL: "Обложка", ADS: "Реклама", POST: "Пост", CARDS: "Подсказки", END_SCREEN: "Конечная заставка", SCHEDULE: "Расписание", DONE: "Готово" } as Record<string, string>)[stage] || stage || "Ожидает"; }
