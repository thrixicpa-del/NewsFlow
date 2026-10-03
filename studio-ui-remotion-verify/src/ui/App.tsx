import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./scenarios.css";
import "./scenarios-light.css";
import "./covers.css";
import "./covers-light.css";
import "./footage.css";
import "./footage-light.css";
import "./editor.css";
import "./montage-light.css";
import "./montage-recommendations.css";
import "./voice.css";
import "./voice-light.css";
import "./sessions.css";
import "./settings-light.css";
import "./dashboard.css";
import "./templates.css";
import "./templates-light.css";
import "./analytics.css";
import "./seo-light.css";
import "./publication.css";
import "./publication-scheduling.css";
import "./publication-allocation.css";
import "./publication-delivery.css";
import "./publication-modern.css";
import "./features/task-center/task-center.css";
import { PublicationPage } from "./publication/PublicationPage";
import { TaskCenter } from "./features/task-center/TaskCenter";
import type { TaskCenterEntry } from "./features/task-center/task-model";
import { AppShell } from "./layout/AppShell";
import { ContextInspector } from "./layout/ContextInspector";
import { Sidebar } from "./layout/Sidebar";
import { WorkspaceErrorBoundary } from "./layout/WorkspaceErrorBoundary";
import { useUiPreferences } from "./layout/ui-preferences";
import { CommandPalette } from "./layout/CommandPalette";
import { buildWorkspaceSearchItems } from "./layout/workspace-search";
import { buildVisualFixture } from "./visual-regression/visual-fixtures";
import { PageHeader } from "./components/page-header";
import { StatCard } from "./components/stat-card";
import { Toast } from "./components/toast";
import { Button as UiButton } from "./components/button";
import { EmptyState } from "./components/states";
import { Switch } from "./components/switch";
import { Input } from "./components/input";
import { Textarea } from "./components/textarea";
import { Select } from "./components/select";
import { Checkbox } from "./components/checkbox";
import { Toolbar } from "./components/toolbar";
import { Dialog } from "./components/dialog";
import { Sheet } from "./components/sheet";
import { DataTable } from "./components/data-table";
import type { ColumnDef } from "@tanstack/react-table";
import type { CommandRequest, NewsFlowCommand } from "../contracts/newsflowCommands";
import {
  coverBuildModePayload,
  coverHeadlineProviderPayload,
  coverPromptProviderPayload,
  coverTextModePayload,
  coverWordPairGenerationPayload,
  coverWordGenerationPayload,
  fastGenOperationPayload,
} from "./thumbnail-word-actions";
import "./agents.css";
import "./ideas.css";
import "./ideas-light.css";
import {
  Activity,
  Aperture,
  BarChart3,
  Bot,
  Check,
  ChevronDown,
  Clapperboard,
  Download,
  FileAudio,
  FileText,
  FolderOpen,
  Image,
  KeyRound,
  LayoutDashboard,
  Library,
  Menu,
  Mic2,
  MonitorPlay,
  Newspaper,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
  Trash2,
  Upload,
  Video,
  WandSparkles,
} from "lucide-react";

type Page =
  | "dashboard"
  | "ideas"
  | "scenarios"
  | "scripts"
  | "templates"
  | "agents"
  | "covers"
  | "coverGallery"
  | "media"
  | "footage"
  | "cutter"
  | "voice"
  | "voices"
  | "audio"
  | "editor"
  | "seo"
  | "tags"
  | "publication"
  | "allocation"
  | "automation"
  | "analytics"
  | "outputs"
  | "sessions"
  | "keys"
  | "knowledge";
type Command = <K extends NewsFlowCommand>(
  name: K,
  payload?: CommandRequest<K>,
) => Promise<NewsFlowSnapshot | undefined>;
type DirtyWorkspace = "templates" | "knowledge" | "keys";
type PendingNavigation = { nextPage: Page; source: DirtyWorkspace } | null;

const defaultSeoPrompt =
  "Создай точное SEO-описание по теме «{title}», естественные хештеги и призыв посмотреть ролик. Верни только JSON.";
const defaultTagsPrompt =
  'Создай релевантные YouTube-теги для темы «{title}». Верни только JSON: {"tags":["..."]}.';

// These documented image routes remain selectable before the first live
// capabilities refresh.  The live FastGen catalogue replaces this list as
// soon as it is available, including its current health and billing data.
const fastGenImageFallbackModels: NewsFlowSnapshot["fastgenCapabilities"]["image"] = [
  {
    id: "flower_image_generate",
    provider: "Flower",
    display_name: "Flower Image",
    health: "degraded" as const,
    health_label: "Требует проверки API",
  },
  {
    id: "grok_image_generate",
    provider: "Grok",
    display_name: "Grok Image",
    health: "degraded" as const,
    health_label: "Требует проверки API",
  },
  {
    id: "gemini_nano_banana_2_image_generate",
    provider: "Gemini",
    model: "gemini-nano-banana-2",
    display_name: "Nano Banana 2",
    health: "degraded" as const,
    health_label: "Требует проверки API",
    billing: { credits: 1, display: "1 credit" },
  },
];

export const fallback: NewsFlowSnapshot = {
  pipelineTarget: 300,
  autoMontageEnabled: false,
  autoPipelineStages: {
    scenarios: true,
    covers: true,
    seo: true,
    voice: true,
    montage: true,
    package: true,
  },
  ideaTopics: [
    "Иран — Ормузский пролив",
    "Украина — удар РФ по военным заводам",
    "Россия–Украина — тупик переговоров",
    "Европа — энергетический кризис",
    "Трамп–Путин — контакты и угрозы",
    "НАТО — реакция на эскалацию",
  ],
  ideaPlan: [],
  ideaSuggestedTopics: [],
  ideaReferenceChannels: [],
  ideaReferenceAnalysis: [],
  ideaReferenceRules: "",
  youtubeSuggestedTopics: [],
  ideaResults: [],
  ideaTitleMetadata: {},
  ideaProductionItems: [],
  ideaPortfolioSummary: {},
  ideaRejectedItems: [],
  ideaRoutePresets: [],
  scenarios: [],
  covers: [],
  coverCounts: { total: 0, ready: 0, missing: 0, failed: 0, generating: 0, queued: 0 },
  seo: [],
  coverSettings: {
    outputFolder: "",
    operation: "flower_image_generate",
    aspectRatio: "16:9",
    variantCount: 1,
    promptTemplate: "",
    provider: "agent",
    useCustomPrompt: false,
    useScriptContext: true,
    promptVariantCount: 2,
    headlineProvider: "agent",
    headlineTemplate:
      "Придумай короткую фразу для текста на YouTube-обложке по теме «{title}». 1–5 слов, конкретно, интригующе, без ложных фактов.",
    subheadlineTemplate:
      "Придумай короткий подзаголовок для YouTube-обложке по теме «{title}». 3–7 слов, не повторяй основной заголовок и не выдумывай факты.",
    headlinePresets: [],
    textMode: "overlay",
    buildMode: "fastgen-full",
    ranges: [],
    presets: [],
    referenceMode: "all",
    referencePaths: [],
    referenceRanges: [],
    aiReferenceMode: "off",
    aiReferencePaths: [],
    aiReferenceRanges: [],
    aiReferenceToFastgen: false,
    useReferences: false,
    referenceImagePaths: [],
    referenceModeStyle: false,
    referenceModeComposition: false,
    referenceModeMoodLighting: false,
    referenceModeAuto: false,
    referenceMissingPaths: [],
    tabloidMode: false,
    sceneIntensityMode: false,
    faceLibraryFolder: "",
    facePreparedFolder: "",
    faceLibraryEnabled: false,
    faceRemoveBackground: false,
    faceLibrary: {
      folder: "",
      exists: false,
      count: 0,
      truncated: false,
      preparedCount: 0,
      preparedFolder: "",
      preparedPaths: [],
      sampleNames: [],
    },
    faceCatalog: [],
    autoOverlayText: true,
    autoTextColor: true,
    generationPaused: false,
    rateLimitPerHour: 0,
    rateAutoResume: false,
    rateUsed: 0,
    seed: "",
    upscale: false,
    quality: "",
    resolution: "",
    activeKeys: 0,
    useTextStructure: true,
    avoidTextRepeats: true,
    headlinePaused: false,
    subheadlinePaused: false,
  },
  fastgenCapabilities: { image: [], video: [] },
  fastgenUsage: { keys: [] },
  seoSettings: {
    promptTemplate: "",
    tagsPromptTemplate: "",
    provider: "agent",
    tagsProvider: "agent",
    hashtagBatchSize: 5,
    tagCharLimit: 500,
    useScriptContext: false,
    callToAction: "",
  },
  voiceProfiles: [{ id: "default", name: "Новости" }],
  voiceRanges: [],
  voiceRangePresets: [],
  voiceDefaultProfileId: "default",
  voiceQueueConcurrency: 20,
  voiceRangePreview: { items: [] },
  voiceKeyFailover: true,
  voiceProvider: "chrome",
  lumeanVoices: [],
  lumeanModels: [],
  voicegenVoices: [],
  voicegenPresets: [],
  voicegenEngines: [],
  voicegenProfile: {},
  wprojectVoices: [],
  wprojectProfile: {},
  wprojectUsage: {},
  voiceApiFallback: true,
  voiceUseChromeSelectedVoice: true,
  voiceQueuePaused: false,
  voiceOutputFolder: "",
  voiceImport: {},
  voiceItems: [],
  footageFolders: [],
  footageIndex: {
    total: 0,
    indexed: 0,
    englishBlocked: 0,
    englishSafe: 0,
    englishUnchecked: 0,
    semanticCurrent: 0,
    semanticOutdated: 0,
    semanticVersion: 0,
    databasePath: "",
  },
  cutterSources: [],
  cutterSettings: {
    outputFolder: "",
    downloadFolder: "",
    mixerOutputFolder: "",
  },
  montageSettings: {
    projectFolder: "",
    outputFolder: "",
    aspectRatio: "16:9",
    renderer: "ffmpeg",
    remotionFrameConcurrency: 2,
    exportDaVinciXml: true,
    davinciAutoImport: false,
    davinciStatus: {
      available: false,
      connected: false,
      message: "DaVinci API ещё не проверен",
    },
    transitionStyle: "crossfade",
    transitionFrames: 7,
    introEnabled: false,
    introFolder: "",
    introDuration: 6,
    overlayEnabled: false,
    overlayFolder: "",
    autoWeb: true,
    autoYoutube: false,
    externalOnly: false,
    useScriptText: true,
    excludeEnglishText: true,
    scenePlanner: "local",
    matchThreshold: 0.22,
    fastReuseEnabled: false,
    uniqueFootagePercent: 100,
    fastReuseRanges: [],
    planningWorkers: 4,
    downloadWorkers: 2,
    renderWorkers: 2,
    queuePaused: false,
  },
  montageProjects: [],
  montageTasks: [],
  outputs: [],
  results: { outputFolder: "", lastExportFolder: "" },
  publication: {
    jobs: [],
    presets: [],
    activity: [],
    readyOutputs: [],
    uploadConcurrency: 2,
    allocation: {
      counters: { required: 0, ready: 0, assigned: 0, missing: 0, reserve: 0 },
      channels: [],
      missingDurationJobIds: [],
      presets: [],
      updatedAt: "",
    },
  },
  analytics: { metricPoints: [], videoMetrics: [], updatedAt: "" },
  mediaResults: [],
  templateSettings: {
    template: "Напиши точный новостной сценарий на тему «{title}».",
    ranges: [],
    targetChars: 0,
    allowedMin: 0,
    allowedMax: 0,
  },
  keyStatus: {
    fastgen: [],
    openai: [],
    voicer: [],
    lumean: [],
    voicegen: [],
    wproject: [],
    youtube: [],
  },
  chromeSessions: [],
  analyticsOAuth: { configured: false, fileName: "" },
  obsidian: {
    vaultPath: "",
    mcpUrl: "",
    mcpConfigured: false,
    syncEnabled: false,
  },
  channels: [],
  counts: { ideas: 0, scripts: 0, voice: 0, montage: 0 },
};

const pageMeta: Record<
  Page,
  { title: string; subtitle: string; icon: typeof LayoutDashboard }
> = {
  dashboard: {
    title: "Центр управления",
    subtitle: "Весь путь ролика — от идеи до готового пакета",
    icon: LayoutDashboard,
  },
  ideas: {
    title: "Генерация идей",
    subtitle: "Выберите направления и подготовьте углы подачи",
    icon: Sparkles,
  },
  scenarios: {
    title: "Новости и сценарии",
    subtitle: "Очередь сценариев, статусы и ручная передача дальше",
    icon: Newspaper,
  },
  scripts: {
    title: "Готовые сценарии",
    subtitle: "Просмотр, редактирование и передача готовых текстов дальше",
    icon: FileText,
  },
  templates: {
    title: "Шаблоны и промпты",
    subtitle: "Библиотека сценарных требований по направлениям",
    icon: Library,
  },
  agents: {
    title: "Агенты NewsFlow",
    subtitle: "Понятные исполнители для текста, SEO, обложек и подбора сцен",
    icon: Bot,
  },
  covers: {
    title: "Обложки YouTube",
    subtitle: "Промпты, варианты и отбор лучшей обложки",
    icon: Image,
  },
  coverGallery: {
    title: "Галерея обложек",
    subtitle: "Просмотр, отбор, удаление и выгрузка готовых вариантов",
    icon: Image,
  },
  media: {
    title: "Картинки и видео",
    subtitle: "Дополнительные кадры и видеовставки через FastGen",
    icon: Aperture,
  },
  footage: {
    title: "Футажи",
    subtitle: "ИИ-библиотека, поиск по папкам и интернет-источникам",
    icon: Video,
  },
  cutter: {
    title: "Нарезка футажей",
    subtitle: "Исходники → тихие клипы → ИИ-индексация",
    icon: Clapperboard,
  },
  voice: {
    title: "Очередь озвучки",
    subtitle: "Импортируйте сценарии, назначьте голоса и запустите обработку",
    icon: Mic2,
  },
  voices: {
    title: "Профили голосов",
    subtitle: "Избранные дикторы, диапазоны и эмоциональная подача",
    icon: FileAudio,
  },
  audio: {
    title: "Готовые MP3",
    subtitle: "Прослушайте озвучку и передайте её в монтаж",
    icon: MonitorPlay,
  },
  editor: {
    title: "Монтаж",
    subtitle: "Футажи и озвучка собираются в таймлайн по длительности MP3",
    icon: MonitorPlay,
  },
  seo: {
    title: "SEO-пакеты",
    subtitle: "Заголовки, описания, теги и хэштеги к роликам",
    icon: Search,
  },
  tags: {
    title: "Теги",
    subtitle: "Отдельная очередь тегов и хештегов для готовых роликов",
    icon: Search,
  },
  publication: {
    title: "Публикация YouTube",
    subtitle: "Распределите, назначьте, загрузите и оформите каждый ролик",
    icon: Upload,
  },
  allocation: {
    title: "Умное распределение",
    subtitle: "Длинные ролики — в монетизированные каналы, остальное — по правилам",
    icon: WandSparkles,
  },
  automation: {
    title: "Автоправила YouTube",
    subtitle: "Посты, карточки и конечные заставки в профиле каждого канала",
    icon: Bot,
  },
  analytics: {
    title: "Аналитика и каналы",
    subtitle: "Каналы YouTube, просмотры, доход и статус монетизации",
    icon: BarChart3,
  },
  outputs: {
    title: "Результаты",
    subtitle: "Готовые папки роликов: MP4, обложка, SEO и описание",
    icon: FolderOpen,
  },
  sessions: {
    title: "Сессии Chrome",
    subtitle:
      "Постоянные профили YouTube и сервисов озвучки — вход сохраняется",
    icon: MonitorPlay,
  },
  keys: {
    title: "API-ключи",
    subtitle: "FastGen, OpenAI и озвучка с защищённым хранением",
    icon: KeyRound,
  },
  knowledge: {
    title: "База проекта",
    subtitle: "Obsidian, заметки, экспорт сценариев и производственная память",
    icon: Library,
  },
};

const navigation: Array<{
  label: string;
  entries: Array<[Page, string, typeof LayoutDashboard]>;
}> = [
  {
    label: "ПОДГОТОВКА",
    entries: [
      ["ideas", "Генерация идей", Sparkles],
      ["scenarios", "Новости", Newspaper],
      ["scripts", "Готовые сценарии", FileText],
      ["templates", "Шаблоны", Library],
      ["agents", "Агенты NewsFlow", Bot],
    ],
  },
  {
    label: "ОБЛОЖКИ И ГЕНЕРАЦИИ",
    entries: [
      ["covers", "Обложки YouTube", Image],
      ["coverGallery", "Галерея обложек", Image],
      ["media", "Картинки и видео", Aperture],
    ],
  },
  {
    label: "ПРОИЗВОДСТВО",
    entries: [
      ["footage", "Футажи — поиск", Video],
      ["cutter", "Футажи — нарезка", Clapperboard],
      ["voice", "Озвучка — очередь", Mic2],
      ["voices", "Озвучка — голоса", FileAudio],
      ["audio", "Озвучка — готовые MP3", MonitorPlay],
      ["editor", "Монтаж", MonitorPlay],
    ],
  },
  {
    label: "ПУБЛИКАЦИЯ",
    entries: [
      ["publication", "Публикация YouTube", Upload],
      ["seo", "SEO-пакеты", Search],
      ["tags", "Теги", Search],
      ["analytics", "Аналитика", BarChart3],
      ["outputs", "Результаты", FolderOpen],
    ],
  },
  {
    label: "НАСТРОЙКИ",
    entries: [
      ["sessions", "Сессии Chrome", MonitorPlay],
      ["keys", "API-ключи", KeyRound],
      ["knowledge", "База проекта", Library],
    ],
  },
];

function Button({
  children,
  kind = "secondary",
  onClick,
  ariaLabel,
  disabled = false,
  type = "button",
}: {
  children: React.ReactNode;
  kind?: "primary" | "success" | "danger" | "secondary";
  onClick?: () => void;
  ariaLabel?: string;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  const available = typeof onClick === "function" || type === "submit";
  const variant = kind === "danger" ? "destructive" : kind;
  return (
    <UiButton
      variant={variant}
      type={type}
      onClick={onClick}
      aria-label={ariaLabel}
      disabled={disabled || !available}
      title={
        available && !disabled
          ? undefined
          : "Этот элемент появится после подключения соответствующего сервиса"
      }
    >
      {children}
    </UiButton>
  );
}

function ProviderSwitch({
  value,
  onChange,
  label,
}: {
  value: "agent" | "openai";
  onChange: (value: "agent" | "openai") => void;
  label: string;
}) {
  return (
    <div className="toolbar compact" aria-label={label}>
      <Button
        kind={value === "agent" ? "primary" : "secondary"}
        onClick={() => onChange("agent")}
      >
        <Bot size={16} />
        Агент NewsFlow
      </Button>
      <Button
        kind={value === "openai" ? "primary" : "secondary"}
        onClick={() => onChange("openai")}
      >
        <Sparkles size={16} />
        ChatGPT
      </Button>
      <small>Выбрано: {value === "agent" ? "агент" : "ChatGPT"}</small>
    </div>
  );
}

function Empty({ title, text }: { title: string; text: string }) {
  return <EmptyState title={title} description={text} />;
}

function finalSentence(value: string) {
  const sentences = value.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [];
  return sentences.at(-1)?.trim() || "Призыв ещё не создан";
}

function humanCommandError(error: unknown) {
  const detail = error instanceof Error ? error.message.trim() : "";
  // Electron decorates rejected IPC promises with this prefix. It helps a
  // developer, but it hides the actionable reason from the NewsFlow operator.
  return detail.replace(
    /^Error invoking remote method 'newsflow:command': Error:\s*/i,
    "",
  );
}

export function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const visualFixture = useMemo(
    () => import.meta.env.DEV
      ? buildVisualFixture(fallback, new URLSearchParams(window.location.search).get("visual-fixture"))
      : null,
    [],
  );
  const [data, setData] = useState<NewsFlowSnapshot>(() => visualFixture || fallback);
  const [target, setTarget] = useState("300");
  const [notice, setNotice] = useState("");
  const [selectedTask, setSelectedTask] = useState<TaskCenterEntry | null>(null);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [uiPreferences, setUiPreferences] = useUiPreferences();
  const [templateDirty, setTemplateDirty] = useState(false);
  const [knowledgeDirty, setKnowledgeDirty] = useState(false);
  const [keysDirty, setKeysDirty] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<PendingNavigation>(null);
  const templateSaveRef = useRef<(() => Promise<boolean>) | null>(null);
  const knowledgeSaveRef = useRef<(() => Promise<boolean>) | null>(null);
  const keysSaveRef = useRef<(() => Promise<boolean>) | null>(null);
  const meta = pageMeta[page];
  const Icon = meta.icon;
  const isPublicationV2 = ["publication", "allocation", "automation"].includes(page);
  const stats = useMemo<Array<[number, string]>>(
    () => [
      [data.counts.ideas, "Идеи"],
      [data.counts.scripts, "Сценарии"],
      [data.counts.voice, "Озвучка"],
      [data.counts.montage, "MP4"],
    ],
    [data],
  );
  const workspaceSearchItems = useMemo(() => buildWorkspaceSearchItems(data), [data]);
  const commitNavigation = useCallback((nextPage: Page) => {
    setSelectedTask(null);
    setPage(nextPage);
  }, []);
  const navigate = useCallback((nextPage: Page) => {
    const dirtySource: DirtyWorkspace | null = page === "templates" && templateDirty
      ? "templates"
      : page === "knowledge" && knowledgeDirty
        ? "knowledge"
        : page === "keys" && keysDirty
          ? "keys"
        : null;
    if (nextPage !== page && dirtySource) {
      setPendingNavigation({ nextPage, source: dirtySource });
      return;
    }
    commitNavigation(nextPage);
  }, [commitNavigation, keysDirty, knowledgeDirty, page, templateDirty]);
  const registerTemplateSave = useCallback((save: (() => Promise<boolean>) | null) => {
    templateSaveRef.current = save;
  }, []);
  const registerKnowledgeSave = useCallback((save: (() => Promise<boolean>) | null) => {
    knowledgeSaveRef.current = save;
  }, []);
  const registerKeysSave = useCallback((save: (() => Promise<boolean>) | null) => {
    keysSaveRef.current = save;
  }, []);

  useEffect(() => {
    const openCommandPalette = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        setCommandPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", openCommandPalette);
    return () => window.removeEventListener("keydown", openCommandPalette);
  }, []);

  useEffect(() => {
    const saveActiveEditor = (event: KeyboardEvent) => {
      if (
        event.isComposing ||
        !(event.ctrlKey || event.metaKey) ||
        event.key.toLocaleLowerCase() !== "s" ||
        !((page === "templates" && templateDirty) || (page === "knowledge" && knowledgeDirty) || (page === "keys" && keysDirty))
      ) {
        return;
      }
      event.preventDefault();
      void (page === "templates" ? templateSaveRef.current : page === "knowledge" ? knowledgeSaveRef.current : keysSaveRef.current)?.();
    };
    window.addEventListener("keydown", saveActiveEditor);
    return () => window.removeEventListener("keydown", saveActiveEditor);
  }, [keysDirty, knowledgeDirty, page, templateDirty]);

  useEffect(() => {
    const protectUnsavedDraft = (event: BeforeUnloadEvent) => {
      if (!templateDirty && !knowledgeDirty && !keysDirty) return;
      event.preventDefault();
      // Electron turns the standard beforeunload contract into its native
      // close confirmation. Keeping this renderer-local preserves the current
      // IPC/core boundary and prevents silent loss of an active form draft.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", protectUnsavedDraft);
    return () => window.removeEventListener("beforeunload", protectUnsavedDraft);
  }, [keysDirty, knowledgeDirty, templateDirty]);

  useEffect(() => {
    const closeInspector = (event: KeyboardEvent) => {
      if (event.isComposing || event.defaultPrevented || event.key !== "Escape" || !selectedTask) return;
      setSelectedTask(null);
    };
    window.addEventListener("keydown", closeInspector);
    return () => window.removeEventListener("keydown", closeInspector);
  }, [selectedTask]);

  const refresh = useCallback(async () => {
    if (visualFixture) {
      setData(visualFixture);
      return;
    }
    try {
      const state = await window.newsflowDesktop?.snapshot();
      if (state) {
        setData(state);
        setTarget(String(state.pipelineTarget));
      }
    } catch {
      setNotice(
        "Ядро NewsFlow временно недоступно — интерфейс открыт в безопасном режиме.",
      );
    }
  }, [visualFixture]);
  useEffect(() => {
    void refresh();
  }, []);
  const saveTarget = async () => {
    if (visualFixture) {
      setNotice("Visual fixture: команда не запускается.");
      return;
    }
    try {
      const state = await window.newsflowDesktop?.saveSettings({
        pipelineTarget: Number(target),
      });
      if (state) {
        setData(state);
        setNotice("Цель конвейера сохранена.");
      }
    } catch {
      setNotice("Не удалось сохранить цель конвейера.");
    }
  };
  const command: Command = async <K extends NewsFlowCommand>(
    name: K,
    payload: CommandRequest<K> = {} as CommandRequest<K>,
  ) => {
    if (visualFixture) {
      setNotice("Visual fixture: команда не запускается.");
      return undefined;
    }
    const labels: Record<string, string> = {
      "run-auto-pipeline":
        "Автоконвейер выполняет этапы. Не закрывайте NewsFlow до завершения.",
      "generate-scenarios": "Генерируются сценарии…",
      "generate-ideas": "Генерируются идеи…",
      "generate-covers": "Создаются обложки через FastGen…",
      "generate-seo": "Создаются SEO-пакеты…",
      "generate-voice": "Создаётся озвучка…",
      "generate-voice-queue": "Готовые сценарии добавляются в очередь озвучки…",
      "index-footage": "Строится локальный ИИ-индекс футажей…",
      "render-montage": "Экспортируется MP4…",
      "run-montage-queue":
        "Очередь монтажа запущена: сначала подбираются футажи, затем создаются MP4.",
      "download-web-footage": "Скачивается выбранный футаж…",
      "clear-production-queue": "Удаление производства…",
    };
    const successLabels: Record<string, string> = {
      "clear-production-queue": "Производство удалено.",
    };
    setNotice(labels[name] || "Выполняется действие NewsFlow…");
    try {
      const state = await window.newsflowDesktop?.command(name, payload);
      if (state) {
        setData(state);
        setNotice(successLabels[name] || "Сохранено в проекте NewsFlow.");
      }
      return state;
    } catch (error) {
      const detail = humanCommandError(error);
      setNotice(
        detail
          ? `Не выполнено: ${detail}`
          : "Команда не выполнилась. Проверьте настройки ядра NewsFlow.",
      );
    }
  };

  return (
    <WorkspaceErrorBoundary workspace="NewsFlow Studio" onRetry={() => void refresh()}>
    <AppShell sidebarCollapsed={uiPreferences.sidebarCollapsed} density={uiPreferences.density}
      sidebar={<Sidebar
        brand={<div className="brand"><div className="brand-mark">N</div><div><strong>NEWSFLOW</strong><small>НОВОСТНЫЕ РОЛИКИ</small></div></div>}
        status={<div><b>Система готова</b><small>{data.chromeSessions.length ? `Сессий Chrome: ${data.chromeSessions.length}` : "Подключите сессии Chrome"}</small></div>}
        collapsed={uiPreferences.sidebarCollapsed}
        onToggle={() => setUiPreferences((current) => ({ ...current, sidebarCollapsed: !current.sidebarCollapsed }))}
      >
          <button
            className={page === "dashboard" ? "active" : ""}
            onClick={() => navigate("dashboard")}
          >
            <LayoutDashboard />
            <span>Центр управления</span>
          </button>
          {navigation.map((group) => (
            <NavGroup
              key={group.label}
              group={group}
              page={page}
              setPage={navigate}
            />
          ))}
        </Sidebar>}
      header={!isPublicationV2 ? <PageHeader eyebrow={page === "dashboard" ? "РАБОЧЕЕ ПРОСТРАНСТВО" : "NEWSFLOW STUDIO"} title={<><Icon size={27} />{meta.title}</>} description={meta.subtitle} meta={<><StatCard label="Ожидают" value={data.counts.ideas} /><StatCard label="В работе" value={page === "editor" ? data.montageTasks.filter((task) => !["Готово", "Ошибка"].includes(task.status || "")).length : 0} tone="info" /><StatCard label="Готово" value={data.counts.montage} tone="success" /></>} /> : null}
      notice={notice ? <Toast message={notice} onDismiss={() => setNotice("")} /> : null}
      taskCenter={<>
        {uiPreferences.inspectorCollapsed ? (
          <div className="toolbar compact" aria-label="Управление инспектором">
            <UiButton
              variant="secondary"
              onClick={() => setUiPreferences((current) => ({ ...current, inspectorCollapsed: false }))}
            >
              Развернуть инспектор
            </UiButton>
          </div>
        ) : null}
        <TaskCenter
          data={data}
          onSelect={(entry) => {
            setSelectedTask(entry);
            setUiPreferences((current) => ({ ...current, inspectorCollapsed: false }));
          }}
        />
      </>}
      inspector={uiPreferences.inspectorCollapsed ? undefined : <ContextInspector
        entry={selectedTask}
        width={uiPreferences.inspectorWidth}
        density={uiPreferences.density}
        onDensityChange={(density) => setUiPreferences((current) => ({ ...current, density }))}
        onWidthChange={(inspectorWidth) => setUiPreferences((current) => ({ ...current, inspectorWidth }))}
        onClose={() => setSelectedTask(null)}
        onHide={() => setUiPreferences((current) => ({ ...current, inspectorCollapsed: true }))}
      />}
      inspectorWidth={uiPreferences.inspectorWidth}
    >
        {page === "dashboard" ? (
          <Dashboard
            stats={stats}
            target={target}
            setTarget={setTarget}
            saveTarget={saveTarget}
            autoEnabled={data.autoMontageEnabled}
            autoStages={data.autoPipelineStages}
            command={command}
            go={navigate}
          />
        ) : null}
        {page === "ideas" ? (
          <Ideas data={data} go={navigate} command={command} onNotice={setNotice} />
        ) : null}
        {page === "scenarios" ? (
          <Scenarios
            data={data}
            go={navigate}
            command={command}
            refresh={refresh}
          />
        ) : null}
        {page === "scripts" ? (
          <FinishedScripts data={data} go={navigate} command={command} />
        ) : null}
        {page === "templates" ? (
          <TemplateEditor data={data} command={command} onDirtyChange={setTemplateDirty} onSaveRequest={registerTemplateSave} />
        ) : null}
        {page === "agents" ? <Agents data={data} go={navigate} /> : null}
        {page === "covers" ? <WorkspaceErrorBoundary workspace="Covers" onRetry={() => void refresh()}><Covers data={data} command={command} /></WorkspaceErrorBoundary> : null}
        {page === "coverGallery" ? (
          <CoverGallery data={data} command={command} />
        ) : null}
        {page === "media" ? <Media data={data} command={command} /> : null}
        {page === "seo" ? <Seo data={data} command={command} /> : null}
        {page === "tags" ? <Tags data={data} command={command} /> : null}
        {page === "footage" ? (
          <Footage data={data} command={command} refresh={refresh} />
        ) : null}
        {page === "cutter" ? <Cutter data={data} command={command} /> : null}
        {page === "editor" ? (
          <WorkspaceErrorBoundary workspace="Montage" onRetry={() => void refresh()}><Editor data={data} command={command} refresh={refresh} /></WorkspaceErrorBoundary>
        ) : null}
        {page === "outputs" ? <Outputs data={data} command={command} /> : null}
        {page === "publication" || page === "allocation" || page === "automation" ? (
          <WorkspaceErrorBoundary workspace="Publication" onRetry={() => void refresh()}><PublicationPage data={data} command={command} /></WorkspaceErrorBoundary>
        ) : null}
        {page === "voice" ? (
          <WorkspaceErrorBoundary workspace="Voice" onRetry={() => void refresh()}><VoiceQueue
            data={data}
            go={navigate}
            command={command}
            refresh={refresh}
          /></WorkspaceErrorBoundary>
        ) : null}
        {page === "voices" ? (
          <VoiceProfilesScreen data={data} command={command} go={navigate} />
        ) : null}
        {page === "audio" ? <Audio data={data} command={command} /> : null}
        {page === "analytics" ? (
          <WorkspaceErrorBoundary workspace="Analytics" onRetry={() => void refresh()}><AnalyticsDashboard data={data} command={command} /></WorkspaceErrorBoundary>
        ) : null}
        {page === "sessions" ? (
          <Sessions data={data} command={command} />
        ) : null}
        {page === "keys" ? <Keys data={data} command={command} onDirtyChange={setKeysDirty} onSaveRequest={registerKeysSave} /> : null}
        {page === "knowledge" ? (
          <Knowledge data={data} command={command} onDirtyChange={setKnowledgeDirty} onSaveRequest={registerKnowledgeSave} />
        ) : null}
        {[
          "dashboard",
          "ideas",
          "scenarios",
          "scripts",
          "templates",
          "agents",
          "covers",
          "coverGallery",
          "media",
          "seo",
          "tags",
          "publication",
          "footage",
          "cutter",
          "editor",
          "outputs",
          "voice",
          "voices",
          "audio",
          "analytics",
          "sessions",
          "keys",
          "knowledge",
        ].includes(page)
          ? null
          : null}
    </AppShell>
    <Dialog
      open={pendingNavigation !== null}
      onOpenChange={(open) => { if (!open) setPendingNavigation(null); }}
      title="Несохранённые изменения"
      description={pendingNavigation?.source === "keys"
        ? "Новый API-ключ ещё не был отправлен в защищённое хранилище. Перед переходом сохраните его, отбросьте форму или продолжите редактирование."
        : pendingNavigation?.source === "knowledge"
        ? "Подключение Obsidian изменено. Перед переходом сохраните настройки, отбросьте их или продолжите редактирование."
        : "Шаблон сценария изменён. Перед переходом сохраните черновик, отбросьте его или продолжите редактирование."}
    >
      <div className="nf-dialog-actions">
        <UiButton variant="secondary" onClick={() => setPendingNavigation(null)}>
          Продолжить редактирование
        </UiButton>
        <UiButton
          variant="secondary"
          onClick={() => {
            const pending = pendingNavigation;
            setPendingNavigation(null);
            if (pending?.source === "templates") setTemplateDirty(false);
            if (pending?.source === "knowledge") setKnowledgeDirty(false);
            if (pending?.source === "keys") setKeysDirty(false);
            if (pending) commitNavigation(pending.nextPage);
          }}
        >
          Не сохранять
        </UiButton>
        <UiButton
          variant="primary"
          onClick={() => void (async () => {
            const pending = pendingNavigation;
            const saved = await (pending?.source === "knowledge" ? knowledgeSaveRef.current : pending?.source === "keys" ? keysSaveRef.current : templateSaveRef.current)?.();
            if (saved && pending) {
              setPendingNavigation(null);
              commitNavigation(pending.nextPage);
            }
          })()}
        >
          Сохранить и перейти
        </UiButton>
      </div>
    </Dialog>
    <CommandPalette
      open={commandPaletteOpen}
      onOpenChange={setCommandPaletteOpen}
      onNavigate={navigate}
      items={workspaceSearchItems}
    />
    </WorkspaceErrorBoundary>
  );
}

function NavGroup({
  group,
  page,
  setPage,
}: {
  group: (typeof navigation)[number];
  page: Page;
  setPage: (page: Page) => void;
}) {
  const [open, setOpen] = useState(group.label === "ПОДГОТОВКА");
  return (
    <section className="nav-group">
      <button className="nav-group-title" onClick={() => setOpen(!open)}>
        <span>{group.label}</span>
        <ChevronDown className={open ? "" : "closed"} size={14} />
      </button>
      {open &&
        group.entries.map(([id, label, Icon]) => (
          <button
            key={id}
            className={page === id ? "active" : ""}
            onClick={() => setPage(id)}
          >
            <Icon />
            <span>{label}</span>
          </button>
        ))}
    </section>
  );
}

export function Dashboard({
  stats,
  target,
  setTarget,
  saveTarget,
  autoEnabled,
  autoStages,
  command,
  go,
}: {
  stats: Array<[number, string]>;
  target: string;
  setTarget: (v: string) => void;
  saveTarget: () => void;
  autoEnabled: boolean;
  autoStages: NewsFlowSnapshot["autoPipelineStages"];
  command: Command;
  go: (p: Page) => void;
}) {
  const [automatic, setAutomatic] = useState(autoEnabled);
  const [stages, setStages] = useState(autoStages);
  useEffect(() => setAutomatic(autoEnabled), [autoEnabled]);
  useEffect(() => setStages(autoStages), [autoStages]);
  const toggleAutomatic = (enabled: boolean) => {
    setAutomatic(enabled);
    void command("save-settings", { autoMontageEnabled: enabled });
  };
  const toggleStage = (stage: keyof NewsFlowSnapshot["autoPipelineStages"]) => {
    const next = { ...stages, [stage]: !stages[stage] };
    setStages(next);
    void command("save-settings", { autoPipelineStages: next });
  };
  const runAuto = () =>
    void command("run-auto-pipeline", { enabled: true, stages });
  const steps: Array<[string, string, Page, typeof Sparkles]> = [
    ["01", "Идеи", "ideas", Sparkles],
    ["02", "Сценарии", "scenarios", Newspaper],
    ["03", "Озвучка", "voice", Mic2],
    ["04", "Футажи", "footage", Video],
    ["05", "Монтаж", "editor", MonitorPlay],
  ];
  return (
    <section className="nf-control-room" aria-label="Готовность Production Control Room">
      <div className="pipeline panel">
        <div>
          <span>КОНВЕЙЕР</span>
          <b>Цель выпуска</b>
          <input aria-label="Цель выпуска" value={target} onChange={(e) => setTarget(e.target.value)} />
          <Button onClick={saveTarget}>Сохранить</Button>
        </div>
        <div className="pipeline-counts">
          {stats.map(([value, label]) => (
            <span key={label}>
              <b>
                {value} / {target}
              </b>
              <small>{label}</small>
            </span>
          ))}
        </div>
      </div>
      <section className="hero panel">
        <div>
          <span className="eyebrow">НОВЫЙ ВЫПУСК</span>
          <h2>
            Соберите новостные ролики
            <br />
            по понятной цепочке
          </h2>
          <p>
            Идеи вы выбираете вручную. Остальные этапы можно передавать дальше
            вручную или запустить автоконвейером.
          </p>
          <div className="auto-toggle"><Switch label="Автоконвейер" checked={automatic} onCheckedChange={toggleAutomatic} /><small>После одобренных идей выполняет настроенные этапы по цепочке.</small></div>
        </div>
        <div className="hero-actions">
          <Button kind="primary" onClick={() => go("ideas")}>
            <Sparkles size={17} />
            Создать выпуск
          </Button>
          <Button kind="success" onClick={runAuto}>
            <Play size={17} />
            Запустить автоэтапы
          </Button>
          <Button onClick={() => go("outputs")}>
            <FolderOpen size={17} />
            Результаты
          </Button>
        </div>
      </section>
      <section className="panel auto-stage-panel">
        <div className="panel-title">
          <div>
            <b>Цепочка автоконвейера</b>
            <small>
              Идеи остаются ручным шагом. Выберите, какие этапы запускать после
              их одобрения.
            </small>
          </div>
          <span className="status">
            {Object.values(stages).filter(Boolean).length} из{" "}
            {Object.keys(stages).length}
          </span>
        </div>
        <div className="auto-stage-grid">
          {(
            [
              ["scenarios", "Сценарии", "Создать тексты по одобренным идеям"],
              ["covers", "Обложки", "Передать сценарии в FastGen"],
              ["seo", "SEO-пакеты", "Заголовки, описание и теги"],
              ["voice", "Озвучка", "Создать MP3 выбранными голосами"],
              ["montage", "Монтаж", "Подобрать футажи и собрать MP4"],
              ["package", "Готовые папки", "Собрать MP4, обложку и SEO вместе"],
            ] as Array<
              [keyof NewsFlowSnapshot["autoPipelineStages"], string, string]
            >
          ).map(([id, title, text], index) => (
            <label
              className={stages[id] ? "auto-stage enabled" : "auto-stage"}
              key={id}
            >
              <input
                type="checkbox"
                checked={stages[id]}
                onChange={() => toggleStage(id)}
              />
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <b>{title}</b>
                <small>{text}</small>
              </div>
            </label>
          ))}
        </div>
      </section>
      <section className="summary">
        {stats.map(([value, label], i) => (
          <article className="metric panel" key={label}>
            <StatCard label={label} value={value} tone={i === 3 ? "success" : "info"} />
            <small>
              {i === 0
                ? "ожидают отбора"
                : i === 1
                  ? "готовы к озвучке"
                  : i === 2
                    ? "MP3 созданы"
                    : "MP4 готовы"}
            </small>
          </article>
        ))}
      </section>
      <section className="panel workflow">
        <div className="panel-title">
          <div>
            <b>Рабочий маршрут</b>
            <small>Открывайте любой этап вручную — данные не потеряются.</small>
          </div>
        </div>
        <div className="steps">
          {steps.map(([number, title, id, Icon]) => (
            <button key={id} onClick={() => go(id)}>
              <span>{number}</span>
              <Icon size={22} />
              <b>{title}</b>
              <small>Открыть этап →</small>
            </button>
          ))}
        </div>
      </section>
    </section>
  );
}

export function Ideas({
  data,
  go,
  command,
  onNotice,
}: {
  data: NewsFlowSnapshot;
  go: (p: Page) => void;
  command: Command;
  onNotice?: (message: string) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [planCountDrafts, setPlanCountDrafts] = useState<Record<string, string>>({});
  const [customTopic, setCustomTopic] = useState("");
  const [suggestedSelected, setSuggestedSelected] = useState<string[]>([]);
  const [ideasSelected, setIdeasSelected] = useState<string[]>([]);
  const [requirements, setRequirements] = useState("");
  const [vectors, setVectors] = useState("5");
  const [provider, setProvider] = useState<"agent" | "openai">("agent");
  const [presetName, setPresetName] = useState("");
  const [generationError, setGenerationError] = useState("");
  const [generationSummary, setGenerationSummary] = useState<{
    generated?: number; suggested?: number; accepted?: number; needsResearch?: number; rejected?: number;
  } | null>(null);
  const [presetError, setPresetError] = useState("");
  const [resultsError, setResultsError] = useState("");
  const [youtubeOpen, setYoutubeOpen] = useState(false);
  const [referenceOpen, setReferenceOpen] = useState(false);
  const [referenceCount, setReferenceCount] = useState("8");
  const [referenceUrl, setReferenceUrl] = useState("");
  const [referenceLabel, setReferenceLabel] = useState("");
  const [referenceRules, setReferenceRules] = useState(data.ideaReferenceRules);
  const [youtubeQuery, setYoutubeQuery] = useState("");
  const [youtubeCount, setYoutubeCount] = useState("6");
  const [youtubeGenerateTogether, setYoutubeGenerateTogether] = useState(false);
  const [youtubeSelected, setYoutubeSelected] = useState<string[]>([]);
  const [youtubeIncludeMine, setYoutubeIncludeMine] = useState(true);
  const [titleFormulaOnly, setTitleFormulaOnly] = useState(false);
  const [youtubeError, setYoutubeError] = useState("");
  const [generationOpen, setGenerationOpen] = useState(false);
  const deleteSelectedTopicsLock = useRef(false);
  const [deletingSelectedTopics, setDeletingSelectedTopics] = useState(false);
  const clearProductionLock = useRef(false);
  const [deletingProduction, setDeletingProduction] = useState(false);
  const [productionResetOpen, setProductionResetOpen] = useState(false);
  const [productionResetPhrase, setProductionResetPhrase] = useState("");
  const generationLock = useRef(false);
  const [generatingIdeas, setGeneratingIdeas] = useState(false);
  const suggestDirectionsLock = useRef(false);
  const [suggestingDirections, setSuggestingDirections] = useState(false);
  const referenceAnalysisLock = useRef(false);
  const [analyzingReferenceChannels, setAnalyzingReferenceChannels] = useState(false);
  const youtubeResearchLock = useRef(false);
  const [researchingYoutube, setResearchingYoutube] = useState(false);
  useEffect(
    () => setReferenceRules(data.ideaReferenceRules),
    [data.ideaReferenceRules],
  );
  useEffect(() => {
    setPlanCountDrafts((current) =>
      Object.fromEntries(
        data.ideaPlan.map((item) => [
          item.topic,
          current[item.topic] ?? String(item.count),
        ]),
      ),
    );
  }, [data.ideaPlan]);
  useEffect(
    () => setSelected((current) => current.filter((topic) => data.ideaTopics.includes(topic))),
    [data.ideaTopics],
  );
  useEffect(
    () => setSuggestedSelected((current) => current.filter((topic) => data.ideaSuggestedTopics.includes(topic))),
    [data.ideaSuggestedTopics],
  );
  useEffect(
    () => setYoutubeSelected((current) => current.filter((topic) => data.youtubeSuggestedTopics.includes(topic))),
    [data.youtubeSuggestedTopics],
  );
  useEffect(
    () => setIdeasSelected((current) => current.filter((idea) => data.ideaResults.includes(idea))),
    [data.ideaResults],
  );
  const plannedTopicCount = data.ideaPlan.length;
  const plannedVectorCount = data.ideaPlan.reduce(
    (total, item) =>
      total + Math.max(0, Number(planCountDrafts[item.topic] ?? item.count) || 0),
    0,
  );
  const selectedVectorCount = selected.length * Math.max(1, Number(vectors) || 1);
  const allTopicsSelected = data.ideaTopics.length > 0 && selected.length === data.ideaTopics.length;
  const toggleAllTopics = () =>
    setSelected(allTopicsSelected ? [] : [...data.ideaTopics]);
  const favoriteTopicColumns = useMemo<ColumnDef<{ topic: string }>[]>(
    () => [
      {
        id: "select",
        header: () => (
          <input
            aria-label="Выбрать все темы"
            checked={allTopicsSelected}
            className="nf-topic-selector"
            onChange={toggleAllTopics}
            type="checkbox"
          />
        ),
        cell: ({ row }) => {
          const topic = row.original.topic;
          return (
            <input
              aria-label={`Выбрать ${topic}`}
              checked={selected.includes(topic)}
              className="nf-topic-selector"
              onChange={() =>
                setSelected((current) =>
                  current.includes(topic)
                    ? current.filter((value) => value !== topic)
                    : [...current, topic],
                )
              }
              type="checkbox"
            />
          );
        },
      },
      {
        accessorKey: "topic",
        header: "Направление",
        cell: ({ row }) => (
          <button
            className={`nf-topic-title${selected.includes(row.original.topic) ? " selected" : ""}`}
            onClick={(event) => toggle(row.original.topic, event.ctrlKey || event.metaKey)}
            type="button"
          >
            {row.original.topic}
          </button>
        ),
      },
      {
        id: "selection",
        header: "Статус",
        cell: ({ row }) => selected.includes(row.original.topic) ? "Выбрано" : "Готово к плану",
      },
    ],
    [allTopicsSelected, data.ideaTopics, selected],
  );
  const toggle = (topic: string, multi: boolean) =>
    setSelected((current) =>
      multi
        ? current.includes(topic)
          ? current.filter((v) => v !== topic)
          : [...current, topic]
        : [topic],
    );
  const toggleSuggested = (topic: string) =>
    setSuggestedSelected((current) =>
      current.includes(topic)
        ? current.filter((value) => value !== topic)
        : [...current, topic],
    );
  const toggleIdea = (idea: string, multi: boolean) =>
    setIdeasSelected((current) =>
      multi
        ? current.includes(idea)
          ? current.filter((value) => value !== idea)
          : [...current, idea]
        : [idea],
    );
  const addTopic = async () => {
    const topic = customTopic.trim();
    if (!topic) {
      setGenerationError("Введите название своего направления.");
      return;
    }
    setGenerationError("");
    const result = await command("add-topic", { topic });
    if (result) {
      setCustomTopic("");
      setSelected((current) =>
        current.includes(topic) ? current : [...current, topic],
      );
    }
  };
  const suggestDirections = async () => {
    if (suggestDirectionsLock.current) return;
    suggestDirectionsLock.current = true;
    setSuggestingDirections(true);
    try {
      const result = await command("suggest-topics", {
        provider,
        count: 6,
        planCount: Number(vectors),
      });
      if (result) setSuggestedSelected([]);
    } finally {
      suggestDirectionsLock.current = false;
      setSuggestingDirections(false);
    }
  };
  const saveSuggestedToFavorites = async () => {
    if (!suggestedSelected.length) {
      setGenerationError(
        "Отметьте предложения агента, которые хотите сохранить в избранное.",
      );
      return;
    }
    const result = await command("add-suggested-topics-to-favorites", {
      topics: suggestedSelected,
    });
    if (result) setSuggestedSelected([]);
  };
  const clearSuggested = async () => {
    const result = await command("clear-suggested-topics");
    if (result) setSuggestedSelected([]);
  };
  const rejectSuggested = async () => {
    if (!suggestedSelected.length) {
      setGenerationError("Отметьте предложения, которые нужно отклонить.");
      return;
    }
    const result = await command("reject-suggested-topics", {
      topics: suggestedSelected,
    });
    if (result) setSuggestedSelected([]);
  };
  const addReferenceChannel = async () => {
    const url = referenceUrl.trim();
    if (!url) {
      setGenerationError("Вставьте публичную ссылку на YouTube‑канал.");
      return;
    }
    const label = referenceLabel.trim() || url;
    setGenerationError("");
    const result = await command("add-idea-reference-channel", { url, label });
    if (result) {
      setReferenceUrl("");
      setReferenceLabel("");
    }
  };
  const analyzeReferenceChannels = async () => {
    if (referenceAnalysisLock.current) return;
    referenceAnalysisLock.current = true;
    setAnalyzingReferenceChannels(true);
    try {
      const result = await command("analyze-idea-reference-channels", {
        count: Number(referenceCount),
        planCount: Number(vectors),
      });
      if (!result)
        setGenerationError(
          "Анализ каналов не выполнился. Проверьте уведомление сверху.",
        );
    } finally {
      referenceAnalysisLock.current = false;
      setAnalyzingReferenceChannels(false);
    }
  };
  const saveReferenceRules = async () => {
    const result = await command("save-idea-reference-rules", {
      rules: referenceRules,
    });
    if (!result) setGenerationError("Не удалось сохранить правила анализа.");
  };
  const deleteSelectedFavorites = async () => {
    if (deleteSelectedTopicsLock.current) return;
    if (!selected.length) {
      setGenerationError(
        "Выберите направления справа, которые нужно удалить из избранного.",
      );
      return;
    }
    if (!window.confirm(`Удалить выбранные темы: ${selected.length}? Остальные темы останутся без изменений.`)) return;
    deleteSelectedTopicsLock.current = true;
    setDeletingSelectedTopics(true);
    try {
      const result = await command("delete-topics", { topics: selected });
      if (result) setSelected([]);
    } finally {
      deleteSelectedTopicsLock.current = false;
      setDeletingSelectedTopics(false);
    }
  };
  const addSelectedToPlan = () => {
    if (selected.length)
      void command("add-topics-to-plan", {
        topics: selected,
        count: Number(vectors),
        provider,
        requirements,
      });
  };
  const saveRoute = () => {
    if (selected.length)
      void command("set-idea-route", { topics: selected, provider, requirements });
  };
  const savePreset = async () => {
    const name = presetName.trim();
    if (!name) {
      setPresetError(
        "Введите название пресета в поле ниже, затем сохраните его.",
      );
      return;
    }
    setPresetError("");
    const result = await command("save-idea-route-preset", {
      name,
      provider,
      requirements,
    });
    if (result) setPresetName("");
    else
      setPresetError(
        "Не удалось сохранить пресет. Проверьте уведомление сверху.",
      );
  };
  const applyPreset = (name: string) => {
    const preset = data.ideaRoutePresets.find((item) => item.name === name);
    if (!preset) return;
    setProvider(preset.provider === "openai" ? "openai" : "agent");
    setRequirements(preset.requirements || "");
  };
  const importPrompt = async () => {
    const content = await window.newsflowDesktop?.choosePromptText();
    if (content) setRequirements(content);
  };
  const generate = async () => {
    if (generationLock.current) return;
    // No selection means "run the prepared plan".  Do not feed every row
    // back as a new selection: that would overwrite its own count and route.
    const requestedTopics = selected.length ? selected : [];
    if (!requestedTopics.length && !data.ideaPlan.length) {
      setGenerationError(
        "Добавьте хотя бы одно направление в план выпуска или выделите его в сетке.",
      );
      return;
    }
    setGenerationError("");
    setGenerationSummary(null);
    generationLock.current = true;
    setGeneratingIdeas(true);
    try {
      const result = await command("generate-ideas", {
        topics: requestedTopics,
        count: Number(vectors),
        provider,
        requirements,
        titleFormulaOnly,
      });
      if (!result) {
        setGenerationError(
          "Не удалось сгенерировать идеи. Проверьте уведомление сверху: там указана точная причина.",
        );
        return;
      }
      const summary = result.operationResult?.kind === "ideas"
        ? result.operationResult.generation
        : undefined;
      if (!summary) {
        setGenerationError("Генерация завершилась без отчёта. Повторите попытку; результат не принят.");
        return;
      }
      setGenerationSummary(summary);
      if (!summary.generated) {
        setGenerationError("Провайдер не вернул заголовков. Идеи не были добавлены.");
      }
    } finally {
      generationLock.current = false;
      setGeneratingIdeas(false);
    }
  };
  const deleteSelectedIdeas = async () => {
    if (!ideasSelected.length) {
      setResultsError("Выберите идеи, которые нужно удалить.");
      return;
    }
    setResultsError("");
    const result = await command("delete-idea-results", {
      ideas: ideasSelected,
    });
    if (result) setIdeasSelected([]);
    else
      setResultsError("Не удалось удалить идеи. Проверьте уведомление сверху.");
  };
  const clearIdeas = async () => {
    setResultsError("");
    const result = await command("delete-idea-results", { all: true });
    if (result) setIdeasSelected([]);
    else
      setResultsError(
        "Не удалось очистить список. Проверьте уведомление сверху.",
      );
  };
  const startNewRelease = () => {
    if (clearProductionLock.current) return;
    setProductionResetPhrase("");
    setProductionResetOpen(true);
  };
  const confirmNewRelease = async () => {
    if (clearProductionLock.current) return;
    const normalizedPhrase = productionResetPhrase.trim();
    if (normalizedPhrase !== "УДАЛИТЬ ПРОИЗВОДСТВО") {
      onNotice?.("Фраза подтверждения не совпадает. Производство не удалено.");
      return;
    }
    clearProductionLock.current = true;
    setDeletingProduction(true);
    try {
      const result = await command("clear-production-queue", {
        confirmed: true,
        confirmationPhrase: normalizedPhrase,
      });
      if (result) {
        setProductionResetOpen(false);
        setProductionResetPhrase("");
        onNotice?.("Производство удалено.");
      }
    } finally {
      clearProductionLock.current = false;
      setDeletingProduction(false);
    }
  };
  const regenerateSelectedIdeas = async () => {
    if (!ideasSelected.length) {
      setResultsError(
        "Выберите идеи для замены. Каждая будет перегенерирована по своему исходному направлению.",
      );
      return;
    }
    setResultsError("");
    const result = await command("regenerate-idea-results", {
      ideas: ideasSelected,
      requirements,
    });
    if (result) setIdeasSelected([]);
    else
      setResultsError(
        "Не удалось перегенерировать идеи. Проверьте уведомление сверху.",
      );
  };
  const researchYoutube = async () => {
    if (youtubeResearchLock.current) return;
    if (!youtubeQuery.trim() && !selected.length) {
      setYoutubeError(
        "Введите запрос для YouTube или выделите направления в сетке.",
      );
      return;
    }
    setYoutubeError("");
    youtubeResearchLock.current = true;
    setResearchingYoutube(true);
    try {
      const result = await command("research-youtube-topics", {
        query: youtubeQuery,
        topics: selected,
        count: Number(youtubeCount),
        generateTogether: youtubeGenerateTogether,
        vectors: Number(vectors),
        provider,
        requirements,
      });
      if (!result)
        setYoutubeError(
          "Поиск не выполнился. Проверьте уведомление сверху: там указана точная причина.",
        );
      else if (!youtubeGenerateTogether)
        setYoutubeSelected(result.youtubeSuggestedTopics || []);
    } finally {
      youtubeResearchLock.current = false;
      setResearchingYoutube(false);
    }
  };
  const toggleYoutubeTopic = (topic: string) =>
    setYoutubeSelected((current) =>
      current.includes(topic)
        ? current.filter((item) => item !== topic)
        : [...current, topic],
    );
  const generateYoutubeVectors = async () => {
    const topics = [
      ...(youtubeIncludeMine ? selected : []),
      ...youtubeSelected,
    ];
    if (!topics.length) {
      setYoutubeError(
        "Сначала выберите хотя бы одну предложенную YouTube‑тему.",
      );
      return;
    }
    setYoutubeError("");
    const result = await command("generate-ideas", {
      topics,
      count: Number(vectors),
      provider,
      requirements,
      onlyRequested: true,
    });
    if (!result)
      setYoutubeError(
        "Не удалось создать векторы. Проверьте уведомление сверху.",
      );
  };
  const clearYoutubeTopics = async () => {
    setYoutubeError("");
    const result = await command("clear-youtube-suggested-topics");
    if (result) setYoutubeSelected([]);
    else
      setYoutubeError(
        "Не удалось очистить YouTube‑темы. Проверьте уведомление сверху.",
      );
  };
  const rejectYoutubeTopics = async () => {
    if (!youtubeSelected.length) {
      setYoutubeError(
        "Отметьте YouTube‑темы, которые нужно отклонить.",
      );
      return;
    }
    setYoutubeError("");
    const result = await command("reject-suggested-topics", {
      topics: youtubeSelected,
      source: "youtube",
    });
    if (result) setYoutubeSelected([]);
    else
      setYoutubeError(
        "Не удалось отклонить темы. Проверьте уведомление сверху.",
      );
  };
  const saveYoutubeSuggestedToFavorites = async () => {
    if (!youtubeSelected.length) {
      setYoutubeError("Отметьте YouTube‑темы, которые хотите сохранить в избранное.");
      return;
    }
    const result = await command("add-suggested-topics-to-favorites", {
      topics: youtubeSelected,
      source: "youtube",
    });
    if (result) setYoutubeSelected([]);
  };
  const addIdeas = async () => {
    if (!ideasSelected.length) {
      setResultsError("Сначала отметьте одну или несколько идей.");
      return;
    }
    const result = await command("add-ideas-to-scenarios", {
      ideas: ideasSelected,
    });
    if (result) {
      setIdeasSelected([]);
      go("scenarios");
    }
  };
  const transferIdeas = async (
    target: "scenarios" | "covers" | "seo" | "voice",
  ) => {
    const ideas = ideasSelected.length ? ideasSelected : data.ideaResults;
    if (!ideas.length) {
      setResultsError(
        "Нет идей для передачи. Сначала сгенерируйте или добавьте их.",
      );
      return;
    }
    setResultsError("");
    const result = await command("transfer-ideas", { ideas, target });
    if (result) {
      setIdeasSelected([]);
      go(target === "scenarios" ? "scenarios" : target);
    }
  };
  return (
    <section className="nf-ideas nf-editorial-workspace" aria-label="Editorial Workspace">
      <Toolbar label="Действия с направлениями">
        <div className="custom-topic-entry">
          <Input
            label="Новая тема"
            value={customTopic}
            onChange={(event) => setCustomTopic(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void addTopic();
            }}
            placeholder="Новая тема — например: Ближний Восток и нефть"
          />
          <Button kind="primary" onClick={() => void addTopic()}>
            <Plus size={17} />
            Добавить тему
          </Button>
        </div>
        <Button
          disabled={suggestingDirections}
          onClick={() => void suggestDirections()}
        >
          <WandSparkles size={17} />
          {suggestingDirections ? "Агент подбирает направления…" : "Агент предложит направления"}
        </Button>
        <Button onClick={() => setReferenceOpen((value) => !value)}>
          <Video size={17} />
          Каналы-референсы
        </Button>
        <Button onClick={() => setYoutubeOpen((value) => !value)}>
          <BarChart3 size={17} />
          YouTube-темы
        </Button>
        <Button kind="success" disabled={generatingIdeas} onClick={generate}>
          <Sparkles size={17} />
          {generatingIdeas ? "Генерация идей…" : "Сгенерировать идеи"}
        </Button>
        <Checkbox
          label="Только трёхчастная формула"
          checked={titleFormulaOnly}
          onCheckedChange={setTitleFormulaOnly}
        />
        <Button onClick={() => setGenerationOpen(true)}>
          <Settings2 size={17} />
          Настроить генерацию
        </Button>
        <Button
          kind="danger"
          disabled={deletingProduction}
          onClick={() => void startNewRelease()}
        >
          <Trash2 size={17} />
          {deletingProduction ? "Удаление производства…" : "Удалить всё производство"}
        </Button>
      </Toolbar>
      <Dialog
        open={productionResetOpen}
        onOpenChange={(open) => {
          if (deletingProduction) return;
          setProductionResetOpen(open);
          if (!open) {
            setProductionResetPhrase("");
            onNotice?.("Удаление производства отменено.");
          }
        }}
        title="Удалить всё производство"
        description="Ключи, каналы, OAuth и постоянные настройки сохранятся. Очереди и результаты текущего выпуска будут очищены."
      >
        <Input
          label="Контрольная фраза"
          value={productionResetPhrase}
          onChange={(event) => setProductionResetPhrase(event.target.value)}
          placeholder="УДАЛИТЬ ПРОИЗВОДСТВО"
          autoFocus
        />
        <small>Для подтверждения введите точно: УДАЛИТЬ ПРОИЗВОДСТВО</small>
        <div className="toolbar">
          <Button
            onClick={() => {
              setProductionResetOpen(false);
              setProductionResetPhrase("");
              onNotice?.("Удаление производства отменено.");
            }}
            disabled={deletingProduction}
          >
            Отмена
          </Button>
          <Button kind="danger" onClick={() => void confirmNewRelease()} disabled={deletingProduction}>
            {deletingProduction ? "Удаление производства…" : "Подтвердить удаление"}
          </Button>
        </div>
      </Dialog>
      <section className="panel publication-target-widget">
        <b>
          План публикации: нужно {data.publication.allocation.counters.required}{" "}
          роликов · назначено {data.publication.allocation.counters.assigned} ·
          создать ещё {data.publication.allocation.counters.missing}
        </b>
        <small>
          Цель берётся из конструктора публикации. Выберите направления и
          создайте нужное число тем; каналы и доступы сохраняются при «Новом
          выпуске».
        </small>
      </section>
      {generatingIdeas ? (
        <div className="knowledge-status" role="status">Идёт генерация заголовков…</div>
      ) : null}
      {generationSummary ? (
        <div className="knowledge-status" role="status">
          Сгенерировано: {generationSummary.generated ?? 0}. Предложений: {generationSummary.suggested ?? 0}. Готово: {generationSummary.accepted ?? 0}. На research: {generationSummary.needsResearch ?? 0}. Отклонено: {generationSummary.rejected ?? 0}.
        </div>
      ) : null}
      {data.ideaSuggestedTopics.length ? (
        <section className="panel youtube-vector-panel">
          <div className="youtube-vector-heading">
            <div>
              <b>Предложения агента</b>
              <small>
                Не добавлены в избранные или план выпуска. Отметьте нужные,
                чтобы сохранить их в постоянное избранное справа.
              </small>
            </div>
            <div className="toolbar compact">
              <Button
                kind="success"
                onClick={() => void saveSuggestedToFavorites()}
              >
                <Check size={16} />В избранные ({suggestedSelected.length})
              </Button>
              <Button kind="danger" onClick={() => void rejectSuggested()}>
                <Trash2 size={16} />
                Отклонить выбранные
              </Button>
              <Button kind="danger" onClick={() => void clearSuggested()}>
                <Trash2 size={16} />
                Очистить предложения
              </Button>
            </div>
          </div>
          <div className="youtube-topic-picks">
            {data.ideaSuggestedTopics.map((topic) => (
              <label key={topic}>
                <input
                  aria-label={`Выбрать предложение ${topic}`}
                  type="checkbox"
                  checked={suggestedSelected.includes(topic)}
                  onChange={() => toggleSuggested(topic)}
                />
                <span>
                  {topic}
                  {data.ideaTitleMetadata?.[topic]?.review_status === "NEEDS_RESEARCH" ? " · needs research" : null}
                </span>
              </label>
            ))}
          </div>
        </section>
      ) : null}
      {referenceOpen ? (
        <section className="panel youtube-research">
          <div className="panel-title">
            <div>
              <b>Каналы-референсы</b>
              <small>
                Анализируются только публичные свежие ролики, которые прошли
                отбор по просмотрам в час. Обычные слабые ролики не
                используются.
              </small>
            </div>
            <span className="status">
              {data.ideaReferenceChannels.length} каналов
            </span>
          </div>
          <div className="youtube-research-controls reference-controls">
            <Input label="Сколько новых тем" value={referenceCount} onChange={(event) => setReferenceCount(event.target.value)} type="number" min="1" max="30" />
            <Input label="Ссылка на YouTube-канал" value={referenceUrl} onChange={(event) => setReferenceUrl(event.target.value)} placeholder="https://www.youtube.com/@channel" />
            <Input label="Название в списке" value={referenceLabel} onChange={(event) => setReferenceLabel(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void addReferenceChannel(); }} placeholder="Название канала (необязательно)" />
            <Button kind="primary" onClick={() => void addReferenceChannel()}>
              <Plus size={17} />
              Добавить канал
            </Button>
            <Button
              kind="success"
              disabled={analyzingReferenceChannels}
              onClick={() => void analyzeReferenceChannels()}
            >
              <WandSparkles size={17} />
              {analyzingReferenceChannels ? "Анализ каналов…" : "Найти залетевшие и проанализировать"}
            </Button>
          </div>
          <div className="youtube-source-sample">
            <div>
              <b>Правила заголовков</b>
              <small>
                Эти правила используются при анализе каждого канала и
                сохраняются в проекте.
              </small>
            </div>
            <textarea
              value={referenceRules}
              onChange={(event) => setReferenceRules(event.target.value)}
              aria-label="Правила заголовков каналов-референсов"
            />
            <div className="toolbar compact">
              <Button onClick={() => void saveReferenceRules()}>
                <Check size={16} />
                Сохранить правила
              </Button>
            </div>
          </div>
          {data.ideaReferenceChannels.length ? (
            <div className="youtube-research-results">
              {data.ideaReferenceChannels.map((channel, index) => (
                <div key={`${channel.url}-${index}`}>
                  <b>{channel.label}</b>
                  <small>{channel.url}</small>
                  <Button
                    kind="danger"
                    onClick={() =>
                      void command("remove-idea-reference-channel", { index })
                    }
                  >
                    <Trash2 size={15} />
                    Удалить
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="Добавьте канал-референс"
              text="Вставьте публичную ссылку на канал. NewsFlow не входит в аккаунт и не использует ваши закрытые данные."
            />
          )}
          {data.ideaReferenceAnalysis.length ? (
            <section className="youtube-source-sample">
              <div>
                <b>Ролики, прошедшие отбор</b>
                <small>Сортировка: просмотры в час после публикации.</small>
              </div>
              <div className="youtube-research-results">
                {data.ideaReferenceAnalysis.map((item, index) => (
                  <div key={`${item.url}-${index}`}>
                    <b>{item.title}</b>
                    <span>{item.channel}</span>
                    <small>
                      {item.views.toLocaleString("ru-RU")} просмотров ·{" "}
                      {item.viewsHour.toLocaleString("ru-RU")} в час · возраст{" "}
                      {item.ageHours} ч
                    </small>
                    <Button
                      onClick={() =>
                        void window.open(
                          item.url,
                          "_blank",
                          "noopener,noreferrer",
                        )
                      }
                    >
                      Открыть
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </section>
      ) : null}
      {youtubeOpen ? (
        <section className="panel youtube-research">
          <div className="panel-title">
            <div>
              <b>YouTube-темы через агента</b>
              <small>
                Шаг 1: агент ищет строго по ключевым словам. Шаг 2: вы отмечаете
                хорошие темы и отдельно создаёте для них векторы.
              </small>
            </div>
            <span className="status">Не рейтинг всей платформы</span>
          </div>
          <div className="youtube-research-controls">
            <Input label="Ключевые слова для YouTube" value={youtubeQuery} onChange={(event) => setYoutubeQuery(event.target.value)} placeholder="Например: Ормуз нефть танкеры" />
            <Input label="Сколько тем" value={youtubeCount} onChange={(event) => setYoutubeCount(event.target.value)} type="number" min="1" max="30" />
            <Button
              kind="primary"
              disabled={researchingYoutube}
              onClick={() => void researchYoutube()}
            >
              <Search size={17} />
              {researchingYoutube
                ? "Поиск YouTube…"
                : youtubeGenerateTogether ? "Найти и сгенерировать" : "Найти темы"}
            </Button>
          </div>
          <div className="youtube-research-options">
            <Checkbox label="Быстрый режим: сразу сгенерировать идеи из моих направлений и тем YouTube" checked={youtubeGenerateTogether} onCheckedChange={setYoutubeGenerateTogether} />
            <Button onClick={() => go("keys")}>
              <KeyRound size={16} />
              Добавить ключ YouTube API
            </Button>
          </div>
          <small className="youtube-research-note">
            Нужны смысловые ключевые слова, не цифры: «Ормуз нефть танкеры»,
            «Одесса порт удары». Если поле пустое, используются смысловые слова
            выделенных направлений. С ключом YouTube Data API метрики берутся
            официально.
          </small>
          {youtubeError ? (
            <div className="key-form-error">{youtubeError}</div>
          ) : null}
          {data.youtubeSuggestedTopics.length ? (
            <div className="youtube-vector-panel">
              <div className="youtube-vector-heading">
                <div>
                  <b>Шаг 2. Выберите темы для векторов</b>
                  <small>
                    Выбрано: {youtubeSelected.length} · векторов на тему:{" "}
                    {vectors}
                  </small>
                </div>
                <div className="toolbar compact">
                  <Button
                    disabled={researchingYoutube}
                    onClick={() => void researchYoutube()}
                  >
                    <WandSparkles size={16} />
                    Перегенерировать
                  </Button>
                  <Button
                    kind="danger"
                    onClick={() => void clearYoutubeTopics()}
                  >
                    <Trash2 size={16} />
                    Очистить
                  </Button>
                </div>
              </div>
              <div className="youtube-topic-picks">
                {data.youtubeSuggestedTopics.map((topic) => (
                  <label key={topic}>
                    <input
                      aria-label={`Выбрать YouTube-предложение ${topic}`}
                      type="checkbox"
                      checked={youtubeSelected.includes(topic)}
                      onChange={() => toggleYoutubeTopic(topic)}
                    />
                    <span>{topic}</span>
                  </label>
                ))}
              </div>
              <div className="youtube-vector-actions">
                <Checkbox label={`Также включить мои выделенные направления (${selected.length})`} checked={youtubeIncludeMine} onCheckedChange={setYoutubeIncludeMine} />
                <Button kind="success" onClick={() => void saveYoutubeSuggestedToFavorites()}>
                  <Check size={17} />
                  В избранные
                </Button>
                <Button kind="danger" onClick={() => void rejectYoutubeTopics()}>
                  <Trash2 size={17} />
                  Отклонить выбранные
                </Button>
                <Button
                  kind="success"
                  onClick={() => void generateYoutubeVectors()}
                >
                  <Sparkles size={17} />
                  Создать векторы для выбранных
                </Button>
              </div>
            </div>
          ) : null}
          {data.youtubeResearch?.length ? (
            <section className="youtube-source-sample">
              <div>
                <b>Выборка источников YouTube</b>
                <small>
                  Это не темы: нажмите «Открыть источник», если хотите проверить
                  ролик.
                </small>
              </div>
              <div className="youtube-research-results">
                {data.youtubeResearch.map((item, index) => (
                  <div key={`${item.url}-${index}`}>
                    <b>{item.title}</b>
                    <span>{item.channel || "Канал не указан"}</span>
                    <small>
                      {item.views.toLocaleString("ru-RU")} просмотров ·{" "}
                      {item.likes.toLocaleString("ru-RU")} лайков ·{" "}
                      {item.comments.toLocaleString("ru-RU")} комментариев
                    </small>
                    <Button
                      onClick={() =>
                        void window.open(
                          item.url,
                          "_blank",
                          "noopener,noreferrer",
                        )
                      }
                    >
                      Открыть источник
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </section>
      ) : null}
      <section className="split-ideas">
        <div className="panel release-plan">
          <div className="panel-title">
            <div>
              <b>План выпуска</b>
              <small>Направления и число векторов на каждое</small>
            </div>
          </div>
          <Input label="Векторов для выбранных направлений" value={vectors} onChange={(event) => setVectors(event.target.value)} type="number" min="1" max="500" />
          <div className="topic-counter">
            <b>{selected.length}</b>
            <div>
              <span>выбрано для добавления</span>
              <small>{selected.length} выбрано · {selectedVectorCount} роликов будет создано</small>
            </div>
          </div>
          <Button kind="primary" onClick={addSelectedToPlan}>
            Добавить в план
          </Button>
          <div className="topic-counter plan-summary">
            <b>{plannedTopicCount}</b>
            <div>
              <span>Уже добавлено в план</span>
              <small>
                {plannedTopicCount} направлений · {plannedVectorCount} роликов
              </small>
            </div>
          </div>
          {data.ideaPlan.length ? (
            <div className="plan-mini">
              {data.ideaPlan.map((item, index) => (
                <div key={item.topic}>
                  <input
                    value={planCountDrafts[item.topic] ?? String(item.count)}
                    type="number"
                    min="1"
                    max="500"
                    onChange={(event) =>
                      setPlanCountDrafts((current) => ({ ...current, [item.topic]: event.target.value }))
                    }
                    onBlur={(event) => {
                      const count = Math.max(1, Math.min(500, Number(event.target.value) || 1));
                      setPlanCountDrafts((current) => ({ ...current, [item.topic]: String(count) }));
                      void command("update-idea-plan", { index, count });
                    }}
                  />
                  <span>{item.topic}</span>
                  <Button
                    kind="danger"
                    onClick={() =>
                      void command("update-idea-plan", { index, remove: true })
                    }
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <div className="panel topics">
          <div className="panel-title">
            <div>
              <b>Избранные направления</b>
              <small>
                Отмечайте темы чекбоксами; заголовок поддерживает Ctrl+клик.
                Здесь хранятся только вручную сохранённые направления.
              </small>
            </div>
            <div className="toolbar compact">
              <span className="status">
                {selected.length ? `Выбрано: ${selected.length}` : "Не выбрано"}
              </span>
              <Button onClick={toggleAllTopics}>
                {allTopicsSelected ? "Снять выделение" : "Выбрать все"}
              </Button>
              <Button
                ariaLabel="Удалить выбранные темы"
                kind="danger"
                onClick={() => void deleteSelectedFavorites()}
              >
                <Trash2 size={16} />
                {deletingSelectedTopics ? "Удаление…" : "Удалить выбранные"}
              </Button>
            </div>
          </div>
          <DataTable
            ariaLabel="Избранные направления"
            preferenceKey="ideas-favorite-topics"
            data={data.ideaTopics.map((topic) => ({ topic }))}
            columns={favoriteTopicColumns}
          />
        </div>
      </section>
      <Sheet
        open={generationOpen}
        onOpenChange={setGenerationOpen}
        title="Маршрут генерации"
        description="Настройте текущий provider, требования и пресет перед запуском."
      >
      <section className="panel ai-route">
        <div className="panel-title">
          <div>
            <b>Маршрут генерации</b>
            <small>
              Выберите темы и нажмите «Генерировать»: NewsFlow сам добавит их в
              план. Все роли работают через активные ключи ChatGPT.
            </small>
          </div>
          <div className="toolbar compact">
            <Select
              label="Сохранённые пресеты"
              value=""
              onChange={(event) => applyPreset(event.target.value)}
              options={[{ value: "", label: "Сохранённые пресеты" }, ...data.ideaRoutePresets.map((item) => ({ value: item.name, label: item.name }))]}
            />
            <Button onClick={() => void savePreset()}>Сохранить пресет</Button>
          </div>
        </div>
        <div className="form-row">
          <Select
            label="Поставщик идей"
            value={provider}
            onChange={(event) =>
              setProvider(event.target.value as "agent" | "openai")
            }
            options={[{ value: "agent", label: "Агент NewsFlow — идеи" }, { value: "openai", label: "ChatGPT — прямой режим" }]}
          />
          <Button onClick={saveRoute}>Применить к выбранным</Button>
          <Button kind="primary" onClick={() => void generate()}>
            Генерировать
          </Button>
        </div>
        <div className="preset-name">
          <Input
            label="Название нового пресета"
            value={presetName}
            onChange={(event) => {
              setPresetName(event.target.value);
              setPresetError("");
            }}
            placeholder="Название нового пресета"
          />
          <small>
            Вставьте промпт ниже или загрузите TXT/MD. При сохранении пресета
            сохранится режим и весь текст промпта.
          </small>
        </div>
        <div className="toolbar compact prompt-actions">
          <Button onClick={() => void importPrompt()}>
            <Upload size={16} />
            Загрузить TXT / MD
          </Button>
          <Button kind="danger" onClick={() => setRequirements("")}>
            <Trash2 size={16} />
            Очистить промпт
          </Button>
        </div>
        <Textarea
          label="Требования к генерации"
          value={requirements}
          onChange={(event) => setRequirements(event.target.value)}
          placeholder="Вставьте свой промпт или загрузите TXT/MD — он будет добавлен к задаче генерации…"
        />
        {presetError ? (
          <div className="key-form-error">{presetError}</div>
        ) : null}
        {generationError ? (
          <div className="key-form-error">{generationError}</div>
        ) : null}
        {data.operationResult?.kind === "ideas" &&
        data.operationResult.message ? (
          <div className="knowledge-status">{data.operationResult.message}</div>
        ) : null}
      </section>
      </Sheet>
      <section className="panel result-panel">
        <div className="panel-title">
          <div>
            <b>Найдено идей: {data.ideaResults.length}</b>
            <small>
              Ctrl+клик — несколько. Передача с выделением отправляет отмеченные
              идеи; без выделения — все.
            </small>
          </div>
          <div className="toolbar compact">
            <Button onClick={() => void command("export-ideas")}>
              <Download size={16} />
              Скачать идеи
            </Button>
            <Button onClick={() => void regenerateSelectedIdeas()}>
              <WandSparkles size={16} />
              Перегенерировать
            </Button>
            <Button kind="danger" onClick={() => void deleteSelectedIdeas()}>
              <Trash2 size={16} />
              Удалить выбранные
            </Button>
            <Button kind="danger" onClick={() => void clearIdeas()}>
              <Trash2 size={16} />
              Очистить всё
            </Button>
          </div>
        </div>
        <div className="toolbar compact">
          <Button kind="success" onClick={() => void addIdeas()}>
            <Newspaper size={16} />
            Добавить сценарии
          </Button>
          <Button onClick={() => void transferIdeas("covers")}>
            <Image size={16} />
            {ideasSelected.length ? "В обложки" : "Все → обложки"}
          </Button>
          <Button onClick={() => void transferIdeas("seo")}>
            <Search size={16} />
            {ideasSelected.length ? "В SEO: текст и теги" : "Все → SEO и теги"}
          </Button>
          <Button kind="primary" onClick={() => void transferIdeas("voice")}>
            <Mic2 size={16} />
            {ideasSelected.length ? "В озвучку" : "Все → озвучку"}
          </Button>
        </div>
        {resultsError ? (
          <div className="key-form-error">{resultsError}</div>
        ) : null}
        {(data.operationResult?.kind === "ideas-to-scenarios" ||
          data.operationResult?.kind === "ideas-transfer") &&
        data.operationResult.message ? (
          <div className="knowledge-status">{data.operationResult.message}</div>
        ) : null}
        {data.ideaPortfolioSummary?.deficit ? (
          <div className="knowledge-status">
            Качественных самостоятельных роликов: {data.ideaPortfolioSummary.accepted ?? data.ideaResults.length} из {data.ideaPortfolioSummary.requested ?? data.ideaResults.length}. Не хватает: {data.ideaPortfolioSummary.deficit} — повторы не добавлены.
          </div>
        ) : null}
        {data.ideaRejectedItems?.length ? (
          <div className="knowledge-status">
            {data.ideaRejectedItems.length} предложений не добавлены: редакционная
            проверка отсеяла повторы или неподходящие варианты.
          </div>
        ) : null}
        {data.ideaResults.length ? (
          <div className="idea-results">
            {data.ideaResults.map((idea, index) => {
              const productionItem = data.ideaProductionItems?.find((item) => item.title === idea);
              return (
              <button
                key={`${idea}-${index}`}
                aria-label={idea}
                className={ideasSelected.includes(idea) ? "selected" : ""}
                onClick={(event) => {
                  setResultsError("");
                  toggleIdea(idea, event.ctrlKey);
                }}
              >
                <span>{ideasSelected.includes(idea) ? "✓" : index + 1}</span>
                <span className="idea-result-copy">
                  <b>{idea}</b>
                  {data.ideaTitleMetadata?.[idea] ? (
                    <small>
                      {data.ideaTitleMetadata[idea].char_count ?? idea.length} символов · {data.ideaTitleMetadata[idea].hook_family || data.ideaTitleMetadata[idea].hook_type || "подача"} · клик {data.ideaTitleMetadata[idea].click_score ?? "—"} · сценарий {data.ideaTitleMetadata[idea].scriptability_score ?? "—"}
                    </small>
                  ) : null}
                  {productionItem ? (
                    <>
                      <small>
                        Режим: {productionItem.framing_type || "EDITORIAL"} · СНГ {productionItem.cis_audience_relevance_score ?? "—"} · ставки {productionItem.emotional_stakes_score ?? "—"} · усиление {productionItem.creative_amplification_score ?? "—"}
                      </small>
                      <small>
                        Риск фактичности: {productionItem.factual_risk_score || "UNKNOWN"}. {productionItem.why_cis_audience_cares || "Причина релевантности аудитории не сохранена."}
                      </small>
                      {productionItem.status === "LEGACY" ? (
                        <small>Legacy-элемент: пересоздайте его, чтобы получить оценки V2.</small>
                      ) : null}
                    </>
                  ) : null}
                  {data.ideaResultSources?.[idea] ? (
                    <small>Направление: {data.ideaResultSources[idea]}</small>
                  ) : null}
                </span>
              </button>
              );
            })}
          </div>
        ) : (
          <Empty
            title="Сначала сгенерируйте идеи"
            text="Выберите направления, добавьте их в план и запустите генерацию."
          />
        )}
      </section>
    </section>
  );
}

export function Scenarios({
  data,
  go,
  command,
  refresh,
}: {
  data: NewsFlowSnapshot;
  go: (p: Page) => void;
  command: Command;
  refresh: () => Promise<void>;
}) {
  const [selected, setSelected] = useState<number[]>([]);
  const [draft, setDraft] = useState("");
  const [manualTitle, setManualTitle] = useState("");
  const [manualText, setManualText] = useState("");
  const [manualImportError, setManualImportError] = useState("");
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameTitle, setRenameTitle] = useState("");
  const [scriptEditorOpen, setScriptEditorOpen] = useState(false);
  const [editedScriptText, setEditedScriptText] = useState("");
  const [savingScript, setSavingScript] = useState(false);
  const manualImportLock = useRef(false);
  const [importingManualScenario, setImportingManualScenario] = useState(false);
  const [generating, setGenerating] = useState(false);
  const scenarioGenerationLock = useRef(false);
  const [provider, setProvider] = useState<"agent" | "openai">(
    data.templateSettings.scenarioProvider || "agent",
  );
  useEffect(
    () => setProvider(data.templateSettings.scenarioProvider || "agent"),
    [data.templateSettings.scenarioProvider],
  );
  useEffect(() => {
    if (!generating) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 900);
    void refresh();
    return () => window.clearInterval(timer);
  }, [generating, refresh]);
  const toggle = (index: number, multi: boolean) =>
    setSelected((current) =>
      multi
        ? current.includes(index)
          ? current.filter((value) => value !== index)
          : [...current, index]
        : [index],
    );
  const counts = useMemo(
    () => ({
      ready: data.scenarios.filter((item) => item.state === "Готово").length,
      active: data.scenarios.filter((item) => item.state === "В обработке")
        .length,
      waiting: data.scenarios.filter((item) => item.state === "Ожидает").length,
      errors: data.scenarios.filter((item) => item.state === "Ошибка").length,
      needsAction: data.scenarios.filter((item) => item.state === "Нужно действие").length,
    }),
    [data.scenarios],
  );
  const unfinishedScenarioCount = counts.waiting + counts.errors + counts.needsAction;
  const scenarioColumns = useMemo<ColumnDef<NewsFlowSnapshot["scenarios"][number]>[]>(
    () => [
      {
        id: "selection",
        header: "Выбор",
        cell: ({ row }) => (
          <button
            aria-label={row.original.title}
            className={selected.includes(row.original.index) ? "selected" : ""}
            onClick={(event) => toggle(row.original.index, event.ctrlKey)}
          >
            {selected.includes(row.original.index) ? "Выбрано" : "Выбрать"}
          </button>
        ),
      },
      {
        accessorKey: "index",
        header: "#",
        cell: ({ row }) => row.original.index + 1,
      },
      { accessorKey: "title", header: "Сценарий" },
      { accessorKey: "state", header: "Статус" },
      {
        id: "progress",
        header: "Состояние",
        cell: ({ row }) => {
          const scenario = row.original;
          return scenario.error ||
            (scenario.storyPartCount
              ? `План истории: ${scenario.completedStoryParts || 0}/${scenario.storyPartCount} частей${scenario.storyPlannerStatus ? ` · ${scenario.storyPlannerStatus}` : ""}`
              : scenario.lengthStatus
              ? `Длина ${scenario.lengthStatus}: ${scenario.actualChars || 0} знаков${scenario.allowedMin || scenario.allowedMax ? ` · допустимо ${scenario.allowedMin || 0}–${scenario.allowedMax || "∞"}` : ""}${scenario.lengthRepairAttempts ? ` · корректировок: ${scenario.lengthRepairAttempts}` : ""}`
              : scenario.state === "В обработке"
                ? "Пишется через выбранного исполнителя…"
                : scenario.result
                  ? "Текст готов — откройте в «Готовых сценариях»"
                  : "Ожидает запуска");
        },
      },
    ],
    [selected],
  );
  const add = () => {
    if (draft.trim()) {
      void command("add-scenarios", { titles: draft });
      setDraft("");
    }
  };
  const edit = () => {
    if (selected.length !== 1) return;
    const item = data.scenarios.find(
      (scenario) => scenario.index === selected[0],
    );
    setRenameTitle(item?.title ?? "");
    setRenameOpen(true);
  };
  const selectedReadyScenario =
    selected.length === 1
      ? data.scenarios.find(
          (scenario) =>
            scenario.index === selected[0] &&
            scenario.state === "Готово" &&
            scenario.result.trim(),
        )
      : undefined;
  const editScript = () => {
    if (!selectedReadyScenario) return;
    setEditedScriptText(selectedReadyScenario.result);
    setScriptEditorOpen(true);
  };
  const saveEditedScript = async () => {
    if (!selectedReadyScenario || !editedScriptText.trim() || savingScript) return;
    setSavingScript(true);
    try {
      const result = await command("save-scenario-text", {
        index: selectedReadyScenario.index,
        text: editedScriptText,
      });
      if (result) {
        setScriptEditorOpen(false);
        setEditedScriptText("");
      }
    } finally {
      setSavingScript(false);
    }
  };
  const confirmRename = async () => {
    if (selected.length !== 1 || !renameTitle.trim()) return;
    const result = await command("rename-scenario", {
      index: selected[0],
      title: renameTitle.trim(),
    });
    if (result) {
      setRenameOpen(false);
      setRenameTitle("");
    }
  };
  const remove = () => {
    if (selected.length) {
      void command("remove-scenarios", { indices: selected });
      setSelected([]);
    }
  };
  const importReady = async () => {
    if (manualImportLock.current) return;
    if (manualTitle.trim() && manualText.trim()) {
      manualImportLock.current = true;
      setImportingManualScenario(true);
      try {
        const result = await command("import-manual-scenario", {
          title: manualTitle,
          text: manualText,
        });
        if (result) {
          setManualTitle("");
          setManualText("");
        }
      } finally {
        manualImportLock.current = false;
        setImportingManualScenario(false);
      }
    }
  };
  const importReadyFiles = async () => {
    if (manualImportLock.current) return;
    manualImportLock.current = true;
    setImportingManualScenario(true);
    setManualImportError("");
    try {
      const items = await window.newsflowDesktop?.chooseScenarioTexts();
      if (!items?.length) return;
      const result = await command("import-manual-scenarios", { items });
      if (result) {
        setSelected([]);
      } else {
        setManualImportError("Не удалось добавить выбранные сценарии. Повторите попытку.");
      }
    } catch (error) {
      setManualImportError(
        error instanceof Error && error.message.trim()
          ? error.message
          : "Не удалось прочитать выбранные сценарии. Повторите попытку.",
      );
    } finally {
      manualImportLock.current = false;
      setImportingManualScenario(false);
    }
  };
  const write = async (indices?: number[], force = false) => {
    if (scenarioGenerationLock.current) return;
    scenarioGenerationLock.current = true;
    setGenerating(true);
    try {
      await command("generate-scenarios", {
        ...(indices?.length ? { indices } : {}),
        provider,
        ...(force ? { force: true } : {}),
      });
    } finally {
      scenarioGenerationLock.current = false;
      setGenerating(false);
    }
  };
  const transferReady = async (
    target: "covers" | "seo" | "voice" | "montage",
  ) => {
    const readyIndices = data.scenarios
      .filter((item) => item.state === "Готово" && item.result.trim())
      .map((item) => item.index);
    const indices = selected.length ? selected : readyIndices;
    const result = await command("transfer-scenarios", {
      target,
      indices,
      requireCompleted: true,
    });
    if (result) {
      setSelected([]);
      go(target === "montage" ? "editor" : target);
    }
  };
  return (
    <div className="nf-scenarios">
      <Dialog
        open={renameOpen}
        onOpenChange={(open) => {
          setRenameOpen(open);
          if (!open) setRenameTitle("");
        }}
        title="Изменить тему сценария"
        description="Введите новое название выбранного сценария."
      >
        <Input
          label="Новое название сценария"
          value={renameTitle}
          onChange={(event) => setRenameTitle(event.target.value)}
          autoFocus
        />
        <div className="toolbar">
          <Button onClick={() => setRenameOpen(false)}>Отмена</Button>
          <Button kind="primary" onClick={() => void confirmRename()} disabled={!renameTitle.trim()}>
            Сохранить название
          </Button>
        </div>
      </Dialog>
      <Dialog
        open={scriptEditorOpen}
        onOpenChange={(open) => {
          setScriptEditorOpen(open);
          if (!open) setEditedScriptText("");
        }}
        title="Редактировать сценарий"
        description="Измените текст выбранного готового сценария и сохраните его в текущей очереди."
      >
        <Textarea
          label={`Текст сценария: ${selectedReadyScenario?.title || ""}`}
          value={editedScriptText}
          onChange={(event) => setEditedScriptText(event.target.value)}
          autoFocus
        />
        <div className="toolbar">
          <Button onClick={() => setScriptEditorOpen(false)}>Отмена</Button>
          <Button
            kind="primary"
            onClick={() => void saveEditedScript()}
            disabled={savingScript || !editedScriptText.trim()}
          >
            {savingScript ? "Сохранение…" : "Сохранить сценарий"}
          </Button>
        </div>
      </Dialog>
      <Toolbar label="Действия со сценариями">
        <Button kind="primary" onClick={add}>
          <Upload size={17} />
          Добавить сценарии
        </Button>
        <Select
          label="Исполнитель сценария"
          value={provider}
          onChange={(event) =>
            setProvider(event.target.value as "agent" | "openai")
          }
          options={[{ value: "agent", label: "Агент NewsFlow — редактор" }, { value: "openai", label: "ChatGPT — прямой режим" }]}
        />
        <Button
          kind="success"
          disabled={generating || !selected.length}
          onClick={() => void write(selected)}
        >
          <Sparkles size={17} />
          Написать выбранные
        </Button>
        <Button
          disabled={generating || !selected.length}
          onClick={() => void write(selected, true)}
        >
          <Sparkles size={17} />
          Переписать выбранные
        </Button>
        <Button
          kind="primary"
          disabled={generating || !unfinishedScenarioCount}
          onClick={() => void write()}
        >
          <Sparkles size={17} />
          {generating
            ? "Сценарии пишутся…"
            : unfinishedScenarioCount
              ? `Написать все сценарии: ${unfinishedScenarioCount}`
              : "Все сценарии готовы"}
        </Button>
        <Button onClick={() => void command("export-scenario-titles")}>
          <Download size={17} />
          Скачать названия
        </Button>
        <Button onClick={() => go("scripts")}>
          <FileText size={17} />
          Готовые сценарии ({counts.ready})
        </Button>
      </Toolbar>
      <section className="panel scenario-progress">
        <div>
          <b>Прогресс написания</b>
          <small>
            {generating || counts.active
              ? "Статусы обновляются автоматически для каждого сценария."
              : "Выберите сценарии и запустите написание."}
          </small>
        </div>
        <div className="scenario-progress-stats">
          <span className="done">
            <b>{counts.ready}</b> готово
          </span>
          <span className="working">
            <b>{counts.active}</b> в работе
          </span>
          <span>
            <b>{counts.waiting}</b> ждут
          </span>
          {counts.errors ? (
            <span className="error">
              <b>{counts.errors}</b> ошибок
            </span>
          ) : null}
          {counts.active > 0 && !generating ? (
            <Button onClick={() => void command("reconcile-runtime-state")}>
              Восстановить прерванные: {counts.active}
            </Button>
          ) : null}
        </div>
      </section>
      <section className="panel scenario-add">
        <div className="panel-title">
          <div>
            <b>Идеи для написания сценариев</b>
            <small>
              Сюда попадают отмеченные идеи из «Генерации идей». Одна строка —
              один сценарий; можно добавить и свои темы.
            </small>
          </div>
          <span className="status">{data.scenarios.length} в очереди</span>
        </div>
        <div className="form-row">
          <Textarea
            label="Идеи для сценариев"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Вставьте темы или готовые идеи…"
          />
          <Button kind="primary" onClick={add}>
            <Plus size={17} />
            Добавить все
          </Button>
        </div>
      </section>
      <section className="panel scenario-add manual-import">
        <div className="panel-title">
          <div>
            <b>Вставить готовый сценарий</b>
            <small>
              Он сразу будет помечен как готовый: можно передать его в озвучку,
              SEO, обложки или монтаж без генерации текста.
            </small>
          </div>
        </div>
        <div className="form-row">
          <Input
            label="Название сценария"
            value={manualTitle}
            onChange={(event) => setManualTitle(event.target.value)}
            placeholder="Название сценария"
          />
          <Button
            kind="success"
            disabled={importingManualScenario}
            onClick={() => void importReadyFiles()}
          >
            <Upload size={17} />
            {importingManualScenario ? "Сохранение…" : "Добавить готовый"}
          </Button>
          <Button
            disabled={importingManualScenario || !manualTitle.trim() || !manualText.trim()}
            onClick={() => void importReady()}
          >
            Добавить своё
          </Button>
        </div>
        <Textarea
          label="Полный текст сценария"
          value={manualText}
          onChange={(event) => setManualText(event.target.value)}
          placeholder="Вставьте полный текст сценария…"
        />
        {manualImportError ? <div className="knowledge-status" role="alert">{manualImportError}</div> : null}
      </section>
      <div className="toolbar compact">
        <Button onClick={edit}>
          <Pencil size={16} />
          Изменить тему
        </Button>
        <Button disabled={!selectedReadyScenario} onClick={editScript}>
          <Pencil size={16} />
          Редактировать сценарий
        </Button>
        <Button kind="danger" onClick={remove}>
          <Trash2 size={16} />
          Удалить выбранные
        </Button>
        <span className="shortcut-tip">
          Ctrl+клик — несколько · Ctrl+A — всё · Delete — удалить
        </span>
      </div>
      <section className="panel transfer-panel">
        <div>
          <b>Передать готовые</b>
          <small>
            Если ничего не выбрано, передаются все готовые сценарии. Выбранные —
            только отмеченные. SEO и теги передаются вместе в одну очередь.
          </small>
        </div>
        <Button onClick={() => void transferReady("covers")}>В обложки</Button>
        <Button onClick={() => void transferReady("seo")}>В SEO и теги</Button>
        <Button kind="primary" onClick={() => void transferReady("voice")}>
          В озвучку
        </Button>
        <Button kind="success" onClick={() => void transferReady("montage")}>
          <MonitorPlay size={16} />В монтаж
        </Button>
      </section>
      <section className="panel table-wrap scenario-table">
        {data.scenarios.length ? (
          <DataTable
            ariaLabel="Очередь сценариев"
            data={data.scenarios}
            columns={scenarioColumns}
          />
        ) : (
          <Empty
            title="Добавьте темы сценариев"
            text="Очередь сохраняется в проекте NewsFlow и не пропадёт после перезапуска."
          />
        )}
      </section>
    </div>
  );
}

export function FinishedScripts({
  data,
  go,
  command,
}: {
  data: NewsFlowSnapshot;
  go: (p: Page) => void;
  command: Command;
}) {
  const scripts = useMemo(
    () =>
      data.scenarios.filter(
        (item) => item.state === "Готово" && item.result.trim(),
      ),
    [data.scenarios],
  );
  const [selected, setSelected] = useState<number[]>([]);
  const [opened, setOpened] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const [savedText, setSavedText] = useState("");
  const [pendingClose, setPendingClose] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(
    () =>
      setSelected((current) =>
        current.filter((index) => scripts.some((item) => item.index === index)),
      ),
    [scripts],
  );
  const toggle = (index: number, multi: boolean) =>
    setSelected((current) =>
      multi
        ? current.includes(index)
          ? current.filter((value) => value !== index)
          : [...current, index]
        : [index],
    );
  const open = (item: NewsFlowSnapshot["scenarios"][number]) => {
    setOpened(item.index);
    setEditingText(item.result);
    setSavedText(item.result);
  };
  const save = async (index: number) => {
    if (saving) return false;
    setSaving(true);
    const result = await command("save-scenario-text", {
      index,
      text: editingText,
    });
    setSaving(false);
    if (result) {
      setSavedText(editingText);
      setOpened(null);
      return true;
    }
    return false;
  };
  const closeEditor = () => {
    if (editingText !== savedText) {
      setPendingClose(true);
      return;
    }
    setOpened(null);
  };
  const discardEditor = () => {
    setPendingClose(false);
    setOpened(null);
  };
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        opened === null ||
        saving ||
        !event.ctrlKey ||
        event.key.toLowerCase() !== "s"
      )
        return;
      event.preventDefault();
      void save(opened);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [editingText, opened, savedText, saving]);
  const allIndices = scripts.map((item) => item.index);
  const openedScript = scripts.find((item) => item.index === opened) ?? null;
  const scriptColumns = useMemo<ColumnDef<NewsFlowSnapshot["scenarios"][number]>[]>(
    () => [
      {
        id: "selection",
        header: "Выбор",
        cell: ({ row }) => (
          <button
            aria-label={row.original.title}
            className="script-select"
            onClick={(event) => toggle(row.original.index, event.ctrlKey)}
          >
            {selected.includes(row.original.index) ? "Выбрано" : "Выбрать"}
          </button>
        ),
      },
      { accessorKey: "index", header: "#", cell: ({ row }) => row.original.index + 1 },
      { accessorKey: "title", header: "Сценарий" },
      {
        id: "words",
        header: "Слова",
        cell: ({ row }) => row.original.result.trim().split(/\s+/).filter(Boolean).length.toLocaleString("ru-RU"),
      },
      {
        id: "open",
        header: "Рабочий текст",
        cell: ({ row }) => (
          <Button onClick={() => opened === row.original.index ? closeEditor() : open(row.original)}>
            {opened === row.original.index ? "Свернуть" : "Развернуть"}
          </Button>
        ),
      },
    ],
    [opened, selected],
  );
  const transfer = async (target: "covers" | "seo" | "voice") => {
    const indices = selected.length ? selected : allIndices;
    const result = await command("transfer-scenarios", {
      target,
      indices,
      requireCompleted: true,
    });
    if (result) {
      setSelected([]);
      go(target);
    }
  };
  const download = async (indices?: number[]) => {
    const isSelected = Boolean(indices?.length);
    const path = await window.newsflowDesktop?.chooseSavePath(
      isSelected ? "Выбранные сценарии.txt" : "Все готовые сценарии.txt",
    );
    if (path)
      await command("export-scenarios", {
        ...(isSelected ? { indices } : {}),
        path,
      });
  };
  const toggleAll = () =>
    setSelected((current) =>
      current.length === scripts.length ? [] : allIndices,
    );
  const remove = async (indices: number[]) => {
    if (!indices.length) return;
    const wording =
      indices.length === scripts.length
        ? "все готовые сценарии"
        : `выбранные сценарии (${indices.length})`;
    if (
      !window.confirm(`Удалить ${wording}? Это удалит их из очереди NewsFlow.`)
    )
      return;
    const result = await command("remove-scenarios", { indices });
    if (result) {
      setSelected([]);
      setOpened(null);
    }
  };
  return (
    <div className="nf-scripts">
      <Toolbar label="Действия с готовыми сценариями">
        <Button kind="primary" onClick={() => go("scenarios")}>
          <Newspaper size={17} />К очереди сценариев
        </Button>
        <Button onClick={scripts.length ? toggleAll : undefined}>
          {selected.length === scripts.length && scripts.length
            ? "Снять выделение"
            : "Выбрать все"}
        </Button>
        <Button
          onClick={selected.length ? () => void download(selected) : undefined}
        >
          <Download size={17} />
          Скачать выбранные
        </Button>
        <Button onClick={scripts.length ? () => void download() : undefined}>
          <Download size={17} />
          Скачать все
        </Button>
        <Button
          kind="primary"
          onClick={scripts.length ? () => void command("export-scenarios-separate-txt", { indices: selected }) : undefined}
        >
          <Download size={17} />
          Скачать все отдельными TXT
        </Button>
        <Button
          kind="danger"
          onClick={selected.length ? () => void remove(selected) : undefined}
        >
          <Trash2 size={17} />
          Удалить выбранные
        </Button>
        <Button
          kind="danger"
          onClick={scripts.length ? () => void remove(allIndices) : undefined}
        >
          <Trash2 size={17} />
          Удалить все готовые
        </Button>
        <Button
          onClick={scripts.length ? () => void transfer("covers") : undefined}
        >
          <Image size={17} />В обложки
        </Button>
        <Button
          onClick={scripts.length ? () => void transfer("seo") : undefined}
        >
          <Search size={17} />В SEO и теги
        </Button>
        <Button
          kind="primary"
          onClick={scripts.length ? () => void transfer("voice") : undefined}
        >
          <Mic2 size={17} />В озвучку
        </Button>
      </Toolbar>
      <section className="panel finished-scripts">
        <div className="panel-title">
          <div>
            <b>Готовые сценарии: {scripts.length}</b>
            <small>
              Клик — выбрать один, Ctrl+клик — несколько. Если ничего не
              выбрано, передача отправит все готовые сценарии. «Развернуть»
              открывает текст для просмотра и редактирования.
            </small>
          </div>
          <span className="status">Выбрано: {selected.length}</span>
        </div>
        {scripts.length ? (
          <>
            <DataTable ariaLabel="Готовые сценарии" preferenceKey="finished-scripts" data={scripts} columns={scriptColumns} />
            <Sheet
              open={openedScript !== null}
              onOpenChange={(isOpen) => { if (!isOpen) closeEditor(); }}
              title="Рабочий текст сценария"
              description={openedScript?.title || ""}
            >
              {openedScript ? <div className="script-editor">
                <Textarea
                  label={`Текст сценария: ${openedScript.title}`}
                  value={editingText}
                  onChange={(event) => setEditingText(event.target.value)}
                />
                <div className="toolbar compact">
                  <UiButton variant="primary" onClick={() => void save(openedScript.index)} disabled={saving}>
                    <Check size={16} />Сохранить текст
                  </UiButton>
                  <Button onClick={() => void download([openedScript.index])}>
                    <Download size={16} />Скачать этот
                  </Button>
                  <Button onClick={closeEditor}>Свернуть</Button>
                </div>
              </div> : null}
            </Sheet>
          </>
        ) : (
          <Empty
            title="Готовых сценариев пока нет"
            text="После написания тексты появятся здесь сами. Здесь же их можно открыть, отредактировать и передать дальше."
          />
        )}
      </section>
      <Dialog
        open={pendingClose}
        onOpenChange={(isOpen) => setPendingClose(isOpen)}
        title="Несохранённые изменения"
        description="Текст сценария изменён, но ещё не передан текущей команде сохранения."
      >
        <div className="nf-dialog-actions">
          <UiButton
            variant="secondary"
            onClick={() => setPendingClose(false)}
          >
            Продолжить редактирование
          </UiButton>
          <UiButton variant="secondary" onClick={discardEditor}>
            Не сохранять
          </UiButton>
          <UiButton
            variant="primary"
            disabled={saving || opened === null}
            onClick={() => {
              if (opened !== null) void save(opened).then((didSave) => {
                if (didSave) setPendingClose(false);
              });
            }}
          >
            Сохранить и закрыть
          </UiButton>
        </div>
      </Dialog>
    </div>
  );
}

function Templates({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const [template, setTemplate] = useState(data.templateSettings.template);
  useEffect(
    () => setTemplate(data.templateSettings.template),
    [data.templateSettings.template],
  );
  return (
    <section className="panel cover-template">
      <div className="panel-title">
        <div>
          <b>Общий шаблон сценария</b>
          <small>
            Используйте {"{title}"} для темы. Этот шаблон применяет
            Python-движок к очереди сценариев.
          </small>
        </div>
        <Button
          kind="primary"
          onClick={() => void command("save-template", { template })}
        >
          Сохранить шаблон
        </Button>
      </div>
      <textarea
        value={template}
        onChange={(event) => setTemplate(event.target.value)}
      />
      <div className="template-ranges">
        <b>Диапазоны сценариев</b>
        <small>
          Дополнительные требования по диапазонам остаются в сохранённых
          настройках проекта: {data.templateSettings.ranges.length}.
        </small>
      </div>
    </section>
  );
}

export function TemplateEditor({
  data,
  command,
  onDirtyChange,
  onSaveRequest,
}: {
  data: NewsFlowSnapshot;
  command: Command;
  onDirtyChange?: (dirty: boolean) => void;
  onSaveRequest?: (save: (() => Promise<boolean>) | null) => void;
}) {
  const [template, setTemplate] = useState(data.templateSettings.template);
  const [ranges, setRanges] = useState(data.templateSettings.ranges);
  const [targetChars, setTargetChars] = useState(Number(data.templateSettings.targetChars || 0));
  const [allowedMin, setAllowedMin] = useState(Number(data.templateSettings.allowedMin || 0));
  const [allowedMax, setAllowedMax] = useState(Number(data.templateSettings.allowedMax || 0));
  const [savedTemplate, setSavedTemplate] = useState(data.templateSettings.template);
  const [savedRanges, setSavedRanges] = useState(data.templateSettings.ranges);
  const [savedTargetChars, setSavedTargetChars] = useState(Number(data.templateSettings.targetChars || 0));
  const [savedAllowedMin, setSavedAllowedMin] = useState(Number(data.templateSettings.allowedMin || 0));
  const [savedAllowedMax, setSavedAllowedMax] = useState(Number(data.templateSettings.allowedMax || 0));
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("");
  const presets = data.templateSettings.presets || [];
  useEffect(() => {
    const nextTarget = Number(data.templateSettings.targetChars || 0);
    const nextMinimum = Number(data.templateSettings.allowedMin || 0);
    const nextMaximum = Number(data.templateSettings.allowedMax || 0);
    setTemplate(data.templateSettings.template);
    setRanges(data.templateSettings.ranges);
    setTargetChars(nextTarget);
    setAllowedMin(nextMinimum);
    setAllowedMax(nextMaximum);
    setSavedTemplate(data.templateSettings.template);
    setSavedRanges(data.templateSettings.ranges);
    setSavedTargetChars(nextTarget);
    setSavedAllowedMin(nextMinimum);
    setSavedAllowedMax(nextMaximum);
    setSaveFailed(false);
  }, [
    data.templateSettings.template,
    data.templateSettings.ranges,
    data.templateSettings.targetChars,
    data.templateSettings.allowedMin,
    data.templateSettings.allowedMax,
  ]);
  const dirty =
    template !== savedTemplate ||
    JSON.stringify(ranges) !== JSON.stringify(savedRanges) ||
    targetChars !== savedTargetChars ||
    allowedMin !== savedAllowedMin ||
    allowedMax !== savedAllowedMax;
  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  const save = async () => {
    if (saving || !dirty) return !dirty;
    setSaving(true);
    setSaveFailed(false);
    const result = await command("save-template", {
      template,
      ranges,
      targetChars,
      allowedMin,
      allowedMax,
    });
    setSaving(false);
    if (!result) {
      setSaveFailed(true);
      return false;
    }
    setSavedTemplate(template);
    setSavedRanges(ranges);
    setSavedTargetChars(targetChars);
    setSavedAllowedMin(allowedMin);
    setSavedAllowedMax(allowedMax);
    return true;
  };
  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => {
    onSaveRequest?.(() => saveRef.current());
    return () => onSaveRequest?.(null);
  }, [onSaveRequest]);
  const importTemplate = async () => {
    const text = await window.newsflowDesktop?.choosePromptText();
    if (text) setTemplate(text);
  };
  const applyPreset = (name: string) => {
    setSelectedPreset(name);
    const preset = presets.find((item) => item.name === name);
    if (preset) {
      setPresetName(preset.name);
      setTemplate(preset.template);
      setRanges(preset.ranges || []);
      setTargetChars(Number(preset.targetChars || 0));
      setAllowedMin(Number(preset.allowedMin || 0));
      setAllowedMax(Number(preset.allowedMax || 0));
    }
  };
  const savePreset = async () => {
    const name = presetName.trim();
    if (!name) return;
    const result = await command("save-template-preset", {
      name,
      template,
      ranges,
      targetChars,
      allowedMin,
      allowedMax,
    });
    if (result) setSelectedPreset(name);
  };
  const removePreset = async () => {
    const name = selectedPreset || presetName.trim();
    if (!name || !window.confirm(`Удалить пресет «${name}»?`)) return;
    const result = await command("delete-template-preset", { name });
    if (result) {
      setSelectedPreset("");
      setPresetName("");
    }
  };
  const [rangePresetName, setRangePresetName] = useState("");
  const [selectedRangePreset, setSelectedRangePreset] = useState("");
  const rangePresets = data.templateSettings.rangePresets || [];
  const applyRangePreset = (name: string) => {
    setSelectedRangePreset(name);
    const preset = rangePresets.find((item) => item.name === name);
    if (preset) {
      setRangePresetName(preset.name);
      setRanges(preset.ranges || []);
    }
  };
  const saveRangePreset = async () => {
    const name = rangePresetName.trim();
    if (!name) return;
    const result = await command("save-range-preset", { name, ranges });
    if (result) setSelectedRangePreset(name);
  };
  const removeRangePreset = async () => {
    const name = selectedRangePreset || rangePresetName.trim();
    if (!name || !window.confirm(`Удалить набор диапазонов «${name}»?`)) return;
    const result = await command("delete-range-preset", { name });
    if (result) {
      setSelectedRangePreset("");
      setRangePresetName("");
    }
  };
  const loadRangePrompt = async (index: number) => {
    const text = await window.newsflowDesktop?.choosePromptText();
    if (text)
      setRanges((current) =>
        current.map((item, row) =>
          row === index ? { ...item, prompt: text } : item,
        ),
      );
  };
  const addRange = () =>
    setRanges((current) => [
      ...current,
      {
        start: Math.max(1, data.scenarios.length || 1),
        end: Math.max(1, data.scenarios.length || 1),
        prompt: "",
      },
    ]);
  const effectiveMinimum = allowedMin || (targetChars ? Math.max(1, Math.round(targetChars * 0.9)) : 0);
  const effectiveMaximum = allowedMax || (targetChars ? Math.max(effectiveMinimum, Math.round(targetChars * 1.1)) : 0);
  return (
    <section
      className="panel cover-template nf-template-workspace"
      aria-label="Writing prompt studio"
    >
      <div className="panel-title nf-template-workspace-header">
        <div>
          <span className="nf-eyebrow">WRITING PRODUCTION DESK</span>
          <b>Базовый шаблон сценария</b>
          <small>
            Используйте {"{title}"} для темы. Этот шаблон применяется
            Python-движком к очереди сценариев.
          </small>
        </div>
        <div className="nf-template-save-state" aria-live="polite">
          <small>{saving ? "Сохранение…" : saveFailed ? "Не удалось сохранить изменения" : dirty ? "Есть несохранённые изменения" : "Все изменения сохранены"}</small>
          <Button kind="primary" onClick={saving || !dirty ? undefined : () => void save()}>
          Сохранить шаблон
          </Button>
        </div>
      </div>
      <Toolbar label="Библиотека шаблонов" className="nf-template-library">
        <select
          value={selectedPreset}
          onChange={(event) => applyPreset(event.target.value)}
          aria-label="Сохранённый пресет"
        >
          <option value="">Сохранённые пресеты</option>
          {presets.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name}
            </option>
          ))}
        </select>
        <input
          value={presetName}
          onChange={(event) => setPresetName(event.target.value)}
          placeholder="Название нового пресета"
        />
        <Button onClick={() => void savePreset()}>
          <Library size={16} />
          Сохранить пресет
        </Button>
        <Button kind="danger" onClick={() => void removePreset()}>
          <Trash2 size={16} />
          Удалить
        </Button>
        <Button onClick={() => void importTemplate()}>
          <Upload size={16} />
          Загрузить TXT / MD
        </Button>
      </Toolbar>
      <Textarea
        label="Базовый шаблон сценария"
        className="nf-template-editor"
        value={template}
        onChange={(event) => {
          setSaveFailed(false);
          setTemplate(event.target.value);
        }}
        placeholder="Вставьте общий промпт сценария или загрузите TXT/MD…"
      />
      <section className="template-global-length" aria-label="Длина сценария для текущего пресета">
        <div>
          <b>Длина сценария для этого пресета</b>
          <small>
            Python считает фактические символы после генерации. Если указать только цель,
            NewsFlow автоматически принимает диапазон ±10%. Диапазоны сценариев ниже могут
            переопределить эти значения для отдельных номеров.
          </small>
        </div>
        <div className="range-length-inputs">
          <label>
            Цель, знаков
            <input
              aria-label="Целевая длина сценария"
              value={targetChars || ""}
              type="number"
              min="0"
              onChange={(event) => setTargetChars(Math.max(0, Number(event.target.value) || 0))}
              placeholder="например 10000"
            />
          </label>
          <label>
            Мин.
            <input
              aria-label="Минимальная длина сценария"
              value={allowedMin || ""}
              type="number"
              min="0"
              onChange={(event) => setAllowedMin(Math.max(0, Number(event.target.value) || 0))}
              placeholder={targetChars ? String(effectiveMinimum) : "авто"}
            />
          </label>
          <label>
            Макс.
            <input
              aria-label="Максимальная длина сценария"
              value={allowedMax || ""}
              type="number"
              min="0"
              onChange={(event) => setAllowedMax(Math.max(0, Number(event.target.value) || 0))}
              placeholder={targetChars ? String(effectiveMaximum) : "авто"}
            />
          </label>
        </div>
        {targetChars || allowedMin || allowedMax ? (
          <small>
            Runtime-контракт: цель {targetChars || "по диапазону"} · допустимо{" "}
            {effectiveMinimum || "0"}–{effectiveMaximum || "∞"} знаков.
          </small>
        ) : (
          <small>Контракт длины выключен: применяется только текст промпта.</small>
        )}
      </section>
      <div className="template-ranges">
        <div className="ranges-title">
          <div>
            <b>Диапазоны сценариев</b>
            <small>
              Для каждого диапазона можно написать дополнительный промпт вручную
              или загрузить TXT/MD. Укажите одинаковые «С» и «По», чтобы
              задать персональную длину одному сценарию. Наборы диапазонов
              сохраняются отдельно.
            </small>
          </div>
          <Button onClick={addRange}>
            <Plus size={15} />
            Добавить диапазон
          </Button>
        </div>
        <div className="preset-name">
          <select
            value={selectedRangePreset}
            onChange={(event) => applyRangePreset(event.target.value)}
            aria-label="Пресет диапазонов"
          >
            <option value="">Пресеты диапазонов</option>
            {rangePresets.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name}
              </option>
            ))}
          </select>
          <input
            value={rangePresetName}
            onChange={(event) => setRangePresetName(event.target.value)}
            placeholder="Название набора диапазонов"
          />
          <Button onClick={() => void saveRangePreset()}>
            <Library size={16} />
            Сохранить набор
          </Button>
          <Button kind="danger" onClick={() => void removeRangePreset()}>
            <Trash2 size={16} />
            Удалить
          </Button>
        </div>
        {ranges.length ? (
          ranges.map((range, index) => (
            <div className="template-range" key={index}>
              <label>
                С
                <input
                  value={range.start}
                  type="number"
                  min="1"
                  onChange={(event) =>
                    setRanges((current) =>
                      current.map((item, row) =>
                        row === index
                          ? { ...item, start: Number(event.target.value) }
                          : item,
                      ),
                    )
                  }
                />
              </label>
              <span>—</span>
              <label>
                По
                <input
                  value={range.end}
                  type="number"
                  min="1"
                  onChange={(event) =>
                    setRanges((current) =>
                      current.map((item, row) =>
                        row === index
                          ? { ...item, end: Number(event.target.value) }
                          : item,
                      ),
                    )
                  }
                />
              </label>
              <div className="range-prompt-contract">
                <textarea
                  value={range.prompt}
                  onChange={(event) =>
                    setRanges((current) =>
                      current.map((item, row) =>
                        row === index
                          ? { ...item, prompt: event.target.value }
                          : item,
                      ),
                    )
                  }
                  placeholder="Дополнительный промпт для этого диапазона…"
                />
                <div className="range-length-inputs">
                  <label>
                    Цель, знаков
                    <input
                      value={range.target_chars || ""}
                      type="number"
                      min="0"
                      onChange={(event) =>
                        setRanges((current) => current.map((item, row) => row === index
                          ? { ...item, target_chars: Math.max(0, Number(event.target.value) || 0) }
                          : item))
                      }
                    />
                  </label>
                  <label>
                    Мин.
                    <input
                      value={range.allowed_min || ""}
                      type="number"
                      min="0"
                      onChange={(event) =>
                        setRanges((current) => current.map((item, row) => row === index
                          ? { ...item, allowed_min: Math.max(0, Number(event.target.value) || 0) }
                          : item))
                      }
                    />
                  </label>
                  <label>
                    Макс.
                    <input
                      value={range.allowed_max || ""}
                      type="number"
                      min="0"
                      onChange={(event) =>
                        setRanges((current) => current.map((item, row) => row === index
                          ? { ...item, allowed_max: Math.max(0, Number(event.target.value) || 0) }
                          : item))
                      }
                    />
                  </label>
                </div>
              </div>
              <Button onClick={() => void loadRangePrompt(index)}>
                <Upload size={15} />
                TXT
              </Button>
              <Button
                kind="danger"
                onClick={() =>
                  setRanges((current) =>
                    current.filter((_item, row) => row !== index),
                  )
                }
              >
                <Trash2 size={15} />
              </Button>
            </div>
          ))
        ) : (
          <small className="range-empty">
            Диапазонов нет: общий шаблон будет применён ко всем сценариям.
          </small>
        )}
        <div className="toolbar">
          <Button kind="primary" onClick={save}>
            Сохранить все диапазоны
          </Button>
        </div>
      </div>
    </section>
  );
}

function localImageUrl(path: string) {
  const normalized = String(path || "")
    .trim()
    .replace(/\\/g, "/");
  if (!normalized) return "";
  // Encode every path segment. Encoding only spaces breaks filenames that
  // contain Cyrillic, '#', '%', '?' or '&' in packaged Electron.
  const driveMatch = normalized.match(/^([A-Za-z]:)\/?(.*)$/);
  if (driveMatch) {
    const [, drive, rest] = driveMatch;
    const segments = rest
      .split("/")
      .filter(Boolean)
      .map((segment) => encodeURIComponent(segment));
    return `file:///${drive}/${segments.join("/")}`;
  }
  return `file://${normalized
    .split("/")
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/")}`;
}

function CoverPreviewImage({
  path,
  alt,
  className,
  loading,
}: {
  path: string;
  alt: string;
  className?: string;
  loading?: "lazy" | "eager";
}) {
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setAttempt(0);
    setFailed(false);
  }, [path]);
  useEffect(() => {
    if (!failed || attempt >= 8) return;
    const timer = window.setTimeout(() => {
      setAttempt((value) => value + 1);
      setFailed(false);
    }, 750);
    return () => window.clearTimeout(timer);
  }, [attempt, failed]);
  if (failed && attempt >= 8)
    return (
      <span className="cover-image-load-error">
        Файл ещё недоступен: откройте папку обложек или повторите рендер.
      </span>
    );
  const source = `${localImageUrl(path)}${localImageUrl(path).includes("?") ? "&" : "?"}newsflow_preview=${attempt}`;
  return (
    <img
      key={`${path}-${attempt}`}
      className={className}
      src={source}
      alt={alt}
      loading={loading}
      decoding="async"
      onLoad={() => setFailed(false)}
      onError={() => setFailed(true)}
    />
  );
}

const coverManualRetryStatuses = new Set([
  "Ошибка FastGen",
  "Нужен новый промпт",
  "Ошибка рендера",
]);

const isCoverManualRetryEligible = (
  cover: NewsFlowSnapshot["covers"][number],
) => coverManualRetryStatuses.has(String(cover.status || "")) &&
  !String(cover.accepted_generation_id || "").trim();

const isCoverNewPaidRetryEligible = (
  cover: NewsFlowSnapshot["covers"][number],
) => String(cover.provider_generation_status || "").toLowerCase() === "failed";

const isCoverRenderActive = (cover: NewsFlowSnapshot["covers"][number]) => {
  const status = String(cover.status || "");
  return ["Подготовка запросов", "Подготовка варианта"].includes(status) ||
    status.startsWith("Повтор того же промпта") ||
    status.startsWith("FastGen принял") ||
    status.startsWith("FastGen генерирует");
};

export function Covers({
  data: rawData,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  // A portable build can briefly run with a previous Python core after a UI
  // update.  Keep the covers page usable even if that core has not yet sent a
  // newly added optional setting.
  const extendedCoverSettings = rawData.coverSettings as NewsFlowSnapshot["coverSettings"] & {
    buildModeRanges?: Array<{
      start: number;
      end: number;
      buildMode: "fastgen-full" | "fastgen-full-my-face";
    }>;
    allowVariedTextPalette?: boolean;
  };
  const data = {
    ...rawData,
    coverCounts: rawData.coverCounts || fallback.coverCounts,
    coverSettings: {
      ...fallback.coverSettings,
      ...(rawData.coverSettings || {}),
      buildModeRanges: extendedCoverSettings.buildModeRanges || [],
      allowVariedTextPalette: Boolean(extendedCoverSettings.allowVariedTextPalette),
      ranges: rawData.coverSettings?.ranges || [],
      presets: rawData.coverSettings?.presets || [],
      headlinePresets: rawData.coverSettings?.headlinePresets || [],
      referenceMode: rawData.coverSettings?.referenceMode || "all",
      referencePaths: rawData.coverSettings?.referencePaths || [],
      referenceRanges: rawData.coverSettings?.referenceRanges || [],
      aiReferenceMode: rawData.coverSettings?.aiReferenceMode || "off",
      aiReferencePaths: rawData.coverSettings?.aiReferencePaths || [],
      aiReferenceRanges: rawData.coverSettings?.aiReferenceRanges || [],
      aiReferenceToFastgen:
        rawData.coverSettings?.aiReferenceToFastgen || false,
      useReferences: Boolean(rawData.coverSettings?.useReferences),
      referenceImagePaths: rawData.coverSettings?.referenceImagePaths || [],
      referenceModeStyle: Boolean(rawData.coverSettings?.referenceModeStyle),
      referenceModeComposition: Boolean(rawData.coverSettings?.referenceModeComposition),
      referenceModeMoodLighting: Boolean(rawData.coverSettings?.referenceModeMoodLighting),
      referenceModeAuto: Boolean(rawData.coverSettings?.referenceModeAuto),
      referenceMissingPaths: rawData.coverSettings?.referenceMissingPaths || [],
      referenceProviderLimit: rawData.coverSettings?.referenceProviderLimit || 10,
      referenceWillSendCount: rawData.coverSettings?.referenceWillSendCount || 0,
      referenceWillSendCountMyFaces: rawData.coverSettings?.referenceWillSendCountMyFaces || 0,
      tabloidMode: Boolean(rawData.coverSettings?.tabloidMode),
      sceneIntensityMode: Boolean(rawData.coverSettings?.sceneIntensityMode),
      faceLibrary: {
        ...fallback.coverSettings.faceLibrary,
        ...(rawData.coverSettings?.faceLibrary || {}),
      },
      faceCatalog: rawData.coverSettings?.faceCatalog || [],
    },
  };
  const [selected, setSelected] = useState<number[]>([]);
  const selectionAnchorRef = useRef<number | null>(null);
  const selectedProductionIdsRef = useRef<string[]>([]);
  const [inspectedCoverIndex, setInspectedCoverIndex] = useState<number | null>(
    null,
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [operation, setOperation] = useState(data.coverSettings.operation);
  const [ratio, setRatio] = useState(data.coverSettings.aspectRatio);
  const [count, setCount] = useState(String(data.coverSettings.variantCount));
  const [template, setTemplate] = useState(data.coverSettings.promptTemplate);
  const [provider, setProvider] = useState<"agent" | "openai">(
    data.coverSettings.provider,
  );
  const [useCustomPrompt, setUseCustomPrompt] = useState(
    data.coverSettings.useCustomPrompt,
  );
  const [useScript, setUseScript] = useState(
    data.coverSettings.useScriptContext,
  );
  const [promptCount, setPromptCount] = useState(
    String(data.coverSettings.promptVariantCount),
  );
  const [ranges, setRanges] = useState(data.coverSettings.ranges || []);
  const [presetName, setPresetName] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("");
  const [references, setReferences] = useState<string[]>(
    data.coverSettings.referencePaths || [],
  );
  const [referenceMode, setReferenceMode] = useState<"all" | "ranges" | "off">(
    data.coverSettings.referenceMode || "all",
  );
  const [referenceRanges, setReferenceRanges] = useState(
    data.coverSettings.referenceRanges || [],
  );
  const [aiReferences, setAiReferences] = useState<string[]>(
    data.coverSettings.aiReferencePaths || [],
  );
  const [aiReferenceMode, setAiReferenceMode] = useState<
    "all" | "ranges" | "off"
  >(data.coverSettings.aiReferenceMode || "off");
  const [aiReferenceRanges, setAiReferenceRanges] = useState<
    Array<{
      start: number;
      end: number;
      paths: string[];
      sendToFastgen?: boolean;
    }>
  >(data.coverSettings.aiReferenceRanges || []);
  const [aiReferenceToFastgen, setAiReferenceToFastgen] = useState(
    data.coverSettings.aiReferenceToFastgen || false,
  );
  const [fastgenUseReferences, setFastgenUseReferences] = useState(
    Boolean(data.coverSettings.useReferences),
  );
  const [fastgenReferencePaths, setFastgenReferencePaths] = useState<string[]>(
    data.coverSettings.referenceImagePaths || [],
  );
  const [fastgenReferenceModeStyle, setFastgenReferenceModeStyle] = useState(
    Boolean(data.coverSettings.referenceModeStyle),
  );
  const [fastgenReferenceModeComposition, setFastgenReferenceModeComposition] = useState(
    Boolean(data.coverSettings.referenceModeComposition),
  );
  const [fastgenReferenceModeMoodLighting, setFastgenReferenceModeMoodLighting] = useState(
    Boolean(data.coverSettings.referenceModeMoodLighting),
  );
  const [fastgenReferenceModeAuto, setFastgenReferenceModeAuto] = useState(
    Boolean(data.coverSettings.referenceModeAuto),
  );
  const [tabloidMode, setTabloidMode] = useState(Boolean(data.coverSettings.tabloidMode));
  const [sceneIntensityMode, setSceneIntensityMode] = useState(
    Boolean(data.coverSettings.sceneIntensityMode),
  );
  const [faceLibraryFolder, setFaceLibraryFolder] = useState(
    data.coverSettings.faceLibraryFolder || "",
  );
  const [facePreparedFolder, setFacePreparedFolder] = useState(
    data.coverSettings.facePreparedFolder || "",
  );
  const [faceLibraryEnabled, setFaceLibraryEnabled] = useState(
    data.coverSettings.faceLibraryEnabled,
  );
  const [faceRemoveBackground, setFaceRemoveBackground] = useState(
    data.coverSettings.faceRemoveBackground,
  );
  const [showPreparedFaces, setShowPreparedFaces] = useState(false);
  const [autoOverlayText, setAutoOverlayText] = useState(
    data.coverSettings.autoOverlayText,
  );
  const [autoTextColor, setAutoTextColor] = useState(
    data.coverSettings.autoTextColor,
  );
  const [seed, setSeed] = useState(data.coverSettings.seed || "");
  const [upscale, setUpscale] = useState(data.coverSettings.upscale);
  const [rateLimitPerHour, setRateLimitPerHour] = useState(
    String(data.coverSettings.rateLimitPerHour || ""),
  );
  const [rateAutoResume, setRateAutoResume] = useState(
    Boolean(data.coverSettings.rateAutoResume),
  );
  const [fastgenKeyLabels, setFastgenKeyLabels] = useState<string[]>(
    data.coverSettings.selectedKeyLabels || [],
  );
  const [headlineProvider, setHeadlineProvider] = useState<"agent" | "openai">(
    data.coverSettings.headlineProvider,
  );
  const [headlineTemplate, setHeadlineTemplate] = useState(
    data.coverSettings.headlineTemplate,
  );
  const [subheadlineTemplate, setSubheadlineTemplate] = useState(
    data.coverSettings.subheadlineTemplate,
  );
  const [useTextStructure, setUseTextStructure] = useState(
    data.coverSettings.useTextStructure,
  );
  const [avoidTextRepeats, setAvoidTextRepeats] = useState(
    data.coverSettings.avoidTextRepeats,
  );
  const [headlinePresetName, setHeadlinePresetName] = useState("");
  const [selectedHeadlinePreset, setSelectedHeadlinePreset] = useState("");
  const [coverTextImportError, setCoverTextImportError] = useState("");
  const [coverTextImporting, setCoverTextImporting] = useState(false);
  const coverTextImportLock = useRef(false);
  const [coverPromptImportError, setCoverPromptImportError] = useState("");
  const [coverPromptImporting, setCoverPromptImporting] = useState(false);
  const coverPromptImportLock = useRef(false);
  const [textMode, setTextMode] = useState<"overlay" | "fastgen">(
    data.coverSettings.textMode,
  );
  type CoverBuildMode = "fastgen-full" | "fastgen-full-my-face";
  const normaliseCoverBuildMode = (value: unknown): CoverBuildMode =>
    value === "fastgen-full" ? "fastgen-full" : "fastgen-full-my-face";
  const [coverBuildMode, setCoverBuildMode] = useState<CoverBuildMode>(
    normaliseCoverBuildMode(data.coverSettings.buildMode),
  );
  const [buildModeRanges, setBuildModeRanges] = useState(
    data.coverSettings.buildModeRanges || [],
  );
  const [allowVariedTextPalette, setAllowVariedTextPalette] = useState(
    data.coverSettings.allowVariedTextPalette,
  );
  const [coverGenerationStarting, setCoverGenerationStarting] = useState(false);
  const coverGenerationStartRef = useRef(false);
  useEffect(() => {
    setOperation(data.coverSettings.operation);
    setRatio(data.coverSettings.aspectRatio);
    setCount(String(data.coverSettings.variantCount));
    setTemplate(data.coverSettings.promptTemplate);
    setProvider(data.coverSettings.provider);
    setUseCustomPrompt(data.coverSettings.useCustomPrompt);
    setUseScript(data.coverSettings.useScriptContext);
    setPromptCount(String(data.coverSettings.promptVariantCount));
    setRanges(data.coverSettings.ranges || []);
    setReferences(data.coverSettings.referencePaths || []);
    setReferenceMode(data.coverSettings.referenceMode || "all");
    setReferenceRanges(data.coverSettings.referenceRanges || []);
    setFaceLibraryFolder(data.coverSettings.faceLibraryFolder || "");
    setFacePreparedFolder(data.coverSettings.facePreparedFolder || "");
    setFaceLibraryEnabled(data.coverSettings.faceLibraryEnabled);
    setFaceRemoveBackground(data.coverSettings.faceRemoveBackground);
    setAutoOverlayText(data.coverSettings.autoOverlayText);
    setAutoTextColor(data.coverSettings.autoTextColor);
    setSeed(data.coverSettings.seed || "");
    setUpscale(data.coverSettings.upscale);
    setRateLimitPerHour(String(data.coverSettings.rateLimitPerHour || ""));
    setRateAutoResume(Boolean(data.coverSettings.rateAutoResume));
    setFastgenKeyLabels(data.coverSettings.selectedKeyLabels || []);
    setHeadlineProvider(data.coverSettings.headlineProvider);
    setHeadlineTemplate(data.coverSettings.headlineTemplate);
    setSubheadlineTemplate(data.coverSettings.subheadlineTemplate);
    setUseTextStructure(data.coverSettings.useTextStructure);
    setAvoidTextRepeats(data.coverSettings.avoidTextRepeats);
    setTextMode(data.coverSettings.textMode);
    setCoverBuildMode(normaliseCoverBuildMode(data.coverSettings.buildMode));
    setBuildModeRanges(data.coverSettings.buildModeRanges || []);
    setAllowVariedTextPalette(data.coverSettings.allowVariedTextPalette);
    setSceneIntensityMode(Boolean(data.coverSettings.sceneIntensityMode));
  // `data.coverSettings` above is a deliberately normalised object created
  // for every render. Depending on it here makes a missing optional field
  // (for example `selectedKeyLabels`) allocate a new fallback array forever
  // and re-run this synchronisation loop. A new core snapshot is the only
  // event that may replace the local draft controls.
  }, [rawData.coverSettings]);
  useEffect(() => {
    setAiReferences(data.coverSettings.aiReferencePaths || []);
    setAiReferenceMode(data.coverSettings.aiReferenceMode || "off");
    setAiReferenceRanges(data.coverSettings.aiReferenceRanges || []);
    setAiReferenceToFastgen(data.coverSettings.aiReferenceToFastgen || false);
  }, [
    data.coverSettings.aiReferencePaths,
    data.coverSettings.aiReferenceMode,
    data.coverSettings.aiReferenceRanges,
    data.coverSettings.aiReferenceToFastgen,
  ]);
  const rateWaitingCovers = data.covers.filter(
    (cover) => cover.status === "Ожидает лимит FastGen",
  );
  const nextRateResume = rateWaitingCovers
    .map((cover) => String(cover.rate_limit_wait_until || ""))
    .filter(Boolean)
    .sort()[0];
  useEffect(() => {
    if (!nextRateResume) return;
    const delay = Math.max(0, new Date(nextRateResume).getTime() - Date.now());
    const timer = window.setTimeout(
      () => void command("resume-cover-generation"),
      delay + 500,
    );
    return () => window.clearTimeout(timer);
  }, [command, nextRateResume, rateAutoResume]);
  const liveModels = (data.fastgenCapabilities.image || []).filter(
    (item) => item.id,
  );
  const liveModelIds = new Set(liveModels.map((item) => String(item.id || "")));
  const catalogOnlyModels = fastGenImageFallbackModels.filter(
    (item) => !liveModelIds.has(String(item.id || "")),
  );
  // A persisted capabilities cache can predate a newly documented FastGen
  // route. Keep catalog-only routes visible until that exact operation appears
  // in the API response; matching live entries remain fully authoritative for
  // current health/billing/provider metadata.
  const models = [...liveModels, ...catalogOnlyModels];
  const hasLiveFastGenModels = liveModels.length > 0;
  const enabledModels = models.filter(
    (item) => item.health !== "unavailable" && !item.deprecated,
  );
  const selectedModel = models.find((item) => item.id === operation);
  const fastgenUsage = data.fastgenUsage?.keys || [];
  useEffect(() => {
    selectedProductionIdsRef.current = selected
      .map((index) => String(data.covers[index]?.production_item_id || "").trim())
      .filter(Boolean);
  }, [selected]);
  useEffect(() => {
    if (!selectedProductionIdsRef.current.length) return;
    const remapped = selectedProductionIdsRef.current
      .map((identity) => data.covers.findIndex(
        (cover) => String(cover.production_item_id || "").trim() === identity,
      ))
      .filter((index) => index >= 0);
    setSelected((current) =>
      current.length === remapped.length && current.every((value, index) => value === remapped[index])
        ? current
        : remapped,
    );
  }, [data.covers]);
  const updateCoverSelection = (
    index: number,
    event: { ctrlKey: boolean; shiftKey: boolean },
  ) => {
    setSelected((current) => {
      if (event.shiftKey && selectionAnchorRef.current !== null) {
        const start = Math.min(selectionAnchorRef.current, index);
        const end = Math.max(selectionAnchorRef.current, index);
        const range = Array.from({ length: end - start + 1 }, (_unused, offset) => start + offset);
        return event.ctrlKey
          ? [...current, ...range.filter((value) => !current.includes(value))]
          : range;
      }
      selectionAnchorRef.current = index;
      if (event.ctrlKey) {
        return current.includes(index)
          ? current.filter((value) => value !== index)
          : [...current, index];
      }
      return [index];
    });
  };
  const activeCoverRows = selected.length
    ? data.covers.filter((_cover, index) => selected.includes(index))
    : data.covers;
  const productionItemIdsFor = (indices: number[]) =>
    indices
      .map((index) => String(data.covers[index]?.production_item_id || "").trim())
      .filter(Boolean);
  const coverSelectionPayload = (indices = selected) => ({
    indices,
    ...(indices.length ? { productionItemIds: productionItemIdsFor(indices) } : {}),
  });
  const selectedTopicCount = selected.length;
  const coverQueue = useMemo(
    () => data.covers.map((cover, index) => ({ cover, index })),
    [data.covers],
  );
  const coverQueueColumns = useMemo<
    ColumnDef<{
      cover: NewsFlowSnapshot["covers"][number];
      index: number;
    }>[]
  >(
    () => [
      {
        id: "selected",
        header: "",
        cell: ({ row }) => {
          const { cover, index } = row.original;
          const isSelected = selected.includes(index);
          return (
            <button
              className="nf-table-select"
              aria-label={`${isSelected ? "Снять выбор" : "Выбрать"}: ${cover.title}`}
              onClick={(event) => updateCoverSelection(index, event)}
            >
              {isSelected ? "✓" : "○"}
            </button>
          );
        },
      },
      {
        id: "scenario",
        header: "Сценарий",
        cell: ({ row }) => {
          const { cover, index } = row.original;
          return (
            <Button
              onClick={() => {
                setSelected([index]);
                setInspectedCoverIndex(index);
              }}
            >
              {cover.scenario_index || index + 1}. {cover.title}
            </Button>
          );
        },
      },
      {
        id: "status",
        header: "Статус",
        cell: ({ row }) => row.original.cover.status || "Ожидает",
      },
      {
        id: "progress",
        header: "Готовность",
        cell: ({ row }) => `${row.original.cover.progress || 0}%`,
      },
      {
        id: "result",
        header: "Результат",
        cell: ({ row }) => {
          const { cover } = row.original;
          return (
            cover.error ||
            cover.timeline?.at(-1)?.detail ||
            (cover.paths?.length
              ? `${cover.paths.length} картинок`
              : "Промпты ещё не созданы")
          );
        },
      },
    ],
    [selected],
  );
  const newPromptsReadyCount = activeCoverRows.filter(
    (cover) => cover.status === "Новые промпты созданы",
  ).length;
  const selectedPromptRows = selected.map((index) => data.covers[index]).filter(Boolean);
  const selectedManualRetryCount = selectedPromptRows.filter(isCoverManualRetryEligible).length;
  const allSelectedManualRetryEligible =
    selected.length > 0 && selectedManualRetryCount === selected.length;
  const allSelectedNewPaidRetryEligible =
    selected.length > 0 && selectedPromptRows.every(isCoverNewPaidRetryEligible);
  const selectedHasActiveRender = selectedPromptRows.some(isCoverRenderActive);
  const selectedNewPromptsReadyCount = selectedPromptRows.filter(
    (cover) => cover.status === "Новые промпты созданы",
  ).length;
  const selectedPromptErrorCount = selectedPromptRows.filter(
    (cover) => cover.status === "Ошибка промпта",
  ).length;
  const allSelectedNewPromptsReady =
    selected.length > 0 && selectedNewPromptsReadyCount === selected.length;
  const selectedPromptSummary = selectedPromptErrorCount
    ? `Новые промпты: ${selectedNewPromptsReadyCount}/${selected.length} готовы · ошибок: ${selectedPromptErrorCount}`
    : `Новые промпты готовы: ${selectedNewPromptsReadyCount}/${selected.length}`;
  // Older projects kept a single selected prompt in image_prompt without a
  // prompt-options array. Both representations are valid and renderable.
  const promptsReady = activeCoverRows.some((cover) =>
    Boolean(
      String(cover.image_prompt || "").trim() ||
        (cover.image_prompt_options || []).length,
    ),
  );
  const promptCountValue = Math.max(1, Math.min(10, Number(promptCount) || 1));
  // The snapshot is refreshed while the screen is open. Persist the number
  // immediately: otherwise a refresh could put the old value (usually 2)
  // back before the user presses "Create prompts".
  const commitPromptCount = (value: number) => {
    const next = Math.max(1, Math.min(10, Math.trunc(value) || 1));
    setPromptCount(String(next));
    void command("save-cover-settings", { promptVariantCount: next });
  };
  const setManualPromptCount = (value: string) => {
    if (value === "") {
      setPromptCount("");
      return;
    }
    const parsed = Number(value);
    if (Number.isFinite(parsed)) commitPromptCount(parsed);
  };
  const decreasePromptCount = () => commitPromptCount(promptCountValue - 1);
  const increasePromptCount = () => commitPromptCount(promptCountValue + 1);
  const imageCountValue = Math.max(1, Math.min(10, Number(count) || 1));
  const plannedImageCount = activeCoverRows.reduce(
    (total, cover) =>
      total +
      Math.max(
        1,
        (cover.image_prompt_options || [cover.image_prompt]).filter(Boolean)
          .length,
      ) *
        imageCountValue,
    0,
  );
  const commitImageCount = (value: number) => {
    const next = Math.max(1, Math.min(10, Math.trunc(value) || 1));
    setCount(String(next));
    void command("save-cover-settings", { variantCount: next });
  };
  const setManualImageCount = (value: string) => {
    if (value === "") {
      setCount("");
      return;
    }
    const parsed = Number(value);
    if (Number.isFinite(parsed)) commitImageCount(parsed);
  };
  const coverHasRenderableImage = (cover: NewsFlowSnapshot["covers"][number]) =>
    Boolean(
      cover.selected_base_path ||
        cover.selected_path ||
        cover.path ||
        cover.text_overlay_path ||
        (cover.face_composite_paths || []).some(Boolean) ||
        (cover.raw_paths || []).some(Boolean) ||
        (cover.paths || []).some(Boolean),
    );
  const localTextReady = activeCoverRows.some((cover) =>
    Boolean(
      coverHasRenderableImage(cover) &&
        String(cover.cover_headline || "").trim(),
    ),
  );
  const fastgenTextReady = activeCoverRows.some((cover) =>
    Boolean(
      (cover.image_prompt || (cover.image_prompt_options || [])[0]) &&
        String(cover.cover_headline || "").trim(),
    ),
  );
  const buildModeRangeError = buildModeRanges.some((range) => range.end < range.start)
    ? "Конец диапазона не может быть меньше начала."
    : buildModeRanges.some((range, index) =>
        buildModeRanges.some((other, otherIndex) =>
          otherIndex > index &&
          range.buildMode !== other.buildMode &&
          Math.max(range.start, other.start) <= Math.min(range.end, other.end),
        ),
      )
      ? "Диапазоны разных режимов пересекаются. Исправьте границы перед запуском."
      : "";
  const addBuildModeRange = () =>
    setBuildModeRanges((current) => [
      ...current,
      {
        start: 1,
        end: Math.max(1, data.covers.length),
        buildMode: coverBuildMode,
      },
    ]);
  const updateBuildModeRange = (
    index: number,
    patch: Partial<(typeof buildModeRanges)[number]>,
  ) => setBuildModeRanges((current) => current.map((range, row) =>
    row === index ? { ...range, ...patch } : range,
  ));
  const removeBuildModeRange = (index: number) =>
    setBuildModeRanges((current) => current.filter((_range, row) => row !== index));
  const coverSettingsPayload = () => ({
    operation,
    aspectRatio: ratio,
    variantCount: Math.max(1, Math.min(10, Number(count) || 1)),
    promptTemplate: template,
    provider,
    useCustomPrompt,
    useScriptContext: useScript,
    promptVariantCount: Math.max(1, Math.min(10, Number(promptCount) || 2)),
    headlineProvider,
    headlineTemplate,
    subheadlineTemplate,
    useTextStructure,
    avoidTextRepeats,
    textMode,
    buildMode: coverBuildMode,
    buildModeRanges,
    allowVariedTextPalette,
    ranges,
    referenceMode,
    referencePaths: references,
    referenceRanges,
    aiReferenceMode,
    aiReferencePaths: aiReferences,
    aiReferenceRanges,
    aiReferenceToFastgen,
    useReferences: fastgenUseReferences,
    referenceImagePaths: fastgenReferencePaths,
    referenceModeStyle: fastgenReferenceModeStyle,
    referenceModeComposition: fastgenReferenceModeComposition,
    referenceModeMoodLighting: fastgenReferenceModeMoodLighting,
    referenceModeAuto: fastgenReferenceModeAuto,
    sceneIntensityMode,
    tabloidMode,
    faceLibraryFolder,
    facePreparedFolder,
    faceLibraryEnabled,
    faceRemoveBackground,
    autoOverlayText,
    autoTextColor,
    seed,
    upscale,
    rateLimitPerHour: Math.max(0, Math.trunc(Number(rateLimitPerHour) || 0)),
    rateAutoResume,
  });
  const save = () =>
    void command("save-cover-settings", coverSettingsPayload());
  const saveBuildModePolicy = () => {
    if (buildModeRangeError) return;
    void command("save-cover-settings", coverSettingsPayload());
  };
  const selectFastGenOperation = (value: string) => {
    setOperation(value);
    // Persist immediately: snapshot polling otherwise restores the previous
    // model before the user can launch the next render.
    void command("save-cover-settings", fastGenOperationPayload(value));
  };
  const selectCoverPromptProvider = (value: "agent" | "openai") => {
    setProvider(value);
    void command("save-cover-settings", coverPromptProviderPayload(value));
  };
  const selectCoverBuildMode = (value: typeof coverBuildMode) => {
    setCoverBuildMode(value);
    void command("save-cover-settings", coverBuildModePayload(value));
  };
  const selectCoverTextMode = (value: "overlay" | "fastgen") => {
    setTextMode(value);
    void command("save-cover-settings", coverTextModePayload(value));
  };
  const toggleTextStructure = () => {
    const next = !useTextStructure;
    setUseTextStructure(next);
    void command("save-cover-settings", {
      ...coverSettingsPayload(),
      useTextStructure: next,
    });
  };
  const toggleTextRepeatGuard = () => {
    const next = !avoidTextRepeats;
    setAvoidTextRepeats(next);
    void command("save-cover-settings", {
      ...coverSettingsPayload(),
      avoidTextRepeats: next,
    });
  };
  const selectHeadlineProvider = (value: "agent" | "openai") => {
    setHeadlineProvider(value);
    // Snapshot polling occurs while this panel is open. Persist the selection
    // at click time so a stale snapshot cannot immediately restore "agent".
    void command("save-cover-settings", coverHeadlineProviderPayload(value));
  };
  const generatePrompts = async (indices = selected) => {
    await command("save-cover-settings", coverSettingsPayload());
    await command("generate-cover-prompts", { ...coverSelectionPayload(indices), provider });
  };
  const rewritePrompts = async () => {
    if (!selected.length) return;
    await command("save-cover-settings", coverSettingsPayload());
    await command("regenerate-covers-new-prompts", {
      ...coverSelectionPayload(),
      provider,
    });
  };
  const generateHeadlines = (force = false) =>
    void command("generate-cover-headlines", coverWordGenerationPayload({
      ...coverSelectionPayload(),
      provider: headlineProvider,
      template: headlineTemplate,
      useStructure: useTextStructure,
      avoidRepeats: avoidTextRepeats,
      tabloidMode,
      force,
    }));
  const generateSubheadlines = (force = false) =>
    void command("generate-cover-subheadlines", coverWordGenerationPayload({
      ...coverSelectionPayload(),
      provider: headlineProvider,
      template: subheadlineTemplate,
      useStructure: useTextStructure,
      avoidRepeats: avoidTextRepeats,
      tabloidMode,
      force,
    }));
  const pauseHeadlines = () =>
    void command("pause-cover-text-generation", { kind: "headline" });
  const resumeHeadlines = () =>
    void command("resume-cover-text-generation", { kind: "headline" });
  const pauseSubheadlines = () =>
    void command("pause-cover-text-generation", { kind: "subheadline" });
  const resumeSubheadlines = () =>
    void command("resume-cover-text-generation", { kind: "subheadline" });
  const generateAutoHeadlines = (force = false) =>
    void command("generate-cover-headlines", coverWordGenerationPayload({
      ...coverSelectionPayload(),
      provider: headlineProvider,
      useDefault: true,
      useStructure: useTextStructure,
      avoidRepeats: avoidTextRepeats,
      tabloidMode,
      force,
    }));
  const generateAutoSubheadlines = (force = false) =>
    void command("generate-cover-subheadlines", coverWordGenerationPayload({
      ...coverSelectionPayload(),
      provider: headlineProvider,
      useDefault: true,
      useStructure: useTextStructure,
      avoidRepeats: avoidTextRepeats,
      tabloidMode,
      force,
    }));
  const generateAutoCoverTextPair = (force = false, indices = selected, replaceManual = false) =>
    void command("generate-cover-texts", coverWordPairGenerationPayload({
      ...coverSelectionPayload(indices),
      provider: headlineProvider,
      useStructure: useTextStructure,
      avoidRepeats: avoidTextRepeats,
      tabloidMode,
      force,
      replaceManual,
    }));
  const cancelSubheadlines = () =>
    void command("cancel-cover-subheadlines", { indices: selected });
  const removeOwnHeadlines = () =>
    void command("remove-cover-headlines", { indices: selected });
  const applyHeadlinePreset = (name: string) => {
    setSelectedHeadlinePreset(name);
    const preset = data.coverSettings.headlinePresets.find(
      (item) => item.name === name,
    );
    if (!preset) return;
    setHeadlinePresetName(preset.name);
    setHeadlineProvider(preset.provider || "agent");
    setHeadlineTemplate(preset.headlineTemplate || "");
    setSubheadlineTemplate(preset.subheadlineTemplate || "");
  };
  const saveHeadlinePreset = () => {
    const name = headlinePresetName.trim();
    if (name)
      void command("save-cover-headline-preset", {
        name,
        provider: headlineProvider,
        headlineTemplate,
        subheadlineTemplate,
      });
  };
  const deleteHeadlinePreset = () => {
    const name = selectedHeadlinePreset || headlinePresetName.trim();
    if (name && window.confirm(`Удалить пресет «${name}»?`))
      void command("delete-cover-headline-preset", { name });
  };
  const importCoverTopics = async () => {
    const text = await window.newsflowDesktop?.choosePromptText();
    if (text) void command("import-cover-topics", { text });
  };
  const importCoverTextTriples = async () => {
    if (coverTextImportLock.current) return;
    coverTextImportLock.current = true;
    setCoverTextImporting(true);
    setCoverTextImportError("");
    try {
      const text = await window.newsflowDesktop?.chooseCoverTextTriples();
      if (!text) return;
      const result = await command("import-cover-text-triples", { text });
      if (!result) {
        setCoverTextImportError("Не удалось импортировать тексты обложек. Исходные строки не изменены.");
      }
    } catch (error) {
      setCoverTextImportError(
        error instanceof Error && error.message.trim()
          ? error.message
          : "Не удалось открыть TXT с текстами обложек.",
      );
    } finally {
      coverTextImportLock.current = false;
      setCoverTextImporting(false);
    }
  };
  const importCoverPromptPairs = async () => {
    if (coverPromptImportLock.current) return;
    coverPromptImportLock.current = true;
    setCoverPromptImporting(true);
    setCoverPromptImportError("");
    try {
      const text = await window.newsflowDesktop?.chooseCoverPromptPairs();
      if (!text) return;
      const result = await command("import-cover-prompt-pairs", { text });
      if (!result) {
        setCoverPromptImportError("Не удалось импортировать промпты. Существующие промпты не изменены.");
      }
    } catch (error) {
      setCoverPromptImportError(
        error instanceof Error && error.message.trim()
          ? error.message
          : "Не удалось открыть TXT с промптами обложек.",
      );
    } finally {
      coverPromptImportLock.current = false;
      setCoverPromptImporting(false);
    }
  };
  const generate = async (
    mode: CoverBuildMode = coverBuildMode,
  ) => {
    if (buildModeRangeError) return;
    if (coverGenerationStartRef.current) return;
    coverGenerationStartRef.current = true;
    setCoverGenerationStarting(true);
    // Both routes finish in FastGen.  The my-faces route may pass a single
    // prepared portrait reference; no route performs a local face composite.
    const fastgenText = true;
    const localFaceOnly = false;
    const faceMode = "auto";
    // The selected route is persisted before the request. This guarantees
    // that retry/restart buttons do not silently switch typography engines.
    try {
      setTextMode(fastgenText ? "fastgen" : "overlay");
      setAutoOverlayText(!fastgenText);
      await command("save-cover-settings", {
        ...coverSettingsPayload(),
        buildMode: mode,
        textMode: fastgenText ? "fastgen" : "overlay",
        autoOverlayText: !fastgenText,
      });
      await command("generate-covers", {
        ...coverSelectionPayload(),
        // This is the primary explicit start action. It must resume a queue
        // previously paused by the operator before the core dispatches workers.
        resumeGeneration: true,
        operation,
        buildMode: mode,
        useBuildModeRanges: true,
        faceMode,
        textMode: fastgenText ? "fastgen" : "overlay",
        localFaceOnly,
      });
    } finally {
      coverGenerationStartRef.current = false;
      setCoverGenerationStarting(false);
    }
  };
  const reconcileGallery = () => void command("reconcile-cover-gallery");
  const importTemplate = async () => {
    const text = await window.newsflowDesktop?.choosePromptText();
    if (text) setTemplate(text);
  };
  const importRange = async (index: number) => {
    const text = await window.newsflowDesktop?.choosePromptText();
    if (text)
      setRanges((current) =>
        current.map((item, row) =>
          row === index ? { ...item, prompt: text } : item,
        ),
      );
  };
  const addRange = () =>
    setRanges((current) => [
      ...current,
      { start: 1, end: Math.max(1, data.scenarios.length), prompt: "" },
    ]);
  const chooseReferences = async () => {
    const paths = await window.newsflowDesktop?.chooseImages();
    if (paths?.length)
      setReferences((current) =>
        [...current, ...paths]
          .filter((path, index, values) => values.indexOf(path) === index)
          .slice(0, 10),
      );
  };
  const addReferenceRange = () =>
    setReferenceRanges((current) => [
      ...current,
      { start: 1, end: Math.max(1, data.scenarios.length), paths: [] },
    ]);
  const chooseReferenceRange = async (index: number) => {
    const paths = await window.newsflowDesktop?.chooseImages();
    if (paths?.length)
      setReferenceRanges((current) =>
        current.map((item, row) =>
          row === index
            ? {
                ...item,
                paths: [...item.paths, ...paths]
                  .filter(
                    (path, itemIndex, values) =>
                      values.indexOf(path) === itemIndex,
                  )
                  .slice(0, 10),
              }
            : item,
        ),
      );
  };
  const chooseAiReferences = async () => {
    const paths = await window.newsflowDesktop?.chooseImages();
    if (paths?.length)
      setAiReferences((current) =>
        [...current, ...paths]
          .filter((path, index, values) => values.indexOf(path) === index)
          .slice(0, 10),
      );
  };
  const chooseFastgenReferences = async () => {
    const paths = await window.newsflowDesktop?.chooseImages();
    if (!paths?.length) return;
    setFastgenReferencePaths((current) =>
      [...current, ...paths].filter((path, index, values) => values.indexOf(path) === index),
    );
  };
  const chooseFastgenReferenceFolder = async () => {
    const folder = await window.newsflowDesktop?.chooseFolder();
    if (!folder) return;
    const saved = await command("save-cover-settings", {
      ...coverSettingsPayload(),
      referenceImageFolders: [folder],
    });
    if (saved?.coverSettings.referenceImagePaths) {
      setFastgenReferencePaths(saved.coverSettings.referenceImagePaths);
    }
  };
  const setFastgenReferenceAuto = (enabled: boolean) => {
    setFastgenReferenceModeAuto(enabled);
    if (enabled) {
      setFastgenReferenceModeStyle(false);
      setFastgenReferenceModeComposition(false);
      setFastgenReferenceModeMoodLighting(false);
    }
  };
  const setFastgenReferenceManualMode = (
    mode: "style" | "composition" | "mood",
    enabled: boolean,
  ) => {
    setFastgenReferenceModeAuto(false);
    if (mode === "style") setFastgenReferenceModeStyle(enabled);
    if (mode === "composition") setFastgenReferenceModeComposition(enabled);
    if (mode === "mood") setFastgenReferenceModeMoodLighting(enabled);
  };
  const addAiReferenceRange = () =>
    setAiReferenceRanges((current) => [
      ...current,
      {
        start: 1,
        end: Math.max(1, data.scenarios.length),
        paths: [],
        sendToFastgen: false,
      },
    ]);
  const chooseAiReferenceRange = async (index: number) => {
    const paths = await window.newsflowDesktop?.chooseImages();
    if (paths?.length)
      setAiReferenceRanges((current) =>
        current.map((item, row) =>
          row === index
            ? {
                ...item,
                paths: [...item.paths, ...paths]
                  .filter(
                    (path, itemIndex, values) =>
                      values.indexOf(path) === itemIndex,
                  )
                  .slice(0, 10),
              }
            : item,
        ),
      );
  };
  const copyAiReferencesToFastgen = () => {
    setReferences(aiReferences);
    setReferenceMode(aiReferences.length ? "all" : "off");
    setReferenceRanges(aiReferenceRanges);
    void command("save-cover-settings", {
      referenceMode: aiReferences.length ? "all" : "off",
      referencePaths: aiReferences,
      referenceRanges: aiReferenceRanges,
    });
  };
  const chooseFaceLibrary = async () => {
    const path = await window.newsflowDesktop?.chooseFolder();
    if (!path) return;
    // A folder chooser returns an absolute path. Save it immediately so the
    // counter below is refreshed without a second, easy-to-miss action.
    setFaceLibraryFolder(path);
    await command("save-cover-settings", { faceLibraryFolder: path });
  };
  const choosePreparedFaceFolder = async () => {
    const path = await window.newsflowDesktop?.chooseFolder();
    if (!path) return;
    setFacePreparedFolder(path);
    await command("save-cover-settings", { facePreparedFolder: path });
  };
  const setFaceLibraryEnabledAndSave = (enabled: boolean) => {
    setFaceLibraryEnabled(enabled);
    // The switch is an immediate setting, not a draft: otherwise it looked as
    // though a click did nothing until the user found the separate Save button.
    void command("save-cover-settings", { faceLibraryEnabled: enabled });
  };
  const setFaceBackgroundRemovalAndSave = (enabled: boolean) => {
    setFaceRemoveBackground(enabled);
    void command("save-cover-settings", { faceRemoveBackground: enabled });
  };
  const chooseFaceForCover = async (index: number) => {
    const paths = await window.newsflowDesktop?.chooseImages();
    if (paths?.[0])
      void command("select-cover-face", { index, path: paths[0] });
  };
  const chooseVisualReferenceForCover = async (index: number) => {
    const paths = await window.newsflowDesktop?.chooseImages();
    if (!paths?.[0]) return;
    const result = await command("select-cover-visual-reference", {
      index,
      path: paths[0],
    });
    if (result)
      await command("generate-cover-prompts", {
        ...coverSelectionPayload([index]),
        provider,
        rewrite: true,
      });
  };
  const exportPrompts = async () => {
    const path = await window.newsflowDesktop?.chooseSavePath(
      "Промпты обложек.txt",
    );
    if (path) void command("export-cover-prompts", { path, indices: selected });
  };
  const exportZip = async () => {
    const path = await window.newsflowDesktop?.chooseZipSavePath(
      "Обложки NewsFlow.zip",
    );
    if (path) void command("export-covers", { path, indices: selected });
  };
  const rendererPayload = () => ({
    currentProfile: false,
    useBuildModeRanges: true,
    operation,
    buildMode: coverBuildMode,
    faceMode: "auto",
    textMode: "fastgen",
    localFaceOnly: false,
  });
  const repeatCurrent = () =>
    void command("regenerate-covers", {
      ...coverSelectionPayload(),
      currentProfile: true,
    });
  const regenerate = () =>
    void command("regenerate-covers", {
      ...coverSelectionPayload(),
      ...rendererPayload(),
    });
  const retrySelectedGeneration = () =>
    void command("retry-cover-generation", coverSelectionPayload());
  const retrySelectedGenerationNewPaid = () =>
    void command("retry-cover-generation-new-paid", coverSelectionPayload());
  const regenerateNewPrompts = () =>
    void command("regenerate-covers-new-prompts", {
      ...coverSelectionPayload(),
      provider,
    });
  const refineFaces = () =>
    void command("refine-cover-faces", coverSelectionPayload());
  const removePrompts = () =>
    void command("remove-cover-prompts", { indices: selected });
  const removeSelectedPrompts = () => {
    if (selected.length)
      void command("remove-cover-prompts", { indices: selected });
  };
  const removeAllPrompts = () => {
    if (
      data.covers.length &&
      window.confirm(
        "Удалить все визуальные промпты? Картинки и темы останутся.",
      )
    )
      void command("remove-cover-prompts", {});
  };
  const removeImages = () => {
    if (
      selected.length &&
      window.confirm(`Удалить картинки у ${selected.length} выбранных тем?`)
    )
      void command("remove-cover-results", coverSelectionPayload());
  };
  const removeAllImages = () => {
    if (
      data.covers.length &&
      window.confirm(`Удалить картинки у всех ${data.covers.length} тем?`)
    )
      void command("remove-cover-results", { all: true });
  };
  const removeRows = () => {
    if (
      selected.length &&
      window.confirm(`Удалить ${selected.length} тем из очереди обложек?`)
    ) {
      void command("remove-cover-queue", { indices: selected });
      setSelected([]);
    }
  };
  const renderText = () =>
    void command("render-cover-text", { indices: selected });
  const renderTextWithFastGen = () =>
    void command("render-cover-text-fastgen", coverSelectionPayload());
  // The default route for normal work: scene is rendered by FastGen and
  // NewsFlow finishes the portrait, headline, panel, outline and shadow.
  const generateAutomatically = () => void generate(coverBuildMode);
  const resumeGeneration = () => void command("resume-cover-generation");
  const applyPreset = (name: string) => {
    setSelectedPreset(name);
    const preset = data.coverSettings.presets.find(
      (item) => item.name === name,
    );
    if (!preset) return;
    setPresetName(preset.name);
    setTemplate(preset.promptTemplate || template);
    setProvider(preset.provider || "agent");
    setUseScript(Boolean(preset.useScriptContext));
    setRanges(preset.ranges || []);
    setHeadlineProvider(preset.headlineProvider || "agent");
    setHeadlineTemplate(preset.headlineTemplate || headlineTemplate);
    setSubheadlineTemplate(preset.subheadlineTemplate || subheadlineTemplate);
    setTextMode(preset.textMode || "overlay");
  };
  const savePreset = () => {
    const name = presetName.trim();
    if (name)
      void command("save-cover-prompt-preset", {
        name,
        provider,
        promptTemplate: template,
        useScriptContext: useScript,
        headlineProvider,
        headlineTemplate,
        subheadlineTemplate,
        textMode,
        ranges,
      });
  };
  const removePreset = () => {
    const name = selectedPreset || presetName.trim();
    if (name && window.confirm(`Удалить пресет «${name}»?`))
      void command("delete-cover-prompt-preset", { name });
  };
  return (
    <div
      className="nf-covers nf-visual-production-studio"
      aria-label="Visual Production Studio"
    >
      <section className="panel cover-studio-hero">
        <div>
          <span className="eyebrow">FASTGEN · THUMBNAIL LAB</span>
          <h2>Обложки по сценарию</h2>
          <p>
            Сначала выберите сценарии, затем получите два разных визуальных хода
            от агента или ChatGPT. Выбираете лучший промпт — FastGen делает
            столько картинок, сколько зададите.
          </p>
        </div>
        <div className="cover-hero-metrics">
          <span>
            <b>{data.coverCounts.total}</b> тем
          </span>
          <span>
            <b>{data.coverCounts.ready}</b> готовы
          </span>
          <span>
            <b>{data.coverCounts.missing}</b> нет файла
          </span>
          <span>
            <b>{data.coverCounts.failed}</b> ошибки
          </span>
          <span>
            <b>{data.coverCounts.generating}</b> в работе
          </span>
          <span>
            <b>{data.coverCounts.queued}</b> в очереди
          </span>
          <span>
            <b>{data.coverSettings.activeKeys}</b> ключей FastGen
          </span>
          <span>
            <b>{enabledModels.length || "—"}</b> активных моделей
          </span>
        </div>
      </section>
      <section className="panel">
        <div className="panel-title">
          <div>
            <b>Ключи FastGen для этой очереди</b>
            <small>Отметьте один или несколько ключей. Без отметок используются все активные ключи.</small>
          </div>
        </div>
        <div className="toolbar compact">
          {data.keyStatus.fastgen.filter((key) => key.active).map((key) => {
            const checked = !fastgenKeyLabels.length || fastgenKeyLabels.includes(key.label);
            return <Checkbox key={key.label} label={key.label} checked={checked} onCheckedChange={(isChecked) => {
                const all = data.keyStatus.fastgen.filter((item) => item.active).map((item) => item.label);
                const current = fastgenKeyLabels.length ? fastgenKeyLabels : all;
                const next = isChecked ? [...new Set([...current, key.label])] : current.filter((item) => item !== key.label);
                setFastgenKeyLabels(next);
                void command("save-cover-settings", { fastgenKeyLabels: next });
              }} />;
          })}
        </div>
      </section>
      <section
        className="panel cover-workflow"
        aria-label="Конвейер создания обложки"
      >
        <div className="cover-workflow-title">
          <div>
            <span className="eyebrow">ОДИН ПОНЯТНЫЙ ПОРЯДОК</span>
            <h3>Соберите обложку за 4 шага</h3>
            <p>
              Выделите темы — создайте два визуальных промпта — выберите режим
              лиц — получите изображения с крупными словами.
            </p>
          </div>
          <span className="cover-workflow-selected">
            {selected.length
              ? `Выбрано тем: ${selected.length}`
              : "Без выбора — все темы"}
          </span>
        </div>
        <div className="cover-workflow-steps">
          <article>
            <span>01</span>
            <div>
              <b>Настройте вариант</b>
              <small>
                Можно вручную указать любое целое число от 1 до 10. Два —
                оптимально: крупный конфликт и панорамный сюжет.
              </small>
              <label>
                Промптов на тему
                <div className="cover-prompt-counter">
                  <Button
                    onClick={
                      promptCountValue > 1 ? decreasePromptCount : undefined
                    }
                  >
                    −
                  </Button>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    step="1"
                    inputMode="numeric"
                    value={promptCount}
                    onChange={(event) =>
                      setManualPromptCount(event.target.value)
                    }
                    onBlur={() => {
                      if (!promptCount) commitPromptCount(1);
                    }}
                  />
                  <Button
                    onClick={
                      promptCountValue < 10 ? increasePromptCount : undefined
                    }
                  >
                    +
                  </Button>
                </div>
              </label>
            </div>
            <Button kind="primary" onClick={() => void generatePrompts([])}>
              <Sparkles size={17} />
              Создать {promptCountValue} промпт
              {promptCountValue === 1 ? "" : promptCountValue < 5 ? "а" : "ов"}
              {" всем"}
            </Button>
            <Button
              onClick={coverPromptImporting ? undefined : importCoverPromptPairs}
              aria-busy={coverPromptImporting}
            >
              <Upload size={16} />
              Импортировать промпты TXT
            </Button>
            <Button
              kind="primary"
              onClick={selected.length ? () => void generatePrompts(selected) : undefined}
            >
              <Sparkles size={17} />
              Создать промпты выбранным
            </Button>
            <Button
              onClick={
                selected.length ? () => void rewritePrompts() : undefined
              }
            >
              <WandSparkles size={16} />
              Переписать выбранные ИИ
            </Button>
            <Button
              kind="danger"
              onClick={selected.length ? removeSelectedPrompts : undefined}
            >
              <Trash2 size={15} />
              Удалить выбранные
            </Button>
            <Button
              kind="danger"
              onClick={data.covers.length ? removeAllPrompts : undefined}
            >
              <Trash2 size={15} />
              Удалить все промпты
            </Button>
            <small className="cover-workflow-render-note">
              {selected.length
                ? `Будут переписаны или очищены промпты только у выбранных тем: ${selected.length}.`
                : "Выделите одну или несколько тем в списке ниже — тогда станет доступно переписывание или удаление только выбранных."}
            </small>
          </article>
          <article>
            <span>02</span>
            <div>
              <b>Выберите движок текста и лица</b>
              <small>
                Это настройка, а не запуск. Выбор персоны в галерее всегда
                учитывается при переписывании промпта.
              </small>
              <div className="cover-workflow-faces">
                <Button
                  kind={
                    coverBuildMode === "fastgen-full" ? "success" : "secondary"
                  }
                  onClick={() => selectCoverBuildMode("fastgen-full")}
                >
                  <Sparkles size={15} />
                  Всё через FastGen
                </Button>
                <Button
                  kind={
                    coverBuildMode === "fastgen-full-my-face"
                      ? "success"
                      : "secondary"
                  }
                  onClick={() => selectCoverBuildMode("fastgen-full-my-face")}
                >
                  <Image size={15} />
                  FastGen всё + мои лица
                </Button>
              </div>
              <small>
                {coverBuildMode === "fastgen-full"
                  ? "FastGen сам рисует сцену, лица и текст; пользовательский PNG не загружается."
                  : "NewsFlow подбирает только подтверждённо релевантный PNG и отправляет один референс в FastGen. FastGen сам рисует финальную сцену, лицо и текст."}
              </small>
              <div className="cover-fastgen-reference-controls">
                <label className="check-row reference-enable-toggle">
                  <input
                    aria-label="Использовать референсы FastGen"
                    type="checkbox"
                    checked={fastgenUseReferences}
                    onChange={(event) => setFastgenUseReferences(event.target.checked)}
                  />
                  Использовать референсы FastGen
                </label>
                {fastgenUseReferences ? (
                  <div className="cover-fastgen-reference-panel">
                    <small>
                      Визуальная подсказка, а не источник сюжета: тема, люди и события всегда берутся только из текущего сценария.
                    </small>
                    <div className="cover-workflow-faces">
                      <Button onClick={() => void chooseFastgenReferences()}>
                        <Upload size={15} />
                        Добавить изображения
                      </Button>
                      <Button onClick={() => void chooseFastgenReferenceFolder()}>
                        <FolderOpen size={15} />
                        Добавить папку
                      </Button>
                      <Button
                        kind="danger"
                        onClick={fastgenReferencePaths.length ? () => setFastgenReferencePaths([]) : undefined}
                      >
                        <Trash2 size={15} />
                        Очистить
                      </Button>
                      <Button kind="primary" onClick={() => void command("save-cover-settings", coverSettingsPayload())}>
                        <Check size={15} />
                        Сохранить референсы FastGen
                      </Button>
                    </div>
                    <div className="cover-workflow-faces">
                      <label className="check-row">
                        <input type="checkbox" checked={fastgenReferenceModeStyle}
                          disabled={fastgenReferenceModeAuto}
                          onChange={(event) => setFastgenReferenceManualMode("style", event.target.checked)} />
                        Стиль
                      </label>
                      <label className="check-row">
                        <input type="checkbox" checked={fastgenReferenceModeComposition}
                          disabled={fastgenReferenceModeAuto}
                          onChange={(event) => setFastgenReferenceManualMode("composition", event.target.checked)} />
                        Композиция
                      </label>
                      <label className="check-row">
                        <input type="checkbox" checked={fastgenReferenceModeMoodLighting}
                          disabled={fastgenReferenceModeAuto}
                          onChange={(event) => setFastgenReferenceManualMode("mood", event.target.checked)} />
                        Атмосфера / цвет / свет
                      </label>
                      <label className="check-row">
                        <input type="checkbox" checked={fastgenReferenceModeAuto}
                          onChange={(event) => setFastgenReferenceAuto(event.target.checked)} />
                        Авто
                      </label>
                    </div>
                    <small>
                      Загружено {fastgenReferencePaths.length} / будет отправлено до {coverBuildMode === "fastgen-full"
                        ? data.coverSettings.referenceWillSendCount
                        : data.coverSettings.referenceWillSendCountMyFaces} визуальных референсов (лимит {data.coverSettings.referenceProviderLimit}; в режиме «мои лица» один слот может занять портрет).
                      {data.coverSettings.referenceMissingPaths.length
                        ? ` Недоступно: ${data.coverSettings.referenceMissingPaths.length}.`
                        : ""}
                    </small>
                    {fastgenReferencePaths.length ? (
                      <div className="reference-list compact">
                        {fastgenReferencePaths.map((path) => (
                          <span key={path}>
                            {path.split(/[\\/]/).pop()}
                            <button aria-label={`Убрать FastGen референс ${path.split(/[\\/]/).pop()}`}
                              onClick={() => setFastgenReferencePaths((current) => current.filter((value) => value !== path))}>×</button>
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div className="cover-mode-ranges" aria-label="Диапазоны режимов FastGen">
                <div className="toolbar compact">
                  <Button onClick={addBuildModeRange}>
                    Добавить диапазон режимов
                  </Button>
                  <Button onClick={buildModeRangeError ? undefined : saveBuildModePolicy}>
                    Сохранить диапазоны режимов
                  </Button>
                </div>
                {buildModeRanges.map((range, index) => (
                  <div className="cover-mode-range" key={`cover-mode-range-${index}`}>
                    <label>
                      С
                      <input
                        aria-label="Начало диапазона режима"
                        type="number"
                        min="1"
                        value={range.start}
                        onChange={(event) => updateBuildModeRange(index, {
                          start: Math.max(1, Number(event.target.value) || 1),
                        })}
                      />
                    </label>
                    <label>
                      По
                      <input
                        aria-label="Конец диапазона режима"
                        type="number"
                        min="1"
                        value={range.end}
                        onChange={(event) => updateBuildModeRange(index, {
                          end: Math.max(1, Number(event.target.value) || 1),
                        })}
                      />
                    </label>
                    <label>
                      Режим
                      <select
                        aria-label="Режим диапазона"
                        value={range.buildMode}
                        onChange={(event) => updateBuildModeRange(index, {
                          buildMode: normaliseCoverBuildMode(event.target.value),
                        })}
                      >
                        <option value="fastgen-full">Всё через FastGen</option>
                        <option value="fastgen-full-my-face">FastGen всё + мои лица</option>
                      </select>
                    </label>
                    <Button kind="danger" onClick={() => removeBuildModeRange(index)}>
                      Удалить диапазон
                    </Button>
                  </div>
                ))}
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={allowVariedTextPalette}
                    onChange={(event) => setAllowVariedTextPalette(event.target.checked)}
                  />
                  Разрешить разные цветовые схемы текста и плашки
                </label>
                <small>
                  Без галочки: светлый/жёлтый текст на красной плашке. С галочкой FastGen выбирает контрастную пару под сцену. Ровная красная рамка остаётся обязательной.
                </small>
                <label className="check-row">
                  <input
                    aria-label="Усилить драматургию сцен"
                    type="checkbox"
                    checked={sceneIntensityMode}
                    onChange={(event) => {
                      setSceneIntensityMode(event.target.checked);
                      void command("save-cover-settings", { sceneIntensityMode: event.target.checked });
                    }}
                  />
                  Усилить драматургию сцен
                </label>
                <small>
                  Только для новых промптов: добавляет уместный масштаб, противостояние и массовую реакцию по теме. «Создать новый промпт» не сохранит прежнюю композицию.
                </small>
                {buildModeRangeError ? <small className="error">{buildModeRangeError}</small> : null}
              </div>
              <div className="cover-workflow-faces">
                <Button onClick={() => void chooseFaceLibrary()}>
                  <FolderOpen size={15} />
                  Исходники
                </Button>
                <Button onClick={() => void choosePreparedFaceFolder()}>
                  <FolderOpen size={15} />
                  Папка PNG
                </Button>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={faceLibraryEnabled}
                    onChange={(event) =>
                      setFaceLibraryEnabledAndSave(event.target.checked)
                    }
                  />
                  Лица
                </label>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={faceRemoveBackground}
                    onChange={(event) =>
                      setFaceBackgroundRemovalAndSave(event.target.checked)
                    }
                  />
                  Вырезать фон
                </label>
              </div>
              <div className="cover-workflow-faces">
                <Button
                  kind="success"
                  onClick={
                    faceLibraryFolder
                      ? () => void command("prepare-cover-face-library")
                      : undefined
                  }
                >
                  <Image size={15} />
                  Подготовить PNG
                </Button>
                <Button
                  onClick={
                    data.coverSettings.faceLibrary.preparedFolder
                      ? () =>
                          void window.newsflowDesktop?.openPath(
                            data.coverSettings.faceLibrary.preparedFolder,
                          )
                      : undefined
                  }
                >
                  <FolderOpen size={15} />
                  Открыть PNG
                </Button>
                <Button
                  onClick={
                    data.coverSettings.faceLibrary.preparedPaths?.length
                      ? () => setShowPreparedFaces((value) => !value)
                      : undefined
                  }
                >
                  <Image size={15} />
                  {showPreparedFaces ? "Скрыть PNG" : "Посмотреть PNG"}
                </Button>
              </div>
              <small>
                {data.coverSettings.faceLibrary.count} исходников ·{" "}
                {data.coverSettings.faceLibrary.preparedCount} PNG без фона
                {data.coverSettings.faceLibrary.preparedFolder
                  ? ` · ${data.coverSettings.faceLibrary.preparedFolder}`
                  : ""}
              </small>
            </div>
            {showPreparedFaces &&
            data.coverSettings.faceLibrary.preparedPaths?.length ? (
              <div className="cover-prepared-face-grid">
                {data.coverSettings.faceLibrary.preparedPaths.map((path) => (
                  <button
                    key={path}
                    title={path}
                    onClick={() => void window.newsflowDesktop?.openPath(path)}
                  >
                    <CoverPreviewImage
                      path={path}
                      alt={path.split(/[\\/]/).pop() || "Вырезанный портрет"}
                    />
                    <small>{path.split(/[\\/]/).slice(-2).join(" / ")}</small>
                  </button>
                ))}
              </div>
            ) : null}
          </article>
          <article>
            <span>03</span>
            <div>
              <b>Запустите FastGen</b>
              <small>
                {promptsReady
                  ? `Промпты готовы. Режим: ${coverBuildMode === "fastgen-full" ? "всё через FastGen" : "FastGen всё + мои лица"}.`
                  : "Сначала создайте промпты на шаге 01."}
              </small>
            </div>
            <Button
              kind="success"
              onClick={promptsReady && !coverGenerationStarting ? generateAutomatically : undefined}
            >
              <Sparkles size={17} />
              Создать обложки
            </Button>
            <Button onClick={reconcileGallery}>
              <RefreshCw size={16} />
              Проверить обложки
            </Button>
          </article>
          <article>
            <span>04</span>
            <div>
              <b>Доработайте готовую картинку</b>
              <small>
                Обычно этот шаг не нужен: в выбранных режимах FastGen уже рисует
                текст. Используйте только если хотите отдельный новый текстовый
                вариант.
              </small>
            </div>
            <label className="check-row">
              <input
                type="checkbox"
                checked={autoTextColor}
                onChange={(event) => {
                  setAutoTextColor(event.target.checked);
                  void command("save-cover-settings", {
                    autoTextColor: event.target.checked,
                  });
                }}
              />
              Автоцвет + чёрная обводка
            </label>
            <Button
              kind="primary"
              onClick={localTextReady ? renderText : undefined}
            >
              <Pencil size={17} />
              Только наложить текст локально
            </Button>
            <Button
              onClick={fastgenTextReady ? renderTextWithFastGen : undefined}
            >
              <WandSparkles size={16} />
              Новый текстовый вариант FastGen
            </Button>
            <small className="cover-workflow-render-note">
              В режиме «Всё через FastGen» локальный текст не добавляется.
              FastGen получает готовые слова, правила шрифта, плашки, рамки и
              портретный референс.
            </small>
            <Button
              kind="danger"
              onClick={
                data.coverSettings.generationPaused
                  ? undefined
                  : () => void command("pause-cover-generation")
              }
            >
              <Pause size={16} />
              Пауза
            </Button>
            <Button
              kind="primary"
              onClick={data.coverSettings.generationPaused ? resumeGeneration : undefined}
            >
              <Play size={16} />
              Продолжить
            </Button>
            <Button
              kind="success"
              onClick={
                !data.coverSettings.generationPaused && promptsReady && !coverGenerationStarting
                  ? generateAutomatically
                  : undefined
              }
            >
              <Sparkles size={16} />
              Запустить
            </Button>
          </article>
        </div>
        {coverPromptImportError ? <div className="knowledge-status" role="alert">{coverPromptImportError}</div> : null}
      </section>
      <section className="panel cover-settings-launcher">
        <div>
          <span className="eyebrow">STUDIO CONFIGURATION</span>
          <b>Рендер, референсы и текст</b>
          <small>
            Тонкие настройки вынесены из рабочей очереди. Они не меняют
            выбранный ProductionItem и применяются только через текущие
            команды сохранения.
          </small>
        </div>
        <Button onClick={() => setSettingsOpen(true)}>
          <Settings2 size={16} />
          Настроить студию
        </Button>
      </section>
      <Sheet
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        title="Настройки Visual Production Studio"
        description="Текущие параметры FastGen, промптов, референсов, лиц и текста."
      >
      <section
        className="cover-control-deck"
        aria-label="Устаревшие быстрые действия для обложек"
      >
        <article className="panel cover-control-card prompt">
          <span className="cover-control-number">01</span>
          <div>
            <b>Промпты для картинок</b>
            <small>
              Выбрано: {selected.length || "все темы"}. Сначала создайте
              визуальный промпт, затем запускайте FastGen.
            </small>
          </div>
          <div className="cover-prompt-count">
            <label>
              Визуальных промптов на тему
              <input
                type="number"
                min="1"
                max="10"
                step="1"
                inputMode="numeric"
                value={promptCount}
                onChange={(event) => setManualPromptCount(event.target.value)}
                onBlur={() => {
                  if (!promptCount) commitPromptCount(1);
                }}
              />
            </label>
            <small>
              От 1 до 10: рекомендуются 2 — крупный конфликт и панорамный
              вариант.
            </small>
          </div>
          <div className="toolbar compact">
            <Button kind="primary" onClick={() => void generatePrompts()}>
              <Sparkles size={16} />
              Создать {promptCountValue} промпт
              {promptCountValue === 1 ? "" : promptCountValue < 5 ? "а" : "ов"}
            </Button>
            <Button
              onClick={
                selected.length ? () => void rewritePrompts() : undefined
              }
            >
              <WandSparkles size={16} />
              Переписать выбранные ИИ
            </Button>
            <Button onClick={exportPrompts}>
              <Download size={15} />
              Скачать
            </Button>
          </div>
        </article>
        <article className="panel cover-control-card faces">
          <span className="cover-control-number">02</span>
          <div className="cover-face-quick">
            <div>
              <b>Лица для обложек</b>
              <small>
                Вложенные папки с Путиным, Алиевым и другими сканируются
                автоматически. Режим выбирается выше и сам по себе не запускает
                генерацию.
              </small>
            </div>
            <label>
              Папка лиц
              <input
                value={faceLibraryFolder}
                onChange={(event) => setFaceLibraryFolder(event.target.value)}
                placeholder="D:\\NewsFlow\\Лица"
              />
            </label>
          </div>
          <div className="toolbar compact">
            <Button onClick={() => void chooseFaceLibrary()}>
              <FolderOpen size={16} />
              Выбрать папку
            </Button>
            <Button
              kind="primary"
              onClick={faceLibraryFolder ? save : undefined}
            >
              <Check size={16} />
              Сохранить путь
            </Button>
            <Button
              onClick={
                faceLibraryFolder
                  ? () => void command("prepare-cover-face-library")
                  : undefined
              }
            >
              <Image size={16} />
              Подготовить PNG
            </Button>
          </div>
          <div className="cover-face-quick-status">
            <span>
              {faceLibraryEnabled
                ? "Автоподбор: включён"
                : "Автоподбор: выключен"}
            </span>
            <span>{data.coverSettings.faceLibrary.count} фото найдено</span>
            <span>
              {data.coverSettings.faceLibrary.preparedCount} PNG без фона
            </span>
            <label className="check-row">
              <input
                type="checkbox"
                checked={faceLibraryEnabled}
                onChange={(event) =>
                  setFaceLibraryEnabledAndSave(event.target.checked)
                }
              />
              Использовать лица
            </label>
            <label className="check-row">
              <input
                type="checkbox"
                checked={faceRemoveBackground}
                onChange={(event) =>
                  setFaceBackgroundRemovalAndSave(event.target.checked)
                }
              />
              Вырезать фон
            </label>
          </div>
        </article>
        <article className="panel cover-control-card errors">
          <span className="cover-control-number">03</span>
          <div>
            <b>Ошибки FastGen</b>
            <small>
              Это ответы последнего рендера. Наведите на тему, чтобы прочитать
              точную причину; можно повторить запрос или подготовить новый
              промпт.
            </small>
          </div>
          {data.covers.some(
            (cover) => cover.error || cover.status?.includes("Ошибка"),
          ) ? (
            <div className="cover-quick-errors">
              {data.covers.map((cover, index) =>
                cover.error || cover.status?.includes("Ошибка") ? (
                  <div
                    key={`${cover.title}-${index}`}
                    title={cover.error || cover.status}
                  >
                    <span>
                      {cover.scenario_index || index + 1}. {cover.title}
                    </span>
                    <Button
                      onClick={isCoverManualRetryEligible(cover)
                        ? () => void command("retry-cover-generation", coverSelectionPayload([index]))
                        : undefined}
                    >
                      <Play size={14} />
                      Повторить генерацию
                    </Button>
                    <Button
                      kind="primary"
                      onClick={() =>
                        void command("regenerate-covers-new-prompts", {
                          ...coverSelectionPayload([index]),
                          provider,
                        })
                      }
                    >
                      <WandSparkles size={14} />
                      Создать новый промпт
                    </Button>
                  </div>
                ) : null,
              )}
            </div>
          ) : (
            <div className="cover-no-errors">
              <Check size={16} />
              Ошибок FastGen пока нет
            </div>
          )}
        </article>
      </section>
      <section className="panel fastgen-rate-resume">
        <div className="panel-title">
          <div>
            <b>Очередь FastGen после лимита</b>
            <small>
              Готовые обложки не повторяются: в ожидании остаются только темы,
              для которых запрос ещё не начинался.
            </small>
          </div>
          <span className="status">
            {rateWaitingCovers.length
              ? `Ожидают: ${rateWaitingCovers.length}`
              : "Очередь не ждёт лимит"}
          </span>
        </div>
        <div className="toolbar">
          <label>
            Лимит изображений в час
            <input
              type="number"
              min="0"
              value={rateLimitPerHour}
              onChange={(event) => setRateLimitPerHour(event.target.value)}
              onBlur={() => void command("save-cover-settings", coverSettingsPayload())}
              placeholder="0 — только лимит API"
            />
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={rateAutoResume}
              onChange={(event) => {
                setRateAutoResume(event.target.checked);
                void command("save-cover-settings", {
                  ...coverSettingsPayload(),
                  rateAutoResume: event.target.checked,
                });
              }}
            />
            Автопродолжение после лимита
          </label>
          <Button
            kind="primary"
            onClick={
              rateWaitingCovers.length
                ? () => void command("resume-cover-generation")
                : undefined
            }
          >
            <Play size={16} />
            Продолжить очередь
          </Button>
        </div>
        <small>
          {nextRateResume
            ? `Следующая попытка: ${new Date(nextRateResume).toLocaleString("ru-RU")}. `
            : "Следующая попытка появится, когда локальный лимит будет достигнут. "}
          Учтено в текущем часовом окне: {data.coverSettings.rateUsed || 0}
          {data.coverSettings.rateLimitPerHour
            ? ` / ${data.coverSettings.rateLimitPerHour}`
            : " — локальный лимит выключен"}.
        </small>
      </section>
      <section className="panel fastgen-live">
        <div className="panel-title">
          <div>
            <b>FastGen: лимиты и активные потоки</b>
            <small>
              {data.fastgenUsage?.updatedAt
                ? `Ответ API получен: ${data.fastgenUsage.updatedAt}`
                : "Нажмите «Обновить модели», чтобы запросить FastGen API."}
            </small>
          </div>
          <Button onClick={() => void command("refresh-fastgen")}>
            <Activity size={16} />
            Обновить FastGen
          </Button>
        </div>
        {fastgenUsage.length ? (
          <div className="fastgen-usage-grid">
            {fastgenUsage.map((item) => (
              <article key={item.label}>
                <b>{item.label}</b>
                {item.error ? (
                  <small className="error">Ошибка API: {item.error}</small>
                ) : (
                  <>
                    <span>
                      Изображения:{" "}
                      {item.image.knownUsed ? item.image.used : "—"} /{" "}
                      {item.image.limit || "—"} в час
                    </span>
                    <span>
                      Потоки изображений: {item.image.threads} /{" "}
                      {item.image.threadLimit || "—"}
                    </span>
                    <span>
                      Видео: {item.video.knownUsed ? item.video.used : "—"} /{" "}
                      {item.video.limit || "—"} в час · потоки{" "}
                      {item.video.threads} / {item.video.threadLimit || "—"}
                    </span>
                    <span>
                      Токены промптов:{" "}
                      {item.prompts.knownUsed ? item.prompts.used : "—"} /{" "}
                      {item.prompts.limit || "—"} в час
                    </span>
                  </>
                )}
              </article>
            ))}
          </div>
        ) : (
          <div className="fastgen-empty">
            Лимиты ещё не запрошены. Данные не выдумываются: они появятся только
            из <code>/api/v6/usage</code>.
          </div>
        )}
      </section>
      <section className="panel fastgen-models-live">
        <div className="panel-title">
          <div>
            <b>Модели FastGen — ответ API</b>
            <small>
              {hasLiveFastGenModels
                ? `${liveModels.length} моделей изображения получено из FastGen${catalogOnlyModels.length ? `; ещё ${catalogOnlyModels.length} документированных маршрута ожидают проверки API` : ""}. Выбрана сейчас: ${selectedModel?.display_name || selectedModel?.id || operation}.`
                : `Доступен документированный каталог до проверки API. Выбрана сейчас: ${selectedModel?.display_name || selectedModel?.id || operation}.`}
            </small>
          </div>
          <span className="api-live-dot">● {hasLiveFastGenModels ? "LIVE" : "CATALOG"}</span>
        </div>
        {models.length ? (
          <div className="fastgen-model-grid">
            {models.map((item) => {
              const modelId = String(item.id || "");
              return <button
                type="button"
                key={modelId}
                className={`${item.health || "unavailable"} ${operation === modelId ? "current" : ""}`}
                disabled={item.health === "unavailable" || item.deprecated}
                onClick={() => selectFastGenOperation(modelId)}
                title={
                  item.health === "unavailable" || item.deprecated
                    ? "Модель недоступна в текущем ответе FastGen"
                    : "Выбрать эту модель для рендера"
                }
              >
                <span>
                  {item.health === "healthy"
                    ? "●"
                    : item.health === "degraded"
                      ? "●"
                      : "●"}{" "}
                  {item.health_label || "Нет ответа API"}
                </span>
                <b>{item.display_name || item.model || item.id}</b>
                <small>
                  {item.provider || "FastGen"} ·{" "}
                  {item.billing?.display || "цена не передана API"}
                </small>
                {operation === modelId ? <em>Выбрана для рендера</em> : null}
              </button>
            })}
          </div>
        ) : (
          <div className="fastgen-empty">Каталог моделей пока недоступен.</div>
        )}
      </section>
      <div className="covers-workspace">
        <section className="panel cover-settings">
          <div className="panel-title">
            <div>
              <b>1. Рендер FastGen</b>
              <small>
                Модели получены из <code>/api/v6/capabilities</code> и сверены с{" "}
                <code>/api/v6/models</code>. Красные модели нельзя выбрать.
              </small>
            </div>
            <Button onClick={() => void command("refresh-fastgen")}>
              <Activity size={16} />
              Обновить модели
            </Button>
          </div>
          <div className="fastgen-layout">
            <label>
              Активная модель
              <select
                value={operation}
                onChange={(event) => selectFastGenOperation(event.target.value)}
              >
                {models.length ? (
                  models.map((item) => (
                    <option
                      key={item.id}
                      value={item.id}
                      disabled={
                        item.health === "unavailable" || item.deprecated
                      }
                    >
                      {item.health === "unavailable" || item.deprecated
                        ? "●"
                        : item.health === "degraded"
                          ? "●"
                          : "●"}{" "}
                      {item.provider || "FastGen"} ·{" "}
                      {item.display_name || item.model || item.id} ·{" "}
                      {item.health_label || "Нет данных"}
                      {item.billing?.display
                        ? ` · ${item.billing.display}`
                        : ""}
                    </option>
                  ))
                ) : null}
              </select>
            </label>
            <div className="model-legend">
              <span className="healthy">● Доступна по API</span>
              <span className="degraded">● Ограничение / beta API</span>
              <span className="unavailable">● Не возвращена API</span>
            </div>
            <div className="form-grid compact-grid">
              <label>
                Формат
                <select
                  value={ratio}
                  onChange={(event) => setRatio(event.target.value)}
                >
                  <option>16:9</option>
                  <option>9:16</option>
                  <option>1:1</option>
                </select>
              </label>
              <label>
                Картинок на промпт
                <input
                  type="number"
                  min="1"
                  max="10"
                  step="1"
                  inputMode="numeric"
                  value={count}
                  onChange={(event) => setManualImageCount(event.target.value)}
                  onBlur={() => {
                    if (!count) commitImageCount(1);
                  }}
                />
                <small>Сейчас: {imageCountValue}</small>
              </label>
              <label>
                Seed{" "}
                <input
                  value={seed}
                  onChange={(event) => setSeed(event.target.value)}
                  placeholder="Необязательно"
                />
              </label>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={upscale}
                  onChange={(event) => setUpscale(event.target.checked)}
                />
                Апскейл 2×
              </label>
            </div>
            <Button kind="primary" onClick={save}>
              <Check size={16} />
              Сохранить настройки
            </Button>
          </div>
        </section>
        <section className="panel cover-template">
          <div className="panel-title">
            <div>
              <b>2. Правила и промпты</b>
              <small>
                Бриф необязателен: по умолчанию агент собирает визуальный промпт
                сам по теме и правилам NewsFlow.
              </small>
            </div>
            <div className="toolbar compact">
              <Button onClick={importTemplate}>
                <Upload size={16} />
                TXT / MD
              </Button>
              <Button onClick={save}>
                <Check size={16} />
                Сохранить
              </Button>
            </div>
          </div>
          <div className="cover-preset-row">
            <select
              value={selectedPreset}
              onChange={(event) => applyPreset(event.target.value)}
            >
              <option value="">Пресеты обложек</option>
              {data.coverSettings.presets.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
            <input
              value={presetName}
              onChange={(event) => setPresetName(event.target.value)}
              placeholder="Название пресета"
            />
            <Button onClick={savePreset}>
              <Library size={15} />
              Сохранить пресет
            </Button>
            <Button kind="danger" onClick={removePreset}>
              <Trash2 size={15} />
            </Button>
          </div>
          <ProviderSwitch
            value={provider}
            onChange={selectCoverPromptProvider}
            label="Кто пишет промпты"
          />
          <label className="check-row">
            <input
              type="checkbox"
              checked={useCustomPrompt}
              onChange={(event) => {
                setUseCustomPrompt(event.target.checked);
                void command("save-cover-settings", {
                  useCustomPrompt: event.target.checked,
                });
              }}
            />
            Использовать мой визуальный бриф{" "}
            <small>
              выключено — агент работает только по теме и встроенным правилам
              NewsFlow
            </small>
          </label>
          <label className="prompt-editor">
            <span>Мой визуальный бриф для агента / ChatGPT</span>
            <textarea
              value={template}
              onChange={(event) => {
                setTemplate(event.target.value);
                setUseCustomPrompt(true);
              }}
              placeholder="Пишите как арт-директор: панорамный вид, люди, взрывы только если это подходит теме, композиция, цвет, запреты. Используйте {title} и {excerpt}."
            />
            <small>
              {template.trim()
                ? `${template.length} символов · твои рекомендации будут переданы выбранному агенту или ChatGPT`
                : "Поле пустое: дополнительные правила не передаются. Напишите рекомендацию — она включится автоматически."}
            </small>
          </label>
          <div className="cover-prompt-options">
            <label>
              Промптов на сценарий
              <input
                type="number"
                min="1"
                max="10"
                step="1"
                inputMode="numeric"
                value={promptCount}
                onChange={(event) => setManualPromptCount(event.target.value)}
                onBlur={() => {
                  if (!promptCount) commitPromptCount(1);
                }}
              />
              <small>От 1 до 10</small>
            </label>
            <label className="check-row">
              <input
                type="checkbox"
                checked={useScript}
                onChange={(event) => setUseScript(event.target.checked)}
              />
              Учитывать текст сценария <small>точнее, но больше токенов</small>
            </label>
          </div>
          <div className="cover-ranges">
            <div className="ranges-title">
              <div>
                <b>Диапазоны обложек</b>
                <small>
                  Каждому диапазону можно дать другой стиль и загрузить TXT/MD.
                </small>
              </div>
              <Button onClick={addRange}>
                <Plus size={15} />
                Диапазон
              </Button>
            </div>
            {ranges.map((range, index) => (
              <div className="cover-range" key={index}>
                <input
                  type="number"
                  min="1"
                  value={range.start}
                  onChange={(event) =>
                    setRanges((current) =>
                      current.map((item, row) =>
                        row === index
                          ? { ...item, start: Number(event.target.value) }
                          : item,
                      ),
                    )
                  }
                />
                <span>—</span>
                <input
                  type="number"
                  min="1"
                  value={range.end}
                  onChange={(event) =>
                    setRanges((current) =>
                      current.map((item, row) =>
                        row === index
                          ? { ...item, end: Number(event.target.value) }
                          : item,
                      ),
                    )
                  }
                />
                <textarea
                  value={range.prompt}
                  onChange={(event) =>
                    setRanges((current) =>
                      current.map((item, row) =>
                        row === index
                          ? { ...item, prompt: event.target.value }
                          : item,
                      ),
                    )
                  }
                  placeholder="Особый стиль для сценариев этого диапазона…"
                />
                <Button onClick={() => void importRange(index)}>
                  <Upload size={15} />
                  TXT
                </Button>
                <Button
                  kind="danger"
                  onClick={() =>
                    setRanges((current) =>
                      current.filter((_item, row) => row !== index),
                    )
                  }
                >
                  <Trash2 size={15} />
                </Button>
              </div>
            ))}
          </div>
        </section>
      </div>
      <section className="panel cover-references">
        <div className="panel-title">
          <div>
            <b>Референсы FastGen</b>
            <small>
              Эти изображения передаются только FastGen при рендере. Они задают
              композицию и стиль, но не копируются буквально.
            </small>
            <label className="check-row reference-enable-toggle">
              <input
                type="checkbox"
                checked={referenceMode !== "off"}
                onChange={(event) =>
                  setReferenceMode(
                    event.target.checked
                      ? referenceRanges.length
                        ? "ranges"
                        : "all"
                      : "off",
                  )
                }
              />
              Учитывать референсы FastGen
            </label>
            <small>
              {referenceMode === "off"
                ? "Выключено: FastGen использует тему и правила NewsFlow."
                : "Включено: FastGen получит картинки выбранного режима ниже."}
            </small>
          </div>
          <Button onClick={save}>
            <Check size={16} />
            Сохранить референсы
          </Button>
        </div>
        <div className="reference-mode-grid">
          <button
            className={referenceMode === "all" ? "selected" : ""}
            onClick={() => setReferenceMode("all")}
          >
            <b>Один стиль на все темы</b>
            <small>Один набор держит единый дизайн канала.</small>
          </button>
          <button
            className={referenceMode === "ranges" ? "selected" : ""}
            onClick={() => setReferenceMode("ranges")}
          >
            <b>Стили по диапазонам</b>
            <small>Например, 1–10 — один пакет, 11–20 — другой.</small>
          </button>
          <button
            className={referenceMode === "off" ? "selected" : ""}
            onClick={() => setReferenceMode("off")}
          >
            <b>Не учитывать</b>
            <small>Агент и FastGen используют только правила NewsFlow.</small>
          </button>
        </div>
        {referenceMode === "all" ? (
          <>
            <div className="toolbar compact">
              <Button onClick={() => void chooseReferences()}>
                <Upload size={16} />
                Добавить и выбрать изображения
              </Button>
              <Button
                kind="danger"
                onClick={
                  references.length ? () => setReferences([]) : undefined
                }
              >
                <Trash2 size={16} />
                Очистить выбор
              </Button>
            </div>
            {references.length ? (
              <div className="reference-list">
                {references.map((path) => (
                  <span key={path}>
                    <CoverPreviewImage
                      className="reference-preview"
                      path={path}
                      alt={`Референс ${path.split(/[\\/]/).pop()}`}
                    />
                    <Image size={15} />
                    {path.split(/[\\/]/).pop()}
                    <button
                      aria-label={`Убрать референс ${path.split(/[\\/]/).pop()}`}
                      onClick={() =>
                        setReferences((current) =>
                          current.filter((value) => value !== path),
                        )
                      }
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <div className="cover-research-note">
                <b>Добавьте референсы канала</b>
                <span>
                  Выберите один, два или до десяти своих удачных примеров. При
                  создании промптов агент увидит их, выделит общую композицию и
                  контраст, а FastGen использует как ориентир.
                </span>
              </div>
            )}
          </>
        ) : null}
        {referenceMode === "ranges" ? (
          <div className="reference-ranges">
            <div className="ranges-title">
              <div>
                <b>Пакеты референсов по темам</b>
                <small>
                  Диапазоны произвольные: 1–3, 7–8, 11–20. Каждый пакет получает
                  только свои выбранные картинки. При пересечении берётся первый
                  пакет сверху.
                </small>
              </div>
              <Button onClick={addReferenceRange}>
                <Plus size={15} />
                Добавить диапазон
              </Button>
            </div>
            {referenceRanges.map((range, index) => (
              <div className="reference-range" key={index}>
                <label>
                  С
                  <input
                    type="number"
                    min="1"
                    value={range.start}
                    onChange={(event) =>
                      setReferenceRanges((current) =>
                        current.map((item, row) =>
                          row === index
                            ? { ...item, start: Number(event.target.value) }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <span>—</span>
                <label>
                  По
                  <input
                    type="number"
                    min="1"
                    value={range.end}
                    onChange={(event) =>
                      setReferenceRanges((current) =>
                        current.map((item, row) =>
                          row === index
                            ? { ...item, end: Number(event.target.value) }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <Button onClick={() => void chooseReferenceRange(index)}>
                  <Upload size={15} />
                  Референсы ({range.paths.length}/10)
                </Button>
                <div className="reference-list compact">
                  {range.paths.map((path) => (
                    <span key={path}>
                      <CoverPreviewImage
                        className="reference-preview"
                        path={path}
                        alt={`Референс ${path.split(/[\\/]/).pop()}`}
                      />
                      {path.split(/[\\/]/).pop()}
                      <button
                        aria-label={`Убрать референс ${path.split(/[\\/]/).pop()}`}
                        onClick={() =>
                          setReferenceRanges((current) =>
                            current.map((item, row) =>
                              row === index
                                ? {
                                    ...item,
                                    paths: item.paths.filter(
                                      (value) => value !== path,
                                    ),
                                  }
                                : item,
                            ),
                          )
                        }
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <Button
                  kind="danger"
                  onClick={() =>
                    setReferenceRanges((current) =>
                      current.filter((_item, row) => row !== index),
                    )
                  }
                >
                  <Trash2 size={15} />
                </Button>
              </div>
            ))}
          </div>
        ) : null}
        {referenceMode === "off" ? (
          <div className="cover-research-note">
            <b>Референсы отключены</b>
            <span>
              Ни агент, ни ChatGPT, ни FastGen не получат загруженные
              изображения. Включите один из двух режимов выше, когда захотите
              снова использовать дизайн-ориентиры.
            </span>
          </div>
        ) : null}
      </section>
      <section className="panel cover-ai-references">
        <div className="panel-title">
          <div>
            <b>Отдельные референсы для ИИ-промптов</b>
            <small>
              Эти изображения видит только агент/ChatGPT при написании промпта.
              Референсы FastGen настраиваются выше отдельно. Можно включать
              общий набор, произвольные диапазоны или выключить.
            </small>
          </div>
          <div className="toolbar compact">
            <Button onClick={save}>
              <Check size={16} />
              Сохранить для ИИ
            </Button>
            <Button onClick={copyAiReferencesToFastgen}>
              <Upload size={16} />
              Отправить выбранные в FastGen
            </Button>
          </div>
        </div>
        <div className="reference-mode-grid">
          <button
            className={aiReferenceMode === "all" ? "selected" : ""}
            onClick={() => setAiReferenceMode("all")}
          >
            <b>Один набор для ИИ</b>
            <small>Один стиль промптов на все темы.</small>
          </button>
          <button
            className={aiReferenceMode === "ranges" ? "selected" : ""}
            onClick={() => setAiReferenceMode("ranges")}
          >
            <b>Диапазоны для ИИ</b>
            <small>Для каждой группы тем свой пакет картинок.</small>
          </button>
          <button
            className={aiReferenceMode === "off" ? "selected" : ""}
            onClick={() => setAiReferenceMode("off")}
          >
            <b>Не учитывать ИИ-референсы</b>
            <small>ИИ работает по теме и правилам NewsFlow.</small>
          </button>
        </div>
        {aiReferenceMode === "all" ? (
          <>
            <div className="toolbar compact">
              <Button onClick={chooseAiReferences}>
                <Upload size={16} />
                Добавить изображения для ИИ
              </Button>
              <Button
                kind="danger"
                onClick={
                  aiReferences.length ? () => setAiReferences([]) : undefined
                }
              >
                <Trash2 size={16} />
                Очистить
              </Button>
            </div>
            {aiReferences.length ? (
              <div className="reference-list">
                {aiReferences.map((path) => (
                  <span key={path}>
                    <CoverPreviewImage
                      className="reference-preview"
                      path={path}
                      alt={`ИИ-референс ${path.split(/[\\/]/).pop()}`}
                    />
                    {path.split(/[\\/]/).pop()}
                    <button
                      aria-label={`Убрать ИИ-референс ${path.split(/[\\/]/).pop()}`}
                      onClick={() =>
                        setAiReferences((current) =>
                          current.filter((value) => value !== path),
                        )
                      }
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <div className="cover-research-note">
                <b>Для ИИ пока нет выбранных изображений</b>
                <span>
                  Добавьте 1–10 примеров дизайна. Они не отправляются в FastGen,
                  пока вы сами не нажмёте «Отправить выбранные в FastGen».
                </span>
              </div>
            )}
          </>
        ) : null}
        {aiReferenceMode === "ranges" ? (
          <div className="reference-ranges">
            <div className="ranges-title">
              <div>
                <b>Пакеты ИИ-референсов по темам</b>
                <small>Диапазоны можно задавать любыми: 1–3, 7–8, 11–20.</small>
              </div>
              <Button onClick={addAiReferenceRange}>
                <Plus size={15} />
                Добавить диапазон
              </Button>
            </div>
            {aiReferenceRanges.map((range, index) => (
              <div className="reference-range" key={index}>
                <label>
                  С
                  <input
                    type="number"
                    min="1"
                    value={range.start}
                    onChange={(event) =>
                      setAiReferenceRanges((current) =>
                        current.map((item, row) =>
                          row === index
                            ? { ...item, start: Number(event.target.value) }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <span>—</span>
                <label>
                  По
                  <input
                    type="number"
                    min="1"
                    value={range.end}
                    onChange={(event) =>
                      setAiReferenceRanges((current) =>
                        current.map((item, row) =>
                          row === index
                            ? { ...item, end: Number(event.target.value) }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <Button onClick={() => chooseAiReferenceRange(index)}>
                  <Upload size={15} />
                  ИИ-референсы ({range.paths.length}/10)
                </Button>
                <div className="reference-list compact">
                  {range.paths.map((path) => (
                    <span key={path}>
                      <CoverPreviewImage
                        className="reference-preview"
                        path={path}
                        alt={`ИИ-референс ${path.split(/[\\/]/).pop()}`}
                      />
                      {path.split(/[\\/]/).pop()}
                      <button
                        aria-label={`Убрать ИИ-референс ${path.split(/[\\/]/).pop()}`}
                        onClick={() =>
                          setAiReferenceRanges((current) =>
                            current.map((item, row) =>
                              row === index
                                ? {
                                    ...item,
                                    paths: item.paths.filter(
                                      (value) => value !== path,
                                    ),
                                  }
                                : item,
                            ),
                          )
                        }
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <Button
                  kind="danger"
                  onClick={() =>
                    setAiReferenceRanges((current) =>
                      current.filter((_item, row) => row !== index),
                    )
                  }
                >
                  <Trash2 size={15} />
                </Button>
              </div>
            ))}
          </div>
        ) : null}
      </section>
      <section className="panel cover-ai-fastgen-target">
        <div className="panel-title">
          <div>
            <b>Передача ИИ-референсов в FastGen</b>
            <small>
              Это независимая галочка: ИИ всегда может изучить картинку для
              промпта, а FastGen получит её только по вашему выбору.
            </small>
          </div>
          <Button onClick={save}>
            <Check size={16} />
            Сохранить
          </Button>
        </div>
        {aiReferenceMode === "all" ? (
          <label className="check-row">
            <input
              type="checkbox"
              checked={aiReferenceToFastgen}
              onChange={(event) =>
                setAiReferenceToFastgen(event.target.checked)
              }
            />
            Также отправить общий набор ИИ-референсов в FastGen
          </label>
        ) : aiReferenceMode === "ranges" ? (
          <div className="reference-ranges">
            {aiReferenceRanges.map((range, index) => (
              <div
                className="reference-range ai-fastgen-range"
                key={`${range.start}-${range.end}-${index}`}
              >
                <b>
                  Темы {range.start}—{range.end}
                </b>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={Boolean(range.sendToFastgen)}
                    onChange={(event) =>
                      setAiReferenceRanges((current) =>
                        current.map((item, row) =>
                          row === index
                            ? { ...item, sendToFastgen: event.target.checked }
                            : item,
                        ),
                      )
                    }
                  />
                  Также отправить {range.paths.length} референс(а) в FastGen
                </label>
              </div>
            ))}
          </div>
        ) : (
          <div className="cover-research-note">
            Сначала включите набор ИИ-референсов или диапазоны.
          </div>
        )}
      </section>
      <section className="panel cover-headline-lab">
        <div className="panel-title">
          <div>
            <b>Заголовки и подзаголовки обложки</b>
            <small>
              Каждая кнопка заполняет левое поле конкретной темы. Авто-режим не
              использует твои промпты.
            </small>
          </div>
          <div className="toolbar compact">
            <Button
              kind="primary"
              onClick={data.covers.length ? () => generateAutoCoverTextPair(false, []) : undefined}
            >
              <Sparkles size={16} />
              Придумать заголовки и подзаголовки — всем
            </Button>
            <Button
              kind="primary"
              onClick={selected.length ? () => generateAutoCoverTextPair(false, selected) : undefined}
            >
              <Sparkles size={16} />
              Придумать заголовки и подзаголовки — выбранным
            </Button>
            <Button kind="primary" onClick={generateAutoHeadlines}>
              <Sparkles size={16} />
              Создать заголовки — авто
            </Button>
            <Button kind="primary" onClick={generateAutoSubheadlines}>
              <Sparkles size={16} />
              Создать подзаголовки — авто
            </Button>
            <Button onClick={() => generateAutoHeadlines(true)}>
              <WandSparkles size={16} />
              Перегенерировать заголовки — авто
            </Button>
            <Button onClick={() => generateAutoSubheadlines(true)}>
              <WandSparkles size={16} />
              Перегенерировать подзаголовки — авто
            </Button>
            <Button
              kind="danger"
              onClick={selected.length ? () => generateAutoCoverTextPair(true, selected, true) : undefined}
            >
              <WandSparkles size={16} />
              Заменить ручной текст ИИ
            </Button>
          </div>
        </div>
        <div className="cover-preset-row cover-headline-preset-row">
          <label className={`check-row cover-tabloid-toggle ${tabloidMode ? "enabled" : ""}`}>
            <input
              aria-label="Жёлтая пресса / максимально кликбейтный стиль"
              type="checkbox"
              checked={tabloidMode}
              onChange={(event) => {
                setTabloidMode(event.target.checked);
                void command("save-cover-settings", { tabloidMode: event.target.checked });
              }}
            />
            <span>
              <b>Жёлтая пресса</b>
              <small>
                {tabloidMode
                  ? "TABLOID: жёстче, эмоциональнее и грязнее, но без метафор и выдуманных фактов"
                  : "STANDARD: прямой, естественный и эмоциональный текст без литературности"}
              </small>
            </span>
            <em>{tabloidMode ? "TABLOID" : "STANDARD"}</em>
          </label>
          <Button
            onClick={coverTextImporting ? undefined : importCoverTextTriples}
            aria-busy={coverTextImporting}
          >
            <Upload size={16} />
            Импортировать тексты TXT
          </Button>
          <select
            value={selectedHeadlinePreset}
            onChange={(event) => applyHeadlinePreset(event.target.value)}
          >
            <option value="">Пресеты текстов обложки</option>
            {data.coverSettings.headlinePresets.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name}
              </option>
            ))}
          </select>
          <input
            value={headlinePresetName}
            onChange={(event) => setHeadlinePresetName(event.target.value)}
            placeholder="Название пресета"
          />
          <Button onClick={saveHeadlinePreset}>
            <Library size={15} />
            Сохранить пресет
          </Button>
          <Button kind="danger" onClick={deleteHeadlinePreset}>
            <Trash2 size={15} />
            Удалить
          </Button>
        </div>
        {coverTextImportError ? <div className="knowledge-status" role="alert">{coverTextImportError}</div> : null}
        <div className="cover-headline-settings">
          <ProviderSwitch
            value={headlineProvider}
            onChange={selectHeadlineProvider}
            label="Кто генерирует текст"
          />
          <label className="prompt-editor">
            <span>Твой промпт для главных слов</span>
            <textarea
              value={headlineTemplate}
              onChange={(event) => setHeadlineTemplate(event.target.value)}
              placeholder="Например: придумай 2–5 сильных слов для обложки по теме {title}…"
            />
            <small>
              Используйте {"{title}"} и {"{excerpt}"}. Без выбора правила
              применяются ко всем темам.
            </small>
          </label>
          <div>
            <label>
              Текст на изображении
              <select
                value={textMode}
                onChange={(event) =>
                  selectCoverTextMode(event.target.value as "overlay" | "fastgen")
                }
              >
                <option value="overlay">
                  NewsFlow наложит точный текст — рекомендовано
                </option>
                <option value="fastgen">
                  Попросить FastGen нарисовать текст
                </option>
              </select>
            </label>
            <label className="check-row cover-auto-overlay">
              <input
                type="checkbox"
                checked={autoOverlayText}
                onChange={(event) => setAutoOverlayText(event.target.checked)}
              />
              Автоматически наложить слова после рендера{" "}
              <small>главные слова и подзаголовок берутся из полей темы</small>
            </label>
            <label className="check-row cover-auto-overlay">
              <input
                type="checkbox"
                checked={autoTextColor}
                onChange={(event) => {
                  setAutoTextColor(event.target.checked);
                  void command("save-cover-settings", {
                    autoTextColor: event.target.checked,
                  });
                }}
              />
              Автоцвет и контраст текста{" "}
              <small>
                выбирает яркую палитру и всегда добавляет чёрную обводку
              </small>
            </label>
          </div>
          <label className="prompt-editor subheadline-template">
            <span>Твой промпт для подзаголовков</span>
            <textarea
              value={subheadlineTemplate}
              onChange={(event) => setSubheadlineTemplate(event.target.value)}
              placeholder="Например: придумай вторую строку, которая усиливает слова на обложке по теме {title}…"
            />
            <small>
              Подзаголовок уточняет главный текст, но не повторяет его.
            </small>
          </label>
        </div>
        <div className="cover-headline-actions">
          <div>
            <b>Создать с моими промптами</b>
            <small>
              Промпт заголовка и промпт подзаголовка применяются отдельно к
              выбранным темам. При создании подзаголовка ИИ учитывает уже
              записанный заголовок. Пауза останавливает следующие запросы; уже
              отправленные API-запросы завершаются.
            </small>
          </div>
          <div className="toolbar compact">
            <Button
              kind={useTextStructure ? "secondary" : "success"}
              onClick={toggleTextStructure}
            >
              <Settings2 size={16} />
              {useTextStructure ? "Без структуры" : "Структура включена"}
            </Button>
            <Button
              kind={avoidTextRepeats ? "success" : "secondary"}
              onClick={toggleTextRepeatGuard}
            >
              <Check size={16} />
              {avoidTextRepeats ? "Без повторов: ВКЛ" : "Без повторов: ВЫКЛ"}
            </Button>
            <Button kind="primary" onClick={generateHeadlines}>
              <Sparkles size={16} />
              Создать заголовки по промпту
            </Button>
            <Button kind="primary" onClick={generateSubheadlines}>
              <Sparkles size={16} />
              Создать подзаголовки по промпту
            </Button>
            <Button onClick={() => generateHeadlines(true)}>
              <WandSparkles size={16} />
              Перегенерировать заголовки по промпту
            </Button>
            <Button onClick={() => generateSubheadlines(true)}>
              <WandSparkles size={16} />
              Перегенерировать подзаголовки по промпту
            </Button>
            <Button
              kind="danger"
              onClick={
                data.coverSettings.headlinePaused ? undefined : pauseHeadlines
              }
            >
              <Pause size={16} />
              Пауза заголовков
            </Button>
            <Button
              kind="primary"
              onClick={
                data.coverSettings.headlinePaused ? resumeHeadlines : undefined
              }
            >
              <Play size={16} />
              Продолжить заголовки
            </Button>
            <Button
              kind="danger"
              onClick={
                data.coverSettings.subheadlinePaused
                  ? undefined
                  : pauseSubheadlines
              }
            >
              <Pause size={16} />
              Пауза подзаголовков
            </Button>
            <Button
              kind="primary"
              onClick={
                data.coverSettings.subheadlinePaused
                  ? resumeSubheadlines
                  : undefined
              }
            >
              <Play size={16} />
              Продолжить подзаголовки
            </Button>
          </div>
        </div>
        <div className="cover-headline-actions">
          <div>
            <b>Темы и очистка строк</b>
            <small>
              TXT только дополняет текущую очередь: одна непустая строка или
              абзац — одна новая тема. Дубликаты не добавляются.
            </small>
          </div>
          <div className="toolbar compact">
            <Button onClick={importCoverTopics}>
              <Upload size={16} />
              Загрузить свои темы TXT
            </Button>
            <Button
              kind="danger"
              onClick={selected.length ? removeOwnHeadlines : undefined}
            >
              <Trash2 size={16} />
              Удалить заголовки выбранных
            </Button>
            <Button
              kind="danger"
              onClick={() => void command("remove-cover-headlines", {})}
            >
              <Trash2 size={16} />
              Удалить заголовки все
            </Button>
            <Button
              kind="danger"
              onClick={selected.length ? cancelSubheadlines : undefined}
            >
              <Trash2 size={16} />
              Удалить подзаголовки выбранных
            </Button>
            <Button
              kind="danger"
              onClick={() => void command("cancel-cover-subheadlines", {})}
            >
              <Trash2 size={16} />
              Удалить подзаголовки все
            </Button>
          </div>
        </div>
      </section>
      <section className="panel mass-cover-selection-summary">
        <div className="mass-cover-count">
          <small>Тем выбрано</small>
          <b>{selectedTopicCount}</b>
          <span>
            {selectedTopicCount
              ? "Массовые действия затронут только выделенные строки."
              : "Выделите темы ниже: Ctrl+клик добавляет их к выбору."}
          </span>
        </div>
        <div className="mass-cover-count ready">
          <small>Новых промптов готово:</small>
          <b>
            {newPromptsReadyCount} из {selectedTopicCount}
          </b>
          <span>
            {newPromptsReadyCount
              ? "Можно запускать «Повторить с новыми»."
              : "Сначала создайте новые промпты для выбранных тем."}
          </span>
        </div>
        <label className="mass-cover-model">
          Модель для массовой генерации
          <select
            value={operation}
            onChange={(event) => setOperation(event.target.value)}
          >
            {models.length ? (
              models.map((item) => (
                <option
                  key={item.id}
                  value={item.id}
                  disabled={item.health === "unavailable" || item.deprecated}
                >
                  {item.provider || "FastGen"} ·{" "}
                  {item.display_name || item.model || item.id}
                </option>
              ))
            ) : (
              <option value={operation}>{operation}</option>
            )}
          </select>
          <small>
            Эта модель используется для новых промптов и «Повторить с новыми».
            «Повторить текущие» всегда использует модель и provider-контракт,
            сохранённые у самой обложки.
          </small>
        </label>
        <div className="toolbar compact">
          <Button
            kind="primary"
            onClick={selectedTopicCount ? rewritePrompts : undefined}
          >
            <WandSparkles size={16} />
            Создать новые промпты для выбранных
          </Button>
          <Button
            onClick={
              selectedTopicCount && promptsReady && !selectedHasActiveRender
                ? repeatCurrent
                : undefined
            }
          >
            <Play size={16} />
            Повторить текущие выбранных
          </Button>
          <Button
            kind="success"
            onClick={newPromptsReadyCount ? regenerate : undefined}
          >
            <Sparkles size={16} />
            Повторить с новыми
          </Button>
        </div>
        <small className="mass-cover-plan">
          План рендера:{" "}
          {selectedTopicCount
            ? `${plannedImageCount} картинок (${imageCountValue} на каждый промпт)`
            : "выберите темы"}
          .
        </small>
      </section>
      </Sheet>
      <section className="panel cover-action-bar">
        <div>
          <b>Промпты, рендер и выбор вариантов</b>
          <small>
            Выбрано: {selected.length || "все"}. Количество картинок считается
            как «промпты × картинки на промпт».
          </small>
        </div>
        <div className="toolbar compact">
          <Button onClick={exportPrompts}>
            <Download size={16} />
            Скачать промпты
          </Button>
          <Button onClick={exportZip}>
            <Download size={16} />
            Скачать ZIP
          </Button>
          <Button kind="primary" onClick={() => void generatePrompts([])}>
            <Sparkles size={17} />
            Создать промпты всем
          </Button>
          <Button
            kind="primary"
            onClick={selected.length ? () => void generatePrompts(selected) : undefined}
          >
            <Sparkles size={17} />
            Создать промпты выбранным
          </Button>
          <Button
            kind="primary"
            onClick={data.covers.length ? () => generateAutoCoverTextPair(false, []) : undefined}
          >
            <Sparkles size={17} />
            Придумать заголовки и подзаголовки — всем
          </Button>
          <Button
            kind="primary"
            onClick={selected.length ? () => generateAutoCoverTextPair(false, selected) : undefined}
          >
            <Sparkles size={17} />
            Придумать заголовки и подзаголовки — выбранным
          </Button>
          <Button
            kind="danger"
            onClick={selected.length ? () => generateAutoCoverTextPair(true, selected, true) : undefined}
          >
            <WandSparkles size={17} />
            Заменить ручной текст ИИ
          </Button>
          <Button
            kind="success"
            onClick={
              !data.coverSettings.generationPaused && promptsReady && !coverGenerationStarting
                ? generateAutomatically
                : undefined
            }
          >
            <Sparkles size={17} />
            Сгенерировать выбранный режим
          </Button>
          <Button
            kind="danger"
            onClick={
              data.coverSettings.generationPaused
                ? undefined
                : () => void command("pause-cover-generation")
            }
          >
            <Pause size={16} />
            Пауза генерации
          </Button>
          <Button
            kind="primary"
            onClick={data.coverSettings.generationPaused ? resumeGeneration : undefined}
          >
            <Play size={16} />
            Продолжить генерацию
          </Button>
          <Button
            kind="success"
            onClick={
              !data.coverSettings.generationPaused && promptsReady && !coverGenerationStarting
                ? generateAutomatically
                : undefined
            }
          >
            <Sparkles size={16} />
            Запустить готовые
          </Button>
          <Button
            kind="primary"
            onClick={selected.length ? rewritePrompts : undefined}
          >
            <WandSparkles size={16} />
            Перегенерировать промпты выбранным
          </Button>
          <span className="status">{selectedPromptSummary}</span>
          <Button
            onClick={allSelectedManualRetryEligible ? retrySelectedGeneration : undefined}
          >
            <Play size={16} />
            Повторить генерацию выбранных
          </Button>
          <span className="status">
            Повтор генерации доступен: {selectedManualRetryCount}/{selected.length}
          </span>
          <Button
            kind="danger"
            onClick={allSelectedNewPaidRetryEligible ? retrySelectedGenerationNewPaid : undefined}
          >
            <Play size={16} />
            Создать новый платный запрос
          </Button>
          <Button
            kind="success"
            onClick={allSelectedNewPromptsReady ? regenerate : undefined}
          >
            <Sparkles size={16} />
            Перегенерировать обложки выбранным
          </Button>
          <Button onClick={selected.length ? refineFaces : undefined}>
            <WandSparkles size={16} />
            Перерисовать с лицом
          </Button>
          <Button kind="danger" onClick={removePrompts}>
            <Trash2 size={16} />
            Удалить промпты {selected.length ? "выбранных" : "все"}
          </Button>
          <Button
            kind="danger"
            onClick={selected.length ? removeImages : undefined}
          >
            <Trash2 size={16} />
            Удалить картинки — выбранные
          </Button>
          <Button
            kind="danger"
            onClick={data.covers.length ? removeAllImages : undefined}
          >
            <Trash2 size={16} />
            Удалить картинки — все
          </Button>
          <Button
            kind="danger"
            onClick={selected.length ? removeRows : undefined}
          >
            <Trash2 size={16} />
            Удалить темы
          </Button>
        </div>
      </section>
      <section className="panel cover-variant-delete-panel">
        <div className="panel-title">
          <div>
            <b>Готовые варианты: удалить один</b>
            <small>
              Удаление варианта не затрагивает остальные картинки этой темы.
              Сначала выбери тему ниже — здесь появятся её варианты.
            </small>
          </div>
        </div>
        {selected.length === 1 && data.covers[selected[0]]?.paths?.length ? (
          <div className="toolbar">
            {(data.covers[selected[0]]?.paths ?? []).map((path) => (
              <Button
                kind="danger"
                key={path}
                onClick={() => {
                  if (window.confirm("Удалить только этот вариант обложки?"))
                    void command("remove-cover-image", {
                      index: selected[0],
                      path,
                    });
                }}
              >
                <Trash2 size={15} />
                Удалить · {path.split(/[\\/]/).pop()}
              </Button>
            ))}
          </div>
        ) : (
          <div className="cover-workflow-render-note">
            Выбери ровно одну тему с готовыми обложками — удаление будет
            доступно здесь и в галерее.
          </div>
        )}
      </section>
      <section className="panel cover-queue-workbench">
        <div className="panel-title">
          <div>
            <span className="eyebrow">CURRENT PRODUCTION ITEMS</span>
            <b>Очередь обложек</b>
            <small>
              Выберите задачи для пакетных действий или откройте одну для
              детальной проверки текста, лица и вариантов.
            </small>
          </div>
          <span className="cover-workflow-selected">
            {selected.length ? `Выбрано: ${selected.length}` : "Выберите задачу"}
          </span>
        </div>
        {coverQueue.length ? (
          <DataTable
            ariaLabel="Очередь обложек"
            preferenceKey="covers"
            data={coverQueue}
            columns={coverQueueColumns}
            getRowClassName={(row) =>
              selected.includes(row.index) ? "nf-table-row-selected" : ""
            }
            onRowActivate={(row) => {
              setSelected([row.index]);
              setInspectedCoverIndex(row.index);
            }}
          />
        ) : (
          <Empty
            title="Передайте сценарии в обложки"
            text="В разделе «Новости» выберите готовые сценарии и нажмите «В обложки»."
          />
        )}
      </section>
      <Sheet
        open={inspectedCoverIndex !== null}
        onOpenChange={(open) => {
          if (!open) setInspectedCoverIndex(null);
        }}
        title="Инспектор обложки"
        description="Текущий ProductionItem: текст, референсы, лицо и варианты FastGen."
      >
      <section className="panel table-wrap cover-table cover-queue-inspector">
        {inspectedCoverIndex !== null ? (
          <div className="scenario-list">
            {data.covers.map((cover, index) =>
              inspectedCoverIndex === index ? (
              <article
                className={`cover-row ${selected.includes(index) ? "selected" : ""}`}
                key={`${cover.title}-${index}`}
              >
                <dl className="cover-provenance" aria-label="Происхождение обложки">
                  <div>
                    <dt>ProductionItem ID</dt>
                    <dd>{cover.production_item_id || "Не получен из текущего snapshot"}</dd>
                  </div>
                  <div>
                    <dt>Prompt provider</dt>
                    <dd>{cover.prompt_provider || "Не сообщён текущим snapshot"}</dd>
                  </div>
                  <div>
                    <dt>Scene source</dt>
                    <dd>{cover.prompt_sources?.SCENE || "Не сообщён текущим snapshot"}</dd>
                  </div>
                  <div>
                    <dt>Face selection</dt>
                    <dd>
                      {cover.faceSelectionMode
                        ? `${cover.faceSelectionMode} · ${cover.semantic_face_label || cover.face_reference_label || "no match"} · ${cover.faceSelectionReason || "reason unavailable"}`
                        : "Не сообщён текущим snapshot"}
                    </dd>
                  </div>
                  <div>
                    <dt>Лицо для обложки</dt>
                    <dd>
                      {cover.portrait_subject
                        ? `${cover.portrait_subject} · ${cover.portrait_side || "side not set"} · ${cover.portrait_source || "source unavailable"} · ${cover.portrait_resolver_reason || "reason unavailable"} · confidence ${cover.portrait_confidence ?? cover.cover_primary_person?.confidence ?? "n/a"}`
                        : cover.portrait_source === "disabled"
                          ? "Отключён пользователем для этой темы"
                          : "Нужно определить лицо для обложки"}
                    </dd>
                  </div>
                  <div>
                    <dt>Alternatives</dt>
                    <dd>{cover.cover_people_candidates?.slice(1).map((person) => person.name).join(", ") || "Нет"}</dd>
                  </div>
                  <div>
                    <dt>Режим FastGen</dt>
                    <dd>{cover.render_profile?.build_mode || "Ещё не запускался"}</dd>
                  </div>
                  <div>
                    <dt>Стиль текста</dt>
                    <dd>{cover.text_style || "STANDARD"} · headline: {cover.headline_candidate_count || 0} · subtitle: {cover.subheadline_candidate_count || 0}</dd>
                  </div>
                  <div>
                    <dt>Visual references</dt>
                    <dd>
                      {cover.reference_use_enabled
                        ? `загружено ${cover.reference_uploaded_count || 0} · отправлено ${cover.reference_final_provider_count || 0}/${cover.reference_provider_limit || 0} · visual ${cover.reference_visual_reference_count || 0}${cover.reference_missing_paths?.length ? ` · missing ${cover.reference_missing_paths.length}` : ""}${cover.reference_dropped_paths?.length ? ` · dropped ${cover.reference_dropped_paths.length}` : ""}`
                        : "Отключены"}
                    </dd>
                  </div>
                  <div>
                    <dt>PNG лица в FastGen</dt>
                    <dd>
                      {(cover as typeof cover & { face_reference_count?: number }).face_reference_count === 0
                        ? `0 · ${cover.faceSelectionReason || "релевантный PNG не найден; генерация продолжена без референса"}`
                        : (cover as typeof cover & { face_reference_count?: number }).face_reference_count === 1
                          ? `1 · ${cover.face_reference_path || cover.face_reference_label || "подготовленный портрет"}`
                          : cover.faceSelectionMode === "prepared-reference"
                        ? `1 · ${cover.face_reference_path || cover.face_reference_label || "подготовленный портрет"}`
                        : cover.faceSelectionMode === "semantic-only"
                          ? "0 · лицо задано семантически"
                          : "Ещё не определено"}
                    </dd>
                  </div>
                  <div>
                    <dt>Последнее событие</dt>
                    <dd>{cover.generation_history?.at(-1)?.at || "Не получено"}</dd>
                  </div>
                  <div>
                    <dt>Файл</dt>
                    <dd>{cover.selected_path || cover.paths?.[0] || "Артефакт ещё не создан"}</dd>
                  </div>
                  <div>
                    <dt>Актуальность</dt>
                    <dd>Текущий snapshot не сообщает признак устаревания</dd>
                  </div>
                </dl>
                {cover.final_provider_prompt ? (
                  <details className="cover-final-prompt">
                    <summary>Final FastGen prompt</summary>
                    <pre>{cover.final_provider_prompt}</pre>
                  </details>
                ) : null}
                <button
                  className="cover-select"
                  onClick={(event) => updateCoverSelection(index, event)}
                >
                  <span>{selected.includes(index) ? "✓" : "○"}</span>
                  <span>{cover.scenario_index || index + 1}</span>
                  <b>{cover.title}</b>
                  <em
                    className={
                      cover.status === "Готово" ||
                      cover.status === "Готово с текстом"
                        ? "done"
                        : cover.status?.includes("Ошибка")
                          ? "error"
                          : ""
                    }
                  >
                    {cover.status || "Ожидает"}
                  </em>
                  <small>
                    {cover.error ||
                      (cover.paths?.length
                        ? `${cover.paths.length} картинок`
                        : "Сначала создайте промпты")}
                  </small>
                </button>
                <div className="cover-timeline">
                  <i style={{ width: `${cover.progress || 0}%` }} />
                  <span>{cover.progress || 0}%</span>
                  {(cover.timeline || []).slice(-3).map((step, stepIndex) => (
                    <small key={`${step.at}-${stepIndex}`}>
                      {step.at} · {step.label}
                      {step.detail ? `: ${step.detail}` : ""}
                    </small>
                  ))}
                  {cover.error || cover.status?.includes("Ошибка") ? (
                    <div className="cover-error-actions">
                      <b>FastGen не принял этот запрос.</b>
                      <Button
                        onClick={isCoverManualRetryEligible(cover)
                          ? () => void command("retry-cover-generation", coverSelectionPayload([index]))
                          : undefined}
                      >
                        <Play size={14} />
                        Повторить генерацию
                      </Button>
                      <Button
                        kind="primary"
                        onClick={() =>
                          void command("regenerate-covers-new-prompts", {
                            ...coverSelectionPayload([index]),
                            provider,
                          })
                        }
                      >
                        <WandSparkles size={14} />
                        Создать новый промпт
                      </Button>
                    </div>
                  ) : null}
                </div>
                <div className="cover-face-row">
                  <span>
                    <b>Лицо:</b>{" "}
                    {cover.face_reference_label
                      ? `${cover.face_reference_label} · ${cover.face_reference_source === "manual" ? "выбрано вручную" : "подобрано по теме"}${cover.face_layout ? ` · ${cover.face_layout}` : ""}`
                      : cover.face_reference_disabled
                        ? "отключено для этой темы"
                        : "не выбрано"}
                  </span>
                  <div className="toolbar compact">
                    <Button onClick={() => void chooseFaceForCover(index)}>
                      <Image size={14} />
                      Выбрать лицо
                    </Button>
                    <Button
                      onClick={() => void chooseVisualReferenceForCover(index)}
                    >
                      <Upload size={14} />
                      Загрузить свою картинку
                    </Button>
                    {cover.visual_reference_path ? (
                      <label className="check-row">
                        <input
                          type="checkbox"
                          checked={Boolean(cover.visual_reference_to_fastgen)}
                          onChange={(event) =>
                            void command("set-cover-visual-reference-target", {
                              index,
                              sendToFastgen: event.target.checked,
                            })
                          }
                        />
                        Также отправить в FastGen
                      </label>
                    ) : null}
                    <Button
                      kind="danger"
                      onClick={
                        cover.face_reference_label ||
                        cover.face_reference_disabled
                          ? () => void command("clear-cover-face", { index })
                          : undefined
                      }
                    >
                      <Trash2 size={14} />
                      Без лица
                    </Button>
                  </div>
                </div>
                <form
                  className="cover-headline-row"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const value = new FormData(event.currentTarget).get("headline");
                    void command("save-cover-headline", { index, headline: String(value || "") });
                  }}
                >
                  <label>
                    <small>Заголовок на обложке</small>
                    <input
                      name="headline"
                      key={`${cover.title}-${cover.cover_headline || ""}`}
                      defaultValue={cover.cover_headline || ""}
                      placeholder="Создай заголовок или впишите его вручную"
                    />
                    <span>
                      {cover.headline_source === "MANUAL"
                        ? "Вручную · сохранено"
                        : cover.headline_status || cover.headline_error || ""}
                    </span>
                  </label>
                  <Button type="submit">Сохранить вручную</Button>
                </form>
                <form
                  className="cover-subheadline-row"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const value = new FormData(event.currentTarget).get("subheadline");
                    void command("save-cover-subheadline", { index, subheadline: String(value || "") });
                  }}
                >
                  <label>
                    <small>Подзаголовок на обложке</small>
                    <input
                      name="subheadline"
                      key={`${cover.title}-${cover.cover_subheadline || ""}`}
                      defaultValue={cover.cover_subheadline || ""}
                      placeholder="Создай подзаголовок или впишите его вручную"
                    />
                    <span>
                      {cover.subheadline_source === "MANUAL"
                        ? "Вручную · сохранено"
                        : cover.subheadline_status || cover.subheadline_error || ""}
                    </span>
                  </label>
                  <Button type="submit">Сохранить вручную</Button>
                </form>
                <form
                  className="cover-headline-row cover-manual-prompt-row"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const productionItemId = String(cover.production_item_id || "").trim();
                    if (!productionItemId) return;
                    const value = new FormData(event.currentTarget).get("manualPrompt");
                    void command("save-cover-manual-prompt", {
                      productionItemId,
                      prompt: String(value || ""),
                    });
                  }}
                >
                  <label>
                    <small>Визуальный промпт для обложки</small>
                    <textarea
                      name="manualPrompt"
                      key={`${cover.production_item_id}-${cover.image_prompt || ""}`}
                      defaultValue={cover.image_prompt || ""}
                      placeholder="Вставьте или отредактируйте ручной визуальный промпт"
                    />
                    <span>
                      {cover.prompt_provider === "manual"
                        ? "Вручную · сохранено"
                        : cover.image_prompt ? "Выбранный prompt" : "Промпт ещё не создан"}
                    </span>
                  </label>
                  <Button type="submit" disabled={!cover.production_item_id}>
                    Сохранить промпт вручную
                  </Button>
                </form>
                {cover.image_prompt_options?.length ? (
                  <div className="cover-prompt-cards">
                    {cover.image_prompt_options.map((prompt, option) => (
                      <button
                        key={prompt}
                        className={
                          cover.selected_prompt_index === option ? "chosen" : ""
                        }
                        onClick={() =>
                          void command("select-cover-prompt", { index, option })
                        }
                      >
                        <span>
                          {cover.selected_prompt_index === option
                            ? "✓ Выбран ИИ / вручную"
                            : `Вариант ${option + 1}`}
                        </span>
                        <p>{prompt}</p>
                      </button>
                    ))}
                  </div>
                ) : null}
                {cover.paths?.length ? (
                  <div className="cover-variants">
                    {cover.paths.map((path: string) => (
                      <button
                        key={path}
                        className={cover.selected_path === path ? "chosen" : ""}
                        onClick={() =>
                          void command("select-cover-variant", { index, path })
                        }
                      >
                        <Image size={14} />
                        {cover.selected_path === path
                          ? "Выбрана"
                          : "Выбрать"} · {path.split(/[\\/]/).pop()}
                      </button>
                    ))}
                  </div>
                ) : null}
              </article>
              ) : null,
            )}
          </div>
        ) : (
          <Empty
            title="Выберите обложку в очереди"
            text="Инспектор показывает только один текущий ProductionItem, чтобы не смешивать его с историей."
          />
        )}
      </section>
      </Sheet>
    </div>
  );
}

export function CoverGallery({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const coverCounts = data.coverCounts || fallback.coverCounts;
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [expandedPath, setExpandedPath] = useState<string | null>(null);
  const [inspectedTopicIndex, setInspectedTopicIndex] = useState<number | null>(
    null,
  );
  const [faceByTopic, setFaceByTopic] = useState<Record<number, string>>({});
  const [operation, setOperation] = useState(data.coverSettings.operation);
  useEffect(
    () => setOperation(data.coverSettings.operation),
    [data.coverSettings.operation],
  );
  const models = (data.fastgenCapabilities.image || []).filter(
    (item) => item.id,
  );
  // A cover with locally placed typography has its own final file.  Older
  // projects kept that path outside `paths`, which made the gallery show the
  // raw FastGen image and look as though the text layer had disappeared.
  const topics = useMemo(
    () =>
      data.covers.map((cover, index) => ({
        cover,
        index,
        variants: Array.from(
          new Set(
            [
              cover.selected_path,
              cover.text_overlay_path,
              ...(cover.paths || []),
            ].filter(
              (path): path is string =>
                typeof path === "string" && path.length > 0,
            ),
          ),
        ).map((path) =>
          cover.galleryPaths?.find((item) => item.path === path) || {
            path,
            state: "ready" as const,
            message: "",
          },
        ),
      })),
    [data.covers],
  );
  const allCards = useMemo(
    () =>
      topics.flatMap(({ cover, index, variants }) =>
        variants.map((variant) => ({
          index,
          cover,
          ...variant,
          key: `${index}::${variant.path}`,
        })),
      ),
    [topics],
  );
  const galleryRows = useMemo(
    () =>
      topics.map(({ cover, index, variants }) => ({
        cover,
        index,
        variantCount: variants.length,
      })),
    [topics],
  );
  const galleryColumns = useMemo<
    ColumnDef<{
      cover: NewsFlowSnapshot["covers"][number];
      index: number;
      variantCount: number;
    }>[]
  >(
    () => [
      {
        id: "topic",
        header: "Тема",
        cell: ({ row }) => {
          const { cover, index } = row.original;
          return (
            <Button onClick={() => setInspectedTopicIndex(index)}>
              {cover.scenario_index || index + 1}. {cover.title}
            </Button>
          );
        },
      },
      {
        id: "status",
        header: "Статус",
        cell: ({ row }) => row.original.cover.status || "Ожидает",
      },
      {
        id: "headline",
        header: "Текст",
        cell: ({ row }) => row.original.cover.cover_headline || "—",
      },
      {
        id: "variants",
        header: "Варианты",
        cell: ({ row }) =>
          row.original.variantCount
            ? `${row.original.variantCount} готово`
            : "Нет файлов",
      },
    ],
    [],
  );
  const selectedCards = allCards.filter((card) =>
    selectedPaths.includes(card.key),
  );
  const selectedTopicIndexes = Array.from(
    new Set(selectedCards.map((card) => card.index)),
  );
  const coverSelectionPayload = (indices: number[]) => ({
    indices,
    ...(indices.length
      ? {
          productionItemIds: indices
            .map((index) => String(data.covers[index]?.production_item_id || "").trim())
            .filter(Boolean),
        }
      : {}),
  });
  const newPromptTopicIndexes = selectedTopicIndexes.filter(
    (index) => data.covers[index]?.status === "Новые промпты созданы",
  );
  const newPromptsReadyCount = newPromptTopicIndexes.length;
  useEffect(
    () =>
      setSelectedPaths((current) =>
        current.filter((key) => allCards.some((card) => card.key === key)),
      ),
    [allCards],
  );
  const toggle = (key: string, multi: boolean) =>
    setSelectedPaths((current) =>
      multi
        ? current.includes(key)
          ? current.filter((item) => item !== key)
          : [...current, key]
        : [key],
    );
  const exportImages = async (all = false) => {
    const path = await window.newsflowDesktop?.chooseZipSavePath(
      "Обложки NewsFlow.zip",
    );
    if (!path) return;
    const cards = all ? allCards : selectedCards;
    await command("export-cover-images", {
      path,
      items: cards.map((card) => ({ index: card.index, path: card.path })),
    });
  };
  const deleteImage = async (index: number, path: string) => {
    if (
      !window.confirm(
        "Удалить этот вариант обложки? Остальные варианты темы останутся.",
      )
    )
      return;
    await command("remove-cover-image", { index, path });
  };
  const clearAll = async () => {
    if (
      !allCards.length ||
      !window.confirm(`Удалить все ${allCards.length} изображений обложек?`)
    )
      return;
    await command("remove-cover-results", { all: true });
    setSelectedPaths([]);
  };
  const replaceOnlyFace = async (index: number) => {
    const person = faceByTopic[index];
    if (!person) return;
    if (person === "__none__") {
      await command("clear-cover-face", { index });
      return;
    }
    await command("select-cover-face-person", { index, person });
    await command("regenerate-covers", {
      ...coverSelectionPayload([index]),
      buildMode: "fastgen-full-my-face",
      faceMode: "auto",
      textMode: "fastgen",
      localFaceOnly: false,
      operation: data.coverSettings.operation,
    });
  };
  const rerenderWithFace = async (index: number) => {
    const person = faceByTopic[index];
    if (!person) return;
    await command("regenerate-cover-with-face", {
      ...coverSelectionPayload([index]),
      person,
      provider: data.coverSettings.provider,
    });
  };
  const uploadVisualReference = async (index: number) => {
    const paths = await window.newsflowDesktop?.chooseImages();
    if (!paths?.[0]) return;
    const result = await command("select-cover-visual-reference", {
      index,
      path: paths[0],
    });
    if (result)
      await command("generate-cover-prompts", {
        ...coverSelectionPayload([index]),
        provider: data.coverSettings.provider,
        rewrite: true,
      });
  };
  const repeatSelectedTopics = () =>
    void command("regenerate-covers", {
      ...coverSelectionPayload(selectedTopicIndexes),
      currentProfile: true,
      operation,
    });
  const repeatSelectedTopicsWithNewPrompts = () =>
    void command("regenerate-covers", {
      ...coverSelectionPayload(newPromptTopicIndexes),
      currentProfile: false,
      useBuildModeRanges: true,
      operation,
      buildMode: data.coverSettings.buildMode,
      faceMode: "auto",
      textMode: "fastgen",
      localFaceOnly: false,
    });
  const createSelectedTopicPrompts = () =>
    void command("regenerate-covers-new-prompts", {
      ...coverSelectionPayload(selectedTopicIndexes),
      provider: data.coverSettings.provider,
    });
  return (
    <>
      <section className="panel cover-gallery-hero">
        <div>
          <span className="eyebrow">COVER REVIEW</span>
          <h2>Галерея обложек</h2>
          <p>
            Здесь видны сами изображения, слова на обложке, этапы FastGen и
            ошибка конкретной темы. Выберите лучший вариант — он станет основным
            для выгрузки и следующего этапа.
          </p>
        </div>
        <div className="cover-gallery-metrics">
          <span>
            <b>{coverCounts.total}</b> всего тем
          </span>
          <span>
            <b>{coverCounts.ready}</b> готовы
          </span>
          <span>
            <b>{coverCounts.missing}</b> нет файла
          </span>
          <span>
            <b>{coverCounts.failed}</b> ошибки
          </span>
          <span>
            <b>{coverCounts.generating}</b> в работе
          </span>
          <span>
            <b>{coverCounts.queued}</b> очередь
          </span>
        </div>
      </section>
      <section className="panel cover-gallery-toolbar">
        <div className="toolbar">
          <Button
            kind="primary"
            onClick={
              selectedCards.length ? () => void exportImages(false) : undefined
            }
          >
            <Download size={16} />
            Скачать выбранные ({selectedCards.length})
          </Button>
          <Button
            onClick={
              allCards.length ? () => void exportImages(true) : undefined
            }
          >
            <Download size={16} />
            Скачать все ZIP
          </Button>
          <Button
            onClick={
              data.coverSettings.outputFolder
                ? () =>
                    void window.newsflowDesktop?.openPath(
                      data.coverSettings.outputFolder,
                    )
                : undefined
            }
          >
            <FolderOpen size={16} />
            Открыть папку обложек
          </Button>
          <label>
            Модель FastGen
            <select
              value={operation}
              onChange={(event) => setOperation(event.target.value)}
            >
              {models.length ? (
                models.map((item) => (
                  <option
                    key={item.id}
                    value={item.id}
                    disabled={item.health === "unavailable" || item.deprecated}
                  >
                    {item.provider || "FastGen"} ·{" "}
                    {item.display_name || item.model || item.id}
                  </option>
                ))
              ) : (
                <option value={operation}>{operation}</option>
              )}
            </select>
          </label>
          <Button
            onClick={
              selectedTopicIndexes.length ? repeatSelectedTopics : undefined
            }
          >
            <Play size={16} />
            Повторить текущие ({selectedTopicIndexes.length})
          </Button>
          <Button
            kind="primary"
            onClick={
              selectedTopicIndexes.length
                ? createSelectedTopicPrompts
                : undefined
            }
          >
            <WandSparkles size={16} />
            Новые промпты ({selectedTopicIndexes.length})
          </Button>
          <Button
            kind="success"
            onClick={
              newPromptsReadyCount
                ? repeatSelectedTopicsWithNewPrompts
                : undefined
            }
          >
            <Sparkles size={16} />
            Повторить с новыми ({newPromptsReadyCount})
          </Button>
          <Button
            kind="danger"
            onClick={
              data.coverSettings.generationPaused
                ? undefined
                : () => void command("pause-cover-generation")
            }
          >
            <Pause size={16} />
            Пауза генерации
          </Button>
          <Button
            kind="primary"
            onClick={
              data.coverSettings.generationPaused
                ? () => void command("resume-cover-generation")
                : undefined
            }
          >
            <Play size={16} />
            Продолжить
          </Button>
          <Button
            kind="danger"
            onClick={allCards.length ? () => void clearAll() : undefined}
          >
            <Trash2 size={16} />
            Удалить все обложки
          </Button>
        </div>
        <small>
          Для массового повтора выделите картинки Ctrl+кликом: учитываются все
          их темы. Файлы в папке и ZIP называются по номеру и теме:{" "}
          <b>001 — название темы — промпт 01 — вариант 01</b>.
        </small>
      </section>
      <section className="panel cover-visual-reference-upload">
        <div>
          <b>Своя картинка как референс</b>
          <small>
            Выберите одну тему/картинку выше, загрузите свой JPG/PNG/WEBP.
            NewsFlow передаст её агенту для анализа композиции и затем FastGen
            создаст новый похожий вариант.
          </small>
        </div>
        <Button
          kind="primary"
          onClick={
            selectedCards.length === 1
              ? () => void uploadVisualReference(selectedCards[0].index)
              : undefined
          }
        >
          <Upload size={16} />
          Загрузить референс для выбранной темы
        </Button>
        {selectedCards.length === 1 ? (
          <span>Выбрана тема: {selectedCards[0].cover.title}</span>
        ) : (
          <span>Сначала выберите ровно одну картинку Ctrl+кликом</span>
        )}
      </section>
      <section className="panel cover-gallery-workbench">
        <div className="panel-title">
          <div>
            <span className="eyebrow">RESULT REVIEW</span>
            <b>Индекс результатов</b>
            <small>
              Откройте один текущий ProductionItem для отбора, повторного
              рендера и точечной работы с результатами.
            </small>
          </div>
        </div>
        {galleryRows.length ? (
          <DataTable
            ariaLabel="Галерея результатов"
            data={galleryRows}
            columns={galleryColumns}
          />
        ) : (
          <Empty
            title="Пока нет тем для обложек"
            text="Передайте готовые сценарии в обложки и создайте промпты — варианты появятся здесь автоматически."
          />
        )}
      </section>
      <Sheet
        open={inspectedTopicIndex !== null}
        onOpenChange={(open) => {
          if (!open) setInspectedTopicIndex(null);
        }}
        title="Инспектор результата обложки"
        description="Текущий результат, варианты, выбор лица и повторный рендер."
      >
      <section className="cover-gallery-list">
        {inspectedTopicIndex !== null ? (
          topics.map(({ cover, index, variants }) =>
            inspectedTopicIndex === index ? (
            <article
              className={`panel cover-gallery-topic ${cover.error || cover.status?.includes("Ошибка") ? "has-error" : ""}`}
              key={`${cover.title}-${index}`}
            >
              <header>
                <div>
                  <span className="cover-gallery-index">
                    {cover.scenario_index || index + 1}
                  </span>
                  <b>{cover.title}</b>
                  <small>
                    {cover.status || "Ожидает"}
                    {cover.error ? ` · ${cover.error}` : ""}
                  </small>
                </div>
                <div className="toolbar compact">
                  <Button
                    onClick={isCoverManualRetryEligible(cover)
                      ? () => void command("retry-cover-generation", coverSelectionPayload([index]))
                      : isCoverRenderActive(cover)
                        ? undefined
                        : cover.status === "Новые промпты созданы"
                          ? () => void command("regenerate-covers", {
                              ...coverSelectionPayload([index]),
                              currentProfile: false,
                              useBuildModeRanges: true,
                              operation,
                              buildMode: data.coverSettings.buildMode,
                              faceMode: "auto",
                              textMode: "fastgen",
                              localFaceOnly: false,
                            })
                          : () => void command("regenerate-covers", {
                              ...coverSelectionPayload([index]),
                              currentProfile: true,
                              operation,
                            })}
                  >
                    <Play size={15} />
                    {isCoverManualRetryEligible(cover)
                      ? "Повторить генерацию"
                      : cover.status === "Новые промпты созданы"
                      ? "Повторить с новыми"
                      : "Повторить текущий"}
                  </Button>
                  <Button
                    kind="primary"
                    onClick={() =>
                      void command("regenerate-covers-new-prompts", {
                        ...coverSelectionPayload([index]),
                        provider: data.coverSettings.provider,
                      })
                    }
                  >
                    <WandSparkles size={15} />
                    Новые промпты
                  </Button>
                </div>
              </header>
              <div className="gallery-topic-timeline">
                <div className="gallery-progress">
                  <i style={{ width: `${cover.progress || 0}%` }} />
                  <span>{cover.progress || 0}%</span>
                </div>
                <div className="gallery-stages">
                  {(cover.timeline || []).slice(-6).map((step, stepIndex) => (
                    <span
                      key={`${step.at}-${stepIndex}`}
                      className={step.label.includes("Ошибка") ? "error" : ""}
                    >
                      <b>{step.at}</b>
                      {step.label}
                      {step.detail ? ` — ${step.detail}` : ""}
                    </span>
                  ))}
                </div>
              </div>
              <div className="gallery-topic-copy">
                <div>
                  <small>Главные слова</small>
                  <b>{cover.cover_headline || "Слова ещё не заданы"}</b>
                </div>
                <div>
                  <small>Подзаголовок</small>
                  <span>{cover.cover_subheadline || "—"}</span>
                </div>
                {cover.error ? (
                  <div className="gallery-error">
                    <b>Ошибка FastGen</b>
                    <span>{cover.error}</span>
                  </div>
                ) : null}
              </div>
              {cover.generation_rounds ? (
                <div className="gallery-retry-state">
                  Круг {cover.generation_round || 1}/{cover.generation_rounds} · попытка {cover.generation_attempt || 1}/{cover.generation_attempts_per_round || 4} · всего {cover.generation_total_attempt || 1}/{cover.generation_max_attempts || 16}
                  {cover.generation_history?.filter((entry) => entry.status === "failed").length
                    ? ` · повторно отправлено: ${cover.generation_history.filter((entry) => entry.status === "failed").length}`
                    : ""}
                </div>
              ) : null}
              <div className="gallery-face-editor">
                <div>
                  <b>Сменить лицо</b>
                  <small>
                    Список берётся из <code>Лица/_вырезанные/имя</code>. При
                    выборе берётся другое подготовленное фото этой персоны.
                  </small>
                </div>
                <select
                  value={faceByTopic[index] || ""}
                  onChange={(event) =>
                    setFaceByTopic((current) => ({
                      ...current,
                      [index]: event.target.value,
                    }))
                  }
                >
                  <option value="">Выберите лицо…</option>
                  <option value="__none__">Без лица</option>
                  {data.coverSettings.faceCatalog.map((person) => (
                    <option key={person.name} value={person.name}>
                      {person.name} · {person.paths.length} фото
                      {person.prepared ? " · PNG" : ""}
                    </option>
                  ))}
                </select>
                <Button
                  onClick={
                    faceByTopic[index]
                      ? () => void replaceOnlyFace(index)
                      : undefined
                  }
                >
                  <Image size={15} />
                  {faceByTopic[index] === "__none__"
                    ? "Убрать лицо"
                    : "Только заменить лицо"}
                </Button>
                <Button
                  kind="primary"
                  onClick={
                    faceByTopic[index] && faceByTopic[index] !== "__none__"
                      ? () => void rerenderWithFace(index)
                      : undefined
                  }
                >
                  <WandSparkles size={15} />
                  Переделать через FastGen
                </Button>
                <small className="gallery-face-current">
                  Сейчас: {cover.face_reference_label || "не выбрано"} ·{" "}
                  {cover.face_reference_source === "manual"
                    ? "вручную"
                    : "автоматически"}
                </small>
              </div>
              {variants.length ? (
                <div className="cover-gallery-grid">
                  {variants.map(({ path, state, message }, variant) => {
                    const key = `${index}::${path}`;
                    const selected = selectedPaths.includes(key);
                    const primary = cover.selected_path === path;
                    const available = state === "ready";
                    return (
                      <article
                        className={`cover-image-card ${selected ? "selected" : ""} ${primary ? "primary" : ""} ${available ? "" : "unavailable"}`}
                        key={path}
                      >
                        {available ? (
                          <button
                            className="cover-image-preview"
                            onClick={(event) =>
                              event.ctrlKey
                                ? toggle(key, true)
                                : setExpandedPath(path)
                            }
                            title="Клик — увеличить; Ctrl+клик — выбрать несколько"
                          >
                            <CoverPreviewImage
                              path={path}
                              alt={`Обложка: ${cover.title}, вариант ${variant + 1}`}
                              loading="lazy"
                            />
                            <span>
                              {selected ? "✓ Выбрано" : `Вариант ${variant + 1}`}
                            </span>
                            {primary ? <em>Основная</em> : null}
                          </button>
                        ) : (
                          <div className="cover-image-unavailable">
                            <b>{state === "missing" ? "Файл не найден" : "Файл повреждён"}</b>
                            <span>{message}</span>
                          </div>
                        )}
                        <div className="cover-image-actions">
                          {available ? (
                            <Button
                              kind={primary ? "success" : "secondary"}
                              onClick={() =>
                                void command("select-cover-variant", {
                                  index,
                                  path,
                                })
                              }
                            >
                              <Check size={14} />
                              {primary ? "Оставлена" : "Оставить"}
                            </Button>
                          ) : (
                            <Button
                              kind="primary"
                              onClick={() =>
                                void command("regenerate-covers", {
                                  ...coverSelectionPayload([index]),
                                  currentProfile: true,
                                })
                              }
                            >
                              <RefreshCw size={14} />
                              Повторить
                            </Button>
                          )}
                          <Button kind="danger" onClick={() => void deleteImage(index, path)}>
                            <Trash2 size={14} />
                            Удалить
                          </Button>
                        </div>
                        <small>{path.split(/[\\/]/).pop()}</small>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className="cover-gallery-empty">
                  <Image size={22} />
                  <span>
                    {cover.error || cover.status?.includes("Ошибка")
                      ? "Рендер не выполнен — попробуйте повторить или создать новый промпт."
                      : "Варианты ещё не готовы. Шкала выше показывает текущий этап."}
                  </span>
                </div>
              )}
            </article>
            ) : null,
          )
        ) : (
          <Empty
            title="Выберите результат в индексе"
            text="Инспектор показывает одну тему, чтобы действия выбора, удаления и повтора не смешивались между вариантами."
          />
        )}
      </section>
      </Sheet>
      {expandedPath ? (
        <div
          className="cover-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label="Увеличенная обложка"
          onClick={() => setExpandedPath(null)}
        >
          <button
            className="cover-lightbox-close"
            onClick={() => setExpandedPath(null)}
            aria-label="Закрыть"
          >
            ×
          </button>
          <CoverPreviewImage
            path={expandedPath}
            alt="Увеличенная обложка"
            className="cover-lightbox-image"
          />
        </div>
      ) : null}
    </>
  );
}

function Media({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const [type, setType] = useState<"image" | "video">("image");
  const [prompt, setPrompt] = useState("");
  const [ratio, setRatio] = useState("16:9");
  const [count, setCount] = useState("1");
  const models = (data.fastgenCapabilities[type] || []).filter(
    (item) => item.id && !item.deprecated,
  );
  const [operation, setOperation] = useState("flower_image_generate");
  useEffect(
    () =>
      setOperation(
        models[0]?.id ||
          (type === "image" ? "flower_image_generate" : "flow_video_from_text"),
      ),
    [type, data.fastgenCapabilities],
  );
  const generate = () =>
    void command("generate-media", {
      type,
      prompt,
      operation,
      aspectRatio: ratio,
      count: Number(count),
    });
  return (
    <>
      <section className="panel media-controls">
        <div className="panel-title">
          <div>
            <b>FastGen: картинки и видео</b>
            <small>
              Активная модель выбирается для типа генерации. Результаты попадают
              в общую медиатеку NewsFlow.
            </small>
          </div>
          <Button onClick={() => void command("refresh-fastgen")}>
            Обновить модели
          </Button>
        </div>
        <div className="toolbar">
          <Button
            kind={type === "image" ? "primary" : "secondary"}
            onClick={() => setType("image")}
          >
            <Image size={17} />
            Изображение
          </Button>
          <Button
            kind={type === "video" ? "primary" : "secondary"}
            onClick={() => setType("video")}
          >
            <Video size={17} />
            Видео
          </Button>
        </div>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Опишите, что нужно создать…"
        />
        <div className="form-row">
          <label>
            Модель
            <select
              value={operation}
              onChange={(event) => setOperation(event.target.value)}
            >
              {models.length ? (
                models.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.provider || "FastGen"} ·{" "}
                    {item.display_name || item.model || item.id}
                  </option>
                ))
              ) : (
                <option value={operation}>Обновите модели FastGen</option>
              )}
            </select>
          </label>
          <select
            value={ratio}
            onChange={(event) => setRatio(event.target.value)}
          >
            <option>16:9</option>
            <option>9:16</option>
            <option>1:1</option>
          </select>
          <select
            value={count}
            onChange={(event) => setCount(event.target.value)}
          >
            {[1, 2, 3, 4, 5, 6].map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
          <Button kind="success" onClick={generate}>
            <Sparkles size={17} />
            Генерировать
          </Button>
        </div>
      </section>
      <section className="panel media-gallery">
        <div className="panel-title">
          <div>
            <b>Результаты генерации</b>
            <small>Нажмите на результат, чтобы открыть файл.</small>
          </div>
        </div>
        {data.mediaResults.length ? (
          <div className="media-items">
            {data.mediaResults.map((path) => (
              <button
                key={path}
                onClick={() => void window.newsflowDesktop?.openPath(path)}
              >
                <Aperture size={17} />
                <span>{path.split(/[\\/]/).pop()}</span>
              </button>
            ))}
          </div>
        ) : (
          <Empty
            title="Пока нет медиа"
            text="Создайте изображение или видео через FastGen — оно появится в этой галерее."
          />
        )}
      </section>
    </>
  );
}

type SeoPrefixRange = {
  start: number;
  end: number;
  text: string;
  enabled?: boolean;
};

function SeoPrefixRanges({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const [ranges, setRanges] = useState<SeoPrefixRange[]>(
    data.seoSettings.descriptionPrefixRanges || [],
  );
  const [fixedPrefix, setFixedPrefix] = useState(
    data.seoSettings.fixedDescriptionPrefix || "",
  );
  const [presetName, setPresetName] = useState("");
  useEffect(
    () => setRanges(data.seoSettings.descriptionPrefixRanges || []),
    [data.seoSettings.descriptionPrefixRanges],
  );
  useEffect(
    () => setFixedPrefix(data.seoSettings.fixedDescriptionPrefix || ""),
    [data.seoSettings.fixedDescriptionPrefix],
  );
  const update = (index: number, patch: Partial<SeoPrefixRange>) =>
    setRanges((current) =>
      current.map((item, row) =>
        row === index ? { ...item, ...patch } : item,
      ),
    );
  const save = () =>
    void command("save-seo-settings", {
      fixedDescriptionPrefix: fixedPrefix,
      descriptionPrefixRanges: ranges,
      descriptionPrefixPresets: data.seoSettings.descriptionPrefixPresets || [],
    });
  const savePreset = () => {
    const name = presetName.trim();
    if (!name) return;
    const presets = [
      ...(data.seoSettings.descriptionPrefixPresets || []).filter(
        (item) => item.name !== name,
      ),
      { name, ranges },
    ];
    void command("save-seo-settings", {
      fixedDescriptionPrefix: fixedPrefix,
      descriptionPrefixRanges: ranges,
      descriptionPrefixPresets: presets,
    });
    setPresetName("");
  };
  const applyPreset = (name: string) => {
    const preset = (data.seoSettings.descriptionPrefixPresets || []).find(
      (item) => item.name === name,
    );
    if (preset) setRanges(preset.ranges || []);
  };
  return (
    <section className="panel seo-prefix-ranges">
      <div className="panel-title">
        <div>
          <b>Вступления к SEO-описанию</b>
          <small>
            Первый включённый диапазон, в который попадает номер темы,
            добавляется в начало автоматически. Например: 1–10 — общий текст
            канала.
          </small>
        </div>
        <Button onClick={save}>
          <Check size={16} />
          Сохранить вступления
        </Button>
      </div>
      <label className="seo-fixed-prefix">
        <b>Постоянное начало каждого описания</b>
        <small>Напишите здесь контакты, ссылку или фразу канала. Этот текст всегда будет первым, перед SEO-текстом и вступлениями по диапазону.</small>
        <textarea
          value={fixedPrefix}
          onChange={(event) => setFixedPrefix(event.target.value)}
          placeholder="Например: Реклама и сотрудничество: @your_contact"
        />
      </label>
      <div className="toolbar compact">
        <input
          value={presetName}
          onChange={(event) => setPresetName(event.target.value)}
          placeholder="Название пресета"
        />
        <Button onClick={presetName.trim() ? savePreset : undefined}>
          Сохранить пресет
        </Button>
        <select value="" onChange={(event) => applyPreset(event.target.value)}>
          <option value="">Применить пресет</option>
          {(data.seoSettings.descriptionPrefixPresets || []).map((item) => (
            <option key={item.name} value={item.name}>
              {item.name}
            </option>
          ))}
        </select>
        <Button
          onClick={() =>
            setRanges((current) => [
              ...current,
              { start: 1, end: 1, text: "", enabled: true },
            ])
          }
        >
          <Plus size={16} />
          Добавить диапазон
        </Button>
      </div>
      {ranges.length ? (
        <div className="voice-ranges">
          {ranges.map((item, index) => (
            <div className="voice-range" key={index}>
              <label title="Включить">
                <input
                  type="checkbox"
                  checked={item.enabled !== false}
                  onChange={(event) =>
                    update(index, { enabled: event.target.checked })
                  }
                />
              </label>
              <input
                type="number"
                min="1"
                value={item.start}
                onChange={(event) =>
                  update(index, { start: Number(event.target.value) || 1 })
                }
              />
              <span>—</span>
              <input
                type="number"
                min="1"
                value={item.end}
                onChange={(event) =>
                  update(index, { end: Number(event.target.value) || 1 })
                }
              />
              <textarea
                value={item.text}
                onChange={(event) =>
                  update(index, { text: event.target.value })
                }
                placeholder="Текст в начале описания…"
              />
              <Button
                kind="danger"
                onClick={() =>
                  setRanges((current) =>
                    current.filter((_item, row) => row !== index),
                  )
                }
              >
                <Trash2 size={14} />
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <small className="range-empty">
          Нет вступлений: описание начинается сразу с текста ИИ.
        </small>
      )}
    </section>
  );
}

export function Seo({ data, command }: { data: NewsFlowSnapshot; command: Command }) {
  const [selected, setSelected] = useState<number[]>([]);
  const [template, setTemplate] = useState(
    data.seoSettings.promptTemplate || defaultSeoPrompt,
  );
  const [provider, setProvider] = useState<"agent" | "openai">(
    data.seoSettings.provider,
  );
  const [hashtagBatchSize, setHashtagBatchSize] = useState(
    String(data.seoSettings.hashtagBatchSize),
  );
  const [callToAction, setCallToAction] = useState(
    data.seoSettings.callToAction,
  );
  const [useScriptContext, setUseScriptContext] = useState(
    data.seoSettings.useScriptContext,
  );
  const [opened, setOpened] = useState<number | null>(null);
  const [description, setDescription] = useState("");
  const [hashtags, setHashtags] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  useEffect(() => {
    setTemplate(data.seoSettings.promptTemplate || defaultSeoPrompt);
    setProvider(data.seoSettings.provider);
    setHashtagBatchSize(String(data.seoSettings.hashtagBatchSize));
    setCallToAction(data.seoSettings.callToAction);
    setUseScriptContext(data.seoSettings.useScriptContext);
  }, [
    data.seoSettings.promptTemplate,
    data.seoSettings.provider,
    data.seoSettings.hashtagBatchSize,
    data.seoSettings.callToAction,
    data.seoSettings.useScriptContext,
  ]);
  const save = () =>
    void command("save-seo-settings", {
      promptTemplate: template,
      provider,
      callToAction,
      useScriptContext,
    });
  const selectProvider = (value: "agent" | "openai") => {
    setProvider(value);
    void command("save-seo-settings", {
      promptTemplate: template,
      provider: value,
      callToAction,
      useScriptContext,
    });
  };
  const generate = () =>
    void command("generate-seo", { indices: selected, provider });
  const exportSeparate = async () => {
    const path = await window.newsflowDesktop?.chooseFolder();
    if (path) void command("export-seo", { mode: "separate", path });
  };
  const exportCombined = async () => {
    const path =
      await window.newsflowDesktop?.chooseSavePath("Все SEO-пакеты.txt");
    if (path) void command("export-seo", { mode: "combined", path });
  };
  const removeSelected = async () => {
    if (
      selected.length &&
      window.confirm(`Удалить SEO-пакеты: ${selected.length}?`)
    ) {
      const result = await command("remove-seo-packages", {
        indices: selected,
      });
      if (result) setSelected([]);
    }
  };
  const clearAll = async () => {
    if (data.seo.length && window.confirm("Очистить все SEO-пакеты и теги?")) {
      const result = await command("remove-seo-packages", { all: true });
      if (result) setSelected([]);
    }
  };
  const openEditor = () => {
    if (selected.length !== 1) return;
    const item = data.seo[selected[0]];
    if (!item) return;
    setOpened(selected[0]);
    setDescription(item.description || "");
    setHashtags((item.hashtags || []).join(" "));
  };
  const saveEditor = async () => {
    if (opened === null) return;
    const result = await command("save-seo-text", {
      index: opened,
      description,
      hashtags,
    });
    if (result) setOpened(null);
  };
  return (
    <div className="nf-seo nf-distribution-workspace" aria-label="Distribution workspace: SEO">
      <section className="panel nf-metadata-control-deck"><div className="panel-title"><div><b>SEO Production Desk</b><small>Выберите темы и работайте с результатами; провайдер, промпт и выгрузка открываются отдельно.</small></div><Button onClick={() => setSettingsOpen(true)}><Settings2 size={16} />Настроить SEO</Button></div></section>
      <Sheet open={settingsOpen} onOpenChange={setSettingsOpen} title="Настройки SEO" description="Провайдер, промпт, вступления и выгрузка SEO-пакетов."><div className="nf-metadata-configuration">
      <section className="panel cover-template">
        <div className="panel-title">
          <div>
            <b>SEO-описание и хештеги</b>
            <small>
              Поле ниже редактируемое: вставьте свой промпт и нажмите «Сохранить
              промпт».
            </small>
          </div>
          <Button onClick={save}>Сохранить промпт</Button>
        </div>
        <ProviderSwitch
          value={provider}
          onChange={selectProvider}
          label="Исполнитель SEO"
        />
        <label className="prompt-editor">
          <span>Промпт SEO</span>
          <textarea
            value={template}
            onChange={(event) => setTemplate(event.target.value)}
            placeholder="Промпт для SEO-описания и хештегов…"
          />
          <small>{template.length} символов</small>
        </label>
        <div className="form-grid">
          <label>
            Пожелание к призыву{" "}
            <input
              value={callToAction}
              onChange={(event) => setCallToAction(event.target.value)}
              onBlur={save}
              placeholder="Необязательно: стиль или тон призыва. Без текста ИИ сам придумает разный призыв под тему."
            />
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={useScriptContext}
              onChange={(event) => {
                setUseScriptContext(event.target.checked);
                void command("save-seo-settings", {
                  useScriptContext: event.target.checked,
                  callToAction,
                  promptTemplate: template,
                  provider,
                });
              }}
            />
            Использовать текст сценария <small>точнее, но больше токенов</small>
          </label>
        </div>
        <div className="toolbar">
          <Button onClick={() => setTemplate(defaultSeoPrompt)}>
            Вернуть пример
          </Button>
          <label>
            Хештегов в пачке{" "}
            <input
              type="number"
              min="1"
              max="30"
              value={hashtagBatchSize}
              onChange={(event) => setHashtagBatchSize(event.target.value)}
              onBlur={() =>
                void command("save-tag-limits", {
                  hashtagBatchSize,
                  tagCharLimit: data.seoSettings.tagCharLimit,
                })
              }
            />
          </label>
          <Button onClick={save}>Применить</Button>
          <Button kind="success" onClick={generate}>
            <Sparkles size={17} />
            Создать SEO и хештеги
          </Button>
        </div>
      </section>
      <SeoPrefixRanges data={data} command={command} />
      <section className="panel">
        <div className="panel-title">
          <div>
            <b>Выгрузка SEO-пакетов</b>
            <small>
              В обоих форматах: тема, единый SEO-текст с призывом, хештеги и
              отдельные теги. Перед выгрузкой создайте теги в одноимённом
              разделе.
            </small>
          </div>
        </div>
        <div className="toolbar">
          <Button kind="primary" onClick={() => void exportSeparate()}>
            <Download size={17} />
            Отдельные TXT по темам
          </Button>
          <Button onClick={() => void exportCombined()}>
            <Download size={17} />
            Один общий TXT со всеми темами
          </Button>
        </div>
      </section>
      <section className="panel">
        <div className="panel-title">
          <div>
            <b>Как создаётся SEO</b>
            <small>
              1. Контекст сценария — сразу · 2. SEO-текст и призыв — обычно
              20–60 секунд · 3. Хештеги — в том же запросе. Время зависит от
              очереди API и длины сценария.
            </small>
          </div>
        </div>
      </section>
      </div></Sheet>
      <section className="panel table-wrap seo-table">
        <div className="panel-title">
          <div>
            <b>Темы для SEO: {data.seo.length}</b>
            <small>
              Передайте готовые сценарии из раздела «Новости» и выберите, для
              каких создать SEO. Ctrl+клик — несколько.
            </small>
          </div>
          <div className="toolbar compact">
            <Button onClick={selected.length === 1 ? openEditor : undefined}>
              <Pencil size={16} />
              Открыть / редактировать
            </Button>
            <Button
              kind="danger"
              onClick={
                selected.length ? () => void removeSelected() : undefined
              }
            >
              <Trash2 size={16} />
              Удалить выбранные
            </Button>
            <Button
              kind="danger"
              onClick={data.seo.length ? () => void clearAll() : undefined}
            >
              <Trash2 size={16} />
              Очистить SEO и теги
            </Button>
          </div>
        </div>
        <div className="table-head">
          <span>☐</span>
          <span>#</span>
          <span>ИСХОДНАЯ ТЕМА</span>
          <span>СТАТУС</span>
          <span>SEO-ОПИСАНИЕ</span>
        </div>
        {data.seo.length ? (
          <div className="scenario-list">
            {data.seo.map((item, index) => (
              <button
                key={`${item.source_title}-${index}`}
                className={selected.includes(index) ? "selected" : ""}
                onClick={(event) =>
                  setSelected((current) =>
                    event.ctrlKey
                      ? current.includes(index)
                        ? current.filter((value) => value !== index)
                        : [...current, index]
                      : [index],
                  )
                }
              >
                <span>{selected.includes(index) ? "✓" : "○"}</span>
                <span>{index + 1}</span>
                <b>{item.source_title}</b>
                <em
                  className={
                    item.status === "Готово" && item.description
                      ? "done"
                      : item.status === "Ошибка"
                        ? "error"
                        : ""
                  }
                >
                  {item.status === "Готово" && !item.description
                    ? "Ожидает"
                    : item.status || "Ожидает"}
                </em>
                <small>
                  {item.error ||
                    item.description ||
                    item.title ||
                    "Будут созданы SEO-текст, призыв и хештеги"}
                </small>
              </button>
            ))}
          </div>
        ) : (
          <Empty
            title="Передайте сценарии в SEO"
            text="В «Новости и сценарии» выберите готовые тексты и нажмите «В SEO и теги»."
          />
        )}
      </section>
      {opened !== null ? (
        <section className="panel cover-template">
          <div className="panel-title">
            <div>
              <b>Просмотр и редактирование SEO</b>
              <small>
                {data.seo[opened]?.source_title || "Тема"}. Призыв — последнее
                предложение SEO-текста.
              </small>
            </div>
            <Button onClick={() => setOpened(null)}>Закрыть</Button>
          </div>
          <div className="result-preview">
            <b>Призыв к просмотру</b>
            <p>{finalSentence(description)}</p>
            <b>SEO-описание</b>
          </div>
          <label className="prompt-editor">
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="SEO-описание…"
            />
            <small>{description.length} символов</small>
          </label>
          <div className="form-grid">
            <label>
              Хештеги
              <input
                value={hashtags}
                onChange={(event) => setHashtags(event.target.value)}
                placeholder="#хештег #ещёодин"
              />
            </label>
            <label>
              Теги для этого ролика
              <textarea
                readOnly
                value={
                  (data.seo[opened]?.tags || []).join(", ") ||
                  "Теги ещё не созданы — откройте раздел «Теги»."
                }
              />
            </label>
          </div>
          <div className="toolbar">
            <Button kind="success" onClick={() => void saveEditor()}>
              <Check size={16} />
              Сохранить SEO
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}

export function Tags({ data, command }: { data: NewsFlowSnapshot; command: Command }) {
  const [selected, setSelected] = useState<number[]>([]);
  const [template, setTemplate] = useState(
    data.seoSettings.tagsPromptTemplate || defaultTagsPrompt,
  );
  const [provider, setProvider] = useState<"agent" | "openai">(
    data.seoSettings.tagsProvider,
  );
  const [tagCharLimit, setTagCharLimit] = useState(
    String(data.seoSettings.tagCharLimit),
  );
  const [opened, setOpened] = useState<number | null>(null);
  const [tagText, setTagText] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  useEffect(() => {
    setTemplate(data.seoSettings.tagsPromptTemplate || defaultTagsPrompt);
    setProvider(data.seoSettings.tagsProvider);
    setTagCharLimit(String(data.seoSettings.tagCharLimit));
  }, [
    data.seoSettings.tagsPromptTemplate,
    data.seoSettings.tagsProvider,
    data.seoSettings.tagCharLimit,
  ]);
  const save = () =>
    void command("save-tags-settings", { promptTemplate: template, provider });
  const selectProvider = (value: "agent" | "openai") => {
    setProvider(value);
    void command("save-tags-settings", {
      promptTemplate: template,
      provider: value,
    });
  };
  const generate = () =>
    void command("generate-tags", { indices: selected, provider });
  const exportSeparate = async () => {
    const path = await window.newsflowDesktop?.chooseFolder();
    if (path) void command("export-seo", { mode: "tags-separate", path });
  };
  const exportCombined = async () => {
    const path = await window.newsflowDesktop?.chooseSavePath("Все теги.txt");
    if (path) void command("export-seo", { mode: "tags-combined", path });
  };
  const removeSelected = async () => {
    if (
      selected.length &&
      window.confirm(
        `Удалить теги у ${selected.length} тем? SEO-описания останутся.`,
      )
    ) {
      const result = await command("clear-tags", { indices: selected });
      if (result) setSelected([]);
    }
  };
  const clearAll = async () => {
    if (
      data.seo.length &&
      window.confirm("Удалить все созданные теги? SEO-описания останутся.")
    ) {
      const result = await command("clear-tags", { all: true });
      if (result) setSelected([]);
    }
  };
  const openTags = () => {
    if (selected.length !== 1) return;
    const item = data.seo[selected[0]];
    if (!item) return;
    setOpened(selected[0]);
    setTagText((item.tags || []).join(", "));
  };
  const saveTags = async () => {
    if (opened === null) return;
    const result = await command("save-tags-text", {
      index: opened,
      tags: tagText,
    });
    if (result) setOpened(null);
  };
  return (
    <div className="nf-tags nf-distribution-workspace" aria-label="Distribution workspace: Tags">
      <section className="panel nf-metadata-control-deck"><div className="panel-title"><div><b>Tag Production Desk</b><small>Очередь тегов остаётся в рабочем поле; лимиты, промпт и выгрузка открываются отдельно.</small></div><Button onClick={() => setSettingsOpen(true)}><Settings2 size={16} />Настроить теги</Button></div></section>
      <Sheet open={settingsOpen} onOpenChange={setSettingsOpen} title="Настройки тегов" description="Провайдер, промпт, лимиты и выгрузка тегов."><div className="nf-metadata-configuration">
      <section className="panel cover-template">
        <div className="panel-title">
          <div>
            <b>Теги</b>
            <small>
              Поле ниже редактируемое: вставьте свой промпт и сохраните его.
              Python обрезает готовый список строго по лимиту.
            </small>
          </div>
          <Button onClick={save}>Сохранить промпт</Button>
        </div>
        <ProviderSwitch
          value={provider}
          onChange={selectProvider}
          label="Исполнитель тегов"
        />
        <label className="prompt-editor">
          <span>Промпт тегов</span>
          <textarea
            value={template}
            onChange={(event) => setTemplate(event.target.value)}
            placeholder="Промпт для тегов…"
          />
          <small>{template.length} символов</small>
        </label>
        <div className="toolbar">
          <Button onClick={() => setTemplate(defaultTagsPrompt)}>
            Вернуть пример
          </Button>
          <label>
            Лимит тегов, символов{" "}
            <input
              type="number"
              min="50"
              max="500"
              value={tagCharLimit}
              onChange={(event) => setTagCharLimit(event.target.value)}
              onBlur={() =>
                void command("save-tag-limits", {
                  hashtagBatchSize: data.seoSettings.hashtagBatchSize,
                  tagCharLimit,
                })
              }
            />
          </label>
          <small>
            Сейчас: до {tagCharLimit || "—"} символов вместе с разделителями.
          </small>
          <Button onClick={save}>Применить</Button>
          <Button
            kind="success"
            onClick={data.seo.length ? generate : undefined}
          >
            <Sparkles size={17} />
            Создать теги
          </Button>
        </div>
      </section>
      <section className="panel">
        <div className="panel-title">
          <div>
            <b>Выгрузка тегов</b>
            <small>
              Выберите папку для отдельных файлов или имя и место для одного
              общего TXT.
            </small>
          </div>
        </div>
        <div className="toolbar">
          <Button
            kind="primary"
            onClick={data.seo.length ? () => void exportSeparate() : undefined}
          >
            <Download size={17} />
            Отдельные TXT по темам
          </Button>
          <Button
            onClick={data.seo.length ? () => void exportCombined() : undefined}
          >
            <Download size={17} />
            Один общий TXT со всеми темами
          </Button>
        </div>
      </section>
      </div></Sheet>
      <section className="panel table-wrap seo-table">
        <div className="panel-title">
          <div>
            <b>Очередь тегов: {data.seo.length}</b>
            <small>
              Выберите одну тему и нажмите «Открыть», чтобы просмотреть или
              исправить теги вручную.
            </small>
          </div>
          <div className="toolbar compact">
            <Button onClick={selected.length === 1 ? openTags : undefined}>
              <Pencil size={16} />
              Открыть / редактировать
            </Button>
            <Button
              kind="danger"
              onClick={
                selected.length ? () => void removeSelected() : undefined
              }
            >
              <Trash2 size={16} />
              Удалить выбранные теги
            </Button>
            <Button
              kind="danger"
              onClick={data.seo.length ? () => void clearAll() : undefined}
            >
              <Trash2 size={16} />
              Очистить все теги
            </Button>
          </div>
        </div>
        <div className="table-head">
          <span>☐</span>
          <span>#</span>
          <span>ТЕМА</span>
          <span>СТАТУС</span>
          <span>ТЕГИ</span>
        </div>
        {data.seo.length ? (
          <div className="scenario-list">
            {data.seo.map((item, index) => (
              <button
                key={`${item.source_title}-tags-${index}`}
                className={selected.includes(index) ? "selected" : ""}
                onClick={(event) =>
                  setSelected((current) =>
                    event.ctrlKey
                      ? current.includes(index)
                        ? current.filter((value) => value !== index)
                        : [...current, index]
                      : [index],
                  )
                }
              >
                <span>{selected.includes(index) ? "✓" : "○"}</span>
                <span>{index + 1}</span>
                <b>{item.source_title}</b>
                <em
                  className={
                    item.tags_status === "Ошибка"
                      ? "error"
                      : item.tags?.length
                        ? "done"
                        : ""
                  }
                >
                  {item.tags_status === "Создание тегов"
                    ? "Создание тегов"
                    : item.tags_status === "Ошибка"
                      ? "Ошибка"
                      : item.tags?.length
                        ? "Готово"
                        : "Ожидают"}
                </em>
                <small>
                  {(item.tags || []).join(", ") ||
                    item.tags_error ||
                    "Теги ещё не созданы"}
                </small>
              </button>
            ))}
          </div>
        ) : (
          <Empty
            title="Тегов пока нет"
            text="Сначала передайте готовые сценарии в SEO-пакеты — здесь можно будет подготовить отдельные теги."
          />
        )}
      </section>
      {opened !== null ? (
        <section className="panel cover-template">
          <div className="panel-title">
            <div>
              <b>Просмотр и редактирование тегов</b>
              <small>
                {data.seo[opened]?.source_title || "Тема"}. Лимит:{" "}
                {tagCharLimit} символов с запятыми.
              </small>
            </div>
            <Button onClick={() => setOpened(null)}>Закрыть</Button>
          </div>
          <label className="prompt-editor">
            <span>Теги через запятую</span>
            <textarea
              value={tagText}
              onChange={(event) => setTagText(event.target.value)}
              placeholder="тег 1, тег 2, тег 3"
            />
            <small>{tagText.length} символов в поле</small>
          </label>
          <div className="toolbar">
            <Button kind="success" onClick={() => void saveTags()}>
              <Check size={16} />
              Сохранить теги
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}

export function Footage({
  data,
  command,
  refresh,
}: {
  data: NewsFlowSnapshot;
  command: Command;
  refresh: () => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("all");
  const [results, setResults] = useState<
    NonNullable<NewsFlowSnapshot["webResults"]>
  >([]);
  const [start, setStart] = useState("0");
  const [duration, setDuration] = useState("6");
  // The indexing command is intentionally long-running.  Start polling as
  // soon as the user presses the button instead of waiting for that command
  // to return its final snapshot.
  const indexLock = useRef(false);
  const [indexRequested, setIndexRequested] = useState(false);
  const [liveIndexStatus, setLiveIndexStatus] = useState<
    NonNullable<NewsFlowSnapshot["footageIndex"]["status"]>
  >({});
  // A completed incremental run can finish in a fraction of a second when
  // there are no new clips. Keep its result visible instead of replacing the
  // progress strip with the generic global "saved" toast.
  const [lastIndexRun, setLastIndexRun] = useState<{
    mode: "scan" | "semantic" | "screenText";
    startedAt: number;
    finishedAt?: number;
    message: string;
    processed?: number;
    total?: number;
    indexed?: number;
    skipped?: number;
    failed?: number;
    error?: string;
  } | null>(null);
  const [downloadFolder, setDownloadFolder] = useState(
    data.cutterSettings.downloadFolder,
  );
  useEffect(() => {
    setDownloadFolder(data.cutterSettings.downloadFolder);
  }, [data.cutterSettings.downloadFolder]);
  const chooseFolder = async () => {
    const folder = await window.newsflowDesktop?.chooseFolder();
    if (folder) void command("add-footage-folder", { folder });
  };
  const chooseDownloadFolder = async () => {
    const folder = await window.newsflowDesktop?.chooseFolder();
    if (folder) setDownloadFolder(folder);
  };
  const search = async () => {
    const state = await command("search-web-footage", { query, source });
    if (state?.webResults) setResults(state.webResults);
  };
  const indexStatus = {
    ...(data.footageIndex.status || {}),
    ...(data.footageIndex.error ? { error: data.footageIndex.error } : {}),
    ...liveIndexStatus,
  };
  const indexing = Boolean(indexStatus.active) || indexRequested;
  const indexPaused = indexStatus.stage === "paused";
  const indexed = Math.max(
    data.footageIndex.indexed,
    Number(indexStatus.indexed || 0),
  );
  const maintenanceStage = ["semantic", "screen-text"].includes(
    String(indexStatus.stage || ""),
  );
  const indexTotal = maintenanceStage
    ? Number(indexStatus.total || 0)
    : Math.max(data.footageIndex.total, Number(indexStatus.total || 0));
  const processed = maintenanceStage
    ? Number(indexStatus.processed || 0)
    : Math.max(indexed, Number(indexStatus.processed || 0));
  const remaining = Math.max(0, indexTotal - processed);
  const progress = indexTotal
    ? Math.min(100, Math.round((processed / indexTotal) * 100))
    : 0;
  const semanticCurrent = Number(data.footageIndex.semanticCurrent || 0);
  const semanticOutdated = Number(data.footageIndex.semanticOutdated || 0);
  const semanticVersion = Number(data.footageIndex.semanticVersion || 0);
  useEffect(() => {
    let disposed = false;
    const pollLiveStatus = async () => {
      try {
        const status = await window.newsflowDesktop?.footageIndexStatus();
        if (!disposed && status) setLiveIndexStatus(status);
      } catch {
        // The overall snapshot remains a safe fallback if the local file is
        // temporarily being written by the index worker.
      }
    };
    void pollLiveStatus();
    const timer = window.setInterval(() => {
      void pollLiveStatus();
    }, 1000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    if (!indexing) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [indexing, refresh]);
  useEffect(() => {
    if (
      indexRequested &&
      indexStatus.active === false &&
      indexStatus.stage &&
      !["scan", "embedding", "semantic", "screen-text"].includes(indexStatus.stage)
    ) {
      setIndexRequested(false);
    }
  }, [indexRequested, indexStatus.active, indexStatus.stage]);
  const indexLibrary = async (mode: "scan" | "semantic" | "screenText" = "scan") => {
    if (indexLock.current) return;
    indexLock.current = true;
    const startedAt = Date.now();
    setIndexRequested(true);
    setLastIndexRun({
      mode,
      startedAt,
      message: mode === "semantic"
        ? "Уточняются смысловые метки уже проиндексированных клипов…"
        : mode === "screenText"
          ? "Проверяются сохранённые векторы English/Latin текста…"
          : "Проверяются новые и изменённые файлы…",
    });
    try {
      const state = await command(
        "index-footage",
        mode === "semantic" ? { enhance: true } : mode === "screenText" ? { screenText: true } : undefined,
      );
      const result = (
        state as
          | (NewsFlowSnapshot & {
              indexResult?: {
                processed?: number;
                total?: number;
                indexed?: number;
                skipped?: number;
                failed?: number;
                screenText?: { checked?: number; blocked?: number; safe?: number; uncertain?: number; modelReady?: boolean };
              };
            })
          | undefined
      )?.indexResult;
      const status = await window.newsflowDesktop?.footageIndexStatus();
      setLastIndexRun({
        mode,
        startedAt,
        finishedAt: Date.now(),
        message: result?.processed
          ? mode === "semantic"
            ? "Смысловые метки обновлены."
            : mode === "screenText"
              ? "Проверка English/Latin текста завершена."
              : "ИИ-индекс обновлён."
          : mode === "semantic"
            ? "Новых клипов для улучшения нет: все доступные клипы уже уточнены."
            : mode === "screenText"
              ? result?.screenText?.modelReady === false
                ? "Локальная text-модель недоступна: проверка не запускалась. Сначала выполните «Улучшить ИИ-индекс» в этом приложении."
                : "Проверка English/Latin текста уже актуальна: новых векторов нет."
              : "Новых или изменённых файлов не найдено.",
        processed: Number(result?.processed || 0),
        total: Number(result?.total || 0),
        indexed: Number(result?.indexed || 0),
        skipped: Number(result?.skipped || 0),
        failed: Number(result?.failed || 0),
        error:
          status?.error ||
          (Number(result?.failed || 0) > 0
            ? `Не обработано файлов: ${Number(result?.failed || 0)}. Проверьте повреждённые или недоступные видео.`
            : undefined),
      });
    } finally {
      indexLock.current = false;
      setIndexRequested(false);
    }
  };
  const download = (
    result: NonNullable<NewsFlowSnapshot["webResults"]>[number],
  ) =>
    void command("download-web-footage", {
      result,
      folder: downloadFolder,
      start: Number(start),
      duration: Number(duration),
    });
  const folderColumns = useMemo<ColumnDef<string>[]>(
    () => [
      { id: "source", header: "Источник", cell: ({ row }) => <span className="nf-footage-source"><FolderOpen size={16} />{row.original}</span> },
      { id: "scope", header: "Область", cell: () => "Текущая локальная библиотека" },
      { id: "action", header: "Действие", cell: ({ row }) => <Button kind="danger" onClick={() => void command("remove-footage-folder", { index: row.index })}>Убрать</Button> },
    ],
    [command],
  );
  const resultColumns: ColumnDef<NonNullable<NewsFlowSnapshot["webResults"]>[number]>[] = [
    { id: "title", header: "Источник", cell: ({ row }) => <b>{row.original.title}</b> },
    { id: "license", header: "Лицензия", cell: ({ row }) => `${row.original.source === "youtube" ? "YouTube" : "Wikimedia"} · ${row.original.license || "Проверьте лицензию"}` },
    { id: "action", header: "Действия", cell: ({ row }) => <div className="toolbar compact"><Button onClick={() => void window.open(row.original.source_url, "_blank", "noopener,noreferrer")}>Источник</Button><Button kind="success" onClick={() => download(row.original)}><Download size={15} />Скачать</Button></div> },
  ];
  return (
    <div className="nf-footage" aria-label="Media Ingest Workspace">
      <section className="panel footage-semantic-tools">
        <div className="panel-title">
          <div>
            <b>Улучшение ИИ-индекса</b>
            <small>
              Уточняет смысловые метки уже проиндексированных клипов: бой,
              войска, разрушения, переговоры, митинг, танкеры. Исходные видео
              повторно не открываются.
            </small>
          </div>
          <div className="toolbar compact">
            <Button
              onClick={
                indexing || !data.footageIndex.indexed
                  ? undefined
                  : () => void indexLibrary("semantic")
              }
            >
              <WandSparkles size={16} />
              Улучшить ИИ-индекс
            </Button>
          </div>
        </div>
        {lastIndexRun ? (
          <div
            className={`footage-index-timeline ${lastIndexRun.error ? "error" : ""}`}
          >
            <div>
              <b>
                {lastIndexRun.error
                  ? "Ошибка улучшения ИИ-индекса"
                  : lastIndexRun.finishedAt
                    ? "Последний запуск улучшения завершён"
                    : "Улучшение ИИ-индекса выполняется"}
              </b>
              <span>
                {lastIndexRun.finishedAt
                  ? `в ${new Date(lastIndexRun.finishedAt).toLocaleTimeString("ru-RU")}`
                  : "идёт обработка"}
              </span>
            </div>
            <div className="footage-index-progress">
              <i style={{ width: lastIndexRun.finishedAt ? "100%" : "35%" }} />
            </div>
            <small>
              {lastIndexRun.error ||
                `${lastIndexRun.message} Обработано: ${Number(lastIndexRun.processed || 0).toLocaleString("ru-RU")}; обновлено: ${Number(lastIndexRun.indexed || 0).toLocaleString("ru-RU")}; пропущено: ${Number(lastIndexRun.skipped || 0).toLocaleString("ru-RU")}; ошибок: ${Number(lastIndexRun.failed || 0).toLocaleString("ru-RU")}.`}
            </small>
          </div>
        ) : (
          <div className="index-hint">
            <small>Базовый индекс готов: {indexed.toLocaleString("ru-RU")} клипов.</small>
            <small>
              {semanticOutdated
                ? `Требуется глубокое обновление: ${semanticOutdated.toLocaleString("ru-RU")} клипа (версия ${semanticVersion}).`
                : semanticCurrent
                  ? `Глубокий семантический индекс актуален: ${semanticCurrent.toLocaleString("ru-RU")} клипов (версия ${semanticVersion}).`
                  : "Глубокое семантическое улучшение ещё не запускалось."}
            </small>
          </div>
        )}
      </section>
      <section className="panel footage-semantic-tools">
        <div className="panel-title">
          <div>
            <b>Проверка English/Latin текста</b>
            <small>
              Проверяет уже сохранённые векторы клипов и исключает только
              явные английские/латинские надписи. Исходные видео повторно не
              открываются и базовая индексация не запускается.
            </small>
          </div>
          <div className="toolbar compact">
            <Button
              onClick={
                indexing || !data.footageIndex.indexed
                  ? undefined
                  : () => void indexLibrary("screenText")
              }
            >
              <WandSparkles size={16} />
              Проверить English/Latin текст
            </Button>
          </div>
        </div>
      </section>
      <section className="panel footage-folders">
        <div className="panel-title">
          <div>
            <b>Многоуровневая библиотека футажей</b>
            <small>
              Можно добавить несколько корней: NewsFlow запоминает пути, строит
              индекс по вложенным папкам и сначала ищет в ваших 6-секундных
              клипах.
            </small>
          </div>
          <div className="toolbar compact">
            <span className="index-status">
              Прочитано: {processed.toLocaleString("ru-RU")} /{" "}
              {indexTotal.toLocaleString("ru-RU")}
            </span>
            <Button onClick={indexing ? undefined : () => void indexLibrary()}>
              <Sparkles size={16} />
              {indexing
                ? "Индексация идёт"
                : indexPaused
                  ? "Продолжить индексацию"
                  : "ИИ-индексация"}
            </Button>
            <Button
              onClick={
                data.footageFolders.length
                  ? () => void command("inspect-footage-tree")
                  : undefined
              }
            >
              <Library size={16} />
              Показать дерево
            </Button>
            <Button kind="primary" onClick={() => void chooseFolder()}>
              <Plus size={17} />
              Добавить корень
            </Button>
          </div>
        </div>
        {indexing || indexPaused || indexStatus.error ? (
          <div
            className={`footage-index-timeline ${indexStatus.error ? "error" : ""}`}
          >
            <div>
              <b>
                {indexStatus.error
                  ? "Ошибка индексации"
                  : indexPaused
                    ? "Индексация приостановлена"
                    : `Анализируется: ${indexStatus.current || "подготовка библиотеки"}`}
              </b>
              <span>
                прочитано: {processed.toLocaleString("ru-RU")} из{" "}
                {indexTotal.toLocaleString("ru-RU")} · осталось:{" "}
                {remaining.toLocaleString("ru-RU")} · {progress}%
              </span>
            </div>
            <div className="footage-index-progress">
              <i style={{ width: `${progress}%` }} />
            </div>
            <small>
              {indexStatus.error ||
                indexStatus.message ||
                `Новых проиндексировано: ${Number(indexStatus.indexed || 0).toLocaleString("ru-RU")}; пропущено без изменений: ${Number(indexStatus.skipped || 0).toLocaleString("ru-RU")}; ошибок: ${Number(indexStatus.failed || 0).toLocaleString("ru-RU")}. Обновление каждые 1,5 секунды.`}
            </small>
          </div>
        ) : null}
        {data.footageFolders.length ? (
          <>
            <div className="footage-labels">
              <span>
                Исключено английских надписей:{" "}
                {Number(data.footageIndex.englishBlocked || 0).toLocaleString(
                  "ru-RU",
                )}
              </span>
              <span>
                Проверено без английского текста:{" "}
                {Number(data.footageIndex.englishSafe || 0).toLocaleString(
                  "ru-RU",
                )}
              </span>
              <span>
                Осталось проверить:{" "}
                {Number(data.footageIndex.englishUnchecked || 0).toLocaleString(
                  "ru-RU",
                )}
              </span>
            </div>
            <DataTable ariaLabel="Источники футажей" data={data.footageFolders} columns={folderColumns} />
            {data.footageTree ? (
              <div className="footage-tree">
                {data.footageTree.roots.map((root) => (
                  <details key={root.path}>
                    <summary>
                      <b>{root.path}</b>
                      <span>{root.clips} клипов</span>
                    </summary>
                    {root.branches.map((branch) => (
                      <div key={branch.name}>
                        <span>└ {branch.name}</span>
                        <small>{branch.clips} клипов</small>
                      </div>
                    ))}
                  </details>
                ))}
                <small>
                  {data.footageTree.limited
                    ? "Показаны только верхние ветки — весь поиск всё равно идёт по всем вложенным папкам."
                    : `Всего в дереве: ${data.footageTree.total} клипов.`}
                </small>
              </div>
            ) : null}
          </>
        ) : (
          <Empty
            title="Подключите папки с футажами"
            text="Подойдут ваши 20 000 коротких клипов. Нажмите «ИИ-индексация» один раз — дальше новые и неизменённые клипы обрабатываются локально."
          />
        )}
      </section>
      <section className="panel footage-search">
        <div className="panel-title">
          <div>
            <b>Поиск и загрузка футажей</b>
            <small>
              Агент ищет по вашему запросу в YouTube и разрешённых источниках.
              Скачивание хранит источник, а автоматический монтаж берёт только
              короткий фрагмент и приводит его к 30 FPS без звука.
            </small>
          </div>
        </div>
        <div className="form-row">
          <input
            value={downloadFolder}
            onChange={(event) => setDownloadFolder(event.target.value)}
            placeholder="D:\\NewsFlow Studio\\Футажи из интернета"
          />
          <Button onClick={() => void chooseDownloadFolder()}>
            Выбрать папку
          </Button>
          <Button
            onClick={
              downloadFolder
                ? () =>
                    void command("save-footage-settings", { downloadFolder })
                : undefined
            }
          >
            <Check size={16} />
            Сохранить путь
          </Button>
        </div>
        <div className="form-row">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Например: Ормузский пролив, нефтяные танкеры"
          />
          <select
            value={source}
            onChange={(event) => setSource(event.target.value)}
          >
            <option value="wikimedia">Разрешённые источники</option>
            <option value="youtube">YouTube</option>
            <option value="all">Все доступные источники</option>
          </select>
          <Button kind="primary" onClick={() => void search()}>
            <Search size={17} />
            Агент: найти видео
          </Button>
        </div>
        {results.length ? (
          <>
            <div className="download-settings">
              <span>Отрезок YouTube</span>
              <label>
                с
                <input
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                  inputMode="decimal"
                />
              </label>
              <label>
                длина
                <input
                  value={duration}
                  onChange={(event) => setDuration(event.target.value)}
                  inputMode="decimal"
                />
              </label>
              <small>
                секунд; для Wikimedia скачивается выбранный исходный файл.
              </small>
            </div>
            <DataTable ariaLabel="Результаты поиска футажей" data={results} columns={resultColumns} />
          </>
        ) : (
          <Empty
            title="Введите запрос"
            text="Результаты поиска появятся здесь — с источником и лицензией."
          />
        )}
      </section>
    </div>
  );
}

export function Cutter({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const [outputFolder, setOutputFolder] = useState(
    data.cutterSettings.outputFolder,
  );
  const [duration, setDuration] = useState("6");
  const [fps, setFps] = useState("30");
  const [bitrate, setBitrate] = useState("4M");
  const [clipsPerVideo, setClipsPerVideo] = useState("12");
  const [variants, setVariants] = useState("10");
  const addSources = async () => {
    const paths = await window.newsflowDesktop?.chooseVideos();
    if (paths?.length) void command("add-cutter-sources", { paths });
  };
  const run = () =>
    void command("run-cutter", {
      outputFolder,
      duration: Number(duration),
      fps: Number(fps),
      bitrate,
    });
  const mix = () =>
    void command("run-mixer", {
      folder: outputFolder,
      clipsPerVideo: Number(clipsPerVideo),
      count: Number(variants),
    });
  const sourceColumns = useMemo<ColumnDef<string>[]>(
    () => [
      { id: "source", header: "Видео", cell: ({ row }) => <span className="nf-footage-source"><Video size={16} />{row.original}</span> },
      { id: "purpose", header: "Назначение", cell: () => "Исходник для нарезки" },
    ],
    [],
  );
  return (
    <div className="nf-cutter" aria-label="Footage Cutter Workspace">
      <section className="panel footage-folders">
        <div className="panel-title">
          <div>
            <b>Исходники для нарезки</b>
            <small>
              Видео будут приведены к одинаковым тихим MP4; оригиналы не
              меняются.
            </small>
          </div>
          <Button kind="primary" onClick={() => void addSources()}>
            <Plus size={17} />
            Добавить видео
          </Button>
        </div>
        <DataTable ariaLabel="Исходники для нарезки" data={data.cutterSources} columns={sourceColumns} />
        {!data.cutterSources.length ? (
          <Empty
            title="Добавьте исходные ролики"
            text="Можно выбрать несколько файлов сразу или использовать скачанные футажи."
          />
        ) : null}
      </section>
      <section className="panel cutter-controls">
        <div className="panel-title">
          <div>
            <b>Нарезка футажей</b>
            <small>
              Для быстрой сборки: 6 секунд, 30 FPS, H.264. Битрейт 4–8 Мбит/с
              достаточно; 25 Мбит/с можно оставить, но он замедлит рендер.
            </small>
          </div>
        </div>
        <div className="form-row">
          <input
            value={outputFolder}
            onChange={(event) => setOutputFolder(event.target.value)}
            placeholder="Папка нарезок"
          />
          <input
            value={duration}
            onChange={(event) => setDuration(event.target.value)}
            aria-label="Длина"
          />
          <input
            value={fps}
            onChange={(event) => setFps(event.target.value)}
            aria-label="FPS"
          />
          <input
            value={bitrate}
            onChange={(event) => setBitrate(event.target.value)}
            aria-label="Битрейт"
          />
          <Button kind="success" onClick={run}>
            <Clapperboard size={17} />
            Нарезать и добавить
          </Button>
        </div>
      </section>
      <section className="panel cutter-controls">
        <div className="panel-title">
          <div>
            <b>Вариации из готовых нарезок</b>
            <small>
              Собирает отдельные MP4 из случайных сочетаний. Исходные клипы
              остаются нетронутыми.
            </small>
          </div>
        </div>
        <div className="form-row">
          <input
            value={clipsPerVideo}
            onChange={(event) => setClipsPerVideo(event.target.value)}
            aria-label="Клипов в видео"
          />
          <input
            value={variants}
            onChange={(event) => setVariants(event.target.value)}
            aria-label="Вариаций"
          />
          <Button kind="primary" onClick={mix}>
            <WandSparkles size={17} />
            Собрать вариации
          </Button>
        </div>
        {data.operationResult ? (
          <div className="operation-result">
            {data.operationResult.kind === "cutter"
              ? "Нарезка готова"
              : "Вариации готовы"}
            : {data.operationResult.count} · {data.operationResult.folder}
          </div>
        ) : null}
      </section>
    </div>
  );
}

function MontageAssets({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const [introFolder, setIntroFolder] = useState(
    data.montageSettings.introFolder,
  );
  const [overlayFolder, setOverlayFolder] = useState(
    data.montageSettings.overlayFolder,
  );
  const [introEnabled, setIntroEnabled] = useState(
    data.montageSettings.introEnabled,
  );
  const [overlayEnabled, setOverlayEnabled] = useState(
    data.montageSettings.overlayEnabled,
  );
  const [introDuration, setIntroDuration] = useState(
    String(data.montageSettings.introDuration),
  );
  useEffect(() => {
    setIntroFolder(data.montageSettings.introFolder);
    setOverlayFolder(data.montageSettings.overlayFolder);
    setIntroEnabled(data.montageSettings.introEnabled);
    setOverlayEnabled(data.montageSettings.overlayEnabled);
    setIntroDuration(String(data.montageSettings.introDuration));
  }, [data.montageSettings]);
  const choose = async (target: "intro" | "overlay") => {
    const folder = await window.newsflowDesktop?.chooseFolder();
    if (folder)
      target === "intro" ? setIntroFolder(folder) : setOverlayFolder(folder);
  };
  const save = () =>
    void command("save-montage-settings", {
      introEnabled,
      introFolder,
      introDuration: Number(introDuration),
      overlayEnabled,
      overlayFolder,
    });
  return (
    <section className="panel montage-assets">
      <div className="panel-title">
        <div>
          <b>Заставка и бегущая строка</b>
          <small>
            Для каждого ролика выбирается случайный файл из папки. Заставка идёт
            до начала озвучки со своим исходным звуком, хромакей накладывается
            один раз на весь ролик.
          </small>
        </div>
        <Button kind="primary" onClick={save}>
          Сохранить настройки
        </Button>
      </div>
      <div className="asset-grid">
        <label className="asset-toggle">
          <input
            type="checkbox"
            checked={introEnabled}
            onChange={(event) => setIntroEnabled(event.target.checked)}
          />
          <span>
            <b>Случайная заставка в начале</b>
            <small>Сохраняет исходный звук; голос начинается после неё.</small>
          </span>
        </label>
        <div className="asset-path">
          <input
            value={introFolder}
            onChange={(event) => setIntroFolder(event.target.value)}
            placeholder="Папка с заставками"
          />
          <input
            value={introDuration}
            onChange={(event) => setIntroDuration(event.target.value)}
            inputMode="decimal"
            aria-label="Длина заставки"
          />
          <Button onClick={() => void choose("intro")}>Выбрать</Button>
        </div>
        <label className="asset-toggle">
          <input
            type="checkbox"
            checked={overlayEnabled}
            onChange={(event) => setOverlayEnabled(event.target.checked)}
          />
          <span>
            <b>Случайный хромакей / бегущая строка</b>
            <small>Один выбранный слой поверх готового ролика.</small>
          </span>
        </label>
        <div className="asset-path">
          <input
            value={overlayFolder}
            onChange={(event) => setOverlayFolder(event.target.value)}
            placeholder="Папка с хромакеем"
          />
          <Button onClick={() => void choose("overlay")}>Выбрать</Button>
        </div>
      </div>
    </section>
  );
}

export function MontageLiveStatus({ data }: { data: NewsFlowSnapshot }) {
  const stages = [
    {
      label: "В очереди",
      statuses: ["В очереди", "Пауза"],
      hint: "ожидают запуска или продолжения",
    },
    {
      label: "Подбор",
      statuses: ["Планирование", "Планирование сцен", "Подбор футажей"],
      hint: "смысл сцен и локальные футажи",
    },
    {
      label: "Внешний футаж",
      statuses: ["Внешний поиск", "Нарезка внешнего футажа"],
      hint: "поиск, загрузка и 30 FPS-нарезка",
    },
    {
      label: "Рендер",
      statuses: ["Ожидает рендер", "Рендер", "Склейка"],
      hint: "сборка MP4 с озвучкой",
    },
    { label: "Готово", statuses: ["Готово"], hint: "MP4 сохранён" },
    { label: "Ошибка", statuses: ["Ошибка"], hint: "можно повторить задачу" },
  ];
  const active = data.montageTasks.filter(
    (task) => !["Готово", "Ошибка"].includes(task.status || ""),
  );
  const lead = active[0];
  return (
    <section className="panel montage-live-status">
      <div className="panel-title">
        <div>
          <b>Монтаж сейчас</b>
          <small>
            {data.montageSettings.queuePaused
              ? "Очередь на паузе: текущая операция остановится на безопасном этапе."
              : lead
                ? `Сейчас: «${lead.title}» — ${lead.phase || lead.status}`
                : data.montageTasks.length
                  ? "Очередь завершена. Откройте MP4 или повторите задачи с ошибкой."
                  : "Очередь ещё не запускалась."}
          </small>
        </div>
        <span className={active.length ? "status montage-active" : "status"}>
          {active.length ? `${active.length} в работе` : "Нет активных задач"}
        </span>
      </div>
      <div className="montage-stage-flow">
        {stages.map((stage) => {
          const count = data.montageTasks.filter((task) =>
            stage.statuses.includes(task.status || ""),
          ).length;
          return (
            <div
              key={stage.label}
              className={`${count ? "busy" : ""} ${stage.label === "Готово" && count ? "complete" : ""} ${stage.label === "Ошибка" && count ? "failed" : ""}`}
            >
              <b>{count}</b>
              <span>{stage.label}</span>
              <small>{stage.hint}</small>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function Editor({
  data,
  command,
  refresh,
}: {
  data: NewsFlowSnapshot;
  command: Command;
  refresh: () => Promise<void>;
}) {
  const montageTasksByIndex = useMemo(
    () => new Map(data.montageTasks.map((task) => [task.index, task])),
    [data.montageTasks],
  );
  const incomingAudio = data.voiceItems.filter(
    (item) =>
      item.path &&
      ["Новый MP3", "Добавлено в монтаж"].includes(
        montageTasksByIndex.get(item.index)?.status || "",
      ),
  );
  const ready = data.voiceItems.filter(
    (item) =>
      item.path &&
      data.scenarios.some((scenario) => scenario.index === item.index) &&
      [
        "Готов к монтажу",
        "В очереди",
        "Планирование",
        "Планирование сцен",
        "Подбор футажей",
        "Внешний поиск",
        "Нарезка внешнего футажа",
        "Ожидает рендер",
        "Рендер",
        "Склейка",
        "Пауза",
        "Готово",
        "Ошибка",
      ].includes(
        montageTasksByIndex.get(item.index)?.status || "Готов к монтажу",
      ),
  );
  const activeMontageStatuses = new Set([
    "В очереди",
    "Планирование",
    "Планирование сцен",
    "Подбор футажей",
    "Внешний поиск",
    "Нарезка внешнего футажа",
    "Ожидает рендер",
    "Рендер",
    "Склейка",
    "Пауза",
  ]);
  // A regular launch/resume is deliberately missing-only. Ready videos have a
  // separate explicit "Перезапустить" action and must never be swept into a
  // new batch merely because the user attached another MP3.
  const unfinished = ready.filter(
    (item) => montageTasksByIndex.get(item.index)?.status !== "Готово",
  );
  const resumable = unfinished.filter(
    (item) =>
      !activeMontageStatuses.has(
        montageTasksByIndex.get(item.index)?.status || "",
      ),
  );
  const [selected, setSelected] = useState<number[]>([]);
  const [inspectedMontageIndex, setInspectedMontageIndex] = useState<
    number | null
  >(null);
  const [selectedProjects, setSelectedProjects] = useState<string[]>([]);
  const [queueLaunching, setQueueLaunching] = useState(false);
  const [ratio, setRatio] = useState(data.montageSettings.aspectRatio);
  const [renderer, setRenderer] = useState(data.montageSettings.renderer);
  const [remotionFrameConcurrency, setRemotionFrameConcurrency] = useState(
    String(data.montageSettings.remotionFrameConcurrency),
  );
  const [exportDaVinciXml, setExportDaVinciXml] = useState(
    data.montageSettings.exportDaVinciXml !== false,
  );
  const [davinciAutoImport, setDavinciAutoImport] = useState(
    Boolean(data.montageSettings.davinciAutoImport),
  );
  const [transitionStyle, setTransitionStyle] = useState(
    data.montageSettings.transitionStyle || "crossfade",
  );
  const [transitionFrames, setTransitionFrames] = useState(
    String(data.montageSettings.transitionFrames ?? 7),
  );
  const [outputFolder, setOutputFolder] = useState(
    data.montageSettings.outputFolder,
  );
  const [planningWorkers, setPlanningWorkers] = useState(
    String(data.montageSettings.planningWorkers),
  );
  const [downloadWorkers, setDownloadWorkers] = useState(
    String(data.montageSettings.downloadWorkers),
  );
  const [renderWorkers, setRenderWorkers] = useState(
    String(data.montageSettings.renderWorkers),
  );
  const [autoWeb, setAutoWeb] = useState(data.montageSettings.autoWeb);
  const [externalOnly, setExternalOnly] = useState(
    data.montageSettings.externalOnly,
  );
  const [useScriptText, setUseScriptText] = useState(
    data.montageSettings.useScriptText !== false,
  );
  const [excludeEnglishText, setExcludeEnglishText] = useState(
    data.montageSettings.excludeEnglishText !== false,
  );
  const [scenePlanner, setScenePlanner] = useState(
    data.montageSettings.scenePlanner,
  );
  const [fastReuseEnabled, setFastReuseEnabled] = useState(
    Boolean(data.montageSettings.fastReuseEnabled),
  );
  const [uniqueFootagePercent, setUniqueFootagePercent] = useState(
    String(data.montageSettings.uniqueFootagePercent ?? 100),
  );
  const [fastReuseRanges, setFastReuseRanges] = useState<
    Array<{ start: number; end: number; percent: number }>
  >(data.montageSettings.fastReuseRanges || []);
  const [configurationOpen, setConfigurationOpen] = useState(false);
  const running = data.montageTasks.some((item) =>
    [
      "В очереди",
      "Планирование",
      "Планирование сцен",
      "Подбор футажей",
      "Внешний поиск",
      "Нарезка внешнего футажа",
      "Ожидает рендер",
      "Рендер",
      "Склейка",
      "Пауза",
    ].includes(item.status || ""),
  );
  const queueActive = running || queueLaunching;
  const inspectedMontage = data.montageTasks.find(
    (task) => task.index === inspectedMontageIndex,
  );
  useEffect(() => {
    setRatio(data.montageSettings.aspectRatio);
    setRenderer(data.montageSettings.renderer);
    setRemotionFrameConcurrency(
      String(data.montageSettings.remotionFrameConcurrency),
    );
    setExportDaVinciXml(data.montageSettings.exportDaVinciXml !== false);
    setDavinciAutoImport(Boolean(data.montageSettings.davinciAutoImport));
    setTransitionStyle(data.montageSettings.transitionStyle || "crossfade");
    setTransitionFrames(String(data.montageSettings.transitionFrames ?? 7));
    setOutputFolder(data.montageSettings.outputFolder);
    setPlanningWorkers(String(data.montageSettings.planningWorkers));
    setDownloadWorkers(String(data.montageSettings.downloadWorkers));
    setRenderWorkers(String(data.montageSettings.renderWorkers));
    setAutoWeb(data.montageSettings.autoWeb);
    setExternalOnly(data.montageSettings.externalOnly);
    setUseScriptText(data.montageSettings.useScriptText !== false);
    setExcludeEnglishText(data.montageSettings.excludeEnglishText !== false);
    setScenePlanner(data.montageSettings.scenePlanner);
    setFastReuseEnabled(Boolean(data.montageSettings.fastReuseEnabled));
    setUniqueFootagePercent(
      String(data.montageSettings.uniqueFootagePercent ?? 100),
    );
    setFastReuseRanges(data.montageSettings.fastReuseRanges || []);
  }, [data.montageSettings]);
  useEffect(() => {
    setSelected((current) =>
      current.filter((index) => ready.some((item) => item.index === index)),
    );
  }, [data.voiceItems.length]);
  useEffect(() => {
    setSelectedProjects((current) =>
      current.filter((path) =>
        data.montageProjects.some((project) => project.path === path),
      ),
    );
  }, [data.montageProjects]);
  // Open the first saved plan automatically. A project is useful only when
  // its timeline is visible; users can still click another row (or Ctrl+click
  // for deletion selection) below.
  const selectedProject =
    data.montageProjects.find(
      (project) =>
        project.path === selectedProjects[selectedProjects.length - 1],
    ) || data.montageProjects[0];
  const localMediaUrl = (path?: string) =>
    path ? encodeURI(`file:///${path.replace(/\\/g, "/")}`) : "";
  useEffect(() => {
    if (!queueActive) return;
    // A Remotion job starts Chromium frame workers. Polling through a separate
    // Python process too aggressively competes with those workers and made the
    // desktop window look frozen on large queues.
    const timer = window.setInterval(
      () => {
        void refresh();
      },
      renderer === "remotion" ? 2500 : 900,
    );
    void refresh();
    return () => window.clearInterval(timer);
  }, [queueActive, refresh]);
  const chooseOutput = async () => {
    const folder = await window.newsflowDesktop?.chooseFolder();
    if (folder) setOutputFolder(folder);
  };
  const saveSettings = () =>
    void command("save-montage-settings", {
      aspectRatio: ratio,
      renderer,
      remotionFrameConcurrency: Number(remotionFrameConcurrency),
      exportDaVinciXml,
      davinciAutoImport,
      transitionStyle,
      transitionFrames: Number(transitionFrames),
      outputFolder,
      planningWorkers: Number(planningWorkers),
      downloadWorkers: Number(downloadWorkers),
      renderWorkers: Number(renderWorkers),
      autoWeb,
      externalOnly,
      useScriptText,
      excludeEnglishText,
      scenePlanner,
      fastReuseEnabled,
      uniqueFootagePercent: Number(uniqueFootagePercent),
      fastReuseRanges,
    });
  const launch = async (indices: number[], replaceOutput = false) => {
    if (!indices.length || queueActive) return;
    setQueueLaunching(true);
    try {
      const saved = await command("save-montage-settings", {
        aspectRatio: ratio,
        renderer,
        remotionFrameConcurrency: Number(remotionFrameConcurrency),
        exportDaVinciXml,
        davinciAutoImport,
        transitionStyle,
        transitionFrames: Number(transitionFrames),
        outputFolder,
        planningWorkers: Number(planningWorkers),
        downloadWorkers: Number(downloadWorkers),
        renderWorkers: Number(renderWorkers),
        autoWeb,
        externalOnly,
        useScriptText,
        excludeEnglishText,
        scenePlanner,
        fastReuseEnabled,
        uniqueFootagePercent: Number(uniqueFootagePercent),
        fastReuseRanges,
      });
      if (saved) await command("run-montage-queue", { indices, replaceOutput });
    } finally {
      setQueueLaunching(false);
      void refresh();
    }
  };
  const remove = async (all = false) => {
    const indices = all
      ? data.montageTasks.map((item) => item.index)
      : selected;
    if (
      !indices.length ||
      !window.confirm(
        all
          ? "Удалить все готовые MP4 и их пакеты результатов?"
          : `Удалить готовые MP4: ${indices.length}?`,
      )
    )
      return;
    const result = await command(
      "remove-montage-results",
      all ? { all: true } : { indices },
    );
    if (result) setSelected([]);
  };
  const removeProjects = async (all = false) => {
    const paths = all
      ? data.montageProjects.map((project) => project.path)
      : selectedProjects;
    if (
      !paths.length ||
      !window.confirm(
        all
          ? "Удалить все планы монтажа и их Remotion JSON? Готовые MP4, сценарии и MP3 останутся."
          : `Удалить выбранные планы монтажа: ${paths.length}? Готовые MP4 останутся.`,
      )
    )
      return;
    const result = await command(
      "remove-montage-projects",
      all ? { all: true } : { paths },
    );
    if (result) setSelectedProjects([]);
  };
  const togglePause = () =>
    void command("save-montage-settings", {
      queuePaused: !data.montageSettings.queuePaused,
    });
  const exportDaVinci = (all = false) =>
    void command(
      "export-davinci-xml",
      all ? { all: true } : { paths: selectedProjects },
    );
  const importDaVinci = () =>
    void command("import-davinci-xml", {
      paths: selectedProjects
        .map(
          (path) =>
            data.montageProjects.find((project) => project.path === path)
              ?.fcpxmlPath,
        )
        .filter(Boolean),
    });
  const updateFastRange = (
    index: number,
    field: "start" | "end" | "percent",
    value: string,
  ) =>
    setFastReuseRanges((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, [field]: Number(value) } : item,
      ),
    );
  const addFastRange = () =>
    setFastReuseRanges((current) => [
      ...current,
      {
        start: 1,
        end: 1,
        percent: Math.max(
          5,
          Math.min(100, Number(uniqueFootagePercent) || 100),
        ),
      },
    ]);
  const enqueueIncomingAudio = async (
    indices = incomingAudio.map((item) => item.index),
  ) => {
    if (!indices.length) return;
    const result = await command("enqueue-montage-audio", { indices });
    if (result) setSelected([]);
  };
  return (
    <div className="nf-montage nf-fast-editing-workspace" aria-label="Fast Editing workspace">
      <section className="panel montage-control-deck">
        <div className="panel-title">
          <div>
            <b>Готовность Fast News монтажа</b>
            <small>Очередь, голос и сохранённые планы остаются в рабочем поле; расширенные настройки открываются отдельно.</small>
          </div>
          <Button onClick={() => setConfigurationOpen(true)}>
            <Settings2 size={16} />
            Настроить монтаж
          </Button>
        </div>
      </section>
      <MontageLiveStatus data={data} />
      <Sheet
        open={configurationOpen}
        onOpenChange={setConfigurationOpen}
        title="Настройки Fast News монтажа"
        description="Движок, подготовка футажей, DaVinci, ресурсы и параметры рендера."
      >
        <div className="nf-montage-configuration">
      <MontageAssets data={data} command={command} />
      <section className="panel montage-short-mode">
        <div className="panel-title">
          <div>
            <b>Короткий ролик из внешних источников</b>
            <small>
              Для ролика на несколько минут пропускает библиотеку и ищет каждый
              футаж в разрешённых новостных и стоковых источниках.
              Автоматическая загрузка коротких фрагментов YouTube выключена.
            </small>
          </div>
        </div>
        <label className="check-row">
          <input
            type="checkbox"
            checked={externalOnly}
            onChange={(event) => setExternalOnly(event.target.checked)}
          />
          Собирать только из внешних источников
        </label>
      </section>
      <section className="panel renderer-choice-panel">
        <div className="panel-title">
          <div>
            <b>Как собрать и передать монтаж</b>
            <small>
              MP4 делает один выбранный движок. DaVinci XML — отдельный
              редактируемый план этой же дорожки, без второго рендера.
            </small>
          </div>
          <Button onClick={() => void saveSettings()}>
            <Check size={16} />
            Сохранить выбор
          </Button>
        </div>
        <div className="renderer-choice renderer-choice-three">
          <button
            className={renderer === "ffmpeg" ? "selected" : ""}
            onClick={() => setRenderer("ffmpeg")}
          >
            <span>01</span>
            <div>
              <b>Только FFmpeg</b>
              <small>
                Быстрая склейка аудио и футажей. Без композиции Remotion, без
                дополнительного Chromium.
              </small>
            </div>
            <em>быстрее</em>
          </button>
          <button
            className={renderer === "remotion" ? "selected remotion" : ""}
            onClick={() => setRenderer("remotion")}
          >
            <span>02</span>
            <div>
              <b>Remotion — композиция</b>
              <small>React-таймлайн: сцены, голос, заставка и переходы.</small>
            </div>
            <em>переходы</em>
          </button>
          <button
            className={exportDaVinciXml ? "selected davinci" : ""}
            onClick={() => setExportDaVinciXml((value) => !value)}
          >
            <span>03</span>
            <div>
              <b>DaVinci Resolve XML</b>
              <small>
                Создать FCPXML с дорожками футажей и MP3. Это не повторный
                рендер MP4.
              </small>
            </div>
            <em>{exportDaVinciXml ? "включён" : "выключен"}</em>
          </button>
        </div>
        {renderer === "remotion" ? (
          <div className="remotion-controls">
            <label>
              Переходы
              <select
                value={transitionStyle}
                onChange={(event) =>
                  setTransitionStyle(
                    event.target.value as
                      | "crossfade"
                      | "dip-black"
                      | "cut"
                      | "slide-left",
                  )
                }
              >
                <option value="crossfade">Мягкое растворение</option>
                <option value="dip-black">Через затемнение</option>
                <option value="slide-left">Сдвиг кадра</option>
                <option value="cut">Жёсткая склейка</option>
              </select>
            </label>
            <label>
              Длина перехода, кадров
              <input
                type="number"
                min="0"
                max="30"
                value={transitionFrames}
                onChange={(event) => setTransitionFrames(event.target.value)}
              />
            </label>
            <label>
              Кадров параллельно в одном ролике
              <input
                type="number"
                min="1"
                max="8"
                value={remotionFrameConcurrency}
                onChange={(event) =>
                  setRemotionFrameConcurrency(event.target.value)
                }
              />
            </label>
            <aside>
              <b>
                Нагрузка сейчас: {Math.max(1, Number(renderWorkers) || 1)} рол.
                × {Math.max(1, Number(remotionFrameConcurrency) || 1)} кадр. ={" "}
                {Math.max(1, Number(renderWorkers) || 1) *
                  Math.max(1, Number(remotionFrameConcurrency) || 1)}{" "}
                процессов
              </b>
              <small>
                Для стабильной работы начните с 2 роликов × 2 кадра.
              </small>
            </aside>
          </div>
        ) : (
          <div className="renderer-note">
            <b>FFmpeg выбран.</b> Он соберёт MP4 быстрее и экономнее, но без
            Remotion-композиции и настраиваемых переходов.
          </div>
        )}
        <div className="davinci-controls">
          <label className="check-row">
            <input
              type="checkbox"
              checked={exportDaVinciXml}
              onChange={(event) => {
                const enabled = event.target.checked;
                setExportDaVinciXml(enabled);
                if (!enabled) setDavinciAutoImport(false);
                // This preference must survive the normal background snapshot
                // refresh. Previously React briefly unchecked it, then the
                // stale persisted `true` re-checked it before the user could
                // press the wider «Сохранить» control.
                void command("save-montage-settings", {
                  exportDaVinciXml: enabled,
                  davinciAutoImport: enabled ? davinciAutoImport : false,
                });
              }}
            />
            Создавать DaVinci XML вместе с каждым планом
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={davinciAutoImport}
              disabled={
                !exportDaVinciXml ||
                !data.montageSettings.davinciStatus?.connected
              }
              onChange={(event) => setDavinciAutoImport(event.target.checked)}
            />
            Автоимпортировать в открытый DaVinci Resolve
          </label>
          <Button onClick={() => void refresh()}>
            <Activity size={15} />
            Проверить API
          </Button>
          <small>
            {data.montageSettings.davinciStatus?.message ||
              "Проверяем DaVinci Scripting API…"}{" "}
            Resolve должен быть открыт с выбранным проектом.
          </small>
        </div>
      </section>
      <section className="panel editor-settings">
        <div className="panel-title">
          <div>
            <b>Конвейер монтажа</b>
            <small>
              Автоматически берёт готовые сценарии и MP3: исходная заставка со
              звуком → голос → футажи по смыслу → MP4. Ручной сценарий и свой
              MP3, добавленные в «Озвучку», здесь появляются так же.
            </small>
          </div>
          <div className="toolbar compact">
            <Button onClick={() => void saveSettings()}>
              <Check size={16} />
              Сохранить параметры
            </Button>
            <Button onClick={() => void chooseOutput()}>Папка MP4</Button>
            <Button
              onClick={
                outputFolder
                  ? () => void window.newsflowDesktop?.openPath(outputFolder)
                  : undefined
              }
            >
              <FolderOpen size={16} />
              Открыть
            </Button>
          </div>
        </div>
        <div className="form-grid montage-grid">
          <label>
            Движок рендера
            <select
              value={renderer}
              onChange={(event) =>
                setRenderer(event.target.value as "remotion" | "ffmpeg")
              }
            >
              <option value="remotion">Remotion — переходы и слои</option>
              <option value="ffmpeg">FFmpeg — быстрый простой монтаж</option>
            </select>
          </label>
          <label>
            Формат
            <select
              value={ratio}
              onChange={(event) => setRatio(event.target.value)}
            >
              <option>16:9</option>
              <option>9:16</option>
              <option>1:1</option>
            </select>
          </label>
          <label>
            Папка только с MP4
            <input
              value={outputFolder}
              onChange={(event) => setOutputFolder(event.target.value)}
              placeholder="D:\\NewsFlow Studio\\Готовые ролики"
            />
          </label>
          <label>
            Планирование и подбор{" "}
            <input
              type="number"
              min="1"
              max="16"
              value={planningWorkers}
              onChange={(event) => setPlanningWorkers(event.target.value)}
            />
          </label>
          <label>
            Скачивание и нарезка{" "}
            <input
              type="number"
              min="1"
              max="8"
              value={downloadWorkers}
              onChange={(event) => setDownloadWorkers(event.target.value)}
            />
          </label>
          <label>
            Видео одновременно{" "}
            <input
              type="number"
              min="1"
              max="8"
              value={renderWorkers}
              onChange={(event) => setRenderWorkers(event.target.value)}
            />
          </label>
          {renderer === "remotion" ? (
            <label>
              Кадров параллельно в каждом рендере{" "}
              <input
                type="number"
                min="1"
                max="8"
                value={remotionFrameConcurrency}
                onChange={(event) =>
                  setRemotionFrameConcurrency(event.target.value)
                }
              />
            </label>
          ) : null}
          <label className="check-row">
            <input
              type="checkbox"
              checked={useScriptText}
              onChange={(event) => setUseScriptText(event.target.checked)}
            />
            Требовать готовый текст сценария; если выключено — разрешить fallback по названию только когда текста нет
          </label>
          <label className="check-row">
            <input type="checkbox" checked disabled readOnly />
            Не использовать футажи с английскими/латинскими надписями — обязательное правило
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={autoWeb}
              onChange={(event) => setAutoWeb(event.target.checked)}
            />
            Искать в разрешённых внешних источниках, если локальный матч слабый
          </label>
        </div>
        <small className="workflow-note">
          Если готовый сценарий есть, NewsFlow всегда использует смысл каждой
          реплики для подбора футажей; MP3 задаёт точную длину. Выключение
          требования TXT разрешает режим по названию только когда текста
          действительно нет. Футаж с английскими/латинскими надписями не
          допускается: безопасная проверка кэшируется в локальном индексе.
        </small>
      </section>
      <section className="panel fast-reuse-panel">
        <div className="panel-title">
          <div>
            <b>Быстрый видеоряд с аккуратной ротацией</b>
            <small>
              Сначала подбираются уникальные футажи на выбранную долю голоса.
              Затем они повторяются только по границам реплик: длительность
              озвучки сохраняется, одинаковый кадр подряд не ставится.
            </small>
          </div>
          <Button onClick={() => void saveSettings()}>
            <Check size={16} />
            Сохранить режим
          </Button>
        </div>
        <label className="check-row">
          <input
            type="checkbox"
            checked={fastReuseEnabled}
            onChange={(event) => setFastReuseEnabled(event.target.checked)}
          />
          <span>
            <b>Быстрый режим: повторять отобранный пул футажей</b>
            <small>
              Подбор уникальных файлов становится заметно быстрее; FFmpeg и
              Remotion получают один и тот же таймлайн.
            </small>
          </span>
        </label>
        <div className="fast-reuse-controls">
          <label>
            По умолчанию уникальных:{" "}
            <b>
              {Math.max(5, Math.min(100, Number(uniqueFootagePercent) || 100))}%
            </b>
            <input
              type="range"
              min="5"
              max="100"
              step="1"
              value={uniqueFootagePercent}
              disabled={!fastReuseEnabled}
              onChange={(event) => setUniqueFootagePercent(event.target.value)}
            />
          </label>
          <input
            type="number"
            min="5"
            max="100"
            value={uniqueFootagePercent}
            disabled={!fastReuseEnabled}
            onChange={(event) => setUniqueFootagePercent(event.target.value)}
            aria-label="Процент уникальных футажей"
          />
          <small>
            {fastReuseRanges.length
              ? "Диапазоны ниже переопределяют этот процент и включают режим только для указанных тем."
              : fastReuseEnabled
                ? `ИИ подберёт новые футажи примерно для первых ${Math.max(5, Math.min(100, Number(uniqueFootagePercent) || 100))}% длительности у всех тем, затем будет ротировать их по голосовым сценам.`
                : "Выключено: для каждой сцены ищется отдельный уникальный футаж."}
          </small>
        </div>
        <div className="fast-reuse-ranges">
          <div>
            <b>Любые диапазоны тем</b>
            <small>
              Добавляйте сколько угодно правил: например 1–3, 7–8, 45–45 или
              120–260. Номера соответствуют очереди; при наличии правил быстрый
              режим сработает только в указанных диапазонах.
            </small>
          </div>
          <Button onClick={fastReuseEnabled ? addFastRange : undefined}>
            <Plus size={15} />
            Добавить диапазон
          </Button>
          {fastReuseRanges.length ? (
            fastReuseRanges.map((item, index) => (
              <div
                className="fast-reuse-range"
                key={`${index}-${item.start}-${item.end}`}
              >
                <label>
                  С
                  <input
                    type="number"
                    min="1"
                    value={item.start}
                    disabled={!fastReuseEnabled}
                    onChange={(event) =>
                      updateFastRange(index, "start", event.target.value)
                    }
                  />
                </label>
                <label>
                  По
                  <input
                    type="number"
                    min="1"
                    value={item.end}
                    disabled={!fastReuseEnabled}
                    onChange={(event) =>
                      updateFastRange(index, "end", event.target.value)
                    }
                  />
                </label>
                <label>
                  Уникальных, %
                  <input
                    type="number"
                    min="5"
                    max="100"
                    value={item.percent}
                    disabled={!fastReuseEnabled}
                    onChange={(event) =>
                      updateFastRange(index, "percent", event.target.value)
                    }
                  />
                </label>
                <Button
                  kind="danger"
                  onClick={
                    fastReuseEnabled
                      ? () =>
                          setFastReuseRanges((current) =>
                            current.filter(
                              (_, itemIndex) => itemIndex !== index,
                            ),
                          )
                      : undefined
                  }
                >
                  <Trash2 size={15} />
                  Убрать
                </Button>
              </div>
            ))
          ) : (
            <em>
              Диапазоны не заданы — после включения правило будет действовать
              для всех тем.
            </em>
          )}
        </div>
      </section>
      <section className="panel montage-planner">
        <div className="panel-title">
          <div>
            <b>Планировщик видеоряда</b>
            <small>
              Локальный режим бесплатен: сопоставляет видимые слова и
              ассоциации. Агент уточняет для каждой реплики объекты, людей,
              место и действие через активные ключи ChatGPT, затем локальный
              индекс ищет клип по этому описанию.
            </small>
          </div>
          <Button onClick={() => void saveSettings()}>
            <Check size={16} />
            Сохранить
          </Button>
        </div>
        <div className="form-row">
          <label>
            Кто планирует
            <select
              value={scenePlanner}
              onChange={(event) =>
                setScenePlanner(event.target.value as "local" | "agent")
              }
            >
              <option value="local">Локальный ИИ-индекс — без токенов</option>
              <option value="agent">
                Агент NewsFlow — точнее, расходует API-токены
              </option>
            </select>
          </label>
          <small>
            Если агент недоступен или лимит ключа исчерпан, монтаж не
            прерывается: применяется локальный план.
          </small>
        </div>
      </section>
        </div>
      </Sheet>
      {incomingAudio.length ? (
        <section className="panel montage-short-mode">
          <div className="panel-title">
            <div>
              <b>Новые озвучки для монтажа: {incomingAudio.length}</b>
              <small>
                MP3 автоматически подтянулись из «Озвучки». Добавление создаёт
                только готовые строки в очереди — рендер не запустится, пока вы
                не нажмёте «Собрать».
              </small>
            </div>
            <Button kind="success" onClick={() => void enqueueIncomingAudio()}>
              <Plus size={16} />
              Добавить {incomingAudio.length} новых в очередь
            </Button>
          </div>
          <div className="scenario-list montage-ready-list">
            {incomingAudio.map((item) => (
              <div key={item.index}>
                <span>{item.index + 1}</span>
                <b>{item.title}</b>
                <small>{item.path.split(/[\\/]/).pop()}</small>
                <em>
                  {montageTasksByIndex.get(item.index)?.status || "Новый MP3"}
                </em>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      <section className="panel table-wrap montage-queue">
        <div className="panel-title">
          <div>
            <b>Очередь: сценарий + MP3</b>
            <small>
              Клик — одна строка, Ctrl+клик — несколько. Повтор с начала
              создаёт замену и публикует её только после успешного рендера:
              прежний MP4 остаётся в сохранности до этого момента.
            </small>
          </div>
          <div className="toolbar compact">
            <Button
              kind="primary"
              onClick={
                selected.length && !queueActive
                  ? () => void launch(selected)
                  : undefined
              }
            >
              <WandSparkles size={17} />
              Собрать выбранные
            </Button>
            <Button
              kind="success"
              onClick={
                unfinished.length && !queueActive
                  ? () => void launch(unfinished.map((item) => item.index))
                  : undefined
              }
            >
              <Play size={17} />
              Собрать незавершённые
            </Button>
            <Button
              kind="primary"
              onClick={
                resumable.length && !queueActive
                  ? () => void launch(resumable.map((item) => item.index))
                  : undefined
              }
            >
              <Play size={17} />
              Продолжить монтаж{resumable.length ? `: ${resumable.length}` : ""}
            </Button>
            <Button
              onClick={
                queueActive || !selected.length
                  ? undefined
                  : () => void launch(selected, true)
              }
            >
              <WandSparkles size={17} />
              Повторить монтаж выбранных
            </Button>
            <Button
              onClick={
                queueActive || !ready.length
                  ? undefined
                  : () =>
                      void launch(
                        ready.map((item) => item.index),
                        true,
                      )
              }
            >
              <WandSparkles size={17} />
              Повторить монтаж всех: {ready.length}
            </Button>
            <Button
              kind={data.montageSettings.queuePaused ? "success" : "secondary"}
              onClick={running ? togglePause : undefined}
            >
              {data.montageSettings.queuePaused ? (
                <Play size={16} />
              ) : (
                <Pause size={16} />
              )}
              {data.montageSettings.queuePaused ? "Продолжить" : "Пауза"}
            </Button>
          </div>
        </div>
        {ready.length ? (
          <div className="scenario-list montage-ready-list">
            {ready.map((item) => {
              const task = montageTasksByIndex.get(item.index);
              return (
                <button
                  key={item.index}
                  className={selected.includes(item.index) ? "selected" : ""}
                  onClick={(event) =>
                    setSelected((current) =>
                      event.ctrlKey
                        ? current.includes(item.index)
                          ? current.filter((value) => value !== item.index)
                          : [...current, item.index]
                        : [item.index],
                    )
                  }
                >
                  <span>{selected.includes(item.index) ? "✓" : "○"}</span>
                  <span>{item.index + 1}</span>
                  <b>{item.title}</b>
                  <small>{item.path.split(/[\\/]/).pop()}</small>
                  <em
                    className={
                      task?.status === "Готово"
                        ? "done"
                        : task?.status === "Ошибка"
                          ? "error"
                          : ""
                    }
                  >
                    {task?.status || "Готов к монтажу"}
                  </em>
                </button>
              );
            })}
          </div>
        ) : (
          <Empty
            title="Нет готовых пар для монтажа"
            text="Готовые MP3 появляются выше как новые. Добавьте их в очередь — и только затем запускайте сборку."
          />
        )}
      </section>
      <section className="panel montage-task-list">
        <div className="panel-title">
          <div>
            <b>Статус задач и временная линия</b>
            <small>
              «Готово» ставится только после сохранения полного MP4. При ошибке
              видно её причину; можно выбрать строку и переделать с другими
              футажами.
            </small>
          </div>
          <div className="toolbar compact">
            <Button
              kind="danger"
              onClick={selected.length ? () => void remove(false) : undefined}
            >
              <Trash2 size={16} />
              Удалить выбранные MP4
            </Button>
            <Button
              kind="danger"
              onClick={
                data.montageTasks.length ? () => void remove(true) : undefined
              }
            >
              <Trash2 size={16} />
              Удалить все MP4
            </Button>
          </div>
        </div>
        {data.montageTasks.length ? (
          <div className="montage-task-cards">
            {data.montageTasks.map((task) => (
              <article
                className={`montage-task ${task.status === "Ошибка" ? "error" : task.status === "Готово" ? "done" : ""}`}
                key={task.index}
              >
                <div>
                  <span className="task-number">{task.index + 1}</span>
                  <b>{task.title}</b>
                  <em>{task.status || "Ожидает"}</em>
                </div>
                <div className="task-progress">
                  <i style={{ width: `${task.progress || 0}%` }} />
                  <span>
                    {task.progress || 0}% · {task.phase || "Ожидание"}
                  </span>
                </div>
                {task.error ? (
                  <p className="task-error">Причина: {task.error}</p>
                ) : null}
                <div className="task-timeline">
                  {(task.timeline || []).slice(-6).map((event, index) => (
                    <small key={`${event.at}-${index}`}>
                      <b>{event.at}</b> {event.label}
                      {event.detail ? ` — ${event.detail}` : ""}
                    </small>
                  ))}
                </div>
                <div className="toolbar compact">
                  <Button onClick={() => setInspectedMontageIndex(task.index)}>
                    <FileText size={15} />
                    Инспектор MP4
                  </Button>
                  {task.status === "Ошибка" ? (
                    <Button
                      kind="primary"
                      onClick={
                        running
                          ? undefined
                          : () => void launch([task.index], true)
                      }
                    >
                      <Play size={15} />
                      Повторить монтаж
                    </Button>
                  ) : null}
                  {task.outputPath ? (
                    <>
                      <Button
                        onClick={() =>
                          void window.newsflowDesktop?.openPath(
                            task.outputPath!,
                          )
                        }
                      >
                        <MonitorPlay size={15} />
                        Открыть MP4
                      </Button>
                      <Button
                        onClick={() =>
                          void window.newsflowDesktop?.openPath(outputFolder)
                        }
                      >
                        <FolderOpen size={15} />
                        Папка
                      </Button>
                    </>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            title="Задач монтажа пока нет"
            text="Выберите готовые MP3 выше и запустите сборку. Очередь, ошибки и готовые ролики сохраняются после перезапуска."
          />
        )}
      </section>
      <Sheet
        open={Boolean(inspectedMontage)}
        onOpenChange={(open) => {
          if (!open) setInspectedMontageIndex(null);
        }}
        title="Инспектор MP4"
        description="Подтверждённые текущим snapshot входы, выход и состояние рендера."
      >
        {inspectedMontage ? (
          <dl className="montage-provenance" aria-label="Происхождение MP4">
            <div>
              <dt>ProductionItem ID</dt>
              <dd>Текущий snapshot не сообщает ProductionItem ID</dd>
            </div>
            <div>
              <dt>Статус</dt>
              <dd>{inspectedMontage.status || "Не сообщён текущим snapshot"}</dd>
            </div>
            <div>
              <dt>Фаза</dt>
              <dd>{inspectedMontage.phase || "Не сообщена"}</dd>
            </div>
            <div>
              <dt>Последнее обновление</dt>
              <dd>{inspectedMontage.updatedAt || "Не получено"}</dd>
            </div>
            <div>
              <dt>Входной MP3</dt>
              <dd>{inspectedMontage.voicePath || "Не получен"}</dd>
            </div>
            <div>
              <dt>Файл MP4</dt>
              <dd>{inspectedMontage.outputPath || "Артефакт ещё не создан"}</dd>
            </div>
            <div>
              <dt>План монтажа</dt>
              <dd>{inspectedMontage.projectPath || "Не получен"}</dd>
            </div>
            <div>
              <dt>Задание</dt>
              <dd>Текущий snapshot не сообщает durable job ID</dd>
            </div>
            <div>
              <dt>Актуальность</dt>
              <dd>Текущий snapshot не сообщает признак устаревания</dd>
            </div>
          </dl>
        ) : null}
      </Sheet>
      <section className="panel timeline-list">
        <div className="panel-title">
          <div>
            <b>Проекты, Remotion и DaVinci</b>
            <small>
              .newsflow — план NewsFlow, .remotion.json — композиция, .fcpxml —
              редактируемая дорожка DaVinci. XML не рендерит MP4 повторно.
            </small>
          </div>
          <div className="toolbar compact">
            <Button
              kind="primary"
              onClick={
                selectedProjects.length ? () => exportDaVinci(false) : undefined
              }
            >
              <FileText size={16} />
              XML выбранных
            </Button>
            <Button
              onClick={
                data.montageProjects.length
                  ? () => exportDaVinci(true)
                  : undefined
              }
            >
              <Download size={16} />
              XML всех
            </Button>
            <Button
              kind="success"
              onClick={
                selectedProjects.length &&
                data.montageSettings.davinciStatus?.connected
                  ? importDaVinci
                  : undefined
              }
            >
              <Play size={16} />
              Импорт в DaVinci
            </Button>
            <Button
              kind="danger"
              onClick={
                selectedProjects.length
                  ? () => void removeProjects(false)
                  : undefined
              }
            >
              <Trash2 size={16} />
              Удалить выбранные
            </Button>
            <Button
              kind="danger"
              onClick={
                data.montageProjects.length
                  ? () => void removeProjects(true)
                  : undefined
              }
            >
              <Trash2 size={16} />
              Удалить все
            </Button>
          </div>
        </div>
        {data.montageProjects.length ? (
          <div className="project-list">
            {data.montageProjects.map((project) => (
              <button
                className={
                  selectedProjects.includes(project.path) ? "selected" : ""
                }
                onClick={(event) =>
                  setSelectedProjects((current) =>
                    event.ctrlKey
                      ? current.includes(project.path)
                        ? current.filter((path) => path !== project.path)
                        : [...current, project.path]
                      : [project.path],
                  )
                }
                onDoubleClick={() =>
                  void window.newsflowDesktop?.openPath(project.path)
                }
                key={project.path}
              >
                <MonitorPlay size={17} />
                <span>
                  <b>{project.title}</b>
                  <small>{project.path}</small>
                </span>
                <em>
                  {project.fcpxmlPath
                    ? "XML готов"
                    : selectedProjects.includes(project.path)
                      ? "Выбрано"
                      : "Клик — выбрать"}
                </em>
              </button>
            ))}
          </div>
        ) : (
          <Empty
            title="Нет сохранённых планов"
            text="После запуска монтажа здесь появятся .newsflow-планы. Они не являются готовыми видео."
          />
        )}
      </section>
      {selectedProject ? (
        <section className="panel project-preview">
          <div className="panel-title">
            <div>
              <b>Предпросмотр и таймлайн: {selectedProject.title}</b>
              <small>
                {selectedProject.outputPath
                  ? "Готовый MP4 можно открыть или смотреть прямо здесь."
                  : "MP4 ещё не готов: ниже показан сохранённый план Remotion."}
              </small>
            </div>
            <div className="toolbar compact">
              <Button
                onClick={() =>
                  void window.newsflowDesktop?.openPath(selectedProject.path)
                }
              >
                <FileText size={16} />
                Открыть план
              </Button>
              {selectedProject.remotionPath ? (
                <Button
                  onClick={() =>
                    void window.newsflowDesktop?.openPath(
                      selectedProject.remotionPath!,
                    )
                  }
                >
                  <Clapperboard size={16} />
                  Remotion JSON
                </Button>
              ) : null}
              {selectedProject.fcpxmlPath ? (
                <>
                  <Button
                    onClick={() =>
                      void window.newsflowDesktop?.openPath(
                        selectedProject.fcpxmlPath!,
                      )
                    }
                  >
                    <FileText size={16} />
                    Открыть DaVinci XML
                  </Button>
                  <Button
                    kind="success"
                    onClick={
                      data.montageSettings.davinciStatus?.connected
                        ? () =>
                            void command("import-davinci-xml", {
                              projectPath: selectedProject.path,
                            })
                        : undefined
                    }
                  >
                    <Play size={16} />В DaVinci
                  </Button>
                </>
              ) : (
                <Button
                  onClick={() =>
                    void command("export-davinci-xml", {
                      projectPath: selectedProject.path,
                    })
                  }
                >
                  <FileText size={16} />
                  Создать DaVinci XML
                </Button>
              )}
              {selectedProject.outputPath ? (
                <Button
                  kind="primary"
                  onClick={() =>
                    void window.newsflowDesktop?.openPath(
                      selectedProject.outputPath!,
                    )
                  }
                >
                  <MonitorPlay size={16} />
                  Открыть MP4
                </Button>
              ) : null}
            </div>
          </div>
          {selectedProject.error ? (
            <p className="task-error">{selectedProject.error}</p>
          ) : null}
          {selectedProject.selectionSummaryText ? (
            <p className="project-duration">
              {selectedProject.selectionSummaryText}
            </p>
          ) : null}
          {selectedProject.outputPath ? (
            <video
              className="project-video"
              controls
              preload="metadata"
              src={localMediaUrl(selectedProject.outputPath)}
            />
          ) : (
            <p className="project-empty">
              Ролик ещё не отрендерен. Запустите его через выбранный движок
              выше; сам файл .newsflow не содержит видео.
            </p>
          )}
          <div className="project-timeline" title="Таймлайн выбранного проекта">
            {selectedProject.clips?.length ? (
              selectedProject.clips.map((clip, index) => (
                <div
                  className={`project-clip ${clip.source || "local"}`}
                  style={{ flexGrow: Math.max(0.5, clip.duration || 1) }}
                  key={`${clip.path}-${index}`}
                >
                  <b>{index + 1}</b>
                  <span>
                    {clip.narration ||
                      clip.query ||
                      clip.path.split(/[\\/]/).pop()}
                  </span>
                  <small>
                    {clip.duration?.toFixed(1)} c · {clip.source || "local"}
                  </small>
                  {clip.fallbackLevel ? (
                    <small title={clip.positionRotationReason || undefined}>
                      {clip.fallbackLevel} · {clip.positionBucket || "—"} · start{" "}
                      {Number(clip.sourceStart || 0).toFixed(1)} c
                    </small>
                  ) : null}
                </div>
              ))
            ) : (
              <span>В плане пока нет футажей.</span>
            )}
          </div>
          <small className="project-duration">
            Общая длительность плана:{" "}
            {Number(selectedProject.duration || 0).toFixed(1)} c. Каждый блок —
            отдельный футаж; ширина соответствует его длительности.
          </small>
        </section>
      ) : null}
    </div>
  );
}

export function Outputs({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const [busy, setBusy] = useState(false);
  const chooseResultsFolder = async () => {
    if (busy) return;
    const folder = await window.newsflowDesktop?.chooseFolder();
    if (!folder) return;
    setBusy(true);
    try {
      await command("save-settings", { resultsOutputFolder: folder });
    } finally {
      setBusy(false);
    }
  };
  const exportResults = async () => {
    if (busy || !data.results.outputFolder) return;
    setBusy(true);
    try {
      await command("export-results-batch");
    } finally {
      setBusy(false);
    }
  };
  const resultsOpenTarget = data.results.lastExportFolder || data.results.outputFolder;
  return (
    <div className="nf-outputs" aria-label="Output Artifact Index">
      <section className="panel outputs-list" aria-label="Пакетные результаты">
        <div className="panel-title">
          <div>
            <b>Результаты для передачи</b>
            <small>Три согласованных TXT, выбранные обложки и готовые MP4 без изменения Publication-пакетов.</small>
          </div>
        </div>
        <div className="toolbar">
          <output aria-label="Папка Results">{data.results.outputFolder || "Папка не выбрана"}</output>
          <Button onClick={() => void chooseResultsFolder()} disabled={busy}>Выбрать папку</Button>
          <Button kind="success" onClick={() => void exportResults()} disabled={busy || !data.results.outputFolder}>
            <FolderOpen size={17} />Собрать результаты
          </Button>
          <Button onClick={() => void window.newsflowDesktop?.openPath(resultsOpenTarget)} disabled={!resultsOpenTarget}>
            <FolderOpen size={16} />Открыть папку
          </Button>
        </div>
        {data.results.lastExportFolder ? <small>Последняя выгрузка: {data.results.lastExportFolder}</small> : null}
        {data.operationResult?.kind === "results-batch" ? (
          <small>Тем: {data.operationResult.topicsTotal ?? data.operationResult.count}; MP4: {(data.operationResult.mp4Linked || 0) + (data.operationResult.mp4Copied || 0)}; обложки: {data.operationResult.coversCopied || 0}; нет MP4: {(data.operationResult.missingMp4Ordinals || []).join(", ") || "—"}; нет обложек: {(data.operationResult.missingCoverOrdinals || []).join(", ") || "—"}.</small>
        ) : null}
      </section>
    </div>
  );
}

function AllocationChannelCard({
  channel,
  command,
  onDropJob,
}: {
  channel: NewsFlowSnapshot["publication"]["allocation"]["channels"][number];
  command: Command;
  onDropJob: (jobId: string, channelId: string) => void;
}) {
  const [quota, setQuota] = useState(channel.quota);
  const [locked, setLocked] = useState(channel.quotaLocked);
  const [minMinutes, setMinMinutes] = useState(Math.round(channel.minDurationSeconds / 60));
  const [maxMinutes, setMaxMinutes] = useState(channel.maxDurationSeconds ? Math.round(channel.maxDurationSeconds / 60) : "");
  useEffect(() => {
    setQuota(channel.quota);
    setLocked(channel.quotaLocked);
    setMinMinutes(Math.round(channel.minDurationSeconds / 60));
    setMaxMinutes(channel.maxDurationSeconds ? Math.round(channel.maxDurationSeconds / 60) : "");
  }, [channel.channelId, channel.maxDurationSeconds, channel.minDurationSeconds, channel.quota, channel.quotaLocked]);
  const mode = channel.monetized ? "монетизация" : channel.growthSignal ? "рост" : "новый";
  const save = () =>
    void command("update-channel-allocation", {
      channelId: channel.channelId,
      quota: Math.max(0, quota),
      quotaLocked: locked,
      minDurationSeconds: Math.max(0, minMinutes) * 60,
      maxDurationSeconds: maxMinutes === "" ? 0 : Math.max(0, Number(maxMinutes)) * 60,
    });
  return (
    <article
      className="allocation-channel-card"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        const jobId = event.dataTransfer.getData("application/x-newsflow-publication-job");
        if (jobId) onDropJob(jobId, channel.channelId);
      }}
    >
      <div className="allocation-channel">
        <span className="allocation-avatar">
          {channel.thumbnailUrl ? <img src={channel.thumbnailUrl} alt="" width={38} height={38} loading="lazy" /> : "▶"}
        </span>
        <span>
          <b>{channel.name || channel.channelId}</b>
          <small>{channel.subscribers || "—"} подписч. · режим: {mode}</small>
        </span>
      </div>
      <span className="allocation-progress">{channel.assignedJobIds.length} из {quota} распределено</span>
      <label>
        Роликов на канал
        <input name={`channel-${channel.channelId}-quota`} autoComplete="off" type="number" min="0" value={quota} onChange={(event) => setQuota(Number(event.target.value) || 0)} />
      </label>
      <label className="check-row">
        <input type="checkbox" checked={locked} onChange={(event) => setLocked(event.target.checked)} />
        Зафиксировать вручную
      </label>
      <label>
        Длина ролика: от, мин
        <input name={`channel-${channel.channelId}-minimum-minutes`} autoComplete="off" type="number" min="0" value={minMinutes} onChange={(event) => setMinMinutes(Number(event.target.value) || 0)} />
      </label>
      <label>
        Длина ролика: до, мин
        <input name={`channel-${channel.channelId}-maximum-minutes`} autoComplete="off" type="number" min="0" value={maxMinutes} placeholder="без ограничения…" onChange={(event) => setMaxMinutes(event.target.value === "" ? "" : Number(event.target.value) || 0)} />
      </label>
      <Button onClick={save}><Check size={14} />Применить изменения</Button>
      <small>Рекомендация: {channel.recommendedQuota}; ручная квота имеет приоритет.</small>
    </article>
  );
}

type PublicationV2Preview = { assignments: Array<{ productionItemId: string; channelId: string; source: string; locked: boolean; reason: string; publishAt?: string; scheduleWarning?: string }>; channelUsage: Record<string, number> };
type PublicationV2ChannelRule = { channelId: string; enabled: boolean; quota: number; privacy: "private" | "unlisted" | "public"; publishMode: "schedule" | "publish_now"; timezone: string; firstPublishAt: string; intervalMinutes: number };

function PublicationDashboard({ data, command }: { data: NewsFlowSnapshot; command: Command }) {
  const v2 = data.publication.v2;
  const [preview, setPreview] = useState<PublicationV2Preview | null>(null);
  const [receipt, setReceipt] = useState<{ title?: string; finalStatus?: string; youtubeVideoUrl?: string; stages?: Record<string, string> } | null>(null);
  const [parallelUploads, setParallelUploads] = useState(v2?.uploadConcurrency || data.publication.uploadConcurrency || 1);
  const initialRules = useMemo(() => Object.fromEntries(data.channels.map((channel, index) => {
    const channelId = channel.id || channel.channel || channel.name || `channel-${index}`;
    const saved = v2?.channelRules[channelId] || {};
    return [channelId, { channelId, enabled: saved.enabled !== false, quota: Math.max(0, Number(saved.quota) || 0), privacy: ["private", "unlisted", "public"].includes(String(saved.privacy)) ? String(saved.privacy) as PublicationV2ChannelRule["privacy"] : "private", publishMode: saved.publishMode === "schedule" ? "schedule" : "publish_now", timezone: String(saved.timezone || "Europe/Minsk"), firstPublishAt: String(saved.firstPublishAt || ""), intervalMinutes: Math.max(1, Number(saved.intervalMinutes) || 180) } satisfies PublicationV2ChannelRule];
  })), [data.channels, v2?.channelRules]);
  const [rules, setRules] = useState<Record<string, PublicationV2ChannelRule>>(initialRules);
  useEffect(() => setParallelUploads(v2?.uploadConcurrency || data.publication.uploadConcurrency || 1), [v2?.uploadConcurrency, data.publication.uploadConcurrency]);
  useEffect(() => setRules(initialRules), [initialRules]);
  const channelName = (channelId: string) => data.channels.find((channel, index) => (channel.id || channel.channel || channel.name || `channel-${index}`) === channelId)?.name || channelId || "Не назначен";
  const prepare = () => void command("migrate-publication-v2");
  const createPreview = async () => {
    const result = await command("preview-publication-v2-distribution");
    setPreview((result as NewsFlowSnapshot & { publicationPreview?: PublicationV2Preview } | undefined)?.publicationPreview || null);
  };
  const confirm = () => preview && void command("confirm-publication-v2-distribution", { assignments: preview.assignments.filter((row) => row.channelId) });
  const retry = (snapshotId: string, stage: string) => void command("retry-publication-v2-stage", { snapshotId, stage });
  const startSafeUploads = () => {
    const snapshotIds = queue.filter((row) => !row.youtubeVideoId && !row.active && ["READY", "WAITING", "RETRYING"].includes(row.status)).map((row) => row.snapshotId);
    if (snapshotIds.length) void command("upload-publication-v2-snapshots", { snapshotIds });
  };
  const reconcileYoutube = () => {
    const snapshotIds = queue.filter((row) => Boolean(row.youtubeVideoId)).map((row) => row.snapshotId);
    if (snapshotIds.length) void command("reconcile-publication-v2-youtube", { snapshotIds });
  };
  const showReceipt = async (snapshotId: string) => {
    const result = await command("publication-v2-receipt", { snapshotId });
    setReceipt((result as NewsFlowSnapshot & { publicationReceipt?: typeof receipt } | undefined)?.publicationReceipt || null);
  };
  const updateRule = (channelId: string, patch: Partial<PublicationV2ChannelRule>) => setRules((current) => ({ ...current, [channelId]: { ...current[channelId], ...patch } }));
  const saveRules = () => void command("save-publication-v2-rules", { rules });
  const queue = v2?.queue || [];
  const items = v2 ? Object.values(v2.items) : [];
  return <div className="publication-modern">
    <section className="publication-hero panel">
      <div><span className="eyebrow">PUBLICATION V2</span><h2>Безопасная очередь публикации</h2><p>Ролик сначала проходит проверку и распределение. MP4 отправляется на YouTube только после явного подтверждения. Уже известный YouTube ID навсегда блокирует обычную повторную загрузку.</p></div>
      <div className="publication-kpis"><b>{items.length}<small>роликов в реестре</small></b><b>{queue.length}<small>snapshots</small></b><b>{queue.filter((row) => row.youtubeVideoId).length}<small>уже на YouTube</small></b></div>
    </section>
    <section className="panel publication-next-step">
      <div><b>Реестр готовых роликов</b><small>Миграция добавляет V2-записи поверх старой очереди: legacy-данные, MP3, MP4 и каналы не удаляются.</small></div>
      <Button kind="primary" onClick={prepare}><RefreshCw size={16}/>Подготовить Publication V2</Button>
    </section>
    <section className="panel publication-bulk-panel">
      <div className="panel-title"><div><b>Ролики и готовность</b><small>Отсутствующий файл показывается как состояние для восстановления, а не удаляется автоматически.</small></div><span className="status">Готово: {items.filter((item) => item.readiness?.state === "VIDEO_READY").length}</span></div>
      {items.length ? <div className="publication-simple-list">{items.map((item) => <article key={item.productionItemId}><span><b>{item.metadata?.title || item.productionItemId}</b><small>{item.readiness?.state === "VIDEO_READY" ? "✓ MP4 найден" : "! MP4 не найден — можно восстановить связь"}</small></span><small>{item.artifacts?.video?.path || "Путь MP4 не сохранён"}</small></article>)}</div> : <Empty title="Реестр ещё не подготовлен" text="Нажмите «Подготовить Publication V2». Это создаст только новые записи V2 и не начнёт загрузку."/>}
    </section>
    <section className="panel publication-schedule-simple">
      <div className="panel-title"><div><b>Распределение и расписание</b><small>Автораспределение является только preview. Ручные и locked назначения не меняются.</small></div><div className="toolbar"><Button onClick={items.length ? createPreview : undefined}><WandSparkles size={16}/>Построить preview</Button><Button kind="success" onClick={preview?.assignments.some((row) => row.channelId) ? confirm : undefined}><Check size={16}/>Подтвердить назначения</Button></div></div>
      {preview ? <div className="publication-simple-list">{preview.assignments.map((row) => <article key={row.productionItemId}><span><b>{v2?.items[row.productionItemId]?.metadata?.title || row.productionItemId}</b><small>{row.locked ? "Ручное locked-назначение" : row.source === "auto" ? "Предложено автоматически" : row.reason}</small></span><b>{channelName(row.channelId)}</b><small>{row.publishAt ? `Выход: ${row.publishAt}` : row.scheduleWarning || "Время не требуется"}</small></article>)}</div> : <small>Preview ещё не построен. Он не создаёт snapshots и не запускает загрузку.</small>}
    </section>
    <section className="panel publication-bulk-panel"><div className="panel-title"><div><b>Правила каналов</b><small>Квота отвечает на количество роликов, расписание — на время. Настройки каждого канала независимы.</small></div><Button onClick={Object.keys(rules).length ? saveRules : undefined}><Check size={16}/>Сохранить правила</Button></div>{Object.values(rules).length ? <div className="publication-simple-list">{Object.values(rules).map((rule) => <article key={rule.channelId}><span><b>{channelName(rule.channelId)}</b><small>{data.channels.find((channel, index) => (channel.id || channel.channel || channel.name || `channel-${index}`) === rule.channelId)?.oauthConnected ? "OAuth подключён" : "OAuth потребуется перед загрузкой"}</small></span><label>Квота<input type="number" min="0" value={rule.quota} onChange={(event) => updateRule(rule.channelId, { quota: Math.max(0, Number(event.target.value) || 0) })}/></label><label>Режим<select value={rule.publishMode} onChange={(event) => updateRule(rule.channelId, { publishMode: event.target.value as PublicationV2ChannelRule["publishMode"], privacy: event.target.value === "schedule" ? "private" : rule.privacy })}><option value="schedule">По расписанию</option><option value="publish_now">Сразу после загрузки</option></select></label><label>Privacy<select value={rule.privacy} disabled={rule.publishMode === "schedule"} onChange={(event) => updateRule(rule.channelId, { privacy: event.target.value as PublicationV2ChannelRule["privacy"] })}><option value="private">private</option><option value="unlisted">unlisted</option><option value="public">public</option></select></label><label>Первый выход<input type="datetime-local" value={rule.firstPublishAt ? rule.firstPublishAt.slice(0, 16) : ""} onChange={(event) => updateRule(rule.channelId, { firstPublishAt: event.target.value ? `${event.target.value}:00` : "" })}/></label><label>Часовой пояс<input value={rule.timezone} onChange={(event) => updateRule(rule.channelId, { timezone: event.target.value })}/></label><label>Интервал, мин<input type="number" min="1" value={rule.intervalMinutes} onChange={(event) => updateRule(rule.channelId, { intervalMinutes: Math.max(1, Number(event.target.value) || 1) })}/></label><label className="check-row"><input type="checkbox" checked={rule.enabled} onChange={(event) => updateRule(rule.channelId, { enabled: event.target.checked })}/>Включён</label></article>)}</div> : <Empty title="Каналы не подключены" text="Подключённые каналы не изменяются. Добавьте или восстановите OAuth в разделе каналов."/>}</section>
    <section className="panel publication-final-actions"><div><b>Очередь загрузок</b><small>Активные передачи ограничены настройкой. Обработка YouTube после передачи не занимает слот загрузки.</small></div><div className="toolbar"><label className="parallel-upload-control">Одновременных загрузок<input type="number" min="1" step="1" value={parallelUploads} onChange={(event) => setParallelUploads(Math.max(1, Number(event.target.value) || 1))} onBlur={() => void command("save-publication-settings", { uploadConcurrency: parallelUploads })}/></label><Button kind="success" onClick={queue.some((row) => !row.youtubeVideoId && !row.active && ["READY", "WAITING", "RETRYING"].includes(row.status)) && !v2?.paused ? startSafeUploads : undefined}><Upload size={16}/>Запустить безопасные</Button><Button onClick={queue.some((row) => Boolean(row.youtubeVideoId)) ? reconcileYoutube : undefined}><RefreshCw size={16}/>Проверить YouTube</Button><Button onClick={() => void command("set-publication-v2-paused", { paused: !v2?.paused })}>{v2?.paused ? <><Play size={16}/>Продолжить очередь</> : <><Pause size={16}/>Приостановить очередь</>}</Button><span className="status">{v2?.paused ? "Пауза: новые задачи не стартуют" : "Очередь принимает новые задачи"}</span></div></section>
    <section className="panel publication-bulk-panel"><div className="panel-title"><div><b>Статусы и поэтапные повторы</b><small>Ошибка обложки, карточек или поста не повторяет загрузку MP4. Cancel после YouTube ID не удаляет ролик с YouTube.</small></div><span className="status">Активно: {queue.filter((row) => row.active).length} · в очереди: {queue.filter((row) => !row.active && !row.youtubeVideoId).length}</span></div>{queue.length ? <div className="publication-simple-list">{queue.map((row) => { const failedStage = Object.entries(row.steps).find(([, stage]) => ["FAILED", "AUTH_REQUIRED", "QUOTA_BLOCKED", "USER_ACTION_REQUIRED"].includes(String(stage.status))); const thumbnailPending = Boolean(row.youtubeVideoId) && row.steps.THUMBNAIL?.status !== "SUCCESS"; return <article key={row.snapshotId}><span><b>{row.title || row.productionItemId}</b><small>{channelName(row.channelId)} · {row.status} · этап: {row.currentStage} · {row.completion.completed}/{row.completion.total}</small></span><span>{row.youtubeVideoUrl ? <a href={row.youtubeVideoUrl} target="_blank" rel="noreferrer">YouTube ID: {row.youtubeVideoId}</a> : "MP4 ещё не отправлен"}</span><div className="toolbar"><Button onClick={() => void showReceipt(row.snapshotId)}>Receipt</Button><Button onClick={thumbnailPending ? () => void command("run-publication-v2-thumbnails", { snapshotIds: [row.snapshotId] }) : undefined}>{thumbnailPending ? "Поставить обложку" : "Обложка подтверждена"}</Button><Button onClick={failedStage ? () => retry(row.snapshotId, failedStage[0]) : undefined}>{failedStage ? `Повторить: ${failedStage[0]}` : "Нет этапа для повтора"}</Button><Button kind="danger" onClick={() => void command("cancel-publication-v2-execution", { snapshotId: row.snapshotId })}>Отменить</Button></div></article>;})}</div> : <Empty title="Подтверждённых публикаций пока нет" text="Сначала подтвердите preview. Это единственный шаг, который создаёт immutable snapshot."/>}</section>
    {receipt ? <section className="panel"><div className="panel-title"><div><b>Receipt: {receipt.title}</b><small>Итог: {receipt.finalStatus}</small></div>{receipt.youtubeVideoUrl ? <a href={receipt.youtubeVideoUrl} target="_blank" rel="noreferrer">Открыть YouTube</a> : null}</div><div className="publication-simple-list">{Object.entries(receipt.stages || {}).map(([stage, status]) => <article key={stage}><b>{stage}</b><span>{status}</span></article>)}</div></section> : null}
  </div>;
}

function LegacyPublicationDashboardSimple({ data, command }: { data: NewsFlowSnapshot; command: Command }) {
  const publication = data.publication;
  const [selected, setSelected] = useState<string[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [parallelUploads, setParallelUploads] = useState(publication.uploadConcurrency || 1);
  const [when, setWhen] = useState(() => new Date(Date.now() + 60 * 60 * 1000).toISOString().slice(0, 16));
  const [interval, setIntervalMinutes] = useState(180);
  const [presetName, setPresetName] = useState("");
  const channelOptions = data.channels.map((channel, index) => ({
    id: channel.id || channel.channel || channel.name || `channel-${index}`,
    name: channel.name || `Канал ${index + 1}`,
    monetized: Boolean(channel.monetaryAccess),
  }));
  const selectedJobs = publication.jobs.filter((job) => selected.includes(job.id));
  useEffect(() => setParallelUploads(publication.uploadConcurrency || 1), [publication.uploadConcurrency]);
  const toggle = (id: string) => setSelected((items) => items.includes(id) ? items.filter((item) => item !== id) : [...items, id]);
  const toggleAll = () => setSelected(selected.length === publication.jobs.length ? [] : publication.jobs.map((job) => job.id));
  const schedule = () => {
    if (!selected.length || !channels.length || !when) return;
    void command("schedule-publication-jobs", {
      jobIds: selected, channelIds: channels, firstCycleAt: new Date(`${when}:00`).toISOString(),
      intervalMinutes: interval, slotMinutes: 15, batchCapacity: 1, distribution: "first-then-batches",
    });
  };
  const saveSchedulePreset = () => {
    if (!presetName.trim() || !channels.length) return;
    void command("save-publication-preset", {
      name: presetName.trim(), channelIds: channels, intervalMinutes: interval,
      distribution: "first-then-batches", slotMinutes: 15, batchCapacity: 1,
    });
    setPresetName("");
  };
  const applySchedulePreset = (name: string) => {
    const preset = publication.presets.find((item) => item.name === name);
    if (!preset) return;
    setIntervalMinutes(Math.max(1, Number(preset.intervalMinutes) || 180));
    setChannels(Array.isArray(preset.channelIds) ? preset.channelIds.filter((item): item is string => typeof item === "string") : []);
  };
  const upload = () => selected.length && void command("upload-publication-jobs", { jobIds: selected });
  const runAutomation = () => {
    const ids = selectedJobs.filter((job) => publication.engagementTasks?.some((task) => task.jobId === job.id)).map((job) => job.id);
    if (ids.length) void command("run-youtube-engagement", { jobIds: ids });
  };
  return <div className="publication-modern">
    <section className="publication-hero panel">
      <div><span className="eyebrow">ПРОСТОЙ ПОТОК</span><h2>Ролики → время → YouTube</h2><p>Выделите ролики, выберите каналы и одно время старта. Всё остальное NewsFlow покажет до загрузки.</p></div>
      <div className="publication-kpis"><b>{publication.readyOutputs.length}<small>новых пакетов</small></b><b>{publication.jobs.filter((job) => job.status === "scheduled").length}<small>в расписании</small></b><b>{publication.jobs.filter((job) => job.status === "uploaded").length}<small>загружено</small></b></div>
    </section>
    <section className="panel publication-next-step">
      <div><b>Шаг 1. Добавьте готовые ролики</b><small>MP4, обложка, SEO-описание и теги подхватываются из результатов автоматически.</small></div>
      <Button kind="success" onClick={publication.readyOutputs.length ? () => void command("queue-ready-publication-outputs") : undefined}><Upload size={16}/>Добавить готовые ({publication.readyOutputs.length})</Button>
    </section>
    <section className="panel publication-bulk-panel">
      <div className="panel-title"><div><b>Шаг 2. Выберите ролики</b><small>Можно выбрать пачку или открыть пакет отдельного ролика.</small></div><span className="status">Выбрано: {selected.length}</span></div>
      <div className="publication-bulk-actions"><Button onClick={publication.jobs.length ? toggleAll : undefined}>{selected.length === publication.jobs.length ? "Снять выделение" : "Выбрать все"}</Button><Button onClick={selected.length ? () => setSelected([]) : undefined}>Очистить</Button></div>
      {publication.jobs.length ? <div className="publication-simple-list">{publication.jobs.map((job) => <article key={job.id} className={selected.includes(job.id) ? "selected" : ""}>
        <label><input type="checkbox" checked={selected.includes(job.id)} onChange={() => toggle(job.id)}/><span><b>{job.title}</b><small className={`publication-state state-${job.status}`}>{job.status === "uploaded" ? "✓ Загружен в YouTube — ждёт времени" : job.status === "published" ? "✓ Опубликован" : job.status === "scheduled" ? "◷ Время назначено" : job.status === "needs-title-rewrite" ? "! Нужно сократить заголовок" : job.status === "failed" ? "! Ошибка загрузки" : "Готов к назначению"}{job.videoUrl ? <> · <a href={job.videoUrl} target="_blank" rel="noreferrer">открыть ролик</a></> : null}</small></span></label>
        <span>{job.durationSeconds ? `${Math.round(job.durationSeconds / 60)} мин` : "Длительность уточняется"}</span><span>{job.channelId ? channelOptions.find((item) => item.id === job.channelId)?.name || "Канал назначен" : "Канал не назначен"}</span>
        <Button onClick={() => void window.newsflowDesktop?.openPath(job.packageFolder)}><FolderOpen size={14}/>Пакет</Button>
      </article>)}</div> : <Empty title="Очередь пока пуста" text="После завершения монтажа нажмите «Добавить готовые» — карточки появятся здесь автоматически."/>}
    </section>
    <section className="panel publication-schedule-simple">
      <div className="panel-title"><div><b>Шаг 3. Назначьте каналы и время</b><small>Для нескольких каналов сетка разложит выбранные ролики по очереди с интервалом.</small></div></div>
      <div className="publication-preset-row"><select aria-label="Пресет назначения времени" defaultValue="" onChange={(event) => applySchedulePreset(event.target.value)}><option value="">Применить пресет назначения</option>{publication.presets.map((preset) => <option key={preset.name} value={preset.name}>{preset.name}</option>)}</select><input value={presetName} onChange={(event) => setPresetName(event.target.value)} placeholder="Название пресета"/><Button onClick={presetName.trim() && channels.length ? saveSchedulePreset : undefined}><Check size={15}/>Сохранить пресет</Button><small>Пресет запоминает выбранные каналы и интервал. Дату первого выхода задавайте для конкретной пачки.</small></div>
      <div className="publication-simple-form"><label>Первый выход<input type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)}/></label><label>Интервал канала, мин<input type="number" min="1" value={interval} onChange={(event) => setIntervalMinutes(Number(event.target.value) || 1)}/></label><label>Каналы<select multiple value={channels} onChange={(event) => setChannels(Array.from(event.target.selectedOptions, (option) => option.value))}>{channelOptions.map((channel, index) => <option key={channel.id} value={channel.id}>{index + 1}. {channel.name}{channel.monetized ? " · монетизация" : ""}</option>)}</select></label><Button kind="success" onClick={selected.length && channels.length ? schedule : undefined}><Check size={16}/>Назначить время выбранным</Button></div>
    </section>
    <PublicationAllocationPanel data={data} command={command} />
    <section className="panel publication-final-actions"><div><b>Шаг 4. Загрузите и оформите</b><small>Загрузка по OAuth не зависит от открытого Chrome. После неё создадутся задания на пост, карточки и конечную заставку.</small></div><div className="toolbar"><label className="parallel-upload-control">Одновременных загрузок<input type="number" min="1" step="1" value={parallelUploads} onChange={(event) => setParallelUploads(Math.max(1, Number(event.target.value) || 1))} onBlur={() => void command("save-publication-settings", { uploadConcurrency: parallelUploads })}/></label><Button kind="primary" onClick={selected.length ? upload : undefined}><Upload size={16}/>Загрузить выбранные</Button><Button kind="success" onClick={runAutomation}><Bot size={16}/>Выполнить оформление</Button></div></section>
    <PublicationAutomationPanel data={data} command={command} />
  </div>;
}

function PublicationAutomationPanel({ data, command }: { data: NewsFlowSnapshot; command: Command }) {
  const tasks = data.publication.engagementTasks || [];
  const policies = data.publication.engagementPolicies || [];
  const connectedJobs = data.publication.jobs.filter((job) => Boolean(job.channelId));
  const policyFor = (channelId: string) => policies.find((policy) => policy.channelId === channelId) || { channelId, enabled: true, postsEnabled: true, cardsEnabled: true, endScreensEnabled: true };
  const savePolicy = (channelId: string, patch: Record<string, boolean>) => void command("save-youtube-engagement-policy", { ...policyFor(channelId), ...patch });
  const state = (value?: string) => value === "done" || value === "scheduled" || value === "published" ? "✓ готово" : value === "skipped" ? "— пропущено" : value === "failed" ? "! ошибка" : "◷ ожидает";
  return <section className="panel publication-automation-modern"><div className="panel-title"><div><span className="eyebrow">ОФОРМЛЕНИЕ РОЛИКОВ</span><h2>Шаг 5. Пост, карточки и конечная заставка</h2><small>Каждая строка относится к одному ролику. Запуск работает только для выбранного ролика и не повторяет уже завершённые шаги.</small></div></div>{connectedJobs.length ? <div className="publication-automation-jobs">{connectedJobs.map((job) => { const task = tasks.find((item) => item.jobId === job.id); return <article key={job.id}><div><b>{job.title}</b><small>{job.channelId ? data.channels.find((channel) => channel.id === job.channelId)?.name || "Канал назначен" : "Канал не назначен"}</small></div><span>Пост: {state(task?.post?.status)}</span><span>Карточки: {state(task?.cards?.status)}</span><span>Заставка: {state(task?.endScreen?.status)}</span><Button kind="success" onClick={task ? () => void command("run-youtube-engagement", { jobIds: [job.id] }) : undefined}><Bot size={14}/>{task ? "Оформить этот ролик" : "Появится после загрузки"}</Button>{task?.lastError ? <small className="automation-job-error">{task.lastError}</small> : null}</article>; })}</div> : <Empty title="Пока нет роликов с назначенным каналом" text="После назначения и загрузки здесь появится отдельное оформление для каждого ролика." />}<details className="publication-policy-details"><summary>Правила по каналам</summary><div className="automation-policy-grid">{data.channels.map((channel, index) => { const channelId = channel.id || channel.channel || channel.name || `channel-${index}`; const policy = policyFor(channelId); return <article key={channelId}><h3>{index + 1}. {channel.name || `Канал ${index + 1}`}</h3><label className="switch-row"><input type="checkbox" checked={policy.enabled !== false} onChange={(event) => savePolicy(channelId, { enabled: event.target.checked })}/>Автоматизация</label><label className="switch-row"><input type="checkbox" checked={policy.postsEnabled !== false} onChange={(event) => savePolicy(channelId, { postsEnabled: event.target.checked })}/>Пост с роликом и описанием</label><label className="switch-row"><input type="checkbox" checked={policy.cardsEnabled !== false} onChange={(event) => savePolicy(channelId, { cardsEnabled: event.target.checked })}/>Карточки на 35% и 65%</label><label className="switch-row"><input type="checkbox" checked={policy.endScreensEnabled !== false} onChange={(event) => savePolicy(channelId, { endScreensEnabled: event.target.checked })}/>Конечная заставка за 20 секунд</label></article>; })}</div></details></section>;
}

function PublicationAllocationPanel({ data, command }: { data: NewsFlowSnapshot; command: Command }) {
  const allocation = data.publication.allocation;
  const unassigned = data.publication.jobs.filter((job) => !job.channelId && ["ready", "needs-title-rewrite"].includes(job.status));
  const assign = () => void command("assign-publication-jobs", { jobIds: unassigned.map((job) => job.id), channelIds: allocation.channels.map((channel) => channel.channelId) });
  return <section className="publication-allocation-modern"><div className="panel-title"><div><span className="eyebrow">УМНОЕ РАСПРЕДЕЛЕНИЕ</span><h2>Шаг 3. Распределение роликов по каналам</h2><small>Рекомендация ничего не загружает: она только назначает ролики. Любой назначенный ролик можно сразу перенести в другой канал.</small></div><div className="toolbar"><Button onClick={() => void command("refresh-publication-allocation")}><Activity size={16}/>Обновить расчёт</Button><Button kind="success" onClick={unassigned.length && allocation.channels.length ? assign : undefined}><WandSparkles size={16}/>Распределить {unassigned.length} роликов</Button></div></div><div className="allocation-modern-counts"><span><b>{allocation.counters.ready}</b> готово</span><span><b>{allocation.counters.assigned}</b> назначено</span><span className={allocation.counters.missing ? "warning" : ""}><b>{allocation.counters.missing}</b> не хватает</span></div><div className="allocation-modern-grid">{allocation.channels.map((channel, index) => <AllocationModernChannelCard key={channel.channelId} channel={channel} number={index + 1} channels={allocation.channels} command={command} />)}</div></section>;
}

function AllocationModernChannelCard({ channel, number, channels, command }: { channel: NewsFlowSnapshot["publication"]["allocation"]["channels"][number]; number: number; channels: NewsFlowSnapshot["publication"]["allocation"]["channels"]; command: Command }) {
  const [quota, setQuota] = useState(channel.quota);
  const [minimum, setMinimum] = useState(Math.round(channel.minDurationSeconds / 60));
  const [maximum, setMaximum] = useState(channel.maxDurationSeconds ? Math.round(channel.maxDurationSeconds / 60) : "");
  useEffect(() => { setQuota(channel.quota); setMinimum(Math.round(channel.minDurationSeconds / 60)); setMaximum(channel.maxDurationSeconds ? Math.round(channel.maxDurationSeconds / 60) : ""); }, [channel.channelId, channel.maxDurationSeconds, channel.minDurationSeconds, channel.quota]);
  const assignments = channel.assignedJobs || channel.assignedJobIds.map((id) => ({ id, title: id, durationSeconds: 0 }));
  const duration = (seconds: number) => seconds > 0 ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}` : "длительность уточняется";
  const saveRules = () => void command("update-channel-allocation", { channelId: channel.channelId, quota: Math.max(0, quota), quotaLocked: true, minDurationSeconds: Math.max(0, minimum) * 60, maxDurationSeconds: maximum === "" ? 0 : Math.max(0, Number(maximum)) * 60 });
  return <article className="panel allocation-channel-modern"><div className="allocation-channel-head"><span className="allocation-avatar">{channel.thumbnailUrl ? <img src={channel.thumbnailUrl} alt="" width={42} height={42} loading="lazy" /> : "▶"}</span><div><span className="allocation-number">Канал {number}</span><h3>{channel.name || channel.channelId}</h3><small>{channel.subscribers || "—"} подписчиков · {channel.monetized ? "монетизация" : "без монетизации"}</small></div></div><p>Рекомендовано: <b>{channel.recommendedQuota}</b> · назначено: <b>{assignments.length}</b></p><div className="allocation-assigned-list"><b>Назначенные ролики</b>{assignments.length ? assignments.map((job) => <label key={job.id}><span>{job.title}<small>{duration(job.durationSeconds)}</small></span><select value={channel.channelId} aria-label={`Канал для ролика ${job.title}`} onChange={(event) => { if (event.target.value !== channel.channelId) void command("move-publication-job-channel", { jobId: job.id, channelId: event.target.value }); }}>{channels.map((option, optionIndex) => <option key={option.channelId} value={option.channelId}>{optionIndex + 1}. {option.name || option.channelId}</option>)}</select></label>) : <small>Пока нет назначенных роликов.</small>}</div><details><summary>Изменить правила канала</summary><div className="allocation-rule-editor"><label>Роликов на канал<input type="number" min="0" value={quota} onChange={(event) => setQuota(Number(event.target.value) || 0)} /></label><label>От, минут<input type="number" min="0" value={minimum} onChange={(event) => setMinimum(Number(event.target.value) || 0)} /></label><label>До, минут<input type="number" min="0" value={maximum} placeholder="без ограничения" onChange={(event) => setMaximum(event.target.value === "" ? "" : Number(event.target.value) || 0)} /></label><Button onClick={saveRules}><Check size={14}/>Сохранить правила</Button></div></details></article>;
}

function PublicationAllocationDashboard({ data, command }: { data: NewsFlowSnapshot; command: Command }) {
  return <div className="publication-modern"><PublicationAllocationPanel data={data} command={command} /></div>;
}

function YouTubeAutomationDashboard({ data, command }: { data: NewsFlowSnapshot; command: Command }) {
  const [selected, setSelected] = useState<string[]>([]);
  const tasks = data.publication.engagementTasks || [];
  const policies = data.publication.engagementPolicies || [];
  const policyFor = (id: string) => policies.find((policy) => policy.channelId === id) || { channelId: id, enabled: true, postsEnabled: true, cardsEnabled: true, endScreensEnabled: true };
  const save = (channelId: string, patch: Record<string, boolean>) => void command("save-youtube-engagement-policy", { ...policyFor(channelId), ...patch });
  const run = () => { const ids = selected.length ? selected : tasks.map((task) => task.jobId); if (ids.length) void command("run-youtube-engagement", { jobIds: ids }); };
  const legacyUploaded = data.publication.jobs.filter((job) => ["uploaded", "published"].includes(job.status) && !tasks.some((task) => task.jobId === job.id));
  return <div className="publication-modern"><section className="publication-hero panel"><div><span className="eyebrow">АВТОПРАВИЛА YOUTUBE</span><h2>Оформление в Chrome-профиле канала</h2><p>Каждый канал использует собственный постоянный Chrome-профиль. OAuth-токен и cookies не смешиваются между каналами.</p></div><div className="publication-kpis"><b>{tasks.length}<small>заданий</small></b><b>{tasks.filter((task) => task.lastError).length}<small>требуют повтора</small></b><b>{tasks.filter((task) => task.post?.status === "scheduled").length}<small>постов в плане</small></b></div></section><section className="automation-policy-grid">{data.channels.map((channel, index) => { const id = channel.id || channel.channel || channel.name || `channel-${index}`; const p = policyFor(id); return <article key={id} className="panel"><h3>{channel.name || `Канал ${index + 1}`}</h3><label className="switch-row"><input type="checkbox" checked={p.enabled !== false} onChange={(event) => save(id, { enabled: event.target.checked })}/>Автоматизация канала</label><label className="switch-row"><input type="checkbox" checked={p.postsEnabled !== false} onChange={(event) => save(id, { postsEnabled: event.target.checked })}/>Пост с роликом и описанием</label><label className="switch-row"><input type="checkbox" checked={p.cardsEnabled !== false} onChange={(event) => save(id, { cardsEnabled: event.target.checked })}/>Карточки на 35% и 65%</label><label className="switch-row"><input type="checkbox" checked={p.endScreensEnabled !== false} onChange={(event) => save(id, { endScreensEnabled: event.target.checked })}/>Конечная заставка за 20 секунд</label></article>; })}</section><section className="panel"><div className="panel-title"><div><b>Очередь Studio</b><small>Отметьте задачи и запустите. Уже завершённые шаги не повторяются.</small></div><div className="toolbar"><Button onClick={legacyUploaded.length ? () => void command("queue-existing-youtube-engagement", { jobIds: legacyUploaded.map((job) => job.id) }) : undefined}>Подготовить уже загруженные ({legacyUploaded.length})</Button><Button kind="success" onClick={tasks.length ? run : undefined}><Play size={16}/>Запустить {selected.length ? "выбранные" : "все ожидающие"}</Button></div></div>{tasks.length ? <div className="automation-task-list">{tasks.map((task) => <label key={task.jobId}><input type="checkbox" checked={selected.includes(task.jobId)} onChange={() => setSelected((items) => items.includes(task.jobId) ? items.filter((item) => item !== task.jobId) : [...items, task.jobId])}/><span><b>{data.publication.jobs.find((job) => job.id === task.jobId)?.title || task.jobId}</b><small>Пост: {task.post?.status || "—"} · карточки: {task.cards?.status || "—"} · заставка: {task.endScreen?.status || "—"}{task.lastError ? ` · ${task.lastError}` : ""}</small></span></label>)}</div> : <Empty title="Заданий пока нет" text="Они появятся сразу после успешной загрузки ролика."/>}</section></div>;
}

function LegacyPublicationDashboard({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const publication = data.publication;
  const [uploadConcurrency, setUploadConcurrency] = useState(
    publication.uploadConcurrency,
  );
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([]);
  const [selectedChannelIds, setSelectedChannelIds] = useState<string[]>([]);
  const [intervalMinutes, setIntervalMinutes] = useState(180);
  const [slotMinutes, setSlotMinutes] = useState(15);
  const [batchCapacity, setBatchCapacity] = useState(1);
  const [distribution, setDistribution] = useState<"first-then-batches" | "always-batches" | "stretch-cycle">("first-then-batches");
  const [presetName, setPresetName] = useState("");
  const [allocationPresetName, setAllocationPresetName] = useState("");
  const [movingJobId, setMovingJobId] = useState("");
  const [movingJobTime, setMovingJobTime] = useState("");
  const [movingJobChannel, setMovingJobChannel] = useState("");
  const [editingTitleJobId, setEditingTitleJobId] = useState("");
  const [editedTitle, setEditedTitle] = useState("");
  const [firstCycleLocal, setFirstCycleLocal] = useState(() =>
    new Date(Date.now() + 60 * 60 * 1000).toISOString().slice(0, 16),
  );
  const awaitingTitle = publication.jobs.filter(
    (job) => job.status === "needs-title-rewrite",
  ).length;
  const scheduled = publication.jobs.filter(
    (job) => job.status === "scheduled",
  ).length;
  const uploaded = publication.jobs.filter(
    (job) => job.status === "uploaded",
  ).length;
  const addReady = () => void command("queue-ready-publication-outputs");
  const uploadSelected = () => {
    if (!selectedJobIds.length) return;
    void command("upload-publication-jobs", { jobIds: selectedJobIds });
  };
  useEffect(
    () => setUploadConcurrency(publication.uploadConcurrency),
    [publication.uploadConcurrency],
  );
  const saveUploadConcurrency = () => {
    if (!Number.isInteger(uploadConcurrency) || uploadConcurrency < 1) return;
    void command("save-publication-settings", { uploadConcurrency });
  };
  const channelOptions = data.channels.map((channel, index) => ({
    index,
    id: channel.id || channel.channel || channel.name || `channel-${index}`,
    name: channel.name || `Канал ${index + 1}`,
    thumbnailUrl: channel.thumbnailUrl || "",
    subscribers: channel.subscribers || "—",
  }));
  const channelNames = new Map(
    channelOptions.map((channel) => [channel.id, channel.name]),
  );
  const channelAvatars = new Map(
    channelOptions.map((channel) => [channel.id, channel.thumbnailUrl]),
  );
  const channelSubscribers = new Map(
    channelOptions.map((channel) => [channel.id, channel.subscribers]),
  );
  const toggleJob = (id: string) =>
    setSelectedJobIds((current) =>
      current.includes(id)
        ? current.filter((value) => value !== id)
        : [...current, id],
    );
  const assignGrid = () => {
    if (
      !selectedJobIds.length ||
      !selectedChannelIds.length ||
      intervalMinutes < 1 ||
      slotMinutes < 1 ||
      batchCapacity < 1 ||
      !firstCycleLocal
    )
      return;
    void command("schedule-publication-jobs", {
      jobIds: selectedJobIds,
      channelIds: selectedChannelIds,
      firstCycleAt: new Date(`${firstCycleLocal}:00`).toISOString(),
      intervalMinutes,
      distribution,
      slotMinutes,
      batchCapacity,
    });
  };
  const savePreset = () => {
    if (!presetName.trim() || !selectedChannelIds.length || intervalMinutes < 1)
      return;
    void command("save-publication-preset", {
      name: presetName.trim(),
      channelIds: selectedChannelIds,
      intervalMinutes,
      distribution,
      slotMinutes,
      batchCapacity,
    });
  };
  const openMoveOne = (
    job: NewsFlowSnapshot["publication"]["jobs"][number],
  ) => {
    setMovingJobId(job.id);
    setMovingJobTime(
      job.publishAt ? new Date(job.publishAt).toISOString().slice(0, 16) : "",
    );
    setMovingJobChannel(job.channelId || "");
  };
  const saveMoveOne = async () => {
    const date = new Date(movingJobTime);
    if (!movingJobId) return;
    if (movingJobChannel)
      await command("move-publication-job-channel", {
        jobId: movingJobId,
        channelId: movingJobChannel,
      });
    if (!Number.isNaN(date.getTime()))
      await command("move-publication-job", {
        jobId: movingJobId,
        publishAt: date.toISOString(),
      });
    setMovingJobId("");
    setMovingJobTime("");
    setMovingJobChannel("");
  };
  const openTitleEdit = (
    job: NewsFlowSnapshot["publication"]["jobs"][number],
  ) => {
    setEditingTitleJobId(job.id);
    setEditedTitle(
      job.seoTitle && job.seoTitle.length <= 100 ? job.seoTitle : job.title,
    );
  };
  const saveTitleEdit = async () => {
    if (!editingTitleJobId || !editedTitle.trim()) return;
    const result = await command("rewrite-publication-title", {
      jobId: editingTitleJobId,
      title: editedTitle,
    });
    if (result) {
      setEditingTitleJobId("");
      setEditedTitle("");
    }
  };
  const copyPost = async (text: string) => {
    if (text) await navigator.clipboard.writeText(text);
  };
  const openPostStudio = (
    job: NewsFlowSnapshot["publication"]["jobs"][number],
  ) => {
    const channel = channelOptions.find((item) => item.id === job.channelId);
    if (channel)
      void command("open-analytics-channel", { index: channel.index });
  };
  const statusLabel: Record<string, string> = {
    ready: "Готово к назначению",
    scheduled: "Запланировано",
    uploaded: "Загружен, ждёт времени",
    "needs-title-rewrite": "Нужен короткий заголовок",
    uploading: "Загружается",
    processing: "Обрабатывается",
    published: "Опубликовано",
    failed: "Ошибка",
  };
  const allocation = publication.allocation;
  const formatDuration = (seconds?: number | null) =>
    seconds && seconds > 0
      ? `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")}`
      : "не определена";
  const assignCompatible = () => {
    const jobIds = selectedJobIds.length
      ? selectedJobIds
      : publication.jobs
          .filter(
            (job) =>
              !job.channelId &&
              (job.status === "ready" || job.status === "needs-title-rewrite"),
          )
          .map((job) => job.id);
    const channelIds = selectedChannelIds.length
      ? selectedChannelIds
      : allocation.channels.map((channel) => channel.channelId);
    if (jobIds.length && channelIds.length)
      void command("assign-publication-jobs", { jobIds, channelIds });
  };
  const saveAllocationPreset = async () => {
    if (!allocationPresetName.trim()) return;
    const result = await command("save-publication-allocation-preset", {
      name: allocationPresetName.trim(),
    });
    if (result) setAllocationPresetName("");
  };
  const dropJobOnChannel = (jobId: string, channelId: string) =>
    void command("move-publication-job-channel", { jobId, channelId });
  return (
    <>
      <section className="publication-command panel">
        <div className="publication-command-copy">
          <span className="eyebrow">ЦЕНТР ПУБЛИКАЦИИ</span>
          <h2>1. План роликов: очередь держит выпуск под контролем</h2>
          <p>
            Готовые пакеты NewsFlow передаются сюда вместе с MP4, обложкой,
            сценарным заголовком, SEO и тегами. Без выбранного времени ролик
            остаётся приватным черновиком.
          </p>
        </div>
        <div className="publication-counts">
          <div>
            <b>{publication.readyOutputs.length}</b>
            <small>новых пакетов</small>
          </div>
          <div>
            <b>{scheduled}</b>
            <small>по расписанию</small>
          </div>
          <div>
            <b>{uploaded}</b>
            <small>загружено</small>
          </div>
          <div className={awaitingTitle ? "warning" : ""}>
            <b>{awaitingTitle}</b>
            <small>нужен заголовок</small>
          </div>
        </div>
      </section>
      <section className="panel publication-allocation">
        <div className="panel-title">
          <div>
            <b>2. Распределение по каналам</b>
            <small>
              Считает, сколько роликов нужно по каналам. Рекомендации не меняют
              лимиты и назначения, пока вы их не примените.
            </small>
          </div>
          <div className="toolbar compact">
            <Button
              onClick={() => void command("refresh-publication-allocation")}
            >
              <Activity size={15} />
              Обновить рекомендации
            </Button>
            <Button
              onClick={() => void command("apply-publication-recommendations")}
            >
              <Check size={15} />
              Применить рекомендации
            </Button>
            <input
              value={allocationPresetName}
              onChange={(event) => setAllocationPresetName(event.target.value)}
              placeholder="Название пресета"
            />
            <Button
              onClick={
                allocationPresetName.trim()
                  ? () => void saveAllocationPreset()
                  : undefined
              }
            >
              <Check size={15} />
              Сохранить пресет
            </Button>
            <Button
              kind="success"
              onClick={
                allocation.channels.length ? assignCompatible : undefined
              }
            >
              <WandSparkles size={15} />
              Распределить совместимые
            </Button>
          </div>
        </div>
        <div className="publication-allocation-counts">
          <div>
            <small>Нужно</small>
            <b>{allocation.counters.required}</b>
          </div>
          <div>
            <small>Готово</small>
            <b>{allocation.counters.ready}</b>
          </div>
          <div>
            <small>Назначено</small>
            <b>{allocation.counters.assigned} из {allocation.counters.required}</b>
          </div>
          <div className={allocation.counters.missing ? "warning" : ""}>
            <small>Не хватает</small>
            <b>{allocation.counters.missing}</b>
          </div>
          <div>
            <small>Резерв</small>
            <b>{allocation.counters.reserve}</b>
          </div>
        </div>
        {allocation.channels.length ? (
          <div className="publication-allocation-list">
            {allocation.channels.map((channel) => (
              <AllocationChannelCard
                key={channel.channelId}
                channel={channel}
                command={command}
                onDropJob={dropJobOnChannel}
              />
            ))}
          </div>
        ) : (
          <Empty
            title="Добавьте каналы"
            text="После OAuth-подключения здесь появятся роли и лимиты каналов."
          />
        )}
        <div className="publication-allocation-reserve">
          <b>Резерв роликов</b>
          {publication.jobs
            .filter(
              (job) =>
                !job.channelId &&
                (job.status === "ready" ||
                  job.status === "needs-title-rewrite"),
            )
            .map((job) => (
              <span key={job.id}>
                {job.thumbnailPath ? (
                  <img src={`file://${job.thumbnailPath}`} alt="" />
                ) : null}
                <strong>{job.title}</strong>
                <small>
                  {formatDuration(job.durationSeconds)}
                  {allocation.missingDurationJobIds.includes(job.id)
                    ? " · нужно определить длительность"
                    : ""}
                </small>
              </span>
            ))}
        </div>
      </section>
      <div className="toolbar publication-toolbar">
        <Button
          kind="success"
          onClick={publication.readyOutputs.length ? addReady : undefined}
        >
          <Upload size={17} />
          Добавить {publication.readyOutputs.length || ""} готовых в очередь
        </Button>
        <Button
          kind="primary"
          onClick={selectedJobIds.length ? uploadSelected : undefined}
        >
          <Upload size={17} />
          Загрузить выбранные ({selectedJobIds.length})
        </Button>
        <Button
          onClick={() =>
            void window.newsflowDesktop?.openPath(
              data.montageSettings.outputFolder,
            )
          }
        >
          <FolderOpen size={17} />
          Открыть результаты
        </Button>
        <label className="publication-concurrency">
          Одновременных загрузок
          <input
            type="number"
            min="1"
            step="1"
            value={uploadConcurrency}
            onChange={(event) =>
              setUploadConcurrency(Number(event.target.value) || 0)
            }
            onBlur={saveUploadConcurrency}
          />
          <small>Без скрытого лимита NewsFlow</small>
        </label>
      </div>
      <section className="panel publication-grid-settings">
        <div className="panel-title">
          <div>
            <b>3. Календарь публикаций</b>
            <small>
              Сначала задайте старт, повтор одного канала и 15-минутные слоты.
              Ниже будет виден итог до запуска загрузки.
            </small>
          </div>
          <span className="status">
            Выбрано: {selectedJobIds.length} роликов
          </span>
        </div>
        <div className="publication-grid-controls">
          <label>
            Первый выход
            <input
              type="datetime-local"
              value={firstCycleLocal}
              onChange={(event) => setFirstCycleLocal(event.target.value)}
            />
          </label>
          <label>
            Повтор одного канала, минут
            <input
              type="number"
              min="1"
              step="1"
              value={intervalMinutes}
              onChange={(event) =>
                setIntervalMinutes(Number(event.target.value) || 0)
              }
            />
          </label>
          <label>
            Шаг слотов, минут
            <input type="number" min="1" step="1" value={slotMinutes} onChange={(event) => setSlotMinutes(Number(event.target.value) || 0)} />
          </label>
          <label>
            Вместимость пачки
            <input type="number" min="1" step="1" value={batchCapacity} onChange={(event) => setBatchCapacity(Number(event.target.value) || 0)} />
          </label>
          <label>
            Режим сетки
            <select
              value={distribution}
              onChange={(event) =>
                setDistribution(event.target.value as "first-then-batches" | "always-batches" | "stretch-cycle")
              }
            >
              <option value="first-then-batches">Сначала по одному, затем пачки</option>
              <option value="always-batches">Всегда пачками</option>
              <option value="stretch-cycle">Растянуть цикл без повторов минут</option>
            </select>
          </label>
          <label>
            Каналы
            <select
              multiple
              value={selectedChannelIds}
              onChange={(event) =>
                setSelectedChannelIds(
                  Array.from(
                    event.target.selectedOptions,
                    (option) => option.value,
                  ),
                )
              }
            >
              {channelOptions.map((channel) => (
                <option key={channel.id} value={channel.id}>
                  {channel.name} · {channel.subscribers} подписч.
                </option>
              ))}
            </select>
          </label>
          <Button
            kind="success"
            onClick={
              selectedJobIds.length &&
              selectedChannelIds.length &&
              intervalMinutes > 0 &&
              slotMinutes > 0 &&
              batchCapacity > 0
                ? assignGrid
                : undefined
            }
          >
            <Check size={16} />
            Назначить сетку
          </Button>
        </div>
        <div className="publication-preset-row">
          <input
            value={presetName}
            onChange={(event) => setPresetName(event.target.value)}
            placeholder="Название пресета"
          />
          <Button
            onClick={
              presetName.trim() &&
              selectedChannelIds.length &&
              intervalMinutes > 0 &&
              slotMinutes > 0 &&
              batchCapacity > 0
                ? savePreset
                : undefined
            }
          >
            Сохранить пресет
          </Button>
          {publication.presets.map((preset) => (
            <Button
              key={preset.name}
              onClick={() => {
                setIntervalMinutes(Number(preset.intervalMinutes || 180));
                setSlotMinutes(Number(preset.slotMinutes || 15));
                setBatchCapacity(Number(preset.batchCapacity || 1));
                setDistribution(preset.distribution === "always-batches" || preset.distribution === "stretch-cycle" ? preset.distribution : "first-then-batches");
                setSelectedChannelIds(
                  Array.isArray(preset.channelIds)
                    ? preset.channelIds.map(String)
                    : [],
                );
              }}
            >
              {preset.name}
            </Button>
          ))}
        </div>
        {channelOptions.length ? null : (
          <small className="publication-hint">
            Сначала добавьте хотя бы один канал в «Аналитика и каналы».
          </small>
        )}
      </section>
      <section className="panel publication-timeline">
        <div className="panel-title">
          <div>
            <b>Линия эфира</b>
            <small>
              Здесь появятся ближайшие назначенные слоты. Правила времени можно
              будет применять массово, а отдельные задачи — фиксировать и
              сдвигать.
            </small>
          </div>
          <span className="status">
            {publication.presets.length
              ? `Пресетов: ${publication.presets.length}`
              : "Пресет не выбран"}
          </span>
        </div>
        {scheduled ? (
          <div className="airline">
            {publication.jobs
              .filter((job) => job.status === "scheduled")
              .slice(0, 16)
              .map((job) => (
                <div className="air-slot" key={job.id}>
                  <b>
                    {job.publishAt
                      ? new Date(job.publishAt).toLocaleString("ru-RU", {
                          day: "2-digit",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "Время не задано"}
                  </b>
                  <small className="publication-channel-line">
                    {channelAvatars.get(job.channelId || "") ? (
                      <img
                        src={channelAvatars.get(job.channelId || "")}
                        alt=""
                      />
                    ) : null}
                    <span>
                      {channelNames.get(job.channelId || "") ||
                        "Канал не выбран"}{" "}
                      · {channelSubscribers.get(job.channelId || "") || "—"}{" "}
                      подписч.
                    </span>
                  </small>
                  <small>{job.title}</small>
                </div>
              ))}
          </div>
        ) : (
          <Empty
            title="Публикации ещё не назначены"
            text="Добавьте готовые ролики в очередь, затем назначьте каналы и правила сетки."
          />
        )}
      </section>
      {movingJobId ? (
        <section className="panel publication-move-form">
          <div className="panel-title">
            <div>
              <b>Перенести публикацию</b>
              <small>
                Выберите другой канал, при необходимости измените время —
                назначение сохраняется отдельно от рекомендаций.
              </small>
            </div>
          </div>
          <div className="toolbar">
            <select
              value={movingJobChannel}
              onChange={(event) => setMovingJobChannel(event.target.value)}
            >
              <option value="">Не менять канал</option>
              {channelOptions.map((channel) => (
                <option key={channel.id} value={channel.id}>
                  {channel.name}
                </option>
              ))}
            </select>
            <input
              type="datetime-local"
              value={movingJobTime}
              onChange={(event) => setMovingJobTime(event.target.value)}
            />
            <Button
              kind="primary"
              onClick={
                movingJobChannel || movingJobTime
                  ? () => void saveMoveOne()
                  : undefined
              }
            >
              <Check size={15} />
              Сохранить перенос
            </Button>
            <Button
              onClick={() => {
                setMovingJobId("");
                setMovingJobTime("");
                setMovingJobChannel("");
              }}
            >
              Отмена
            </Button>
          </div>
        </section>
      ) : null}
      <section className="panel publication-queue">
        <div className="panel-title">
          <div>
            <b>4. Загрузка и посты</b>
            <small>
              Название сценария — это заголовок YouTube. SEO‑вариант хранится
              отдельно и не подменяет его автоматически.
            </small>
          </div>
          <span className="status">Всего: {publication.jobs.length}</span>
        </div>
        {publication.jobs.length ? (
          <div className="publication-job-list">
            {publication.jobs.map((job) => (
              <article
                key={job.id}
                className={`publication-job ${job.status === "needs-title-rewrite" ? "needs-title" : ""}`}
                draggable
                onDragStart={(event) => {
                  event.dataTransfer.setData("application/x-newsflow-publication-job", job.id);
                  event.dataTransfer.effectAllowed = "move";
                }}
              >
                <label
                  className="publication-job-select"
                  title="Добавить в массовое назначение"
                >
                  <input
                    type="checkbox"
                    checked={selectedJobIds.includes(job.id)}
                    onChange={() => toggleJob(job.id)}
                  />
                </label>
                <div className="publication-job-main">
                  <b>{job.title}</b>
                  <small>
                    {job.scriptName || "Название сценария не найдено"} ·{" "}
                    {job.title.length}/100 символов
                  </small>
                  <div className="publication-meta">
                    <span>{statusLabel[job.status] || job.status}</span>
                    <span>
                      {job.privacy === "private"
                        ? "Приватный черновик"
                        : job.privacy}
                    </span>
                    {job.channelId ? (
                      <span>
                        Канал:{" "}
                        {channelNames.get(job.channelId) || job.channelId}
                      </span>
                    ) : (
                      <span>Канал не выбран</span>
                    )}
                  </div>
                  {job.titleRewriteInstruction ? (
                    <p className="publication-warning">
                      {job.titleRewriteInstruction}
                    </p>
                  ) : null}
                  {editingTitleJobId === job.id ? (
                    <div className="publication-title-edit">
                      <input
                        maxLength={100}
                        value={editedTitle}
                        onChange={(event) => setEditedTitle(event.target.value)}
                        placeholder="Новый заголовок до 100 символов"
                      />
                      <Button
                        kind="primary"
                        onClick={
                          editedTitle.trim()
                            ? () => void saveTitleEdit()
                            : undefined
                        }
                      >
                        <Check size={14} />
                        Сохранить
                      </Button>
                      <Button
                        onClick={() => {
                          setEditingTitleJobId("");
                          setEditedTitle("");
                        }}
                      >
                        Отмена
                      </Button>
                    </div>
                  ) : job.status === "needs-title-rewrite" ? (
                    <Button kind="primary" onClick={() => openTitleEdit(job)}>
                      <Pencil size={14} />
                      Исправить заголовок
                    </Button>
                  ) : null}
                </div>
                <div className="publication-job-seo">
                  <b>SEO</b>
                  <span>{job.seoTitle || "SEO‑заголовок не добавлен"}</span>
                  <small>
                    {job.seoDescription || "SEO-описание не добавлено"}
                  </small>
                  <small>
                    {job.tags?.length
                      ? `Теги: ${job.tags.join(", ")}`
                      : "Теги не добавлены"}
                  </small>
                </div>
                <div className="publication-job-actions">
                  <small>Перетяните карточку на канал выше или используйте «Перенести / время».</small>
                  <Button onClick={() => openMoveOne(job)}>
                    <Pencil size={15} />
                    Перенести / время
                  </Button>
                  <Button
                    onClick={() =>
                      void window.newsflowDesktop?.openPath(job.packageFolder)
                    }
                  >
                    <FolderOpen size={15} />
                    Пакет
                  </Button>
                  {job.post?.status ? (
                    <>
                      <textarea
                        readOnly
                        value={job.post.text || ""}
                        aria-label={`Пост к ролику ${job.title}`}
                      />
                      <Button
                        onClick={() => void copyPost(job.post?.text || "")}
                      >
                        <Download size={15} />
                        Копировать пост
                      </Button>
                      <Button onClick={() => openPostStudio(job)}>
                        <MonitorPlay size={15} />
                        Открыть Studio
                      </Button>
                      {job.post.status === "prepared" ? (
                        <Button
                          kind="success"
                          onClick={() =>
                            void command("mark-publication-post-done", {
                              jobId: job.id,
                            })
                          }
                        >
                          <Check size={15} />
                          Пост опубликован
                        </Button>
                      ) : (
                        <small>Пост отмечен: {job.post.status}</small>
                      )}
                    </>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            title="Очередь публикаций пуста"
            text="Сначала соберите папки результатов, затем передайте готовые ролики в очередь."
          />
        )}
      </section>
    </>
  );
}

export function VoiceQueue({
  data,
  go,
  command,
  refresh,
}: {
  data: NewsFlowSnapshot;
  go: (p: Page) => void;
  command: Command;
  refresh: () => Promise<void>;
}) {
  const [selected, setSelected] = useState<number[]>([]);
  const [provider, setProvider] = useState(data.voiceProvider);
  const [outputFolder, setOutputFolder] = useState(data.voiceOutputFolder);
  const [generating, setGenerating] = useState(false);
  const [rebuildingTiming, setRebuildingTiming] = useState(false);
  const voiceGenerationLock = useRef(false);
  type VoiceQueueItem = (typeof data.voiceItems)[number] & {
    jobProvider?: string;
    resumeSafe?: boolean;
  };
  const queued: VoiceQueueItem[] = data.voiceItems.filter((item) =>
    data.scenarios.some((scenario) => scenario.index === item.index),
  );
  const montageTasksByIndex = useMemo(
    () => new Map(data.montageTasks.map((task) => [task.index, task])),
    [data.montageTasks],
  );
  const newForMontage = queued.filter(
    (item) =>
      item.path && montageTasksByIndex.get(item.index)?.status === "Новый MP3",
  );
  const resumable = queued.filter(
    (item) =>
      item.jobState === "queued" ||
      (["running", "interrupted", "retrying"].includes(item.jobState || "") &&
        item.resumeSafe === true),
  );
  const unsafeInterrupted = queued.filter(
    (item) =>
      ["running", "interrupted", "retrying"].includes(item.jobState || "") &&
      item.resumeSafe !== true,
  );
  const voiceQueueColumns = useMemo<ColumnDef<(typeof queued)[number]>[]>(
    () => [
      {
        id: "selected",
        header: "",
        cell: ({ row }) => {
          const item = row.original;
          const isSelected = selected.includes(item.index);
          return (
            <button
              className="nf-table-select"
              aria-label={`${isSelected ? "Снять выбор" : "Выбрать"}: ${item.title}`}
              onClick={(event) =>
                setSelected((current) =>
                  event.ctrlKey
                    ? current.includes(item.index)
                      ? current.filter((value) => value !== item.index)
                      : [...current, item.index]
                    : [item.index],
                )
              }
            >
              {isSelected ? "✓" : "○"}
            </button>
          );
        },
      },
      {
        id: "script",
        header: "Сценарий",
        cell: ({ row }) => {
          const item = row.original;
          return (
            <Button onClick={() => setSelected([item.index])}>
              {item.index + 1}. {item.title}
            </Button>
          );
        },
      },
      {
        id: "voice",
        header: "Профиль",
        cell: ({ row }) => row.original.voiceName || "Голос по умолчанию",
      },
      {
        id: "status",
        header: "Статус",
        cell: ({ row }) =>
          ["running", "interrupted", "retrying"].includes(
            row.original.jobState || "",
          ) && row.original.resumeSafe !== true
            ? "Автопродолжение заблокировано — требуется явная переозвучка"
            : row.original.voiceStatus || row.original.state,
      },
      {
        id: "progress",
        header: "Готовность",
        cell: ({ row }) => `${row.original.voiceProgress || 0}%`,
      },
      {
        id: "voice-map",
        header: "Тайминг",
        cell: ({ row }) => row.original.voiceMapLabel || (row.original.path ? "Тайминг устарел" : "Ожидает MP3"),
      },
      {
        id: "artifact",
        header: "MP3",
        cell: ({ row }) =>
          row.original.path
            ? row.original.path.split(/[\\/]/).pop()
            : "Ещё не готов",
      },
    ],
    [selected],
  );
  useEffect(() => {
    setProvider(data.voiceProvider);
    setOutputFolder(data.voiceOutputFolder);
  }, [data.voiceProvider, data.voiceOutputFolder]);
  useEffect(() => {
    if (!generating) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 900);
    void refresh();
    return () => window.clearInterval(timer);
  }, [generating, refresh]);
  const setVoiceProvider = (value: string) => {
    setProvider(value);
    void command("save-voice-settings", { provider: value });
  };
  const importOwnTexts = async () => {
    const items = await window.newsflowDesktop?.chooseScenarioTexts();
    if (!items?.length) return;
    const result = await command("import-manual-scenarios", { items });
    if (result) setSelected([]);
  };
  const importOwnAudio = async () => {
    const paths = await window.newsflowDesktop?.chooseAudioFiles();
    if (paths?.length)
      void command("import-voiceover-files", { paths });
  };
  const importAudioFolder = async () => {
    const root = await window.newsflowDesktop?.chooseFolder();
    if (root) void command("import-voiceover-folder", { root });
  };
  const exportOwnAudio = async () => {
    if (selected.length !== 1) return;
    const item = queued.find((value) => value.index === selected[0]);
    const path = await window.newsflowDesktop?.chooseAudioSavePath(
      `${item?.title || "Озвучка"}.mp3`,
    );
    if (path)
      await command("export-stage", {
        stage: "voice",
        scenarioIndex: selected[0],
        path,
      });
  };
  const chooseOutputFolder = async () => {
    const path = await window.newsflowDesktop?.chooseFolder();
    if (path) setOutputFolder(path);
  };
  const saveOutputFolder = () =>
    void command("save-voice-settings", { outputFolder });
  const rebuildVoiceMap = async () => {
    if (selected.length !== 1 || rebuildingTiming) return;
    const item = queued.find((value) => value.index === selected[0]);
    if (!item?.path || !item.productionItemId) return;
    setRebuildingTiming(true);
    try {
      await command("rebuild-voice-map", {
        scenarioIndex: item.index,
        productionItemId: item.productionItemId,
      });
    } finally {
      setRebuildingTiming(false);
    }
  };
  const generateVoice = async () => {
    if (!selected.length || voiceGenerationLock.current) return;
    voiceGenerationLock.current = true;
    setGenerating(true);
    try {
      await command("generate-voice", { indices: selected });
    } finally {
      voiceGenerationLock.current = false;
      setGenerating(false);
    }
  };
  const generateVoiceQueue = async () => {
    if (voiceGenerationLock.current) return;
    voiceGenerationLock.current = true;
    setGenerating(true);
    try {
      await command("generate-voice-queue", {});
    } finally {
      voiceGenerationLock.current = false;
      setGenerating(false);
    }
  };
  const restartVoice = async (indices: number[]) => {
    if (!indices.length || voiceGenerationLock.current) return;
    voiceGenerationLock.current = true;
    setGenerating(true);
    try {
      await command("generate-voice", { indices, force: true });
    } finally {
      voiceGenerationLock.current = false;
      setGenerating(false);
    }
  };
  const resumeVoice = async () => {
    if (!resumable.length || voiceGenerationLock.current) return;
    voiceGenerationLock.current = true;
    setGenerating(true);
    try {
      await command("generate-voice", {
        indices: resumable.map((item) => item.index),
        resume: true,
      });
    } finally {
      voiceGenerationLock.current = false;
      setGenerating(false);
    }
  };
  const removeVoiceResults = async () => {
    if (
      !selected.length ||
      !window.confirm(`Удалить выбранные MP3: ${selected.length}?`)
    )
      return;
    const result = await command("remove-voiceovers", { indices: selected });
    if (result) setSelected([]);
  };
  const removeScenarios = async () => {
    if (
      !selected.length ||
      !window.confirm(`Удалить сценарии и их MP3: ${selected.length}?`)
    )
      return;
    const result = await command("remove-scenarios", { indices: selected });
    if (result) setSelected([]);
  };
  const transferNewAudioToMontage = async (
    indices = newForMontage.map((item) => item.index),
  ) => {
    if (!indices.length) return;
    const result = await command("transfer-scenarios", {
      target: "montage",
      indices,
      handoffOnly: true,
      requireCompleted: true,
    });
    if (result) setSelected([]);
  };
  return (
    <div className="nf-voice nf-audio-production-console" aria-label="Audio Production Console">
      <Toolbar label="Действия очереди озвучки">
        <Button
          kind="primary"
          onClick={() => void command("open-voice-session")}
        >
          <MonitorPlay size={17} />
          Открыть Chrome / вход
        </Button>
        <Button
          kind="success"
          onClick={
            selected.length && !generating
              ? () => void generateVoice()
              : undefined
          }
        >
          <Play size={17} />
          {generating ? "Озвучка идёт…" : "Озвучить выбранные"}
        </Button>
        <Button
          kind="primary"
          disabled={generating || !queued.length}
          onClick={() => void generateVoiceQueue()}
        >
          <Play size={17} />
          {generating ? "Озвучка идёт…" : "Озвучить всё"}
        </Button>
        <Button
          onClick={
            selected.length && !generating
              ? () => void restartVoice(selected)
              : undefined
          }
        >
          <Play size={17} />
          Переозвучить выбранные
        </Button>
        <Button
          onClick={
            queued.length && !generating
              ? () => void restartVoice(queued.map((item) => item.index))
              : undefined
          }
        >
          <Play size={17} />
          Переозвучить все
        </Button>
        <Button
          kind="primary"
          onClick={resumable.length && !generating ? () => void resumeVoice() : undefined}
        >
          <Play size={17} />
          Продолжить очередь: {resumable.length}
        </Button>
        {unsafeInterrupted.length ? (
          <span className="status">
            Требуют явной переозвучки: {unsafeInterrupted.length}
          </span>
        ) : null}
        <Button
          kind="success"
          onClick={
            newForMontage.length
              ? () => void transferNewAudioToMontage()
              : undefined
          }
        >
          <MonitorPlay size={17} />В монтаж: новые {newForMontage.length}
        </Button>
        <Button
          kind={data.voiceQueuePaused ? "success" : "secondary"}
          onClick={() =>
            void command("set-voice-queue-paused", {
              paused: !data.voiceQueuePaused,
            })
          }
        >
          {data.voiceQueuePaused ? <Play size={17} /> : <Pause size={17} />}
          {data.voiceQueuePaused ? "Продолжить" : "Пауза"}
        </Button>
        <Button kind="primary" onClick={() => void importOwnTexts()}>
          <Upload size={17} />
          Загрузить свои TXT
        </Button>
        <Button onClick={() => void importOwnAudio()}>
          <Upload size={17} />
          Добавить свою озвучку
        </Button>
        <Button kind="primary" onClick={() => void importAudioFolder()}>
          <FolderOpen size={17} />
          Импортировать папку озвучек
        </Button>
        <Button onClick={() => void window.newsflowDesktop?.openPath(outputFolder)}>
          <FolderOpen size={17} />
          Показать результаты MP3
        </Button>
        <Button
          onClick={
            selected.length === 1 ? () => void exportOwnAudio() : undefined
          }
        >
          <Download size={17} />
          Скачать MP3
        </Button>
        <Button
          onClick={
            selected.length === 1 &&
            queued.some((item) => item.index === selected[0] && item.path && item.productionItemId) &&
            !rebuildingTiming
              ? () => void rebuildVoiceMap()
              : undefined
          }
        >
          {rebuildingTiming ? "Анализ аудио…" : "Перестроить тайминг"}
        </Button>
        <Button
          kind="danger"
          onClick={
            selected.length ? () => void removeVoiceResults() : undefined
          }
        >
          <Trash2 size={17} />
          Удалить MP3
        </Button>
        <Button
          kind="danger"
          onClick={selected.length ? () => void removeScenarios() : undefined}
        >
          <Trash2 size={17} />
          Удалить сценарии
        </Button>
      </Toolbar>
      <section className="panel voice-range-preview">
        <div className="panel-title">
          <div>
            <b>Предпросмотр распределения голосов</b>
            <small>
              Batch {data.voiceRangePreview?.batch?.id?.slice(0, 8) || "ещё не создан"} зафиксирован по ProductionItem ID.
              Сортировка строк и изменения диапазонов не меняют уже запущенные задания.
            </small>
          </div>
          <Button onClick={() => void command("preview-voice-ranges")}>Обновить предпросмотр</Button>
        </div>
        {data.voiceRangePreview?.error ? <small className="voice-error">{data.voiceRangePreview.error}</small> : null}
        <div className="voice-preview-items">
          {(data.voiceRangePreview?.items || []).slice(0, 30).map((item) => (
            <span key={item.production_item_id} title={item.title}>
              #{item.position} · {item.profile.name || "Без имени"} · {item.profile.provider || "chrome"}
            </span>
          ))}
          {(data.voiceRangePreview?.items?.length || 0) > 30 ? <small>Показаны первые 30 из {data.voiceRangePreview?.items?.length}.</small> : null}
        </div>
      </section>
      {data.voiceImport.root ? (
        <section className="panel voice-import-summary">
          <div>
            <b>Последний импорт готовой озвучки</b>
            <small>{data.voiceImport.root}</small>
          </div>
          <span>Найдено папок: <b>{data.voiceImport.foldersFound || 0}</b></span>
          <span>Найдено аудио: <b>{data.voiceImport.audioFound || 0}</b></span>
          <span className="done">Сопоставлено: <b>{data.voiceImport.matched || 0}</b></span>
          <span className={data.voiceImport.requiresChoice ? "warning" : ""}>Требует выбора: <b>{data.voiceImport.requiresChoice || 0}</b></span>
          <span className={data.voiceImport.unmatched ? "warning" : ""}>Не сопоставлено: <b>{data.voiceImport.unmatched || 0}</b></span>
          <span className={data.voiceImport.errors ? "error" : ""}>Ошибок: <b>{data.voiceImport.errors || 0}</b></span>
          {(data.voiceImport.review?.length || data.voiceImport.unmatchedItems?.length) ? (
            <small className="voice-import-review">Не прикреплены автоматически: {[...(data.voiceImport.review || []), ...(data.voiceImport.unmatchedItems || [])].slice(0, 6).map((item) => item.folder || item.file).filter(Boolean).join(" · ")}</small>
          ) : null}
        </section>
      ) : null}
      {newForMontage.length ? (
        <section className="panel transfer-panel">
          <div>
            <b>Готово новых озвучек: {newForMontage.length}</b>
            <small>
              Они автоматически обнаружены после создания или импорта MP3. Можно
              передать все сразу либо выделить строки и передать выбранные.
            </small>
          </div>
          <Button
            kind="success"
            onClick={() => void transferNewAudioToMontage()}
          >
            <MonitorPlay size={16} />
            Перенести {newForMontage.length} в монтаж
          </Button>
          <Button
            onClick={
              selected.filter((index) =>
                newForMontage.some((item) => item.index === index),
              ).length
                ? () =>
                    void transferNewAudioToMontage(
                      selected.filter((index) =>
                        newForMontage.some((item) => item.index === index),
                      ),
                    )
                : undefined
            }
          >
            Перенести выбранные
          </Button>
        </section>
      ) : null}
      <section className="panel assignment">
        <div>
          <b>Назначение голосов</b>
          <span>
            {data.voiceQueuePaused
              ? "Очередь на паузе: текущая внешняя генерация завершится, но следующий сценарий не начнётся до «Продолжить»."
              : provider === "lumean"
                ? "Lumean запускает заказы параллельно по сумме потоков активных ключей. Каждый сценарий получает профиль из заданного диапазона."
                : provider === "voicegen"
                  ? "VoiceGen отправляет задачи в собственную очередь. Число одновременных задач определяется суммой потоков включённых ключей, а размер чанка и пресет — профилем."
                  : provider === "wproject"
                    ? "WProject создаёт удалённые задачи по официальному API. Их ID сохраняются: после перезапуска NewsFlow продолжит ожидание той же задачи, не создавая второй запрос."
                  : "Выделите строки, которые нужно озвучить: NewsFlow запускает только их. Chrome ждёт готовность до 20 минут, обновляет страницу и сохраняет MP3 под названием сценария."}
          </span>
        </div>
        <select
          value={provider}
          onChange={(event) => setVoiceProvider(event.target.value)}
        >
          <option value="chrome">Chrome — Telegram (фон)</option>
          <option value="api">API — Secret Voicer</option>
          <option value="lumean">API — Lumean</option>
          <option value="voicegen">API — VoiceGen</option>
          <option value="wproject">API — WProject</option>
        </select>
        <label className="voice-fallback">
          <input
            type="checkbox"
            checked={data.voiceUseChromeSelectedVoice}
            onChange={(event) =>
              void command("save-voice-settings", {
                useChromeSelectedVoice: event.target.checked,
              })
            }
          />
          Голос из открытого Chrome
        </label>
        <label className="voice-fallback">
          <input
            type="checkbox"
            checked={data.voiceApiFallback}
            onChange={(event) =>
              void command("save-voice-settings", {
                apiFallback: event.target.checked,
              })
            }
          />
          Резерв через API
        </label>
        <Button onClick={() => go("voices")}>
          <Settings2 size={16} />
          Голоса и API
        </Button>
      </section>
      <section className="panel voice-output-folder">
        <div className="panel-title">
          <div>
            <b>Папка готовых озвучек</b>
            <small>
              Сюда сохраняются новые MP3 и копии импортированных аудиофайлов.
              Смена папки не переносит старые файлы.
            </small>
          </div>
          <Button
            onClick={() => void window.newsflowDesktop?.openPath(outputFolder)}
          >
            <FolderOpen size={16} />
            Открыть
          </Button>
        </div>
        <div className="form-row">
          <input
            value={outputFolder}
            onChange={(event) => setOutputFolder(event.target.value)}
            placeholder="Выберите папку для MP3"
          />
          <Button onClick={() => void chooseOutputFolder()}>Выбрать</Button>
          <Button
            kind="primary"
            onClick={outputFolder.trim() ? saveOutputFolder : undefined}
          >
            <Check size={16} />
            Сохранить путь
          </Button>
        </div>
      </section>
      <section className="panel voice-queue-workbench">
        <div className="panel-title">
          <div>
            <span className="eyebrow">CURRENT PRODUCTION ITEMS</span>
            <b>Очередь озвучки</b>
            <small>
              Выберите один или несколько сценариев: действия сверху остаются
              на текущем voice contract и не создают локальную очередь.
            </small>
          </div>
          <span className="status">Выбрано: {selected.length}</span>
        </div>
        {queued.length ? (
          <DataTable
            ariaLabel="Очередь озвучки"
            preferenceKey="voice"
            data={queued}
            columns={voiceQueueColumns}
            onRowActivate={(item) => setSelected([item.index])}
            getRowClassName={(item) =>
              selected.includes(item.index) ? "nf-table-row-selected" : ""
            }
          />
        ) : (
          <Empty
            title="Передайте сценарии в озвучку"
            text="В «Новостях» выберите сценарии и нажмите «В озвучку»."
          />
        )}
      </section>
    </div>
  );
}

export function Audio({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const ready = data.voiceItems.filter((item) => item.path);
  const [selected, setSelected] = useState<number[]>([]);
  const [inspectedAudioIndex, setInspectedAudioIndex] = useState<number | null>(
    null,
  );
  const inspectedAudio = ready.find((item) => item.index === inspectedAudioIndex);
  const readyAudioColumns = useMemo<ColumnDef<(typeof ready)[number]>[]>(
    () => [
      {
        id: "selected",
        header: "",
        cell: ({ row }) => {
          const item = row.original;
          const isSelected = selected.includes(item.index);
          return (
            <button
              className="nf-table-select"
              aria-label={`${isSelected ? "Снять выбор" : "Выбрать"}: ${item.title}`}
              onClick={(event) =>
                setSelected((current) =>
                  event.ctrlKey
                    ? current.includes(item.index)
                      ? current.filter((value) => value !== item.index)
                      : [...current, item.index]
                    : [item.index],
                )
              }
            >
              {isSelected ? "✓" : "○"}
            </button>
          );
        },
      },
      {
        id: "title",
        header: "Сценарий",
        cell: ({ row }) => {
          const item = row.original;
          return (
            <Button
              onClick={() => {
                setSelected([item.index]);
                setInspectedAudioIndex(item.index);
              }}
            >
              {item.index + 1}. {item.title}
            </Button>
          );
        },
      },
      {
        id: "file",
        header: "Файл",
        cell: ({ row }) => row.original.path.split(/[\\/]/).pop(),
      },
      {
        id: "open",
        header: "",
        cell: ({ row }) => (
          <Button onClick={() => void window.newsflowDesktop?.openPath(row.original.path)}>
            <FileAudio size={15} />
            Открыть
          </Button>
        ),
      },
    ],
    [selected],
  );
  const removeAudio = async () => {
    if (
      !selected.length ||
      !window.confirm(`Удалить выбранные MP3: ${selected.length}?`)
    )
      return;
    const result = await command("remove-voiceovers", { indices: selected });
    if (result) setSelected([]);
  };
  const removeScenarios = async () => {
    if (
      !selected.length ||
      !window.confirm(`Удалить сценарии и их MP3: ${selected.length}?`)
    )
      return;
    const result = await command("remove-scenarios", { indices: selected });
    if (result) setSelected([]);
  };
  return (
    <div className="nf-audio">
      <Toolbar label="Действия с готовой озвучкой">
        <Button
          onClick={() =>
            void window.newsflowDesktop?.openPath(data.voiceOutputFolder)
          }
        >
          <FolderOpen size={17} />
          Открыть папку MP3
        </Button>
        <Button
          kind="danger"
          onClick={selected.length ? () => void removeAudio() : undefined}
        >
          <Trash2 size={17} />
          Удалить MP3
        </Button>
        <Button
          kind="danger"
          onClick={selected.length ? () => void removeScenarios() : undefined}
        >
          <Trash2 size={17} />
          Удалить сценарии
        </Button>
      </Toolbar>
      <section className="panel outputs-list">
        <div className="panel-title">
          <div>
            <b>Готовые MP3</b>
            <small>
              Клик — выбрать для удаления; Ctrl+клик — несколько. Двойной клик
              открывает файл. Монтаж использует MP3 выбранного сценария.
            </small>
          </div>
          <span className="status">Выбрано: {selected.length}</span>
        </div>
        {ready.length ? (
          <DataTable
            ariaLabel="Готовые MP3"
            data={ready}
            columns={readyAudioColumns}
            onRowActivate={(item) => {
              setSelected([item.index]);
              setInspectedAudioIndex(item.index);
            }}
            getRowClassName={(item) =>
              selected.includes(item.index) ? "nf-table-row-selected" : ""
            }
          />
        ) : (
          <Empty
            title="MP3 пока нет"
            text="Передайте готовые сценарии в озвучку и запустите очередь."
          />
        )}
      </section>
      <Sheet
        open={Boolean(inspectedAudio)}
        onOpenChange={(open) => {
          if (!open) setInspectedAudioIndex(null);
        }}
        title="Инспектор MP3"
        description="Только подтверждённые текущим snapshot происхождение и состояние аудиоартефакта."
      >
        {inspectedAudio ? (
          <dl className="audio-provenance" aria-label="Происхождение MP3">
            <div>
              <dt>ProductionItem ID</dt>
              <dd>{inspectedAudio.productionItemId || "Не получен из текущего snapshot"}</dd>
            </div>
            <div>
              <dt>Provider</dt>
              <dd>{inspectedAudio.voiceProvider || "Не сообщён текущим snapshot"}</dd>
            </div>
            <div>
              <dt>Профиль</dt>
              <dd>{inspectedAudio.voiceName || "Не сообщён текущим snapshot"}</dd>
            </div>
            <div>
              <dt>Задание</dt>
              <dd>{inspectedAudio.jobSnapshotId || "Не получено"}</dd>
            </div>
            <div>
              <dt>Последнее обновление</dt>
              <dd>{inspectedAudio.voiceUpdatedAt || "Не получено"}</dd>
            </div>
            <div>
              <dt>Файл</dt>
              <dd>{inspectedAudio.path || "Артефакт ещё не создан"}</dd>
            </div>
            <div>
              <dt>Актуальность</dt>
              <dd>Текущий snapshot не сообщает признак устаревания</dd>
            </div>
          </dl>
        ) : null}
      </Sheet>
    </div>
  );
}

function VoiceApiPool({
  data,
  command,
  go,
}: {
  data: NewsFlowSnapshot;
  command: Command;
  go: (page: Page) => void;
}) {
  const [keys, setKeys] = useState(
    data.keyStatus.voicer.map((key, index) => ({
      index,
      active: key.active,
      streams: key.streams || 1,
    })),
  );
  useEffect(
    () =>
      setKeys(
        data.keyStatus.voicer.map((key, index) => ({
          index,
          active: key.active,
          streams: key.streams || 1,
        })),
      ),
    [data.keyStatus.voicer],
  );
  const allSelected = keys.length > 0 && keys.every((key) => key.active);
  const apply = () => void command("update-voicer-key-settings", { keys });
  const toggleAll = () =>
    setKeys((current) =>
      current.map((key) => ({ ...key, active: !allSelected })),
    );
  const totalStreams = keys
    .filter((key) => key.active)
    .reduce((sum, key) => sum + key.streams, 0);
  return (
    <section className="panel voice-api-pool">
      <div className="panel-title">
        <div>
          <b>Пул API Secret Voicer</b>
          <small>
            Отметьте используемые ключи и задайте одновременные сценарии для
            каждого. При режиме API общий параллелизм — сумма включённых
            потоков.
          </small>
        </div>
        <span className="status">
          {totalStreams ? `${totalStreams} потоков` : "Ключи не выбраны"}
        </span>
      </div>
      <div className="voice-api-actions">
        <Button kind="primary" onClick={() => go("keys")}>
          <KeyRound size={16} />
          Добавить ключ
        </Button>
        <Button onClick={toggleAll}>
          {allSelected ? "Снять все" : "Выбрать все"}
        </Button>
        <Button onClick={() => void command("refresh-voicer-balances")}>
          <Activity size={16} />
          Обновить баланс
        </Button>
        <Button kind="success" onClick={apply}>
          <Check size={16} />
          Применить ключи и потоки
        </Button>
      </div>
      {keys.length ? (
        <div className="voice-key-table">
          <div>
            <span>ИСП.</span>
            <span>КЛЮЧ</span>
            <span>ПОТОКИ</span>
            <span>БАЛАНС / СТАТУС API</span>
          </div>
          {keys.map((row) => {
            const source = data.keyStatus.voicer[row.index];
            return (
              <div key={`${source.label}-${row.index}`}>
                <label>
                  <input
                    type="checkbox"
                    checked={row.active}
                    onChange={(event) =>
                      setKeys((current) =>
                        current.map((key) =>
                          key.index === row.index
                            ? { ...key, active: event.target.checked }
                            : key,
                        ),
                      )
                    }
                  />
                </label>
                <b>{source.label}</b>
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={row.streams}
                  onChange={(event) =>
                    setKeys((current) =>
                      current.map((key) =>
                        key.index === row.index
                          ? {
                              ...key,
                              streams: Math.max(
                                1,
                                Math.min(20, Number(event.target.value) || 1),
                              ),
                            }
                          : key,
                      ),
                    )
                  }
                />
                <span
                  className={
                    source.balanceStatus === "ok"
                      ? "api-ok"
                      : source.balanceStatus &&
                          source.balanceStatus !== "not_checked"
                        ? "api-error"
                        : ""
                  }
                >
                  {source.balanceStatus === "ok"
                    ? source.balance || "Доступ подтверждён"
                    : source.balanceStatus &&
                        source.balanceStatus !== "not_checked"
                      ? source.balanceStatus
                      : "Не проверялся"}
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <Empty
          title="Добавьте API-ключ Secret Voicer"
          text="Откройте раздел «API-ключи», добавьте ключ Secret Voicer — затем здесь выберите его и число потоков."
        />
      )}
    </section>
  );
}

function LumeanApiPool({
  data,
  command,
  go,
}: {
  data: NewsFlowSnapshot;
  command: Command;
  go: (page: Page) => void;
}) {
  const [keys, setKeys] = useState(
    data.keyStatus.lumean.map((key, index) => ({
      index,
      active: key.active,
      streams: key.streams || 1,
    })),
  );
  useEffect(
    () =>
      setKeys(
        data.keyStatus.lumean.map((key, index) => ({
          index,
          active: key.active,
          streams: key.streams || 1,
        })),
      ),
    [data.keyStatus.lumean],
  );
  const allSelected = keys.length > 0 && keys.every((key) => key.active);
  const totalStreams = keys
    .filter((key) => key.active)
    .reduce((sum, key) => sum + key.streams, 0);
  const apply = () => void command("update-lumean-key-settings", { keys });
  const refresh = () => void command("refresh-lumean-catalog");
  return (
    <section className="panel voice-api-pool">
      <div className="panel-title">
        <div>
          <b>Пул API Lumean</b>
          <small>
            Шаблон Lumean создаётся автоматически для выбранного профиля и
            переиспользуется, пока не изменятся голос, модель или настройки.
            Каталог и лимиты обновляются только по кнопке.
          </small>
        </div>
        <span className="status">
          {totalStreams ? `${totalStreams} потоков` : "Ключи не выбраны"}
        </span>
      </div>
      <div className="voice-api-actions">
        <Button kind="primary" onClick={() => go("keys")}>
          <KeyRound size={16} />
          Добавить ключ
        </Button>
        <Button
          onClick={() =>
            setKeys((current) =>
              current.map((key) => ({ ...key, active: !allSelected })),
            )
          }
        >
          {allSelected ? "Снять все" : "Выбрать все"}
        </Button>
        <Button onClick={refresh}>
          <Activity size={16} />
          Голоса, модели и лимиты
        </Button>
        <Button kind="success" onClick={apply}>
          <Check size={16} />
          Применить ключи и потоки
        </Button>
      </div>
      {keys.length ? (
        <div className="voice-key-table">
          <div>
            <span>ИСП.</span>
            <span>КЛЮЧ</span>
            <span>ПОТОКИ</span>
            <span>ЛИМИТ / СТАТУС API</span>
          </div>
          {keys.map((row) => {
            const source = data.keyStatus.lumean[row.index];
            return (
              <div key={`${source.label}-${row.index}`}>
                <label>
                  <input
                    type="checkbox"
                    checked={row.active}
                    onChange={(event) =>
                      setKeys((current) =>
                        current.map((key) =>
                          key.index === row.index
                            ? { ...key, active: event.target.checked }
                            : key,
                        ),
                      )
                    }
                  />
                </label>
                <b>{source.label}</b>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={row.streams}
                  onChange={(event) =>
                    setKeys((current) =>
                      current.map((key) =>
                        key.index === row.index
                          ? {
                              ...key,
                              streams: Math.max(
                                1,
                                Math.min(100, Number(event.target.value) || 1),
                              ),
                            }
                          : key,
                      ),
                    )
                  }
                />
                <span
                  className={
                    source.balanceStatus === "ok"
                      ? "api-ok"
                      : source.balanceStatus &&
                          source.balanceStatus !== "not_checked"
                        ? "api-error"
                        : ""
                  }
                >
                  {source.balanceStatus === "ok"
                    ? source.balance || "Доступ подтверждён"
                    : source.balanceStatus &&
                        source.balanceStatus !== "not_checked"
                      ? source.balanceStatus
                      : "Не проверялся"}
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <Empty
          title="Добавьте API-ключ Lumean"
          text="Откройте «API-ключи», добавьте Lumean, затем обновите каталог голосов и лимиты."
        />
      )}
    </section>
  );
}

function VoiceGenApiPool({
  data,
  command,
  go,
}: {
  data: NewsFlowSnapshot;
  command: Command;
  go: (page: Page) => void;
}) {
  const [keys, setKeys] = useState(
    data.keyStatus.voicegen.map((key, index) => ({
      index,
      active: key.active,
      streams: key.streams || 1,
    })),
  );
  useEffect(
    () =>
      setKeys(
        data.keyStatus.voicegen.map((key, index) => ({
          index,
          active: key.active,
          streams: key.streams || 1,
        })),
      ),
    [data.keyStatus.voicegen],
  );
  const allSelected = keys.length > 0 && keys.every((key) => key.active);
  const totalStreams = keys
    .filter((key) => key.active)
    .reduce((sum, key) => sum + key.streams, 0);
  return (
    <section className="panel voice-api-pool">
      <div className="panel-title">
        <div>
          <b>Пул API VoiceGen</b>
          <small>
            Потоки задаются отдельно для каждого ключа. VoiceGen использует свою
            очередь задач; профиль ключа, подписка, голоса V3 и пресеты читаются
            только по кнопке.
          </small>
        </div>
        <span className="status">
          {totalStreams
            ? `${totalStreams} задач одновременно`
            : "Ключи не выбраны"}
        </span>
      </div>
      <div className="voice-api-actions">
        <Button kind="primary" onClick={() => go("keys")}>
          <KeyRound size={16} />
          Добавить ключ
        </Button>
        <Button
          onClick={() =>
            setKeys((current) =>
              current.map((key) => ({ ...key, active: !allSelected })),
            )
          }
        >
          {allSelected ? "Снять все" : "Выбрать все"}
        </Button>
        <Button onClick={() => void command("refresh-voicegen-catalog")}>
          <Activity size={16} />
          Голоса, V3 и подписка
        </Button>
        <Button
          kind="success"
          onClick={() => void command("update-voicegen-key-settings", { keys })}
        >
          <Check size={16} />
          Применить ключи и потоки
        </Button>
      </div>
      {keys.length ? (
        <div className="voice-key-table">
          <div>
            <span>ИСП.</span>
            <span>КЛЮЧ</span>
            <span>ПОТОКИ</span>
            <span>ПОДПИСКА / СТАТУС</span>
          </div>
          {keys.map((row) => {
            const source = data.keyStatus.voicegen[row.index];
            return (
              <div key={`${source.label}-${row.index}`}>
                <label>
                  <input
                    type="checkbox"
                    checked={row.active}
                    onChange={(event) =>
                      setKeys((current) =>
                        current.map((key) =>
                          key.index === row.index
                            ? { ...key, active: event.target.checked }
                            : key,
                        ),
                      )
                    }
                  />
                </label>
                <b>{source.label}</b>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={row.streams}
                  onChange={(event) =>
                    setKeys((current) =>
                      current.map((key) =>
                        key.index === row.index
                          ? {
                              ...key,
                              streams: Math.max(
                                1,
                                Math.min(100, Number(event.target.value) || 1),
                              ),
                            }
                          : key,
                      ),
                    )
                  }
                />
                <span
                  className={
                    source.balanceStatus === "ok"
                      ? "api-ok"
                      : source.balanceStatus &&
                          source.balanceStatus !== "not_checked"
                        ? "api-error"
                        : ""
                  }
                >
                  {source.balanceStatus === "ok"
                    ? source.balance || "Доступ подтверждён"
                    : source.balanceStatus &&
                        source.balanceStatus !== "not_checked"
                      ? source.balanceStatus
                      : "Не проверялся"}
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <Empty
          title="Добавьте API-ключ VoiceGen"
          text="Откройте «API-ключи», добавьте VoiceGen, затем обновите голоса и статус подписки."
        />
      )}
    </section>
  );
}

function WProjectApiPool({ data, command, go }: { data: NewsFlowSnapshot; command: Command; go: (page: Page) => void }) {
  const [keys, setKeys] = useState(data.keyStatus.wproject.map((key, index) => ({ index, active: key.active, streams: key.streams || 1 })));
  useEffect(() => setKeys(data.keyStatus.wproject.map((key, index) => ({ index, active: key.active, streams: key.streams || 1 }))), [data.keyStatus.wproject]);
  const totalStreams = keys.filter((key) => key.active).reduce((sum, key) => sum + key.streams, 0);
  return <section className="panel voice-api-pool">
    <div className="panel-title"><div><b>Пул API WProject</b><small>Сумма потоков ключей ограничивает параллельные задачи. Каталог и лимиты запрашиваются отдельно и не создают озвучку.</small></div><span className="status">{totalStreams ? `${totalStreams} задач одновременно` : "Ключи не выбраны"}</span></div>
    <div className="voice-api-actions"><Button kind="primary" onClick={() => go("keys")}><KeyRound size={16}/>Добавить ключ</Button><Button onClick={() => void command("refresh-wproject-catalog")}><Activity size={16}/>Голоса и лимиты</Button><Button kind="success" onClick={() => void command("update-wproject-key-settings", { keys })}><Check size={16}/>Применить потоки</Button></div>
    {keys.length ? <div className="voice-key-table"><div><span>ИСП.</span><span>КЛЮЧ</span><span>ПОТОКИ</span><span>ЛИМИТ / СТАТУС</span></div>{keys.map((row) => { const source = data.keyStatus.wproject[row.index]; return <div key={`${source.label}-${row.index}`}><label><input type="checkbox" checked={row.active} onChange={(event) => setKeys((current) => current.map((key) => key.index === row.index ? { ...key, active: event.target.checked } : key))}/></label><b>{source.label}</b><input type="number" min="1" max="100" value={row.streams} onChange={(event) => setKeys((current) => current.map((key) => key.index === row.index ? { ...key, streams: Math.max(1, Math.min(100, Number(event.target.value) || 1)) } : key))}/><span className={source.balanceStatus === "ok" ? "api-ok" : source.balanceStatus && source.balanceStatus !== "not_checked" ? "api-error" : ""}>{source.balanceStatus === "ok" ? source.balance || "Доступ подтверждён" : source.balanceStatus && source.balanceStatus !== "not_checked" ? source.balanceStatus : "Не проверялся"}</span></div>; })}</div> : <Empty title="Добавьте API-ключ WProject" text="Откройте «API-ключи», добавьте WProject, затем обновите каталог голосов и лимиты."/>}
  </section>;
}

export function VoiceProfilesScreen({
  data,
  command,
  go,
}: {
  data: NewsFlowSnapshot;
  command: Command;
  go: (page: Page) => void;
}) {
  const [readinessOpen, setReadinessOpen] = useState(false);
  return (
    <>
      <section className="panel voice-provider-readiness">
        <div className="panel-title">
          <div>
            <b>Готовность поставщиков</b>
            <small>Ключи, каталоги голосов и лимиты открываются отдельно от редактора профилей.</small>
          </div>
          <Button onClick={() => setReadinessOpen(true)}>
            <Activity size={16} />
            Проверить готовность провайдеров
          </Button>
        </div>
      </section>
      <VoiceProfiles data={data} command={command} go={go} />
      <Sheet
        open={readinessOpen}
        onOpenChange={setReadinessOpen}
        title="Готовность провайдеров озвучки"
        description="Проверьте ключи, лимиты и каталоги без потери контекста профиля."
      >
        <div className="voice-provider-readiness-sheet">
          <VoiceApiPool data={data} command={command} go={go} />
          <LumeanApiPool data={data} command={command} go={go} />
          <VoiceGenApiPool data={data} command={command} go={go} />
          <WProjectApiPool data={data} command={command} go={go} />
        </div>
      </Sheet>
    </>
  );
}

export function VoiceProfiles({
  data,
  command,
  go,
}: {
  data: NewsFlowSnapshot;
  command: Command;
  go: (page: Page) => void;
}) {
  const [profiles, setProfiles] = useState(data.voiceProfiles);
  const [ranges, setRanges] = useState(data.voiceRanges);
  const [defaultProfileId, setDefaultProfileId] = useState(data.voiceDefaultProfileId || data.voiceProfiles[0]?.id || "");
  const [queueConcurrency, setQueueConcurrency] = useState(data.voiceQueueConcurrency || 20);
  const [active, setActive] = useState(0);
  const [presetDialogOpen, setPresetDialogOpen] = useState(false);
  const [presetNameDraft, setPresetNameDraft] = useState("");
  useEffect(() => {
    setProfiles(data.voiceProfiles);
    setRanges(data.voiceRanges);
    setDefaultProfileId(data.voiceDefaultProfileId || data.voiceProfiles[0]?.id || "");
    setQueueConcurrency(data.voiceQueueConcurrency || 20);
    setActive((current) =>
      Math.min(current, Math.max(0, data.voiceProfiles.length - 1)),
    );
  }, [data.voiceProfiles, data.voiceRanges]);
  const profile = profiles[active] || {
    id: "",
    name: "Новости",
    provider: "lumean" as const,
    voice_id: "",
    model_id: "",
    stability: 0.3,
    style: 0.5,
  };
  const update = (patch: Partial<typeof profile>) =>
    setProfiles((current) =>
      current.map((item, index) =>
        index === active ? { ...item, ...patch } : item,
      ),
    );
  const addProfile = () => {
    const profileId = crypto.randomUUID();
    setProfiles((current) => [
      ...current,
      {
        id: profileId,
        name: `Голос ${current.length + 1}`,
        provider: "lumean",
        voice_id: "",
        model_id: "",
        stability: 0.3,
        style: 0.5,
      },
    ]);
    setActive(profiles.length);
  };
  const removeProfile = () => {
    if (profiles.length < 2) return;
    const deletedId = profiles[active]?.id;
    const replacementId = profiles.find((item, index) => index !== active)?.id || "";
    setProfiles((current) =>
      current.filter((_item, index) => index !== active),
    );
    setRanges((current) =>
      current.map((item) => ({
        ...item,
        profile_id: item.profile_id === deletedId ? replacementId : item.profile_id,
      })),
    );
    if (defaultProfileId === deletedId) setDefaultProfileId(replacementId);
    setActive(Math.max(0, active - 1));
  };
  const save = () => void command("save-voice-settings", {
    profiles, ranges, defaultProfileId, queueConcurrency,
  });
  const savePreset = () => {
    setPresetNameDraft("");
    setPresetDialogOpen(true);
  };
  const confirmSavePreset = async () => {
    const name = presetNameDraft.trim();
    if (!name) return;
    const result = await command("save-voice-range-preset", {
      name,
      profiles,
      ranges,
      defaultProfileId,
      keyFailover: data.voiceKeyFailover,
    });
    if (result) {
      setPresetDialogOpen(false);
      setPresetNameDraft("");
    }
  };
  const addRange = () =>
    setRanges((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        start: Math.max(1, ...current.filter((item) => item.enabled !== false).map((item) => item.end + 1)),
        end: Math.max(1, ...current.filter((item) => item.enabled !== false).map((item) => item.end + 1)),
        profile_id: profile.id || defaultProfileId,
        enabled: true,
      },
    ]);
  const isLumean = profile.provider === "lumean";
  const isVoiceGen = profile.provider === "voicegen";
  const isWProject = profile.provider === "wproject";
  const isSecretApi = profile.provider === "api";
  const profileColumns = useMemo<ColumnDef<(typeof profiles)[number]>[]>(
    () => [
      {
        id: "name",
        header: "Профиль",
        cell: ({ row }) => (
          <Button onClick={() => setActive(row.index)}>{row.original.name}</Button>
        ),
      },
      {
        id: "provider",
        header: "Провайдер",
        cell: ({ row }) => row.original.provider || "chrome",
      },
      {
        id: "voice",
        header: "Голос",
        cell: ({ row }) => row.original.voice_name || row.original.voice_id || "Не выбран",
      },
    ],
    [],
  );
  return (
    <div className="split">
      <Dialog
        open={presetDialogOpen}
        onOpenChange={(open) => {
          setPresetDialogOpen(open);
          if (!open) setPresetNameDraft("");
        }}
        title="Сохранить пресет голосов"
        description="Название будет использоваться для набора профилей и диапазонов."
      >
        <Input
          label="Название пресета"
          value={presetNameDraft}
          onChange={(event) => setPresetNameDraft(event.target.value)}
          autoFocus
        />
        <div className="toolbar">
          <Button onClick={() => setPresetDialogOpen(false)}>Отмена</Button>
          <Button kind="primary" onClick={() => void confirmSavePreset()} disabled={!presetNameDraft.trim()}>
            Подтвердить сохранение
          </Button>
        </div>
      </Dialog>
      <section className="panel list-panel">
        <div className="panel-title">
          <div>
            <b>Профили</b>
            <small>Диктор, сервис и подача для диапазонов сценариев</small>
          </div>
          <Button kind="primary" onClick={addProfile}>
            <Plus size={16} />
          </Button>
        </div>
        <DataTable
          ariaLabel="Профили голосов"
          data={profiles}
          columns={profileColumns}
          getRowClassName={(item) =>
            item.id === profiles[active]?.id ? "nf-table-row-selected" : ""
          }
        />
      </section>
      <section className="panel editor">
        <div className="panel-title">
          <div>
            <b>Профиль голоса</b>
            <small>
              Профиль назначается любому диапазону. Каждый сервис хранит свои
              параметры голоса и модели.
            </small>
          </div>
          <Button kind="danger" onClick={removeProfile}>
            <Trash2 size={16} />
            Удалить
          </Button>
        </div>
        <div className="form-grid">
          <label>
            Название профиля
            <input
              value={profile.name}
              onChange={(event) => update({ name: event.target.value })}
            />
          </label>
          <label>
            Провайдер
            <select
              value={profile.provider || "chrome"}
              onChange={(event) =>
                update({
                  provider: event.target.value as
                    | "chrome"
                    | "api"
                    | "lumean"
                    | "voicegen"
                    | "wproject",
                  template_id: "",
                  template_signature: "",
                })
              }
            >
              <option value="lumean">Lumean API</option>
              <option value="voicegen">VoiceGen API</option>
              <option value="wproject">WProject API</option>
              <option value="api">Secret Voicer API</option>
              <option value="chrome">Secret Voicer Chrome</option>
            </select>
          </label>
          <label>
            Voice ID
            <input
              value={profile.voice_id || ""}
              onChange={(event) =>
                update({
                  voice_id: event.target.value,
                  template_id: "",
                  template_signature: "",
                })
              }
              placeholder="ID выбранного голоса"
            />
          </label>
          <label>
            Название голоса
            <input
              value={profile.voice_name || ""}
              onChange={(event) => update({ voice_name: event.target.value })}
              placeholder="Например: News male"
            />
          </label>
          {isSecretApi ? (
            <label>
              Режим Secret Voicer
              <select
                value={profile.secret_mode || "emotional"}
                onChange={(event) =>
                  update({
                    secret_mode: event.target.value as "standard" | "emotional",
                  })
                }
              >
                <option value="emotional">Эмоциональный</option>
                <option value="standard">Стандартный</option>
              </select>
              <small>
                Это все поддерживаемые режимы текущего API; model_id у Secret
                Voicer устарел и не отправляется.
              </small>
            </label>
          ) : null}
          {isLumean ? (
            <>
              <label>
                Модель Lumean
                <input
                  list="lumean-models"
                  value={profile.model_id || ""}
                  onChange={(event) =>
                    update({
                      model_id: event.target.value,
                      template_id: "",
                      template_signature: "",
                    })
                  }
                  placeholder="Сначала обновите каталог"
                />
                <datalist id="lumean-models">
                  {data.lumeanModels.map((model) => (
                    <option key={model} value={model} />
                  ))}
                </datalist>
              </label>
              <label>
                Голос Lumean
                <select
                  value={profile.voice_id || ""}
                  onChange={(event) => {
                    const voice = data.lumeanVoices.find(
                      (item) => item.voice_id === event.target.value,
                    );
                    update({
                      voice_id: event.target.value,
                      voice_name: voice?.name || "",
                      template_id: "",
                      template_signature: "",
                    });
                  }}
                >
                  <option value="">Выберите после обновления каталога</option>
                  {data.lumeanVoices.map((voice) => (
                    <option key={voice.voice_id} value={voice.voice_id}>
                      {voice.name} · {voice.voice_id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="favorite-toggle">
                <Button onClick={() => void command("refresh-lumean-catalog")}>
                  <Activity size={15} />
                  Обновить голоса и модели
                </Button>
              </label>
            </>
          ) : null}
          {isVoiceGen ? (
            <>
              <label>
                Движок VoiceGen
                <select
                  value={profile.model_id || "elevenLabsV3"}
                  onChange={(event) => update({ model_id: event.target.value })}
                >
                  {(data.voicegenEngines.length
                    ? data.voicegenEngines
                    : ["elevenLabsV3"]
                  ).map((engine) => (
                    <option key={engine} value={engine}>
                      {engine}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Голос VoiceGen
                <select
                  value={profile.voice_id || ""}
                  onChange={(event) => {
                    const voice = data.voicegenVoices.find(
                      (item) => item.id === event.target.value,
                    );
                    update({
                      voice_id: event.target.value,
                      voice_name: voice?.display || voice?.name || "",
                    });
                  }}
                >
                  <option value="">Выберите после обновления каталога</option>
                  {data.voicegenVoices.map((voice) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.display || voice.name || voice.id} ·{" "}
                      {voice.source_type || "public"}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Пресет
                <select
                  value={profile.settings_preset || "standard"}
                  onChange={(event) =>
                    update({ settings_preset: event.target.value })
                  }
                >
                  {data.voicegenPresets.length ? (
                    data.voicegenPresets.map((preset) => (
                      <option key={preset.id} value={preset.id}>
                        {preset.title || preset.id}
                      </option>
                    ))
                  ) : (
                    <option value="standard">standard</option>
                  )}
                </select>
              </label>
              <label>
                Чанк, символов
                <input
                  type="number"
                  min="200"
                  max="10000"
                  value={profile.chunk_size || 1200}
                  onChange={(event) =>
                    update({ chunk_size: Number(event.target.value) || 1200 })
                  }
                />
              </label>
              <label>
                Пауза между чанками
                <input
                  type="number"
                  min="0"
                  max="30"
                  step="0.1"
                  value={profile.delay_between_chunks ?? 0.5}
                  onChange={(event) =>
                    update({
                      delay_between_chunks: Number(event.target.value) || 0,
                    })
                  }
                />
              </label>
              <label>
                Потоков внутри задачи
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={profile.task_threads || 5}
                  onChange={(event) =>
                    update({ task_threads: Number(event.target.value) || 1 })
                  }
                />
              </label>
              <label className="favorite-toggle">
                <Button
                  onClick={() => void command("refresh-voicegen-catalog")}
                >
                  <Activity size={15} />
                  Голоса, V3 и подписка
                </Button>
              </label>
            </>
          ) : null}
          {isWProject ? (
            <>
              <label>
                Голос WProject
                <select
                  value={profile.voice_id || ""}
                  onChange={(event) => {
                    const voice = data.wprojectVoices.find((item) => String(item.id || item.voice_id || "") === event.target.value);
                    update({ voice_id: event.target.value, voice_name: String(voice?.name || "") });
                  }}
                >
                  <option value="">Выберите после обновления каталога</option>
                  {data.wprojectVoices.map((voice) => {
                    const id = String(voice.id || voice.voice_id || "");
                    return <option key={id} value={id}>{String(voice.name || id)} · {id}</option>;
                  })}
                </select>
              </label>
              <label>
                Разбиение текста
                <select value={profile.wproject_split || "single"} onChange={(event) => update({ wproject_split: event.target.value as "paragraphs" | "lines" | "sentences" | "single" })}>
                  <option value="single">Один файл</option><option value="paragraphs">Абзацы</option><option value="lines">Строки</option><option value="sentences">Предложения</option>
                </select>
              </label>
              <label>
                Автотеги эмоций
                <select value={profile.wproject_autotag || "off"} onChange={(event) => update({ wproject_autotag: event.target.value as "off" | "light" | "medium" | "heavy" })}>
                  <option value="off">Выключены</option><option value="light">Легко</option><option value="medium">Средне</option><option value="heavy">Активно</option>
                </select>
              </label>
              <label>
                Качество / скорость
                <select value={profile.wproject_latency || "normal"} onChange={(event) => update({ wproject_latency: event.target.value as "normal" | "balanced" })}>
                  <option value="normal">normal — качество</option><option value="balanced">balanced — быстрее</option>
                </select>
              </label>
              <label>
                Скорость речи
                <input type="number" min="0.5" max="2" step="0.05" value={profile.wproject_prosody_speed ?? 1} onChange={(event) => update({ wproject_prosody_speed: Number(event.target.value) || 1 })}/>
              </label>
              <label>
                Громкость, dB
                <input type="number" min="-20" max="20" step="0.5" value={profile.wproject_prosody_volume ?? 0} onChange={(event) => update({ wproject_prosody_volume: Number(event.target.value) || 0 })}/>
              </label>
              <label>
                Потоков внутри задачи
                <input type="number" min="1" max="100" value={profile.task_threads || 5} onChange={(event) => update({ task_threads: Number(event.target.value) || 1 })}/>
              </label>
              <label className="favorite-toggle"><input type="checkbox" checked={profile.wproject_join !== false} onChange={(event) => update({ wproject_join: event.target.checked })}/>Склеить части в один MP3</label>
              <label className="favorite-toggle"><input type="checkbox" checked={profile.wproject_normalize !== false} onChange={(event) => update({ wproject_normalize: event.target.checked })}/>Нормализовать числа и сокращения</label>
              <label className="favorite-toggle"><input type="checkbox" checked={profile.wproject_normalize_loudness !== false} onChange={(event) => update({ wproject_normalize_loudness: event.target.checked })}/>Выровнять громкость</label>
              <label className="favorite-toggle"><Button onClick={() => void command("refresh-wproject-catalog")}><Activity size={15}/>Голоса и лимиты WProject</Button></label>
            </>
          ) : null}
          <label className="favorite-toggle">
            <input
              type="checkbox"
              checked={Boolean(profile.fallback)}
              onChange={(event) => update({ fallback: event.target.checked })}
            />
            Резервный профиль
          </label>
          <label className="favorite-toggle">
            <input
              type="checkbox"
              checked={Boolean(profile.favorite)}
              onChange={(event) => update({ favorite: event.target.checked })}
            />
            В избранном
          </label>
        </div>
        <Slider
          label="Стабильность"
          value={Number(profile.stability ?? 0.3)}
          onChange={(value) =>
            update({
              stability: value,
              template_id: "",
              template_signature: "",
            })
          }
        />
        <Slider
          label="Сходство / сила голоса"
          value={Number(profile.style ?? 0.5)}
          onChange={(value) =>
            update({ style: value, template_id: "", template_signature: "" })
          }
        />
        <div className="voice-preset-bar">
          <label>
            Голос по умолчанию для промежутков
            <select value={defaultProfileId} onChange={(event) => setDefaultProfileId(event.target.value)}>
              {profiles.map((voice) => <option key={voice.id || voice.name} value={voice.id}>{voice.name}</option>)}
            </select>
          </label>
          <label>
            Одновременных TTS-задач
            <input aria-label="Одновременных TTS-задач" type="number" min="1" max="100" value={queueConcurrency}
              onChange={(event) => setQueueConcurrency(Math.max(1, Number(event.target.value) || 1))} />
            <small>Фактический параллелизм = минимум из этого значения и доступных потоков API-ключей; Chrome работает в 1 браузерный поток.</small>
          </label>
          <label className="voice-fallback">
            <input
              type="checkbox"
              checked={data.voiceKeyFailover}
              onChange={(event) =>
                void command("save-voice-settings", {
                  keyFailover: event.target.checked,
                })
              }
            />
            Автоматически переключать ключ/резервный сервис при лимите или
            подписке
          </label>
          <Button onClick={savePreset}>Сохранить пресет</Button>
          {data.voiceRangePresets.map((preset) => (
            <span key={preset.name}>
              <Button
                onClick={() =>
                  void command("apply-voice-range-preset", {
                    name: preset.name,
                  })
                }
              >
                {preset.name}
              </Button>
              <Button
                kind="danger"
                onClick={() =>
                  void command("delete-voice-range-preset", {
                    name: preset.name,
                  })
                }
              >
                <Trash2 size={13} />
              </Button>
            </span>
          ))}
        </div>
        <div className="voice-ranges">
          <div>
            <b>Диапазоны сценариев</b>
            <small>
              Можно задать любые диапазоны, например 1–3 и 7–8; каждый
              использует выбранный профиль. Границы относятся к зафиксированному
              production batch, а не к сортировке таблицы.
            </small>
          </div>
          <Button onClick={addRange}>
            <Plus size={15} />
            Добавить диапазон
          </Button>
          {ranges.length ? (
            ranges.map((item, index) => (
              <div className="voice-range" key={item.id || index}>
                <label title="Включить этот диапазон">
                  <input
                    type="checkbox"
                    checked={item.enabled !== false}
                    onChange={(event) =>
                      setRanges((current) =>
                        current.map((range, row) =>
                          row === index
                            ? { ...range, enabled: event.target.checked }
                            : range,
                        ),
                      )
                    }
                  />
                </label>
                <input
                  value={item.start}
                  type="number"
                  min="1"
                  onChange={(event) =>
                    setRanges((current) =>
                      current.map((range, row) =>
                        row === index
                          ? { ...range, start: Number(event.target.value) }
                          : range,
                      ),
                    )
                  }
                />
                <span>—</span>
                <input
                  value={item.end}
                  type="number"
                  min="1"
                  onChange={(event) =>
                    setRanges((current) =>
                      current.map((range, row) =>
                        row === index
                          ? { ...range, end: Number(event.target.value) }
                          : range,
                      ),
                    )
                  }
                />
                <select
                  value={item.profile_id || defaultProfileId}
                  onChange={(event) =>
                    setRanges((current) =>
                      current.map((range, row) =>
                        row === index
                          ? { ...range, profile_id: event.target.value }
                          : range,
                      ),
                    )
                  }
                >
                  {profiles.map((voice) => (
                    <option key={voice.id || voice.name} value={voice.id}>
                      {voice.name}
                    </option>
                  ))}
                </select>
                <Button
                  onClick={() => void command("generate-voice-range", { rangeId: item.id })}
                >
                  Озвучить
                </Button>
                <Button
                  onClick={() => void command("generate-voice-range", { rangeId: item.id, force: true })}
                >
                  Переозвучить
                </Button>
                <Button
                  kind="danger"
                  onClick={() =>
                    setRanges((current) =>
                      current.filter((_range, row) => row !== index),
                    )
                  }
                >
                  <Trash2 size={14} />
                </Button>
              </div>
            ))
          ) : (
            <small className="range-empty">
              Нет диапазонов: первый профиль применяется ко всем сценариям.
            </small>
          )}
        </div>
        <div className="toolbar">
          <Button kind="primary" onClick={save}>
            Сохранить профили и диапазоны
          </Button>
        </div>
      </section>
    </div>
  );
}
function Slider({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="slider">
      <span>
        <b>{label}</b>
        <small>Настройка подачи голоса</small>
      </span>
      <output>{value.toFixed(2)}</output>
      <input
        type="range"
        min="0"
        max="1"
        step="0.01"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}
function ChannelMetadataEditor({
  channel,
  index,
  command,
}: {
  channel: NewsFlowSnapshot["channels"][number];
  index: number;
  command: Command;
}) {
  const [tag, setTag] = useState(channel.operatorTag || "");
  const [notes, setNotes] = useState(channel.operatorNotes || "");
  useEffect(() => {
    setTag(channel.operatorTag || "");
    setNotes(channel.operatorNotes || "");
  }, [channel.operatorNotes, channel.operatorTag]);
  return (
    <div className="analytics-channel-meta-editor">
      <label className="analytics-channel-tag">
        Метка
        <input
          value={tag}
          maxLength={120}
          onChange={(event) => setTag(event.target.value)}
          placeholder="Например: основной"
        />
      </label>
      <label className="analytics-channel-notes">
        Заметки по каналу
        <textarea
          value={notes}
          maxLength={4000}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Например: длинные ролики, время, особые правила…"
        />
      </label>
      <Button
        onClick={() =>
          void command("update-analytics-channel-metadata", { index, tag, notes })
        }
      >
        <Check size={14} />
        Сохранить заметку
      </Button>
    </div>
  );
}
export function AnalyticsDashboard({ data, command }: { data: NewsFlowSnapshot; command: Command }) {
  const [channelIds, setChannelIds] = useState<string[]>([]);
  const [period, setPeriod] = useState<"current" | "previous" | "30" | "90">("current");
  const [revenue, setRevenue] = useState<"all" | "available" | "missing">("all");
  const [channelFormOpen, setChannelFormOpen] = useState(false);
  const [newChannelName, setNewChannelName] = useState("");
  const [newChannelLink, setNewChannelLink] = useState("");
  const [oauthJobs, setOauthJobs] = useState<Record<number, { id: string; state: 'waiting' | 'succeeded' | 'failed' | 'cancelled'; message?: string }>>({});
  const channels = data.channels.map((channel, index) => ({ ...channel, index, id: channel.id || channel.channel || channel.name || `channel-${index}` }));
  const now = new Date();
  const start = new Date(now);
  if (period === "current") start.setDate(1), start.setHours(0, 0, 0, 0);
  if (period === "previous") start.setMonth(start.getMonth() - 1, 1), start.setHours(0, 0, 0, 0), now.setDate(1), now.setHours(0, 0, 0, 0);
  if (period === "30") start.setDate(start.getDate() - 30);
  if (period === "90") start.setDate(start.getDate() - 90);
  const selected = new Set(channelIds.length ? channelIds : channels.map((channel) => channel.id));
  const sourcePoints = data.analytics.metricPoints.filter((point) => selected.has(point.channelId) && new Date(point.at) >= start && new Date(point.at) < now);
  const revenueKnown = new Set(sourcePoints.filter((point) => point.estimatedRevenue !== null && point.estimatedRevenue !== undefined).map((point) => point.channelId));
  const filteredChannels = channels.filter((channel) => revenue === "all" || (revenue === "available" ? revenueKnown.has(channel.id) : !revenueKnown.has(channel.id)));
  const activeIds = new Set(filteredChannels.map((channel) => channel.id));
  const points = sourcePoints.filter((point) => activeIds.has(point.channelId));
  const totals = points.reduce((sum, point) => ({ views: sum.views + point.views, subscribers: sum.subscribers + (point.subscribers || 0), publications: sum.publications + (point.publications || 0), revenue: sum.revenue + (point.estimatedRevenue || 0) }), { views: 0, subscribers: 0, publications: 0, revenue: 0 });
  const watchHours = data.analytics.videoMetrics.filter((metric) => activeIds.has(metric.channelId)).reduce((sum, metric) => sum + (Number(metric.views || 0) * Number(metric.averageViewDuration || 0)) / 3600, 0);
  const addChannel = async () => {
    const result = await command("add-channel", { name: newChannelName, channel: newChannelLink });
    if (result) { setNewChannelName(""); setNewChannelLink(""); setChannelFormOpen(false); }
  };
  const connectChannel = async (index: number, includeMonetary: boolean) => {
    if (!data.analyticsOAuth.configured || data.analyticsOAuth.mode !== "cloudflare" || !window.newsflowDesktop?.startYoutubeOAuthHandoff) {
      window.alert("Сервис OAuth YouTube не настроен. Откройте настройки OAuth и укажите адрес tinkbro.");
      return;
    }
    try {
      const job = await window.newsflowDesktop.startYoutubeOAuthHandoff({ index, includeMonetary });
      setOauthJobs((current) => ({ ...current, [index]: { id: job.id, state: job.state, message: job.message } }));
      const watch = async () => {
        try {
          const current = await window.newsflowDesktop?.youtubeOAuthHandoffStatus(job.id);
          if (!current) throw new Error("Сессия входа в Google не найдена.");
          setOauthJobs((jobs) => ({ ...jobs, [index]: { id: current.id, state: current.state, message: current.message } }));
          if (current.state === "waiting") window.setTimeout(() => void watch(), 1500);
          if (current.state === "succeeded") void command("refresh-analytics");
        } catch (error) {
          setOauthJobs((jobs) => ({ ...jobs, [index]: { id: job.id, state: "failed", message: humanCommandError(error) || "Не удалось проверить вход в Google." } }));
        }
      };
      window.setTimeout(() => void watch(), 1000);
    } catch (error) {
      setOauthJobs((jobs) => ({ ...jobs, [index]: { id: "", state: "failed", message: humanCommandError(error) || "Не удалось начать вход в Google." } }));
    }
  };
  const channelColumns = useMemo<ColumnDef<(typeof channels)[number]>[]>(
    () => [
      {
        id: "channel",
        header: "Канал",
        cell: ({ row }) => <div className="analytics-channel-identity">{row.original.thumbnailUrl ? <img src={row.original.thumbnailUrl} alt="" /> : <span>{row.original.name.slice(0, 1)}</span>}<div><b>{row.index + 1}. {row.original.name}</b><small>{row.original.subscribers || "—"} подписчиков</small></div></div>,
      },
      {
        id: "pulse",
        header: "Темп",
        cell: ({ row }) => <span>{row.original.viewsHour || "—"}<small>просмотров / час</small></span>,
      },
      {
        id: "last48",
        header: "48 часов",
        cell: ({ row }) => <span>{row.original.views48h || "—"}<small>за 48 часов</small></span>,
      },
      {
        id: "access",
        header: "Доступ",
        cell: ({ row }) => revenueKnown.has(row.original.id) ? "Доход доступен" : "Доход не подключён",
      },
      {
        id: "actions",
        header: "Операции",
        cell: ({ row }) => <div className="toolbar compact"><Button kind="primary" onClick={() => void connectChannel(row.original.index, false)}><KeyRound size={14} />OAuth</Button><Button onClick={() => void connectChannel(row.original.index, true)}>Доход</Button><Button onClick={() => void command("open-analytics-channel", { index: row.original.index })}><MonitorPlay size={14} />Studio</Button><Button kind="danger" onClick={() => { if (window.confirm(`Удалить канал «${row.original.name}» из NewsFlow? Сессия Chrome не будет удалена.`)) void command("remove-analytics-channel", { index: row.original.index }); }}><Trash2 size={14} />Удалить</Button></div>,
      },
    ],
    [command, connectChannel, revenueKnown],
  );
  return <div className="publication-modern analytics-modern nf-analytics-portfolio" aria-label="Channel Portfolio Workspace">
    <section className="publication-hero panel"><div><span className="eyebrow">АНАЛИТИКА YOUTUBE</span><h2>Понятная сводка по каналам</h2><p>Данные приходят из OAuth YouTube. Доход без доступа показывается как «нет доступа», а не как ноль.</p></div><div className="toolbar"><Button kind="success" onClick={() => void command("refresh-analytics")}><Activity size={16}/>Обновить данные</Button><Button kind="primary" onClick={() => setChannelFormOpen((open) => !open)}><Plus size={16}/>Добавить канал</Button></div></section>
    {channelFormOpen ? <section className="panel analytics-channel-form"><div className="panel-title"><div><b>Новый канал</b><small>Создайте строку, затем подключите YouTube через OAuth.</small></div></div><div className="analytics-add-channel-fields"><label>Название канала<input autoFocus value={newChannelName} onChange={(event) => setNewChannelName(event.target.value)} placeholder="Например: Новости мира" /></label><label>Ссылка на канал (необязательно)<input value={newChannelLink} onChange={(event) => setNewChannelLink(event.target.value)} placeholder="https://youtube.com/@channel" /></label><Button kind="primary" onClick={newChannelName.trim() ? addChannel : undefined}><Plus size={16}/>Создать канал</Button><Button onClick={() => setChannelFormOpen(false)}>Отмена</Button></div></section> : null}
    <section className="panel analytics-modern-filters"><label>Каналы<select multiple value={channelIds} onChange={(event) => setChannelIds(Array.from(event.target.selectedOptions, (option) => option.value))}>{channels.map((channel, index) => <option key={channel.id} value={channel.id}>{index + 1}. {channel.name}</option>)}</select></label><label>Период<select value={period} onChange={(event) => setPeriod(event.target.value as typeof period)}><option value="current">Текущий месяц</option><option value="previous">Прошлый месяц</option><option value="30">Последние 30 дней</option><option value="90">Последние 90 дней</option></select></label><label>Доход<select value={revenue} onChange={(event) => setRevenue(event.target.value as typeof revenue)}><option value="all">Все каналы</option><option value="available">Есть доступ к доходу</option><option value="missing">Нет доступа к доходу</option></select></label><Button onClick={() => setChannelIds([])}>Все каналы</Button></section>
    <section className="analytics-summary-grid"><article><small>Каналов в фильтре</small><b>{filteredChannels.length}</b></article><article><small>Просмотры</small><b>{totals.views.toLocaleString("ru-RU")}</b></article><article><small>Подписчики</small><b>{totals.subscribers.toLocaleString("ru-RU")}</b></article><article><small>Публикации</small><b>{totals.publications.toLocaleString("ru-RU")}</b></article><article><small>Часы просмотра</small><b>{watchHours.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}</b></article><article><small>Доход</small><b>{revenueKnown.size ? totals.revenue.toLocaleString("ru-RU", { style: "currency", currency: "USD" }) : "Нет доступа"}</b></article></section>
    <section className="panel analytics-channel-cards"><div className="panel-title"><div><b>Каналы и доступ</b><small>Каждая строка открывает собственный постоянный Chrome-профиль канала. OAuth проходит через Google и tinkbro, после чего токен сохраняется в NewsFlow.</small></div><span className="status">Обновлено: {data.analytics.updatedAt ? new Date(data.analytics.updatedAt).toLocaleString("ru-RU") : "ещё не было"}</span></div>{filteredChannels.length ? <DataTable ariaLabel="Каналы YouTube" data={filteredChannels} columns={channelColumns} expanded={(channel) => <div className="analytics-channel-details">{oauthJobs[channel.index]?.state === "waiting" ? <div className="oauth-channel-wait" role="status"><b>Ожидаем входа в Google</b><span>После страницы tinkbro токен будет забран автоматически.</span></div> : null}{oauthJobs[channel.index]?.state === "succeeded" ? <div className="oauth-channel-result succeeded" role="status"><b>Канал подключён</b><span>{oauthJobs[channel.index]?.message || "Токен получен, данные обновляются."}</span></div> : null}{oauthJobs[channel.index]?.state === "failed" ? <div className="oauth-channel-result failed" role="status"><b>Не удалось подключить канал</b><span>{oauthJobs[channel.index]?.message || "Повторите OAuth."}</span></div> : null}<ChannelMetadataEditor channel={channel} index={channel.index} command={command} /></div>} /> : <Empty title="Нет каналов по выбранному фильтру" text="Сбросьте фильтры или подключите новый канал."/>}</section>
  </div>;
}

function LegacyAnalyticsDashboard({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const [channelFilter, setChannelFilter] = useState("all");
  const [periodHours, setPeriodHours] = useState(720);
  const [oauthJobs, setOauthJobs] = useState<Record<number, { id: string; state: 'waiting' | 'succeeded' | 'failed' | 'cancelled'; message?: string }>>({});
  const [channelFormOpen, setChannelFormOpen] = useState(false);
  const [newChannelName, setNewChannelName] = useState("");
  const [newChannelLink, setNewChannelLink] = useState("");
  const addChannel = async () => {
    const result = await command("add-channel", {
      name: newChannelName,
      channel: newChannelLink,
    });
    if (result) {
      setNewChannelName("");
      setNewChannelLink("");
      setChannelFormOpen(false);
    }
  };
  const connectOAuth = () => window.alert("OAuth подключается локально через кнопку «Подключить YouTube» у нужного канала.");
  const connectChannel = async (index: number, includeMonetary: boolean) => {
    if (!data.analyticsOAuth.configured) {
      window.alert("Сначала настройте сервис входа Google.");
      return;
    }
    if (data.analyticsOAuth.mode !== 'cloudflare' || !window.newsflowDesktop?.startYoutubeOAuthHandoff) {
      void command("connect-youtube-channel", { index, includeMonetary });
      return;
    }
    const job = await window.newsflowDesktop.startYoutubeOAuthHandoff({ index, includeMonetary });
    setOauthJobs((current) => ({ ...current, [index]: { id: job.id, state: job.state, message: job.message } }));
    const watch = async () => {
      const current = await window.newsflowDesktop?.youtubeOAuthHandoffStatus(job.id);
      if (!current) return;
      setOauthJobs((jobs) => ({ ...jobs, [index]: { id: current.id, state: current.state, message: current.message } }));
      if (current.state === 'waiting') window.setTimeout(() => void watch(), 1500);
      if (current.state === 'succeeded') void command("refresh-analytics");
    };
    window.setTimeout(() => void watch(), 1000);
  };
  const channelOptions = data.channels.map((channel, index) => ({
    id: channel.id || channel.channel || channel.name || `channel-${index}`,
    name: channel.name || `Канал ${index + 1}`,
  }));
  const cutoff = Date.now() - periodHours * 60 * 60 * 1000;
  const selectedIds =
    channelFilter === "all"
      ? new Set(channelOptions.map((channel) => channel.id))
      : new Set([channelFilter]);
  const points = data.analytics.metricPoints.filter(
    (point) =>
      selectedIds.has(point.channelId) &&
      new Date(point.at).getTime() >= cutoff,
  );
  const totals = points.reduce(
    (sum, point) => ({
      views: sum.views + point.views,
      subscribers: sum.subscribers + (point.subscribers || 0),
      publications: sum.publications + (point.publications || 0),
      revenue: sum.revenue + (point.estimatedRevenue ?? 0),
    }),
    { views: 0, subscribers: 0, publications: 0, revenue: 0 },
  );
  const revenueChannels = new Set(
    points
      .filter(
        (point) =>
          point.estimatedRevenue !== null &&
          point.estimatedRevenue !== undefined,
      )
      .map((point) => point.channelId),
  );
  const missingRevenueChannels = [...selectedIds].filter(
    (id) => !revenueChannels.has(id),
  );
  const buckets = new Map<string, { at: string; views: number }>();
  points.forEach((point) => {
    const bucket = buckets.get(point.at) || { at: point.at, views: 0 };
    bucket.views += point.views;
    buckets.set(point.at, bucket);
  });
  const series = [...buckets.values()].sort((left, right) =>
    left.at.localeCompare(right.at),
  );
  const peak = Math.max(1, ...series.map((point) => point.views));
  const line = series
    .map(
      (point, index) =>
        `${series.length === 1 ? 50 : 6 + (index * 88) / (series.length - 1)},${94 - (point.views * 82) / peak}`,
    )
    .join(" ");
  const videoMetrics = data.analytics.videoMetrics.filter((metric) => selectedIds.has(metric.channelId));
  const jobsByVideoId = new Map(data.publication.jobs.filter((job) => job.videoId).map((job) => [job.videoId!, job]));
  return (
    <>
      {channelFormOpen ? (
        <section className="panel analytics-channel-form">
          <div className="panel-title">
            <div>
              <b>Добавить канал</b>
              <small>
                OAuth‑файл уже общий. После создания строки нажмите «OAuth» у
                нужного канала — NewsFlow сам подставит настоящее название,
                аватар и подписчиков.
              </small>
            </div>
          </div>
          <div className="analytics-channel-form-fields">
            <label>
              Временное название (необязательно)
              <input
                autoFocus
                value={newChannelName}
                onChange={(event) => setNewChannelName(event.target.value)}
                placeholder="Например: Взгляд сверху"
              />
            </label>
            <label>
              Ссылка на канал или YouTube Studio (необязательно)
              <input
                value={newChannelLink}
                onChange={(event) => setNewChannelLink(event.target.value)}
                placeholder="https://youtube.com/@..."
              />
            </label>
          </div>
          <div className="toolbar">
            <Button kind="primary" onClick={() => void addChannel()}>
              <Plus size={16} />
              Создать строку канала
            </Button>
            <Button onClick={() => setChannelFormOpen(false)}>Отмена</Button>
          </div>
        </section>
      ) : null}
      <div className="toolbar">
        <Button
          kind="success"
          onClick={() => void command("refresh-analytics")}
        >
          <Activity size={17} />
          Обновить данные
        </Button>
        <Button onClick={() => void connectOAuth()}>
          <KeyRound size={17} />
          {data.analyticsOAuth.configured ? "Сервис входа готов" : "Настроить сервис входа"}
        </Button>
        <Button kind="primary" onClick={() => setChannelFormOpen(true)}>
          <Plus size={17} />
          Добавить канал
        </Button>
      </div>
      <section className="panel analytics-oauth">
        <div className="panel-title">
          <div>
            <b>Google OAuth и постоянные сессии каналов</b>
            <small>
              {data.analyticsOAuth.mode === 'cloudflare'
                ? "Вход завершается через защищённый сервис. Токен каждого канала остаётся локально в NewsFlow."
                : "Настройте сервис входа. До подключения здесь не будет вымышленных показателей."}
            </small>
          </div>
          <span
            className={
              data.analyticsOAuth.configured ? "status oauth-ready" : "status"
            }
          >
            {data.analyticsOAuth.configured
              ? "Сервис входа готов"
              : "Сервис входа не настроен"}
          </span>
        </div>
        <ol className="oauth-steps" aria-label="Подключение канала">
          <li><b>1. Создайте строку канала</b><span>Она получит собственный профиль Chrome.</span></li>
          <li><b>2. Подключите YouTube</b><span>Войдите в Google в открывшемся отдельном профиле.</span></li>
          <li><b>3. Обновите данные</b><span>NewsFlow покажет фактические название, аватар и подписчиков.</span></li>
        </ol>
      </section>
      <section className="panel analytics-video-level">
        <div className="panel-title">
          <div>
            <b>Ролики и темы</b>
            <small>Метрики привязаны к опубликованному ролику, его сценарию и SEO-пакету.</small>
          </div>
          <span className="status">{videoMetrics.length} роликов с метриками</span>
        </div>
        {videoMetrics.length ? <div className="analytics-video-grid">
          {videoMetrics.map((metric) => {
            const job = jobsByVideoId.get(metric.videoId);
            return <article key={`${metric.channelId}-${metric.videoId}`}>
              {job?.thumbnailPath ? <img src={`file://${job.thumbnailPath}`} alt={`Обложка: ${job.title}`} width={48} height={48} loading="lazy" /> : <span className="analytics-video-cover">▶</span>}
              <div><b>{job?.scriptName || job?.title || metric.videoId}</b><small>{job?.seoTitle || "SEO пока не связано"}</small></div>
              <span>{Number(metric.views || 0).toLocaleString("ru-RU")} просмотров</span>
              <span>{metric.impressionsClickThroughRate === undefined ? "CTR ещё нет" : `CTR ${Number(metric.impressionsClickThroughRate).toFixed(1)}%`}</span>
              <span>{metric.averageViewPercentage === undefined ? "Удержание ещё нет" : `${Number(metric.averageViewPercentage).toFixed(1)}% досмотра`}</span>
              <span>{metric.financialAvailable ? "Доход доступен" : "Доход: нужен отдельный доступ"}</span>
            </article>;
          })}
        </div> : <Empty title="Пока нет данных по роликам" text="После OAuth и первого обновления здесь появятся реальные ролики; отсутствие дохода не будет показано как ноль." />}
      </section>
      <section className="panel analytics-overview">
        <div className="panel-title">
          <div>
            <b>Сводка и графики</b>
            <small>
              Фильтры меняют и карточки, и линию просмотров.{" "}
              {data.analytics.updatedAt
                ? `Последнее обновление: ${new Date(data.analytics.updatedAt).toLocaleString("ru-RU")}.`
                : "Измерений пока нет."}
            </small>
          </div>
        </div>
        <div className="analytics-filters">
          <label>
            Каналы
            <select
              value={channelFilter}
              onChange={(event) => setChannelFilter(event.target.value)}
            >
              <option value="all">Все каналы</option>
              {channelOptions.map((channel) => (
                <option key={channel.id} value={channel.id}>
                  {channel.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Период
            <select
              value={periodHours}
              onChange={(event) => setPeriodHours(Number(event.target.value))}
            >
              <option value={1}>1 час</option>
              <option value={24}>24 часа</option>
              <option value={48}>48 часов</option>
              <option value={168}>7 дней</option>
              <option value={672}>28 дней</option>
              <option value={720}>30 дней</option>
            </select>
          </label>
        </div>
        <div className="analytics-metric-cards">
          <div>
            <small>Просмотры</small>
            <b>{totals.views.toLocaleString("ru-RU")}</b>
          </div>
          <div>
            <small>Подписчики</small>
            <b>{totals.subscribers.toLocaleString("ru-RU")}</b>
          </div>
          <div>
            <small>Публикации</small>
            <b>{totals.publications.toLocaleString("ru-RU")}</b>
          </div>
          <div>
            <small>Доход</small>
            <b>
              {revenueChannels.size
                ? totals.revenue.toLocaleString("ru-RU", {
                    style: "currency",
                    currency: "USD",
                  })
                : "Нет доступа"}
            </b>
            <em>
              {missingRevenueChannels.length
                ? `Доступен не для ${missingRevenueChannels.length} кан.`
                : "Все выбранные каналы с доступом"}
            </em>
          </div>
        </div>
        <div className="analytics-chart">
          <div>
            <b>Просмотры по измерениям</b>
            <small>
              {series.length
                ? `Пик: ${peak.toLocaleString("ru-RU")}`
                : "После OAuth и первого обновления здесь появится фактическая линия."}
            </small>
          </div>
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-label="График просмотров"
          >
            <line x1="0" y1="94" x2="100" y2="94" />
            <polyline points={line} />
          </svg>
        </div>
      </section>
      <section className="panel table-wrap analytics-table">
        <div className="table-head">
          <span>КАНАЛ</span>
          <span>ПОДПИСЧИКИ</span>
          <span>1 ЧАС</span>
          <span>48 ЧАСОВ</span>
          <span>ДОХОД</span>
          <span>СТАТУС / ДЕЙСТВИЯ</span>
        </div>
        {data.channels.length ? (
          <div className="analytics-list">
            {data.channels.map((channel, index) => (
              <div key={`${channel.id || channel.name}-${index}`}>
                <div className="analytics-channel-identity">
                  {channel.thumbnailUrl ? (
                    <img src={channel.thumbnailUrl} alt="" />
                  ) : (
                    <span>
                      {(channel.name || "К").slice(0, 1).toUpperCase()}
                    </span>
                  )}
                  <b>
                    {channel.name}
                    <small>{channel.channel || "Ссылка не задана"}</small>
                  </b>
                </div>
                <span>{channel.subscribers}</span>
                <span>{channel.viewsHour || "—"}</span>
                <span>{channel.views48h || "—"}</span>
                <span>{channel.income || "—"}</span>
                <div>
                  <small>{channel.status}</small>
                  {channel.oauthAccountEmail ? <small>Google: {channel.oauthAccountEmail}</small> : null}
                  <ChannelMetadataEditor
                    channel={channel}
                    index={index}
                    command={command}
                  />
                  <Button kind="primary" onClick={() => void connectChannel(index, false)}>
                    <KeyRound size={14} />
                    Подключить YouTube
                  </Button>
                  <Button onClick={() => void connectChannel(index, true)}>
                    <KeyRound size={14} />
                    Доход
                  </Button>
                  {oauthJobs[index]?.state === 'waiting' ? <div className="oauth-channel-wait" role="status" aria-live="polite">
                    <span>Этот канал → Google → Данные YouTube</span>
                    <b>Ожидаем подтверждение в Google</b>
                    <Button onClick={() => void window.newsflowDesktop?.cancelYoutubeOAuthHandoff(oauthJobs[index].id).then((job) => setOauthJobs((jobs) => ({ ...jobs, [index]: { id: job.id, state: job.state, message: job.message } })))}>
                      Отменить вход
                    </Button>
                  </div> : null}
                  {oauthJobs[index] && oauthJobs[index].state !== 'waiting' ? <div className={`oauth-channel-result ${oauthJobs[index].state}`} role="status" aria-live="polite">
                    {oauthJobs[index].message || "Вход завершён"}
                  </div> : null}
                  <Button
                    onClick={() =>
                      void command("open-analytics-channel", { index })
                    }
                  >
                    <MonitorPlay size={14} />
                    Открыть Studio
                  </Button>
                  {channel.oauthConnected ? <Button
                    onClick={() => void command("reset-youtube-channel-account", { index })}
                  >
                    <KeyRound size={14} />
                    Сменить Google-аккаунт
                  </Button> : null}
                  <Button
                    kind="danger"
                    onClick={() =>
                      void command("remove-analytics-channel", { index })
                    }
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty
            title="Добавьте YouTube-канал"
            text="Для каждого канала NewsFlow создаёт отдельный постоянный профиль Chrome. Сессия не очистится после перезапуска приложения."
          />
        )}
      </section>
    </>
  );
}

function SessionUsagePanel({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const stages: Array<
    [keyof NewsFlowSnapshot["chromeSessions"][number]["usage"], string]
  > = [
    ["ideas", "Идеи"],
    ["scenarios", "Сценарии"],
    ["covers", "Обложки"],
    ["seo", "SEO"],
  ];
  if (!data.chromeSessions.length) return null;
  return (
    <section className="panel session-usage">
      <div className="panel-title">
        <div>
          <b>Назначение профилей</b>
          <small>
            Chrome-профили нужны для YouTube, сервисов озвучки и ручной работы в
            браузере. Текстовые агенты NewsFlow используют активный API-ключ
            ChatGPT, а не браузерные чаты.
          </small>
        </div>
      </div>
      <div className="usage-table">
        <div className="usage-head">
          <span>Сессия</span>
          {stages.map(([, label]) => (
            <span key={label}>{label}</span>
          ))}
        </div>
        {data.chromeSessions.map((session, index) => (
          <div className="usage-row" key={`${session.label}-${index}`}>
            <b>{session.label}</b>
            {stages.map(([stage, label]) => (
              <label key={stage} title={`${session.label}: ${label}`}>
                <input
                  type="checkbox"
                  checked={Boolean(session.usage?.[stage])}
                  onChange={(event) =>
                    void command("set-session-usage", {
                      index,
                      stage,
                      enabled: event.target.checked,
                    })
                  }
                />
                <span>{session.usage?.[stage] ? "Вкл." : "Выкл."}</span>
              </label>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

export function Sessions({
  data,
  command,
}: {
  data: NewsFlowSnapshot;
  command: Command;
}) {
  const [sessionDialogOpen, setSessionDialogOpen] = useState(false);
  const [sessionLabel, setSessionLabel] = useState("");
  const add = () => {
    setSessionLabel("");
    setSessionDialogOpen(true);
  };
  const confirmAddSession = async () => {
    const label = sessionLabel.trim();
    if (!label) return;
    const result = await command("add-session", { label });
    if (result) {
      setSessionDialogOpen(false);
      setSessionLabel("");
    }
  };
  return (
    <div className="nf-settings nf-structured-settings" aria-label="Structured settings: sessions">
      <Dialog
        open={sessionDialogOpen}
        onOpenChange={(open) => {
          setSessionDialogOpen(open);
          if (!open) setSessionLabel("");
        }}
        title="Добавить Chrome-сессию"
        description="Создайте отдельный постоянный профиль авторизации."
      >
        <Input
          label="Название Chrome-сессии"
          value={sessionLabel}
          onChange={(event) => setSessionLabel(event.target.value)}
          autoFocus
        />
        <div className="toolbar">
          <Button onClick={() => setSessionDialogOpen(false)}>Отмена</Button>
          <Button kind="primary" onClick={() => void confirmAddSession()} disabled={!sessionLabel.trim()}>
            Создать сессию
          </Button>
        </div>
      </Dialog>
      <SessionUsagePanel data={data} command={command} />
      <div className="toolbar">
        <Button kind="primary" onClick={add}>
          <Plus size={17} />
          Добавить сессию
        </Button>
      </div>
      <section className="panel sessions">
        <div className="panel-title">
          <div>
            <b>Постоянные Chrome‑сессии</b>
            <small>
              Профили сохраняются в NewsFlow и не очищаются после перезапуска.
            </small>
          </div>
        </div>
        {data.chromeSessions.length ? (
          <div className="session-list">
            {data.chromeSessions.map((session, index) => (
              <div key={`${session.label}-${index}`}>
                <span
                  className={
                    session.active ? "session-dot active" : "session-dot"
                  }
                />
                <div>
                  <b>{session.label}</b>
                  <small>
                    {session.limitStatus === "exhausted"
                      ? "Лимит закончился"
                      : "Лимит активен"}
                  </small>
                </div>
                <Button
                  onClick={() => void command("open-chrome-session", { index })}
                >
                  <MonitorPlay size={15} />
                  Войти
                </Button>
                <Button
                  onClick={() =>
                    void command("set-session-active", {
                      index,
                      active: !session.active,
                    })
                  }
                >
                  {session.active ? "Выключить" : "Включить"}
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <Empty
            title="Добавьте Chrome-сессию"
            text="Для каждого профиля создаётся отдельное постоянное хранилище авторизации."
          />
        )}
      </section>
    </div>
  );
}
export function Keys({
  data,
  command,
  onDirtyChange,
  onSaveRequest,
}: {
  data: NewsFlowSnapshot;
  command: Command;
  onDirtyChange?: (dirty: boolean) => void;
  onSaveRequest?: (save: (() => Promise<boolean>) | null) => void;
}) {
  const [kind, setKind] = useState<
    "fastgen" | "openai" | "voicer" | "lumean" | "voicegen" | "wproject" | "youtube"
  >("fastgen");
  const [adding, setAdding] = useState(false);
  const [label, setLabel] = useState("");
  const [secret, setSecret] = useState("");
  const [formError, setFormError] = useState("");
  const [keyDirty, setKeyDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [discardKeyOpen, setDiscardKeyOpen] = useState(false);
  const [editingKey, setEditingKey] = useState<{ index: number; fingerprint: string; revision: string } | null>(null);
  const [secretVisible, setSecretVisible] = useState(false);
  const [loadingKey, setLoadingKey] = useState(false);
  const keyOperation = useRef(false);
  const keyRequest = useRef(0);
  useEffect(() => () => { keyRequest.current += 1; }, []);
  const titles = {
    fastgen: "FastGen",
    openai: "OpenAI / ChatGPT",
    voicer: "Secret Voicer",
    lumean: "Lumean",
    voicegen: "VoiceGen",
    wproject: "WProject",
    youtube: "YouTube Data API",
  };
  const defaultLabel = (nextKind = kind) =>
    nextKind === "fastgen"
      ? "FastGen основной"
      : nextKind === "openai"
        ? "ChatGPT основной"
        : nextKind === "voicer"
          ? "Secret Voicer основной"
          : nextKind === "lumean"
            ? "Lumean основной"
          : nextKind === "voicegen"
            ? "VoiceGen основной"
            : nextKind === "wproject"
              ? "WProject основной"
            : "YouTube Data API";
  const markKeyDirty = () => {
    setKeyDirty(true);
    onDirtyChange?.(true);
  };
  const openAdd = () => {
    if (keyOperation.current || adding) return;
    setEditingKey(null);
    setSecretVisible(false);
    setLabel(defaultLabel());
    setSecret("");
    setFormError("");
    setKeyDirty(false);
    onDirtyChange?.(false);
    setAdding(true);
  };
  const openEdit = async (index: number, fingerprint: string) => {
    if (keyOperation.current || adding) return;
    keyOperation.current = true;
    setLoadingKey(true);
    setFormError("");
    const requestId = ++keyRequest.current;
    try {
      const result = await window.newsflowDesktop?.revealApiKey({ kind, index, fingerprint });
      if (requestId !== keyRequest.current) return;
      if (!result || typeof result.secret !== "string" || typeof result.label !== "string" || typeof result.revision !== "string") throw new Error();
      setEditingKey({ index, fingerprint, revision: result.revision });
      setLabel(result.label);
      setSecret(result.secret);
      setSecretVisible(false);
      setKeyDirty(false);
      setAdding(true);
    } catch {
      if (requestId === keyRequest.current) setFormError("Не удалось открыть ключ. Обновите список и попробуйте снова.");
    } finally {
      keyOperation.current = false;
      if (requestId === keyRequest.current) setLoadingKey(false);
    }
  };
  const closeAdd = () => {
    if (keyDirty) {
      setDiscardKeyOpen(true);
      return;
    }
    setSecret("");
    setSecretVisible(false);
    setEditingKey(null);
    setAdding(false);
  };
  const discardAdd = () => {
    setDiscardKeyOpen(false);
    setKeyDirty(false);
    onDirtyChange?.(false);
    setSecret("");
    setSecretVisible(false);
    setEditingKey(null);
    setFormError("");
    setAdding(false);
  };
  const changeKind = (nextKind: typeof kind) => {
    setKind(nextKind);
    if (adding) setLabel(defaultLabel(nextKind));
  };
  const save = async () => {
    if (keyOperation.current) return false;
    if (!secret.trim()) {
      setFormError("Вставьте API-ключ.");
      return false;
    }
    keyOperation.current = true;
    setSaving(true);
    let result: NewsFlowSnapshot | undefined;
    try {
      result = await command(editingKey ? "update-api-key" : "add-api-key", {
        kind,
        ...(editingKey || {}),
        label: label.trim() || defaultLabel(),
        secret: secret.trim(),
      });
    } catch {
      // Do not render arbitrary transport errors beside a secret input.
      result = undefined;
    } finally {
      keyOperation.current = false;
      setSaving(false);
    }
    if (result) {
      setSecret("");
      setSecretVisible(false);
      setEditingKey(null);
      setKeyDirty(false);
      onDirtyChange?.(false);
      setAdding(false);
      setFormError("");
      return true;
    }
    setFormError("Не удалось сохранить API-ключ. Форма остаётся открытой.");
    return false;
  };
  useEffect(() => onDirtyChange?.(adding && keyDirty), [adding, keyDirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => {
    onSaveRequest?.(() => saveRef.current());
    return () => onSaveRequest?.(null);
  }, [onSaveRequest]);
  const services: Array<{ kind: typeof kind; title: string; purpose: string }> =
    [
      {
        kind: "fastgen",
        title: "FastGen",
        purpose: "обложки, изображения и видео",
      },
      {
        kind: "openai",
        title: "OpenAI / ChatGPT",
        purpose: "идеи, сценарии, SEO и монтажный план",
      },
      { kind: "voicer", title: "Secret Voicer", purpose: "озвучка сценариев" },
      {
        kind: "lumean",
        title: "Lumean",
        purpose: "озвучка: каталог голосов, модели и заказ через API",
      },
      {
        kind: "voicegen",
        title: "VoiceGen",
        purpose: "озвучка: V3, личные голоса, пресеты и очередь задач",
      },
      {
        kind: "wproject",
        title: "WProject",
        purpose: "озвучка: асинхронные задачи W-Voice, голоса и лимиты",
      },
      {
        kind: "youtube",
        title: "YouTube Data API",
        purpose: "поиск, статистика и анализ каналов",
      },
    ];
  const apiOverview = (
    <section className="panel key-panel">
      <div className="panel-title">
        <div>
          <b>Все подключённые API</b>
          <small>
            Все добавленные сервисы видны одновременно. Секреты остаются
            зашифрованными; отображаются метки, состояние и данные лимита, если
            API их отдаёт.
          </small>
        </div>
        <span className="status">
          {services.reduce(
            (total, service) => total + data.keyStatus[service.kind].length,
            0,
          )}{" "}
          ключей
        </span>
      </div>
      <div className="key-list">
        {services.map((service) => (
          <div key={service.kind}>
            <KeyRound size={17} />
            <span>
              <b>{service.title}</b>
              <small>
                {service.purpose} ·{" "}
                {data.keyStatus[service.kind].length
                  ? data.keyStatus[service.kind]
                      .map(
                        (key) =>
                          `${key.label} (${key.active ? "активен" : "выключен"}${key.balance ? ` · ${key.balance}` : ""})`,
                      )
                      .join(" · ")
                  : "ключ не добавлен"}
              </small>
            </span>
            <Button disabled={adding || loadingKey} onClick={() => changeKind(service.kind)}>Управлять</Button>
          </div>
        ))}
      </div>
    </section>
  );
  return (
    <div className="nf-settings nf-structured-settings" aria-label="Structured settings: API keys">
      {apiOverview}
      <div className="toolbar">
        <select
          disabled={adding || loadingKey}
          value={kind}
          onChange={(event) => changeKind(event.target.value as typeof kind)}
        >
          <option value="fastgen">FastGen</option>
          <option value="openai">OpenAI / ChatGPT</option>
          <option value="voicer">Secret Voicer</option>
          <option value="lumean">Lumean</option>
          <option value="voicegen">VoiceGen</option>
          <option value="wproject">WProject</option>
          <option value="youtube">YouTube Data API</option>
        </select>
        <Button kind="primary" disabled={adding || loadingKey} onClick={openAdd}>
          <KeyRound size={17} />
          Добавить ключ
        </Button>
      </div>
      {adding ? (
        <section className="panel key-add-form">
          <div className="panel-title">
            <div>
              <b>{editingKey ? "Редактировать ключ" : "Новый ключ"} {titles[kind]}</b>
              <small>
                Секрет сохраняется зашифрованным в профиле Windows.
                Просмотр — только по вашему запросу.
              </small>
            </div>
            <Button disabled={saving} onClick={closeAdd}>Отмена</Button>
          </div>
          <div className="key-add-fields">
            <label>
              Название ключа
              <input
                disabled={kind === "youtube" || saving}
                value={label}
                onChange={(event) => {
                  setLabel(event.target.value);
                  markKeyDirty();
                }}
                placeholder={defaultLabel()}
              />
            </label>
            <label>
              API-ключ
              <input
                autoFocus
                type={secretVisible ? "text" : "password"}
                autoComplete="off"
                spellCheck={false}
                disabled={saving}
                value={secret}
                onChange={(event) => {
                  setSecret(event.target.value);
                  setFormError("");
                  markKeyDirty();
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void save();
                }}
                placeholder="Вставьте ключ сюда"
              />
            </label>
            <Button onClick={() => setSecretVisible((value) => !value)}>
              {secretVisible ? "Скрыть ключ" : "Показать ключ"}
            </Button>
            <Button kind="primary" onClick={saving ? undefined : () => void save()}>
              <Check size={16} />
              {saving ? "Сохранение…" : "Сохранить ключ"}
            </Button>
          </div>
          {kind === "youtube" ? (
            <small className="youtube-key-note">
              Нужен ключ проекта с включённым YouTube Data API v3. Он
              используется для поиска и публичной статистики роликов.
            </small>
          ) : null}
        </section>
      ) : null}
      {formError ? <div role="alert" className="key-form-error">{formError}</div> : null}
      <section className="panel key-panel">
        <div className="panel-title">
          <div>
            <b>Управление: {titles[kind]}</b>
            <small>
              Лимит или баланс показывается, когда выбранный API возвращает эти
              данные. Для Lumean обновите каталог и лимиты в «Голоса и API».
            </small>
          </div>
        </div>
        {data.keyStatus[kind].length ? (
          <div className="key-list">
            {data.keyStatus[kind].map((key, index) => (
              <div key={`${key.label}-${index}`}>
                <KeyRound size={17} />
                <span>
                  <b>
                    {key.label} · ID {key.fingerprint || "—"}
                  </b>
                  <small>
                    {key.active ? "Активен" : "Выключен"}
                    {key.balance
                      ? ` · лимит/баланс: ${key.balance}`
                      : key.balanceStatus && key.balanceStatus !== "not_checked"
                        ? ` · ${key.balanceStatus}`
                        : ""}
                  </small>
                  <input
                    defaultValue={key.note || ""}
                    placeholder="Заметка к этому ключу"
                    onBlur={(event) =>
                      void command("save-api-key-note", {
                        kind,
                        index,
                        note: event.target.value,
                      })
                    }
                  />
                </span>
                <Button disabled={adding || loadingKey} ariaLabel={`Редактировать ключ ${key.label}`}
                  onClick={() => void openEdit(index, key.fingerprint || "")}>
                  Редактировать
                </Button>
                <Button
                  onClick={() =>
                    void command("set-key-active", {
                      kind,
                      index,
                      active: !key.active,
                    })
                  }
                >
                  {key.active ? "Выключить" : "Включить"}
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <Empty
            title={`Добавьте ключ ${titles[kind]}`}
            text="Ключ используется только выбранным провайдером и сохраняется зашифрованным."
          />
        )}
      </section>
      <Dialog
        open={discardKeyOpen}
        onOpenChange={setDiscardKeyOpen}
        title="Несохранённый API-ключ"
        description="Введённый секрет ещё не был отправлен в защищённое хранилище. Сохраните его или отбросьте форму."
      >
        <div className="nf-dialog-actions">
          <UiButton variant="secondary" onClick={() => setDiscardKeyOpen(false)}>
            Продолжить редактирование
          </UiButton>
          <UiButton variant="destructive" onClick={discardAdd}>
            Не сохранять
          </UiButton>
          <UiButton variant="primary" onClick={() => void save()}>
            Сохранить ключ
          </UiButton>
        </div>
      </Dialog>
    </div>
  );
}

export function Agents({
  data,
  go,
}: {
  data: NewsFlowSnapshot;
  go: (page: Page) => void;
}) {
  const ready = data.keyStatus.openai.some((key) => key.active);
  const agents: Array<{
    title: string;
    text: string;
    action: string;
    page: Page;
    icon: typeof Newspaper;
  }> = [
    {
      title: "Сценарист",
      text: "Пишет новостной сценарий по выбранной идее или вашему шаблону.",
      action: "Открыть сценарии",
      page: "scenarios",
      icon: Newspaper,
    },
    {
      title: "Редактор SEO",
      text: "Собирает заголовок, описание, теги и хештеги для готового текста.",
      action: "Открыть SEO",
      page: "seo",
      icon: Search,
    },
    {
      title: "Агент обложек",
      text: "Делает промпт, варианты изображения и оставляет лучший вариант в проекте.",
      action: "Открыть обложки",
      page: "covers",
      icon: Image,
    },
    {
      title: "Агент футажей",
      text: "Ищет сначала в ваших папках, затем предлагает подходящие интернет-источники.",
      action: "Открыть футажи",
      page: "footage",
      icon: Video,
    },
  ];
  const agentColumns: ColumnDef<(typeof agents)[number]>[] = [
    {
      id: "capability",
      header: "Возможность",
      cell: ({ row }) => {
        const Icon = row.original.icon;
        return <span className="nf-agent-capability"><Icon size={16} />{row.original.title}</span>;
      },
    },
    { accessorKey: "text", header: "Роль в выпуске" },
    {
      id: "route",
      header: "Рабочая зона",
      cell: ({ row }) => <Button onClick={() => go(row.original.page)}>{row.original.action}</Button>,
    },
  ];
  return (
    <section className="nf-agent-workspace" aria-label="Editorial agent workspace">
      <section className="panel agent-intro">
        <div className="panel-title">
          <div>
            <span className="nf-eyebrow">EDITORIAL ROUTING</span>
            <b>Рабочие агенты</b>
            <small>
              {ready
                ? "Активный ключ ChatGPT найден — агенты готовы генерировать."
                : "Сначала добавьте активный ключ ChatGPT: агенты используют его вместо браузерных чатов."}
            </small>
          </div>
          <Button kind="primary" onClick={() => go("keys")}>
            <KeyRound size={16} />
            Ключи ChatGPT
          </Button>
        </div>
      </section>
      <section className="panel nf-agent-capabilities">
        <div className="panel-title">
          <div>
            <b>Маршрутизация редакции</b>
            <small>Откройте нужную рабочую зону; запусков и фоновых задач на этой странице нет.</small>
          </div>
          <span className={ready ? "status oauth-ready" : "status"}>{ready ? "AI-ready" : "Нужен ключ"}</span>
        </div>
        <DataTable ariaLabel="Возможности агентов" data={agents} columns={agentColumns} />
      </section>
    </section>
  );
}

export function Knowledge({
  data,
  command,
  onDirtyChange,
  onSaveRequest,
}: {
  data: NewsFlowSnapshot;
  command: Command;
  onDirtyChange?: (dirty: boolean) => void;
  onSaveRequest?: (save: (() => Promise<boolean>) | null) => void;
}) {
  const [vaultPath, setVaultPath] = useState(data.obsidian.vaultPath);
  const [mcpUrl, setMcpUrl] = useState(data.obsidian.mcpUrl);
  const [token, setToken] = useState("");
  const [syncEnabled, setSyncEnabled] = useState(data.obsidian.syncEnabled);
  const [savedVaultPath, setSavedVaultPath] = useState(data.obsidian.vaultPath);
  const [savedMcpUrl, setSavedMcpUrl] = useState(data.obsidian.mcpUrl);
  const [savedSyncEnabled, setSavedSyncEnabled] = useState(data.obsidian.syncEnabled);
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const dirty = vaultPath !== savedVaultPath || mcpUrl !== savedMcpUrl || token !== "" || syncEnabled !== savedSyncEnabled;
  useEffect(() => {
    if (dirty || saving) return;
    setVaultPath(data.obsidian.vaultPath);
    setMcpUrl(data.obsidian.mcpUrl);
    setSyncEnabled(data.obsidian.syncEnabled);
    setSavedVaultPath(data.obsidian.vaultPath);
    setSavedMcpUrl(data.obsidian.mcpUrl);
    setSavedSyncEnabled(data.obsidian.syncEnabled);
  }, [data.obsidian.mcpUrl, data.obsidian.syncEnabled, data.obsidian.vaultPath, dirty, saving]);
  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  const chooseVault = async () => {
    const path = await window.newsflowDesktop?.chooseFolder();
    if (path) setVaultPath(path);
  };
  const save = async () => {
    if (saving || !dirty) return !dirty;
    setSaving(true);
    setSaveFailed(false);
    const result = await command("save-obsidian-settings", {
      vaultPath,
      mcpUrl,
      token,
      syncEnabled,
    });
    setSaving(false);
    if (!result) {
      setSaveFailed(true);
      return false;
    }
    setSavedVaultPath(vaultPath);
    setSavedMcpUrl(mcpUrl);
    setSavedSyncEnabled(syncEnabled);
    setToken("");
    return true;
  };
  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => {
    onSaveRequest?.(() => saveRef.current());
    return () => onSaveRequest?.(null);
  }, [onSaveRequest]);
  return (
    <div className="nf-settings knowledge-layout">
      <section className="panel">
        <div className="panel-title">
          <div>
            <b>Obsidian и папка заметок</b>
            <small>
              NewsFlow может выгружать идеи и материалы производства в Markdown
              прямо в ваш vault.
            </small>
          </div>
          <span
            className={
              data.obsidian.mcpConfigured ? "status oauth-ready" : "status"
            }
          >
            {data.obsidian.mcpConfigured ? "MCP настроен" : "Локальный режим"}
          </span>
        </div>
        <div className="knowledge-form">
          <label>
            Папка Obsidian vault
            <div className="inline-control">
              <input
                value={vaultPath}
                onChange={(event) => setVaultPath(event.target.value)}
                placeholder="Выберите папку vault"
              />
              <Button onClick={() => void chooseVault()}>
                <FolderOpen size={15} />
                Выбрать
              </Button>
            </div>
          </label>
          <label>
            Адрес локального Vault MCP{" "}
            <input
              value={mcpUrl}
              onChange={(event) => setMcpUrl(event.target.value)}
              placeholder="http://127.0.0.1:3000/mcp"
            />
          </label>
          <label>
            Токен MCP{" "}
            <input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              type="password"
              placeholder="Оставьте пустым, чтобы не менять сохранённый токен"
            />
          </label>
          <label className="favorite-toggle">
            <input
              type="checkbox"
              checked={syncEnabled}
              onChange={(event) => setSyncEnabled(event.target.checked)}
            />
            Разрешить экспорт заметок NewsFlow в выбранный vault
          </label>
        </div>
        <div className="knowledge-actions">
          <Button kind="primary" onClick={saving || !dirty ? undefined : () => void save()}>
            <Check size={16} />
            {saving ? "Сохранение…" : "Сохранить подключение"}
          </Button>
          <Button onClick={() => void command("test-obsidian-mcp")}>
            <Activity size={16} />
            Проверить MCP
          </Button>
          <Button
            kind="success"
            onClick={() => void command("export-obsidian-notes")}
          >
            <Download size={16} />
            Выгрузить заметки
          </Button>
        </div>
        {data.obsidianStatus ? (
          <div className="knowledge-status">{data.obsidianStatus}</div>
        ) : null}
        {saveFailed ? <div className="knowledge-status" role="alert">Не удалось сохранить подключение Obsidian. Черновик остаётся открытым.</div> : null}
      </section>
      <aside className="panel knowledge-note">
        <div className="panel-title">
          <div>
            <b>Как это работает</b>
            <small>Подключение остаётся только на вашем компьютере.</small>
          </div>
        </div>
        <div className="step">
          <b>1</b>
          <span>Выберите существующую папку Obsidian vault.</span>
        </div>
        <div className="step">
          <b>2</b>
          <span>
            Если установите Vault MCP-плагин в Obsidian, укажите его локальный
            адрес и токен.
          </span>
        </div>
        <div className="step">
          <b>3</b>
          <span>
            Нажмите «Выгрузить заметки»: идеи и сценарии появятся в{" "}
            <b>NewsFlow</b> внутри vault.
          </span>
        </div>
      </aside>
    </div>
  );
}
