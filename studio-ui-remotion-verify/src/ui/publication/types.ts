import type { CommandRequest, NewsFlowCommand } from "../../contracts/newsflowCommands";

export type PublicationCommand = <K extends NewsFlowCommand>(
  name: K,
  payload?: CommandRequest<K>,
) => Promise<NewsFlowSnapshot | undefined>;
export type PublicationTab = "videos" | "channels" | "distribution" | "dayplan" | "queue" | "history";
export type PublicationStatus = "Готов" | "Требует внимания" | "Требует канала" | "Назначен" | "Запланирован" | "Загружается" | "Оформляется" | "Готово" | "Ошибка";

export type ChannelRule = {
  channelId: string; enabled: boolean; quota: number; monetized: boolean; distributionStrategy: "balanced" | "longest_monetized";
  privacy: "private" | "unlisted" | "public"; publishMode: "schedule" | "publish_now"; timezone: string; firstPublishAt: string; intervalMinutes: number;
  allowedWeekdays: number[]; publishWindowStart: string; publishWindowEnd: string; dailyCap: number; minDurationSeconds: number; maxDurationSeconds: number;
  orderStart: number; orderEnd: number;
  automation: { upload: boolean; metadata: boolean; thumbnail: boolean; ads: boolean; post: boolean; cards: boolean; endScreen: boolean };
};

export type ChannelRow = ChannelRule & { name: string; oauthConnected: boolean; subscribers: string; assigned: number };
export type RulePreset = { name: string; rules: Record<string, ChannelRule>; updatedAt?: string };
export type QueueStep = { status?: string; error?: unknown; startedAt?: string; finishedAt?: string; durationSeconds?: number; detail?: string; providerResult?: Record<string, unknown> };
export type QueueRow = { snapshotId: string; productionItemId: string; title: string; channelId: string; publishAt?: string; privacy: string; publishMode: string; youtubeVideoId?: string; youtubeVideoUrl?: string; currentStage: string; status: string; active: boolean; ads?: { status?: string; mode?: string; automatic?: boolean; manualSlotsSeconds?: number[]; confirmedManualSlotsSeconds?: number[] }; completion: { completed: number; total: number }; steps: Record<string, QueueStep>; timeline: Array<{ at?: string; stage?: string; status?: string; detail?: string }> };
export type VideoRow = { id: string; number: number; title: string; duration: string; mp4Ready: boolean; coverReady: boolean; seoReady: boolean; mp3Ready: boolean; metadataReady: boolean; channelId: string; channelName: string; publishAt: string; assignmentType: string; status: PublicationStatus; readiness: string; queue?: QueueRow; expanded?: boolean };
export type DistributionRow = { productionItemId: string; title: string; duration: string; channelId: string; channelName: string; source: string; locked: boolean; reason: string; publishAt: string; warning: string };
export type ReceiptRow = { snapshotId: string; productionItemId: string; title: string; channelId: string; channelName: string; youtubeVideoId: string; youtubeVideoUrl: string; requestedPublishAt: string; confirmedPublishAt: string; finalStatus: string; completion: string; duration: string; ads: { status: string; mode: string; automatic: boolean; manualSlotsSeconds: number[]; confirmedManualSlotsSeconds: number[] }; stages: Record<string, string> };
export type PublicationViewModel = { videos: VideoRow[]; channels: ChannelRow[]; queue: QueueRow[]; receipts: ReceiptRow[]; rulePresets: RulePreset[]; uploadConcurrency: number; paused: boolean; counters: Record<string, number> };
