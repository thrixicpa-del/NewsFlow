import type { ChannelRow, ChannelRule, PublicationStatus, PublicationViewModel, QueueRow, ReceiptRow, VideoRow } from "./types";

const record = (value: unknown): Record<string, any> => value && typeof value === "object" ? value as Record<string, any> : {};
const text = (value: unknown) => String(value || "").trim();
const titleKey = (value: string) => value.trim().toLocaleLowerCase("ru-RU");
const channelId = (channel: NewsFlowSnapshot["channels"][number], index: number) => text(channel.id || channel.channel || channel.name || `channel-${index}`);

export function defaultRule(id: string, saved: Record<string, any> = {}, monetized = false): ChannelRule {
  return { channelId: id, enabled: saved.enabled !== false, quota: Math.max(0, Number(saved.quota) || 0), monetized: Boolean(saved.monetized ?? monetized), distributionStrategy: saved.distributionStrategy === "longest_monetized" ? "longest_monetized" : "balanced", privacy: ["private", "unlisted", "public"].includes(text(saved.privacy)) ? text(saved.privacy) as ChannelRule["privacy"] : "private", publishMode: saved.publishMode === "schedule" ? "schedule" : "publish_now", timezone: text(saved.timezone) || "Europe/Minsk", firstPublishAt: text(saved.firstPublishAt), intervalMinutes: Math.max(1, Number(saved.intervalMinutes) || 180), allowedWeekdays: Array.isArray(saved.allowedWeekdays) ? saved.allowedWeekdays.map(Number).filter((day) => day >= 0 && day <= 6) : [0, 1, 2, 3, 4, 5, 6], publishWindowStart: text(saved.publishWindowStart), publishWindowEnd: text(saved.publishWindowEnd), dailyCap: Math.max(0, Number(saved.dailyCap) || 0), minDurationSeconds: Math.max(0, Number(saved.minDurationSeconds) || 0), maxDurationSeconds: Math.max(0, Number(saved.maxDurationSeconds) || 0) };
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
  const queue = (Array.isArray(rawV2.queue) ? rawV2.queue : []).map((item) => ({ ...record(item), completion: record(record(item).completion), steps: record(record(item).steps), timeline: Array.isArray(record(item).timeline) ? record(item).timeline : [] })) as QueueRow[];
  const queueByProduction = new Map(queue.map((item) => [item.productionItemId, item]));
  const assignments = record(rawV2.assignments);
  const channels = data.channels.map((channel, index) => ({ channel, id: channelId(channel, index) }));
  const rules = record(rawV2.channelRules);
  const names = new Map(channels.map(({ channel, id }) => [id, channel.name || channel.channel || id]));
  const coverByTitle = new Set((data.covers || []).filter((cover) => ["Готово", "Готово с текстом"].includes(text(cover.status)) && Boolean(cover.selected_path || cover.path || cover.paths?.length)).map((cover) => titleKey(text(cover.title))));
  const seoByTitle = new Map((data.seo || []).map((item) => [titleKey(text(item.source_title)), item]));
  const voiceByProduction = new Set((data.voiceItems || []).filter((voice) => Boolean(voice.path)).map((voice) => text(voice.productionItemId)));
  const voiceByTitle = new Set((data.voiceItems || []).filter((voice) => Boolean(voice.path)).map((voice) => titleKey(text(voice.title))));
  const videoRows: VideoRow[] = Object.entries(rawItems).map(([id, raw], index) => {
    const item = record(raw); const metadata = record(item.metadata); const artifacts = record(item.artifacts); const video = record(artifacts.video); const title = text(metadata.title) || id; const assignment = record(assignments[id]); const execution = queueByProduction.get(id); const assignedChannel = text(execution?.channelId || assignment.channelId); const seo = record(seoByTitle.get(titleKey(title))); const mp4Ready = text(record(item.readiness).state) === "VIDEO_READY" && Boolean(video.exists ?? video.path); const metadataReady = Boolean(metadata.title && (metadata.description || metadata.tags || seo.description || seo.tags)); const row = { id, number: Number(metadata.index) || index + 1, title, duration: text(video.duration || metadata.duration || "—"), mp4Ready, coverReady: coverByTitle.has(titleKey(title)), seoReady: text(seo.status) === "Готово" || Boolean(seo.description), mp3Ready: voiceByProduction.has(id) || voiceByTitle.has(titleKey(title)), metadataReady, channelId: assignedChannel, channelName: names.get(assignedChannel) || (assignedChannel ? assignedChannel : "—"), publishAt: text(execution?.publishAt || assignment.publishAt), assignmentType: assignment.locked ? "LOCKED" : text(assignment.source || (execution ? "AUTO" : "—")), readiness: text(record(item.readiness).state), queue: execution };
    return { ...row, status: statusFor(row) };
  }).sort((a, b) => a.number - b.number);
  const channelRows: ChannelRow[] = channels.map(({ channel, id }) => ({ ...defaultRule(id, record(rules[id]), Boolean(channel.monetaryAccess)), name: channel.name || channel.channel || id, oauthConnected: Boolean(channel.oauthConnected), subscribers: channel.subscribers || "—", assigned: videoRows.filter((video) => video.channelId === id).length }));
  const receiptsRaw = record(rawV2.receipts);
  const receipts: ReceiptRow[] = Object.entries(receiptsRaw).map(([snapshotId, raw]) => { const receipt = record(raw); const id = text(receipt.productionItemId); const row = videoRows.find((video) => video.id === id); const stages = record(receipt.stages); return { snapshotId, productionItemId: id, title: text(receipt.title) || row?.title || id, channelId: text(receipt.channelId), channelName: names.get(text(receipt.channelId)) || text(receipt.channelId), youtubeVideoId: text(receipt.youtubeVideoId), youtubeVideoUrl: text(receipt.youtubeVideoUrl), requestedPublishAt: text(receipt.requestedPublishAt), confirmedPublishAt: text(receipt.confirmedPublishAt), finalStatus: text(receipt.finalStatus), completion: `${Object.values(stages).filter((state) => ["SUCCESS", "SKIPPED", "NOT_REQUIRED"].includes(text(state))).length}/${Object.keys(stages).length}`, duration: text(receipt.totalDuration || "—"), stages: Object.fromEntries(Object.entries(stages).map(([key, value]) => [key, text(value)])) }; });
  return { videos: videoRows, channels: channelRows, queue, receipts, uploadConcurrency: Math.max(1, Number(rawV2.uploadConcurrency || data.publication.uploadConcurrency) || 1), paused: Boolean(rawV2.paused), counters: record(rawV2.counters) as Record<string, number> };
}

export function stageLabel(stage: string) { return ({ WAITING: "Ожидает", AUTH_CHECK: "Проверка OAuth", VIDEO_UPLOAD: "Загрузка MP4", YOUTUBE_PROCESSING: "YouTube обрабатывает", TITLE: "Заголовок", DESCRIPTION: "Описание", TAGS: "Теги", THUMBNAIL: "Обложка", POST: "Пост", CARDS: "Карточки", END_SCREEN: "Конечная заставка", SCHEDULE: "Расписание", DONE: "Готово" } as Record<string, string>)[stage] || stage || "Ожидает"; }
