/**
 * Renderer command names supported by the current Python bridge.
 *
 * This list is intentionally explicit. A new renderer action must add a
 * canonical Python handler and a contract test before it can cross Electron
 * IPC. Critical Light-path payloads below are typed more narrowly; legacy
 * screen commands retain object payloads until their own bounded phase.
 */
export const NEWSFLOW_COMMANDS = [
  "snapshot", "reconcile-runtime-state", "save-settings", "save-obsidian-settings", "test-obsidian-mcp", "export-obsidian-notes",
  "add-topic", "delete-topics", "suggest-topics", "add-suggested-topics-to-favorites", "clear-suggested-topics", "reject-suggested-topics", "add-idea-reference-channel", "remove-idea-reference-channel", "save-idea-reference-rules", "analyze-idea-reference-channels", "research-youtube-topics", "clear-youtube-suggested-topics", "add-session", "add-topics-to-plan", "set-idea-route", "save-idea-route-preset", "update-idea-plan", "generate-ideas", "delete-idea-results", "regenerate-idea-results", "add-ideas-to-scenarios", "transfer-ideas", "export-ideas",
  "import-manual-scenario", "import-manual-scenarios", "import-voiceover", "import-voiceover-files", "import-voiceover-folder", "remove-voiceovers", "export-stage", "export-scenario-titles", "export-scenarios", "export-scenarios-separate-txt", "set-session-active", "set-session-usage",
  "add-channel", "import-channel-research-txt", "update-analytics-channel-metadata", "open-analytics-channel", "remove-analytics-channel", "save-google-oauth", "save-youtube-oauth-service", "start-youtube-channel-handoff", "finish-youtube-channel-handoff", "cancel-youtube-channel-handoff", "connect-youtube-channel", "reset-youtube-channel-account", "refresh-analytics",
  "add-scenarios", "generate-scenarios", "rename-scenario", "remove-scenarios", "save-scenario-text", "transfer-scenarios", "enqueue-montage-audio",
  "save-cover-settings", "save-cover-prompt-preset", "delete-cover-prompt-preset", "save-cover-headline-preset", "delete-cover-headline-preset", "select-cover-prompt", "refresh-fastgen", "generate-cover-prompts", "generate-cover-headlines", "generate-cover-subheadlines", "pause-cover-text-generation", "resume-cover-text-generation", "generate-cover-texts", "apply-cover-headline-suggestions", "apply-cover-subheadline-suggestions", "cancel-cover-subheadlines", "remove-cover-headline-suggestions", "import-cover-headlines", "import-cover-text-triples", "remove-cover-headlines", "import-cover-topics", "save-cover-headline", "save-cover-subheadline", "export-cover-prompts", "generate-covers", "reconcile-cover-gallery", "pause-cover-generation", "resume-cover-generation", "prepare-cover-face-library", "select-cover-face", "select-cover-face-person", "clear-cover-face", "select-cover-visual-reference", "set-cover-visual-reference-target", "refine-cover-faces", "compose-cover-faces", "regenerate-covers", "retry-cover-generation", "recover-cover-generation", "retry-cover-generation-new-paid", "regenerate-cover-with-face", "regenerate-covers-new-prompts", "remove-cover-prompts", "select-cover-variant", "remove-cover-results", "remove-cover-image", "remove-cover-queue", "export-covers", "export-cover-images", "render-cover-text", "render-cover-text-fastgen",
  "save-seo-settings", "save-tags-settings", "save-tag-limits", "generate-seo", "generate-tags", "remove-seo-packages", "clear-tags", "save-tags-text", "save-seo-text", "export-seo",
  "generate-voice", "generate-voice-queue", "generate-voice-range", "rebuild-voice-map", "preview-voice-ranges", "set-voice-queue-paused", "open-voice-session", "save-voice-settings", "save-voice-range-preset", "apply-voice-range-preset", "delete-voice-range-preset",
  "add-footage-folder", "remove-footage-folder", "save-footage-settings", "inspect-footage-tree", "add-cutter-sources", "run-cutter", "run-mixer", "search-web-footage", "download-web-footage", "index-footage",
  "save-montage-settings", "prepare-montage", "render-montage", "export-davinci-xml", "import-davinci-xml", "run-montage-queue", "remove-montage-results", "remove-montage-projects", "package-outputs", "export-results-batch",
  "queue-ready-publication-outputs", "save-publication-settings", "save-youtube-engagement-policy", "run-youtube-engagement", "reconcile-youtube-engagement", "queue-existing-youtube-engagement", "update-channel-allocation", "refresh-publication-allocation", "apply-publication-recommendations", "assign-publication-jobs", "save-publication-allocation-preset", "clear-production-queue", "schedule-publication-jobs", "duplicate-publication-job", "save-publication-preset", "move-publication-job", "move-publication-job-channel", "rewrite-publication-title", "mark-publication-post-done", "upload-publication-jobs", "migrate-publication-v2", "save-publication-v2-rule-preset", "apply-publication-v2-rule-preset", "delete-publication-v2-rule-preset", "save-publication-v2-plan-version", "restore-publication-v2-plan-version", "delete-publication-v2-plan-version", "save-publication-v2-rules", "set-publication-v2-item-priority", "preview-publication-v2-distribution", "confirm-publication-v2-distribution", "retry-publication-v2-stage", "resolve-publication-v2-uncertain-upload", "open-publication-v2-identity-verification", "queue-publication-v2-reupload", "set-publication-v2-paused", "cancel-publication-v2-execution", "publication-v2-receipt", "upload-publication-v2-snapshots", "reconcile-publication-v2-youtube", "run-publication-v2-thumbnails", "run-publication-v2-studio",
  "run-auto-pipeline", "generate-media", "save-template", "save-template-preset", "delete-template-preset", "save-range-preset", "delete-range-preset", "add-api-key", "set-key-active", "save-api-key-note", "update-voicer-key-settings", "refresh-voicer-balances", "update-lumean-key-settings", "refresh-lumean-catalog", "update-voicegen-key-settings", "refresh-voicegen-catalog", "update-wproject-key-settings", "refresh-wproject-catalog", "open-chrome-session",
] as const;

export type NewsFlowCommand = (typeof NEWSFLOW_COMMANDS)[number];
export type GenericCommandPayload = Record<string, unknown>;

export interface CriticalCommandPayloads {
  "save-settings": GenericCommandPayload;
  "generate-ideas": { topics?: string[]; count?: number; requirements?: string; provider?: "agent" | "openai"; titleFormulaOnly?: boolean };
  "generate-scenarios": { indices?: number[]; provider?: "agent" | "openai"; force?: boolean; restart?: boolean };
  "generate-voice-queue": { force?: boolean };
  "generate-voice-range": { rangeId?: string; force?: boolean };
  "rebuild-voice-map": { scenarioIndex: number; productionItemId: string };
  "generate-covers": { indices?: number[]; provider?: "agent" | "openai"; force?: boolean };
  "run-montage-queue": { indices?: number[]; missingOnly?: boolean; replaceOutput?: boolean };
  "generate-seo": { indices?: number[]; provider?: "agent" | "openai" };
  "generate-tags": { indices?: number[]; provider?: "agent" | "openai" };
  "set-publication-v2-item-priority": { productionItemId: string; priority: number };
  "preview-publication-v2-distribution": { productionItemIds?: string[]; bulkSchedule?: { date: string; startTime: string; endTime: string; timezone: string; channelIds: string[]; maxPerChannel: number; spacingStrategy?: "adaptive_jittered"; timeWindows?: Array<{ id: "morning" | "day" | "evening"; startTime: string; endTime: string; quota: number; enabled: boolean }> } };
  "confirm-publication-v2-distribution": { assignments?: Array<Record<string, unknown>> };
  "save-publication-v2-rule-preset": { name: string; rules: Record<string, Record<string, unknown>> };
  "apply-publication-v2-rule-preset": { name: string };
  "delete-publication-v2-rule-preset": { name: string };
  "save-publication-v2-plan-version": { name: string; assignments: Array<Record<string, unknown>> };
  "restore-publication-v2-plan-version": { id: string };
  "delete-publication-v2-plan-version": { id: string };
  "resolve-publication-v2-uncertain-upload": { snapshotId: string; outcome: "found" | "not_found"; youtubeVideoId?: string };
  "open-publication-v2-identity-verification": { snapshotId: string };
  "queue-publication-v2-reupload": { snapshotIds: string[]; reason: string; metadataConfirmed: true };
  "reconcile-publication-v2-youtube": { snapshotIds?: string[]; statusOnly?: boolean };
  "run-publication-v2-studio": { snapshotIds?: string[]; steps?: Array<"ads" | "post" | "cards" | "end-screen"> };
}

export type CommandRequest<K extends NewsFlowCommand> = K extends keyof CriticalCommandPayloads
  ? CriticalCommandPayloads[K] & GenericCommandPayload
  : GenericCommandPayload;
