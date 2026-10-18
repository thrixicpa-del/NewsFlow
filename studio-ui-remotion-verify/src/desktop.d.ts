interface NewsFlowSnapshot {
  pipelineTarget: number;
  autoMontageEnabled: boolean;
  autoPipelineStages: Record<'scenarios' | 'covers' | 'seo' | 'voice' | 'montage' | 'package', boolean>;
  ideaTopics: string[];
  ideaSuggestedTopics: string[];
  ideaReferenceChannels: Array<{ label: string; url: string }>;
  ideaReferenceAnalysis: Array<{ title: string; url: string; channel: string; views: number; ageHours: number; viewsHour: number }>;
  ideaReferenceRules: string;
  ideaPlan: Array<{ topic: string; count: number; provider?: string; requirements?: string; chat_url?: string; profile_id?: string }>;
  youtubeSuggestedTopics: string[];
  ideaResults: string[];
  ideaResultSources?: Record<string, string>;
  ideaTitleMetadata?: Record<string, { char_count?: number; valid_length?: boolean; hook_type?: string; hook_family?: string; angle?: string; title_structure?: string; duplicate_score?: number; click_score?: number; novelty_score?: number; scriptability_score?: number; framing_type?: 'FACTUAL' | 'EDITORIAL' | 'HYPOTHETICAL'; review_status?: 'READY' | 'NEEDS_RESEARCH'; main_consequence?: string; information_payload?: Record<string, unknown>; script_requirements?: string[] }>;
  ideaProductionItems?: Array<{ title: string; direction: string; topic: string; angle: string; event_ids?: string[]; script_requirements?: string[]; click_score?: number; novelty_score?: number; scriptability_score?: number; char_count?: number; hook_family?: string; framing_type?: 'FACTUAL' | 'EDITORIAL' | 'HYPOTHETICAL'; factual_risk_score?: 'LOW' | 'MEDIUM' | 'HIGH' | 'UNKNOWN'; cis_audience_relevance_score?: number; why_cis_audience_cares?: string; emotional_stakes_score?: number; creative_amplification_score?: number; direction_fit_score?: number; main_consequence?: string; information_payload?: Record<string, unknown>; status?: 'APPROVED' | 'LEGACY' }>;
  ideaPortfolioSummary?: { requested?: number; generated?: number; suggested?: number; accepted?: number; needs_research?: number; rejected?: number; deficit?: number; question_count?: number; diversity?: Record<string, number>; providerRequested?: boolean; providerResponseReceived?: boolean; providerRequestDirections?: number; providerResponseDirections?: number };
  ideaRejectedItems?: Array<{ reason?: string; candidate?: Record<string, unknown>; nearest_duplicate?: string; similarity?: number; script_overlap?: number; event_bundle_overlap?: number; payload_overlap?: number; rejection_detail?: string }>;
  youtubeResearch?: Array<{ title: string; url: string; channel?: string; views: number; likes: number; comments: number; score?: number }>;
  newsResearch?: Array<{ title: string; source: string; url: string; published?: string }>;
  ideaRoutePresets: Array<{ name: string; provider: string; requirements?: string; profile_id?: string; chat_url?: string }>;
  scenarios: Array<{ index: number; productionItemId?: string; title: string; state: string; result: string; error: string; targetChars?: number; allowedMin?: number; allowedMax?: number; actualChars?: number; lengthStatus?: string; lengthRepairAttempts?: number; storyPartCount?: number; completedStoryParts?: number; storyPlannerStatus?: string; storyPlannerFailure?: { phase?: string; reason?: string; response_chars?: string; response_sha256?: string } }>;
  browserTopicScenarios: {
    projectUrl: string;
    sessionId: string;
    requirementsMode: 'text' | 'file';
    requirementsText: string;
    requirementsFile: string;
    companionPrompt: string;
    minimumChars: number;
    maximumChars: number;
    concurrency: number;
    lengthOverrides: Record<string, { minimum_chars: number; maximum_chars: number }>;
    additionalPromptOverrides: Record<string, string>;
    promptOverrides: Record<string, string>;
    urlOverrides: Record<string, string>;
  };
  covers: Array<{ production_item_id?: string; title: string; script?: string; scenario_index?: number; status?: string; progress?: number; timeline?: Array<{ at: string; label: string; progress: number; detail?: string }>; path?: string; paths?: string[]; galleryPaths?: Array<{ path: string; state: 'ready' | 'missing' | 'invalid'; message?: string }>; raw_paths?: string[]; face_composite_paths?: string[]; text_overlay_path?: string; selected_base_path?: string; selected_path?: string; image_prompt?: string; image_prompt_options?: string[]; recent_visual_prompt_history?: string[]; prompt_image_paths?: Array<{ promptIndex: number; prompt: string; paths: string[] }>; selected_prompt_index?: number; prompt_provider?: string; cover_headline?: string; headline_source?: 'AI' | 'MANUAL'; cover_headline_suggestion?: string; headline_status?: string; headline_error?: string; headline_candidate_count?: number; headline_selection_reason?: string; cover_subheadline?: string; subheadline_source?: 'AI' | 'MANUAL'; subheadline_status?: string; subheadline_error?: string; subheadline_candidate_count?: number; subheadline_selection_reason?: string; text_style?: 'STANDARD' | 'TABLOID'; face_reference_path?: string; face_reference_label?: string; face_reference_source?: 'auto' | 'manual'; face_reference_disabled?: boolean; semantic_face_label?: string; semantic_face_source?: string; faceSelectionMode?: 'semantic-only' | 'prepared-reference'; faceSelectionReason?: string; cover_face_required?: boolean; cover_people_candidates?: Array<{ name: string; entity_type: string; role_in_story?: string; relation_to_story?: string; source?: string; confidence?: number }>; cover_primary_person?: { name: string; entity_type: string; role_in_story?: string; relation_to_story?: string; source?: string; confidence?: number } | null; cover_face_resolution_status?: 'RESOLVED' | 'NEEDS_REVIEW' | string; portrait_subject?: string; portrait_side?: 'LEFT' | 'RIGHT' | ''; portrait_source?: string; portrait_resolver_reason?: string; portrait_confidence?: number; final_provider_prompt?: string; final_provider_prompt_options?: string[]; final_provider_reference_paths?: string[]; final_provider_face_reference_count?: number; reference_use_enabled?: boolean; reference_uploaded_count?: number; reference_visual_reference_count?: number; reference_missing_paths?: string[]; reference_dropped_paths?: string[]; reference_final_provider_count?: number; reference_provider_limit?: number; reference_mode_style?: boolean; reference_mode_composition?: boolean; reference_mode_mood_lighting?: boolean; reference_mode_auto?: boolean; accepted_generation_id?: string; provider_generation_id?: string; provider_generation_status?: 'processing' | 'succeeded' | 'failed' | string; provider_generation_error?: string; recovery_checked_at?: string; prompt_sources?: Record<string, string>; face_layout?: string; visual_reference_path?: string; visual_reference_to_fastgen?: boolean; rate_limit_wait_until?: string; rate_limit_used?: number; generation_round?: number; generation_rounds?: number; generation_attempt?: number; generation_attempts_per_round?: number; generation_total_attempt?: number; generation_max_attempts?: number; generation_history?: Array<{ promptIndex?: number; round?: number; attempt?: number; totalAttempt?: number; rewritten?: boolean; status?: string; error?: string; at?: string }>; render_profile?: { build_mode?: string; face_mode?: string; text_mode?: string; local_face_only?: boolean; operation?: string }; error?: string }>;
  coverCounts: { total: number; ready: number; missing: number; failed: number; generating: number; queued: number };
  seo: Array<{ production_item_id?: string; source_title: string; script?: string; status?: string; title?: string; description?: string; hashtags?: string[]; tags?: string[]; tags_status?: string; tags_error?: string; error?: string }>;
  coverSettings: { outputFolder: string; operation: string; aspectRatio: string; variantCount: number; promptTemplate: string; provider: 'agent' | 'openai'; useCustomPrompt: boolean; useScriptContext: boolean; promptVariantCount: number; headlineProvider: 'agent' | 'openai'; headlineTemplate: string; subheadlineTemplate: string; headlinePresets: Array<{ name: string; provider?: 'agent' | 'openai'; headlineTemplate?: string; subheadlineTemplate?: string }>; textMode: 'overlay' | 'fastgen'; buildMode: 'fastgen-full' | 'fastgen-full-my-face'; ranges: Array<{ start: number; end: number; prompt: string }>; presets: Array<{ name: string; provider?: 'agent' | 'openai'; promptTemplate?: string; ranges?: Array<{ start: number; end: number; prompt: string }>; useScriptContext?: boolean; headlineProvider?: 'agent' | 'openai'; headlineTemplate?: string; subheadlineTemplate?: string; textMode?: 'overlay' | 'fastgen' }>; referenceMode: 'all' | 'ranges' | 'off'; referencePaths: string[]; referenceRanges: Array<{ start: number; end: number; paths: string[] }>; aiReferenceMode: 'all' | 'ranges' | 'off'; aiReferencePaths: string[]; aiReferenceRanges: Array<{ start: number; end: number; paths: string[]; sendToFastgen?: boolean }>; aiReferenceToFastgen: boolean; useReferences?: boolean; referenceImagePaths?: string[]; referenceModeStyle?: boolean; referenceModeComposition?: boolean; referenceModeMoodLighting?: boolean; referenceModeAuto?: boolean; referenceMissingPaths?: string[]; referenceProviderLimit?: number; referenceWillSendCount?: number; referenceWillSendCountMyFaces?: number; tabloidMode?: boolean; sceneIntensityMode?: boolean; faceLibraryFolder: string; facePreparedFolder: string; faceLibraryEnabled: boolean; faceRemoveBackground: boolean; faceLibrary: { folder: string; exists: boolean; count: number; truncated: boolean; preparedCount: number; preparedFolder: string; preparedPaths: string[]; sampleNames: string[] }; faceCatalog: Array<{ name: string; paths: string[]; prepared: boolean }>; autoOverlayText: boolean; autoTextColor: boolean; generationPaused: boolean; rateLimitPerHour?: number; rateAutoResume?: boolean; rateUsed?: number; selectedKeyLabels?: string[]; seed: string; upscale: boolean; quality: string; resolution: string; activeKeys: number; useTextStructure: boolean; avoidTextRepeats: boolean; headlinePaused: boolean; subheadlinePaused: boolean };
  fastgenCapabilities: Record<string, { id?: string; provider?: string; display_name?: string; model?: string; deprecated?: boolean; experimental?: boolean; api_checked?: boolean; api_available?: boolean; health?: 'healthy' | 'degraded' | 'unavailable'; health_label?: string; billing?: { credits?: number; base_credits?: number; display?: string }; outputs?: { max_items?: number }; options?: { aspect_ratio?: { enum?: string[] } } }[]>;
  fastgenUsage: { updatedAt?: string; keys?: Array<{ label: string; error?: string; window?: string; image: { used: number; knownUsed: boolean; limit: number; threads: number; threadLimit: number }; video: { used: number; knownUsed: boolean; limit: number; threads: number; threadLimit: number }; prompts: { used: number; knownUsed: boolean; limit: number }; expiresAt?: number }> };
  seoSettings: { promptTemplate: string; tagsPromptTemplate: string; provider: 'agent' | 'openai'; tagsProvider: 'agent' | 'openai'; hashtagBatchSize: number; tagCharLimit: number; useScriptContext: boolean; callToAction: string; fixedDescriptionPrefix?: string; descriptionPrefixRanges?: Array<{ start: number; end: number; text: string; enabled?: boolean }>; descriptionPrefixPresets?: Array<{ name: string; ranges: Array<{ start: number; end: number; text: string; enabled?: boolean }> }> };
  voiceProfiles: Array<{ id?: string; name: string; provider?: 'chrome' | 'api' | 'lumean' | 'voicegen' | 'wproject'; voice_id?: string; voice_name?: string; model_id?: string; template_id?: string; template_signature?: string; settings_preset?: string; chunk_size?: number; delay_between_chunks?: number; task_threads?: number; secret_mode?: 'standard' | 'emotional'; wproject_split?: 'paragraphs' | 'lines' | 'sentences' | 'single'; wproject_join?: boolean; wproject_join_pause?: number; wproject_autotag?: 'off' | 'light' | 'medium' | 'heavy'; wproject_prosody_speed?: number; wproject_prosody_volume?: number; wproject_latency?: 'normal' | 'balanced'; wproject_normalize?: boolean; wproject_normalize_loudness?: boolean; wproject_tag_compat?: boolean; stability?: number; style?: number; favorite?: boolean; fallback?: boolean }>;
  voiceRanges: Array<{ id?: string; start: number; end: number; profile_id?: string; profile?: number; enabled?: boolean }>;
  voiceRangePresets: Array<{ name: string; profiles: NewsFlowSnapshot['voiceProfiles']; ranges: NewsFlowSnapshot['voiceRanges']; keyFailover?: boolean }>;
  voiceDefaultProfileId?: string;
  voiceQueueConcurrency?: number;
  voiceRangePreview?: { batch?: { id: string; items: Array<{ position: number; production_item_id: string; title: string; scenario_index?: number }> } | null; items?: Array<{ batch_id: string; position: number; production_item_id: string; scenario_index?: number; title: string; range_id: string; profile: NewsFlowSnapshot['voiceProfiles'][number] }>; error?: string };
  voiceProvider: string;
  lumeanVoices: Array<{ voice_id: string; name: string; [key: string]: unknown }>;
  lumeanModels: string[];
  voicegenVoices: Array<{ id: string; name?: string; display?: string; default_voice_engine?: string; voice_engines?: string[]; source_type?: string; [key: string]: unknown }>;
  voicegenPresets: Array<{ id: string; title?: string; voice_engine?: string }>;
  voicegenEngines: string[];
  voicegenProfile: Record<string, unknown>;
  wprojectVoices: Array<{ id?: string; voice_id?: string; name?: string; [key: string]: unknown }>;
  wprojectProfile: Record<string, unknown>;
  wprojectUsage: Record<string, unknown>;
  voiceApiFallback: boolean;
  voiceUseChromeSelectedVoice: boolean;
  voiceQueuePaused: boolean;
  voiceKeyFailover: boolean;
  voiceOutputFolder: string;
  voiceImport: { root?: string; foldersFound?: number; audioFound?: number; matched?: number; requiresChoice?: number; unmatched?: number; errors?: number; review?: Array<{ file?: string; folder?: string; reason?: string }>; unmatchedItems?: Array<{ file?: string; folder?: string }> };
  voiceItems: Array<{ index: number; title: string; state: string; path: string; productionItemId?: string; rangeId?: string; voiceName?: string; voiceProvider?: string; jobSnapshotId?: string; jobState?: string; voiceStatus?: string; voiceProgress?: number; voiceUpdatedAt?: string; voiceError?: string; voiceMapState?: string; voiceMapLabel?: string; voiceMapPath?: string; voiceMapReason?: string; voiceMapTimingMode?: "aligned" | "approximate" | ""; voiceMapEngine?: string; voiceMapConfidence?: number }>;
  footageFolders: string[];
  footageIndex: { total: number; indexed: number; mediaQuarantined?: number; mediaQuarantine?: Array<{ path: string; reason: string }>; englishBlocked?: number; englishSafe?: number; englishUnchecked?: number; semanticCurrent?: number; semanticOutdated?: number; semanticVersion?: number; databasePath: string; error?: string; status?: { stage?: string; active?: boolean; total?: number; processed?: number; indexed?: number; skipped?: number; failed?: number; quarantined?: number; current?: string; startedAt?: string; updatedAt?: string; error?: string; message?: string } };
  proxyCache: { status?: { stage?: string; active?: boolean; pauseRequested?: boolean; total?: number; processed?: number; ready?: number; skipped?: number; excluded?: number; failed?: number; current?: string; sourceBytes?: number; cacheFolder?: string; startedAt?: string; updatedAt?: string; error?: string; message?: string } };
  footageTree?: { total: number; limited: boolean; roots: Array<{ path: string; clips: number; branches: Array<{ name: string; clips: number }> }> };
  cutterSources: string[];
  cutterSettings: { outputFolder: string; downloadFolder: string; mixerOutputFolder: string };
  montageSettings: { overlayTemplate?: import("./contracts/montageOverlays").MontageOverlayTemplate; projectFolder: string; outputFolder: string; aspectRatio: string; renderer: 'remotion' | 'ffmpeg' | 'gpu-timeline'; remotionFrameConcurrency: number; exportDaVinciXml?: boolean; davinciAutoImport?: boolean; davinciStatus?: { available: boolean; connected: boolean; message: string }; transitionStyle: 'crossfade' | 'dip-black' | 'cut' | 'slide-left'; transitionFrames: number; introEnabled: boolean; introFolder: string; introDuration: number; overlayEnabled: boolean; overlayFolder: string; autoWeb: boolean; autoYoutube: boolean; externalOnly: boolean; useScriptText: boolean; excludeEnglishText: boolean; scenePlanner: 'local' | 'agent'; matchThreshold: number; fastReuseEnabled: boolean; uniqueFootagePercent: number; fastReuseRanges: Array<{ start: number; end: number; percent: number }>; planningWorkers: number; downloadWorkers: number; renderWorkers: number; gpuChunkSize?: number; queuePaused: boolean; queueRunning?: boolean };
  montageProjects: Array<{ overlayNeedsRender?: boolean; overlayTemplate?: import("./contracts/montageOverlays").MontageOverlayTemplate; overlayTemplateIndividualized?: boolean; title: string; path: string; duration?: number; voicePath?: string; outputPath?: string; remotionPath?: string; fcpxmlPath?: string; transitionStyle?: string; transitionFrames?: number; error?: string; selectionSummary?: Record<string, unknown>; selectionSummaryText?: string; preparationMetricsMs?: Record<string, number>; voiceMapProvenance?: Record<string, unknown>; clips?: Array<{ path: string; duration: number; narration?: string; query?: string; source?: string; sourceStart?: number; fallbackLevel?: string; sourceFamily?: string; reused?: boolean; positionBucket?: string; positionRotationReason?: string; voiceSegmentId?: number; narrationStart?: number; narrationEnd?: number }> }>;
  montageTasks: Array<{ renderAttempt?: number; overlayTemplate?: import("./contracts/montageOverlays").MontageOverlayTemplate; overlayNeedsRender?: boolean; overlayTemplateIndividualized?: boolean; overlayTemplateRevision?: number; index: number; scenarioIndex?: number; title: string; status?: string; phase?: string; progress?: number; error?: string; detail?: string; updatedAt?: string; voicePath?: string; outputPath?: string; projectPath?: string; runtimeCurrent?: boolean; runtimeProvenance?: 'current-session' | 'previous-session' | 'legacy-unattributed'; timeline?: Array<{ at: string; label: string; progress: number; detail?: string }> }>;
  outputs: Array<{ video: string; folder: string }>;
  results: { outputFolder: string; lastExportFolder: string };
  publication: {
    jobs: Array<{ id: string; productionItemId?: string; title: string; status: string; privacy: 'private' | 'unlisted' | 'public'; publishAt?: string; channelId?: string; scriptName?: string; seoTitle?: string; seoDescription?: string; seoPhrases?: string[]; tags?: string[]; hashtags?: string[]; thumbnailPath?: string; durationSeconds?: number | null; packageFolder: string; titleRewriteInstruction?: string; videoId?: string; videoUrl?: string; videoStatus?: string; uploadError?: string; post?: { text?: string; status?: string; publishAt?: string; publishedAt?: string; videoUrl?: string; requiresManualConfirmation?: boolean } }>;
    presets: Array<{ name: string; intervalMinutes?: number; slotMinutes?: number; batchCapacity?: number; distribution?: string; [key: string]: unknown }>;
    activity: Array<{ at?: string; kind?: string; jobId?: string; title?: string; detail?: string }>;
    engagementPolicies?: Array<{ channelId: string; enabled?: boolean; postsEnabled?: boolean; cardsEnabled?: boolean; endScreensEnabled?: boolean }>;
    engagementTasks?: Array<{ jobId: string; channelId: string; videoId?: string; videoUrl?: string; publishAt?: string; lastError?: string; post?: { status?: string }; cards?: { status?: string }; endScreen?: { status?: string } }>;
    readyOutputs: Array<{ video: string; folder: string }>;
    uploadConcurrency: number;
    allocation: {
      counters: { required: number; ready: number; assigned: number; missing: number; reserve: number };
      channels: Array<{ channelId: string; name?: string; thumbnailUrl?: string; subscribers?: string; monetized: boolean; growthSignal: boolean; recommendedQuota: number; quota: number; quotaLocked: boolean; minDurationSeconds: number; maxDurationSeconds: number; assignedJobIds: string[]; assignedJobs?: Array<{ id: string; title: string; durationSeconds: number }> }>;
      missingDurationJobIds: string[];
      presets: Array<{ name: string; channelIds?: string[]; profiles?: Array<Record<string, unknown>> }>;
      updatedAt: string;
    };
    v2?: {
      items: Record<string, {
        productionItemId?: string;
        durationSeconds?: number;
        metadata?: { title?: string; seoTitle?: string; description?: string; tags?: string[]; hashtags?: string[]; duration?: number; durationSeconds?: number; index?: number; seoStatus?: string; tagsStatus?: string };
        readiness?: { state?: string; reasons?: string[]; videoReady?: boolean; contentReady?: boolean; publicationReady?: boolean };
        artifacts?: {
          video?: { path?: string; exists?: boolean; duration?: number; durationSeconds?: number };
          thumbnail?: { path?: string; exists?: boolean };
          audio?: { path?: string; exists?: boolean };
        };
      }>;
      queue: Array<{
        snapshotId: string; productionItemId: string; title: string; channelId: string; publishAt?: string;
        privacy: 'private' | 'unlisted' | 'public'; publishMode: string; youtubeVideoId?: string; youtubeVideoUrl?: string;
        currentStage: string; status: string; active: boolean;
        reupload?: { status?: string; oldVideoId?: string; oldVideoUrl?: string; newVideoId?: string; newVideoUrl?: string; reason?: string; requestedAt?: string; startedAt?: string; uploadedAt?: string; completedAt?: string; failedAt?: string; lastCheckedAt?: string; originalPrivacy?: string; originalPublishMode?: string; originalPublishAt?: string; metadataConfirmedAt?: string; replacementPrivacy?: string; scheduleApplied?: boolean };
        ads?: { status?: string; mode?: string; automatic?: boolean; manualSlotsSeconds?: number[]; confirmedManualSlotsSeconds?: number[] };
        completion: { completed: number; total: number };
        steps: Record<string, { status?: string; error?: unknown; detail?: string; startedAt?: string; finishedAt?: string; durationSeconds?: number; providerResult?: Record<string, unknown>; progress?: Record<string, unknown> }>;
        timeline?: Array<{ at?: string; stage?: string; status?: string; detail?: string }>;
      }>;
      counters: Record<string, number>;
      paused: boolean;
      uploadConcurrency: number;
      channelRules: Record<string, Record<string, unknown>>;
      rulePresets?: Array<{ name: string; rules?: Record<string, Record<string, unknown>> }>;
      planVersions?: Array<{ id: string; name: string; createdAt?: string; assignments?: Array<Record<string, unknown>> }>;
      assignments: Record<string, Record<string, unknown>>;
      receipts?: Record<string, {
        productionItemId?: string; title?: string; channelId?: string; youtubeVideoId?: string; youtubeVideoUrl?: string;
        requestedPublishAt?: string; confirmedPublishAt?: string; finalStatus?: string; totalDuration?: string;
        ads?: { status?: string; mode?: string; automatic?: boolean; manualSlotsSeconds?: number[]; confirmedManualSlotsSeconds?: number[]; midRollEligible?: boolean };
        stages?: Record<string, string>;
      }>;
    };
  };
  analytics: {
    metricPoints: Array<{ channelId: string; at: string; views: number; subscribers?: number; publications?: number; estimatedRevenue?: number | null }>;
    videoMetrics: Array<{ channelId: string; videoId: string; at: string; views?: number; impressions?: number; impressionsClickThroughRate?: number; averageViewDuration?: number; averageViewPercentage?: number; likes?: number; comments?: number; shares?: number; financialAvailable?: boolean }>;
    updatedAt: string;
  };
  mediaResults: string[];
  templateSettings: {
    template: string;
    ranges: Array<{ start: number; end: number; prompt: string; target_chars?: number; allowed_min?: number; allowed_max?: number }>;
    targetChars?: number;
    allowedMin?: number;
    allowedMax?: number;
    scenarioProvider?: 'agent' | 'openai';
    presets?: Array<{ name: string; template: string; ranges: Array<{ start: number; end: number; prompt: string; target_chars?: number; allowed_min?: number; allowed_max?: number }>; targetChars?: number; allowedMin?: number; allowedMax?: number }>;
    rangePresets?: Array<{ name: string; ranges: Array<{ start: number; end: number; prompt: string; target_chars?: number; allowed_min?: number; allowed_max?: number }> }>;
  };
  keyStatus: { fastgen: Array<{ label: string; active: boolean; fingerprint?: string; note?: string; streams?: number; balance?: string; balanceStatus?: string }>; openai: Array<{ label: string; active: boolean; fingerprint?: string; note?: string; streams?: number; balance?: string; balanceStatus?: string }>; voicer: Array<{ label: string; active: boolean; fingerprint?: string; note?: string; streams?: number; balance?: string; balanceStatus?: string }>; lumean: Array<{ label: string; active: boolean; fingerprint?: string; note?: string; streams?: number; balance?: string; balanceStatus?: string }>; voicegen: Array<{ label: string; active: boolean; fingerprint?: string; note?: string; streams?: number; balance?: string; balanceStatus?: string }>; wproject: Array<{ label: string; active: boolean; fingerprint?: string; note?: string; streams?: number; balance?: string; balanceStatus?: string }>; youtube: Array<{ label: string; active: boolean; fingerprint?: string; note?: string; balance?: string; balanceStatus?: string }> };
  preparedProject?: { warning?: string; title: string; path: string; clips: number; duration: number; summary?: Record<string, unknown>; summaryText?: string; timingsMs?: Record<string, number> };
  operationResult?: { kind: string; count: number; folder?: string; message?: string; skipped?: Record<string, string>; skippedIndices?: number[]; assets?: Array<{ path: string; kind: "image" | "video"; name: string }>; skippedSymlinks?: number; topicsTotal?: number; txtEntries?: number; mp4Linked?: number; mp4Copied?: number; coversCopied?: number; missingMp4Ordinals?: number[]; missingCoverOrdinals?: number[]; missingSeoDescriptionOrdinals?: number[]; missingTagsOrdinals?: number[]; generation?: { requested?: number; generated?: number; suggested?: number; accepted?: number; needsResearch?: number; rejected?: number; providerRequested?: boolean; providerResponseReceived?: boolean } };
  pipelineResult?: { status: string; scenarios?: number; message?: string };
  webResults?: Array<{ title: string; source?: string; source_url?: string; download_url?: string; license?: string; artist?: string; duration?: number }>;
  chromeSessions: Array<{ id: string; label: string; active: boolean; limitStatus: string; usage: Record<'ideas' | 'scenarios' | 'covers' | 'seo', boolean> }>;
  analyticsOAuth: { configured: boolean; mode?: 'cloudflare' | 'loopback'; serviceUrl?: string; fileName: string };
  obsidian: { vaultPath: string; mcpUrl: string; mcpConfigured: boolean; syncEnabled: boolean };
  obsidianStatus?: string;
  channels: Array<{ id?: string; channelId?: string; name: string; channel: string; thumbnailUrl?: string; operatorTag?: string; operatorNotes?: string; subscribers: string; status: string; monetaryAccess?: boolean; oauthConnected?: boolean; oauthAccountEmail?: string; viewsHour?: string; views48h?: string; income?: string }>;
  counts: { ideas: number; scripts: number; voice: number; montage: number };
}

interface Window {
  newsflowDesktop?: {
    snapshot: () => Promise<NewsFlowSnapshot>;
    footageIndexStatus: () => Promise<NonNullable<NewsFlowSnapshot['footageIndex']['status']>>;
    proxyCacheStatus: () => Promise<NonNullable<NewsFlowSnapshot['proxyCache']['status']>>;
    saveSettings: (patch: unknown) => Promise<NewsFlowSnapshot>;
    revealApiKey: (input: { kind: string; index: number; fingerprint: string }) => Promise<{ label: string; secret: string; revision: string }>;
    command: <K extends import("./contracts/newsflowCommands").NewsFlowCommand>(
      command: K,
      payload?: import("./contracts/newsflowCommands").CommandRequest<K>,
    ) => Promise<NewsFlowSnapshot>;
    startYoutubeOAuthHandoff: (input: { index: number; includeMonetary: boolean }) => Promise<{ id: string; channelIndex: number; state: 'waiting' | 'succeeded' | 'failed' | 'cancelled'; expiresAt: string; message?: string }>;
    youtubeOAuthHandoffStatus: (id: string) => Promise<{ id: string; channelIndex: number; state: 'waiting' | 'succeeded' | 'failed' | 'cancelled'; expiresAt: string; message?: string } | null>;
    cancelYoutubeOAuthHandoff: (id: string) => Promise<{ id: string; channelIndex: number; state: 'waiting' | 'succeeded' | 'failed' | 'cancelled'; expiresAt: string; message?: string }>;
    openPath: (target: string) => Promise<string>;
    chooseFolder: () => Promise<string>;
    chooseVideos: () => Promise<string[]>;
    chooseImages: () => Promise<string[]>;
    chooseAudio: () => Promise<string>;
    chooseAudioFiles: () => Promise<string[]>;
    chooseJson: () => Promise<string>;
    choosePromptText: () => Promise<string>;
    chooseBrowserScenarioRequirements: () => Promise<string>;
    chooseCoverTextTriples: () => Promise<string>;
    chooseCoverPromptPairs: () => Promise<string>;
    chooseScenarioTexts: () => Promise<Array<{ title: string; text: string }>>;
    chooseSavePath: (suggestedName: string) => Promise<string>;
    chooseZipSavePath: (suggestedName: string) => Promise<string>;
    chooseAudioSavePath: (suggestedName: string) => Promise<string>;
  };
}
