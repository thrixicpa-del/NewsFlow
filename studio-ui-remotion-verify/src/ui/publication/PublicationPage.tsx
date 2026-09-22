import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Clock3, RefreshCw, Undo2 } from "lucide-react";
import { Tabs } from "../components/tabs";
import { UiButton } from "../components/button";
import { ChannelSettingsSheet } from "./ChannelSettingsSheet";
import { ChannelsTable } from "./ChannelsTable";
import { DistributionTable } from "./DistributionTable";
import { DistributionHealth, PublicationDayPlan } from "./PublicationDayPlan";
import { PublicationHeader } from "./PublicationHeader";
import { PublicationHistory } from "./PublicationHistory";
import { PublicationQueue } from "./PublicationQueue";
import { VideosTable } from "./VideosTable";
import { buildPublicationView } from "./view-model";
import type { ChannelRow, DistributionRow, PublicationCommand, PublicationTab, QueueRow } from "./types";
import "./publication-ui.css";

type Preview = {
  assignments: Array<{
    productionItemId: string;
    channelId: string;
    source: string;
    locked: boolean;
    reason: string;
    publishAt?: string;
    scheduleWarning?: string;
    scheduleSuggestion?: string;
  }>;
};
type BulkSchedule = {
  date: string;
  startTime: string;
  endTime: string;
  timezone: string;
  channelIds: string[];
  maxPerChannel: number;
};

const uploadableStatuses = new Set(["READY", "WAITING", "RETRYING", "SCHEDULED"]);

function queueFromSnapshot(state: NewsFlowSnapshot | undefined): QueueRow[] {
  const raw = (state?.publication as any)?.v2?.queue;
  return Array.isArray(raw) ? raw as QueueRow[] : [];
}

export function PublicationPage({ data, command }: { data: NewsFlowSnapshot; command: PublicationCommand }) {
  const model = useMemo(() => buildPublicationView(data), [data]);
  const [tab, setTab] = useState<PublicationTab>("videos");
  const [rules, setRules] = useState(model.channels);
  const [editingChannel, setEditingChannel] = useState<ChannelRow | null>(null);
  const [distribution, setDistribution] = useState<DistributionRow[]>([]);
  const [distributionHistory, setDistributionHistory] = useState<DistributionRow[][]>([]);
  const [selectedVideoIds, setSelectedVideoIds] = useState<string[]>([]);
  const [presetName, setPresetName] = useState("");
  const [selectedPresetName, setSelectedPresetName] = useState("");
  const [planVersionName, setPlanVersionName] = useState("");
  const [selectedPlanVersionId, setSelectedPlanVersionId] = useState("");
  const [uploadConcurrency, setUploadConcurrency] = useState(model.uploadConcurrency);
  const [uploadStarting, setUploadStarting] = useState(false);
  const [continuing, setContinuing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [bulkSchedule, setBulkSchedule] = useState<BulkSchedule>(() => ({
    date: "",
    startTime: "04:00",
    endTime: "10:00",
    timezone: "Europe/Minsk",
    channelIds: model.channels.filter((channel) => channel.enabled).map((channel) => channel.channelId),
    maxPerChannel: 1,
  }));
  const uploadStartRef = useRef(false);
  const confirmRef = useRef(false);

  useEffect(() => {
    setRules(model.channels);
    setUploadConcurrency(model.uploadConcurrency);
  }, [model.channels, model.uploadConcurrency]);

  useEffect(() => {
    setBulkSchedule((current) => ({
      ...current,
      channelIds: current.channelIds.length
        ? current.channelIds.filter((id) => model.channels.some((channel) => channel.channelId === id && channel.enabled))
        : model.channels.filter((channel) => channel.enabled).map((channel) => channel.channelId),
    }));
  }, [model.channels]);

  const name = (id: string) => rules.find((channel) => channel.channelId === id)?.name || id || "Не назначен";
  const refreshReadiness = () => void command("migrate-publication-v2");
  const rememberDistribution = (next: DistributionRow[]) => {
    if (distribution.length) {
      setDistributionHistory((history) => [...history.slice(-19), distribution.map((row) => ({ ...row }))]);
    }
    setDistribution(next);
  };
  const undoDistribution = () => {
    if (!distributionHistory.length) return;
    const previous = distributionHistory[distributionHistory.length - 1];
    setDistribution(previous.map((row) => ({ ...row })));
    setDistributionHistory(distributionHistory.slice(0, -1));
  };

  const buildPreview = async (range?: BulkSchedule) => {
    const payload = {
      ...(selectedVideoIds.length ? { productionItemIds: selectedVideoIds } : {}),
      ...(range ? { bulkSchedule: range } : {}),
    };
    const result = Object.keys(payload).length
      ? await command("preview-publication-v2-distribution", payload)
      : await command("preview-publication-v2-distribution");
    const resultPreview = (result as (NewsFlowSnapshot & { publicationPreview?: Preview } | undefined))?.publicationPreview || null;
    if (!resultPreview) return;
    rememberDistribution(resultPreview.assignments.map((assignment) => {
      const video = model.videos.find((row) => row.id === assignment.productionItemId);
      return {
        productionItemId: assignment.productionItemId,
        title: video?.title || assignment.productionItemId,
        duration: video?.duration || "—",
        channelId: assignment.channelId,
        channelName: name(assignment.channelId),
        source: assignment.source,
        locked: assignment.locked,
        reason: assignment.reason,
        publishAt: assignment.publishAt || "",
        warning: assignment.scheduleWarning || "",
        suggestion: assignment.scheduleSuggestion || "",
      };
    }));
    setTab("distribution");
  };

  const saveRules = async () => command("save-publication-v2-rules", {
    rules: Object.fromEntries(rules.map((rule) => [rule.channelId, rule])),
  });
  const saveChannel = () => {
    void saveRules();
    setEditingChannel(null);
  };
  const savePreset = async () => {
    const nameValue = presetName.trim();
    if (!nameValue) return;
    await command("save-publication-v2-rule-preset", {
      name: nameValue,
      rules: Object.fromEntries(rules.map((rule) => [rule.channelId, rule])),
    });
    setSelectedPresetName(nameValue);
    setPresetName("");
  };
  const applyPreset = async () => {
    const preset = model.rulePresets.find((item) => item.name === selectedPresetName);
    if (!preset) return;
    await command("apply-publication-v2-rule-preset", { name: preset.name });
    setRules((current) => current.map((row) => {
      const saved = preset.rules[row.channelId];
      return saved ? { ...row, ...saved, name: row.name, oauthConnected: row.oauthConnected, subscribers: row.subscribers, assigned: row.assigned } : row;
    }));
  };
  const deletePreset = async () => {
    if (!selectedPresetName) return;
    await command("delete-publication-v2-rule-preset", { name: selectedPresetName });
    setSelectedPresetName("");
  };

  const savePlanVersion = async () => {
    const nameValue = planVersionName.trim();
    if (!nameValue || !distribution.length) return;
    const state = await command("save-publication-v2-plan-version", {
      name: nameValue,
      assignments: distribution.map((row) => ({
        productionItemId: row.productionItemId,
        channelId: row.channelId,
        publishAt: row.publishAt || "",
        source: row.source,
        locked: row.locked,
        reason: row.reason,
      })),
    });
    const versions = ((state?.publication as any)?.v2?.planVersions || []) as Array<{ id?: string; name?: string }>;
    const saved = [...versions].reverse().find((version) => version.name === nameValue);
    if (saved?.id) setSelectedPlanVersionId(saved.id);
    setPlanVersionName("");
  };

  const restorePlanVersion = async () => {
    if (!selectedPlanVersionId) return;
    const state = await command("restore-publication-v2-plan-version", { id: selectedPlanVersionId });
    const assignments = ((state?.publication as any)?.v2?.assignments || {}) as Record<string, Record<string, unknown>>;
    const restored = model.videos
      .map((video) => {
        const assignment = assignments[video.id];
        if (!assignment) return null;
        const channelId = String(assignment.channelId || "");
        return {
          productionItemId: video.id,
          title: video.title,
          duration: video.duration,
          channelId,
          channelName: name(channelId),
          source: String(assignment.source || "manual"),
          locked: Boolean(assignment.locked),
          reason: String(assignment.reason || "restored_plan"),
          publishAt: String(assignment.publishAt || ""),
          warning: "",
          suggestion: "",
        } satisfies DistributionRow;
      })
      .filter((row): row is NonNullable<typeof row> => row !== null);
    rememberDistribution(restored);
  };

  const deletePlanVersion = async () => {
    if (!selectedPlanVersionId) return;
    await command("delete-publication-v2-plan-version", { id: selectedPlanVersionId });
    setSelectedPlanVersionId("");
  };

  const hasScheduleConflicts = distribution.some((row) => Boolean(row.warning));
  const confirm = async () => {
    if (confirmRef.current || hasScheduleConflicts || !distribution.some((row) => row.channelId)) return;
    confirmRef.current = true;
    setConfirming(true);
    try {
      const state = await command("confirm-publication-v2-distribution", {
        assignments: distribution
          .filter((row) => row.channelId)
          .map((row) => ({
            productionItemId: row.productionItemId,
            channelId: row.channelId,
            publishAt: row.publishAt || undefined,
            source: row.source,
            locked: row.locked,
          })),
      });
      if (!state) return;
      setDistributionHistory([]);
      setTab("queue");
    } finally {
      confirmRef.current = false;
      setConfirming(false);
    }
  };

  const selectedQueueIds = (explicit?: string[]) => {
    if (explicit !== undefined) return explicit;
    if (selectedVideoIds.length) {
      const wanted = new Set(selectedVideoIds);
      return model.queue.filter((row) => wanted.has(row.productionItemId)).map((row) => row.snapshotId);
    }
    return [];
  };

  const continueFormatting = async (explicitIds?: string[], sourceRows: QueueRow[] = model.queue) => {
    const filter = new Set(selectedQueueIds(explicitIds));
    const ids = sourceRows
      .filter((row) => row.youtubeVideoId && (!filter.size || filter.has(row.snapshotId)))
      .map((row) => row.snapshotId);
    if (!ids.length || continuing) return;
    setContinuing(true);
    try {
      await command("reconcile-publication-v2-youtube", { snapshotIds: ids });
      await command("run-publication-v2-thumbnails", { snapshotIds: ids });
      await command("run-publication-v2-studio", { snapshotIds: ids });
    } finally {
      setContinuing(false);
    }
  };

  const start = async (explicitIds?: string[]) => {
    if (uploadStartRef.current) return;
    const explicit = new Set(selectedQueueIds(explicitIds));
    const ids = model.queue
      .filter((row) =>
        !row.youtubeVideoId
        && !row.active
        && uploadableStatuses.has(row.status)
        && (!explicit.size || explicit.has(row.snapshotId))
      )
      .map((row) => row.snapshotId);
    if (!ids.length) return;
    uploadStartRef.current = true;
    setUploadStarting(true);
    try {
      const state = await command("upload-publication-v2-snapshots", { snapshotIds: ids });
      const nextRows = queueFromSnapshot(state);
      const uploaded = nextRows.filter((row) => ids.includes(row.snapshotId) && row.youtubeVideoId).map((row) => row.snapshotId);
      if (uploaded.length) await continueFormatting(uploaded, nextRows);
    } finally {
      uploadStartRef.current = false;
      setUploadStarting(false);
    }
  };

  const reconcile = (explicitIds?: string[]) => {
    const explicit = new Set(selectedQueueIds(explicitIds));
    const ids = model.queue
      .filter((row) => row.youtubeVideoId && (!explicit.size || explicit.has(row.snapshotId)))
      .map((row) => row.snapshotId);
    if (ids.length) void command("reconcile-publication-v2-youtube", { snapshotIds: ids });
  };

  const updateChannel = (patch: Partial<ChannelRow>) => {
    if (!editingChannel) return;
    const next = { ...editingChannel, ...patch };
    setEditingChannel(next);
    setRules((current) => current.map((row) => row.channelId === next.channelId ? next : row));
  };
  const updateDistribution = (id: string, patch: Partial<DistributionRow>) =>
    rememberDistribution(distribution.map((row) => row.productionItemId === id ? { ...row, ...patch } : row));

  const dayPlanRows: DistributionRow[] = distribution.length
    ? distribution
    : model.queue.map((row) => ({
      productionItemId: row.productionItemId,
      title: row.title || row.productionItemId,
      duration: "—",
      channelId: row.channelId,
      channelName: name(row.channelId),
      source: "confirmed_snapshot",
      locked: true,
      reason: "confirmed_snapshot",
      publishAt: row.publishAt || "",
      warning: "",
      suggestion: "",
    }));

  const selectedVideoSet = new Set(selectedVideoIds);
  const headerStartRows = selectedVideoIds.length
    ? model.queue.filter((row) => selectedVideoSet.has(row.productionItemId))
    : model.queue;
  const headerCanStart = headerStartRows.some((row) =>
    !row.youtubeVideoId && !row.active && uploadableStatuses.has(String(row.status || "").toUpperCase())
  );

  return <div className="nf-publication-page">
    <PublicationHeader
      model={model}
      onReadiness={refreshReadiness}
      onPreview={() => void buildPreview()}
      onStart={() => void start()}
      starting={uploadStarting}
      canStart={headerCanStart}
    />
    <Tabs<PublicationTab>
      value={tab}
      onChange={setTab}
      items={[
        { id: "videos", label: "Ролики", count: model.videos.length },
        { id: "channels", label: "Каналы", count: model.channels.length },
        { id: "distribution", label: "Распределение", count: distribution.length || undefined },
        { id: "dayplan", label: "План дня", count: dayPlanRows.filter((row) => row.publishAt).length || undefined },
        { id: "queue", label: "Очередь", count: model.queue.length || undefined },
        { id: "history", label: "История", count: model.receipts.length || undefined },
      ]}
    />

    {tab === "videos" ? <VideosTable
      rows={model.videos}
      onSelectionChange={setSelectedVideoIds}
      onPriorityChange={(productionItemId, priority) => void command("set-publication-v2-item-priority", { productionItemId, priority })}
    /> : null}
    {tab === "channels" ? <section>
      <div className="nf-preset-toolbar">
        <div><b>Пресеты каналов</b><small>Квоты, диапазоны, 15-минутный тайминг и automation rules.</small></div>
        <label>Пресет<select aria-label="Пресет правил каналов" value={selectedPresetName} onChange={(event) => setSelectedPresetName(event.target.value)}><option value="">Выберите…</option>{model.rulePresets.map((preset) => <option key={preset.name} value={preset.name}>{preset.name}</option>)}</select></label>
        <UiButton variant="secondary" disabled={!selectedPresetName} onClick={() => void applyPreset()}>Применить</UiButton>
        <UiButton variant="ghost" disabled={!selectedPresetName} onClick={() => void deletePreset()}>Удалить</UiButton>
        <label>Новый пресет<input aria-label="Название нового пресета" value={presetName} onChange={(event) => setPresetName(event.target.value)} placeholder="Будни / Срочные новости"/></label>
        <UiButton variant="secondary" disabled={!presetName.trim()} onClick={() => void savePreset()}>Сохранить текущие</UiButton>
      </div>
      <ChannelsTable rows={rules} onEdit={setEditingChannel}/>
    </section> : null}

    {tab === "distribution" ? <section>
      <div className="nf-section-toolbar">
        <div>
          <b>Распределение до загрузки</b>
          <small>
            {selectedVideoIds.length ? `В preview только выбранные ролики: ${selectedVideoIds.length}. ` : ""}
            Ручные и уже подтверждённые назначения защищены.
            {hasScheduleConflicts ? " Исправьте конфликты до подтверждения." : ""}
          </small>
        </div>
        <div>
          <UiButton variant="ghost" disabled={!distributionHistory.length} onClick={undoDistribution}><Undo2 size={15}/>Отменить изменение</UiButton>
          <UiButton variant="secondary" onClick={() => void buildPreview()}><RefreshCw size={15}/>Пересчитать</UiButton>
          <UiButton variant="primary" disabled={confirming || !distribution.some((row) => row.channelId) || hasScheduleConflicts} onClick={() => void confirm()}><CheckCircle2 size={15}/>{confirming ? "Подтверждение…" : "Подтвердить назначения"}</UiButton>
        </div>
      </div>

      <div className="nf-preset-toolbar nf-plan-version-toolbar" aria-label="Версии плана">
        <div><b>Версии плана</b><small>Сохраняются между перезапусками. Frozen snapshots при восстановлении не меняются.</small></div>
        <label>Сохранённая версия<select aria-label="Сохранённая версия плана" value={selectedPlanVersionId} onChange={(event) => setSelectedPlanVersionId(event.target.value)}><option value="">Выберите…</option>{model.planVersions.map((version) => <option key={version.id} value={version.id}>{version.name}{version.createdAt ? " · " + version.createdAt.slice(0, 16) : ""}</option>)}</select></label>
        <UiButton variant="secondary" disabled={!selectedPlanVersionId} onClick={() => void restorePlanVersion()}>Восстановить</UiButton>
        <UiButton variant="ghost" disabled={!selectedPlanVersionId} onClick={() => void deletePlanVersion()}>Удалить</UiButton>
        <label>Новая версия<input aria-label="Название версии плана" value={planVersionName} onChange={(event) => setPlanVersionName(event.target.value)} placeholder="План на вечер"/></label>
        <UiButton variant="secondary" disabled={!planVersionName.trim() || !distribution.length} onClick={() => void savePlanVersion()}>Сохранить версию</UiButton>
      </div>

      <section className="nf-bulk-schedule" aria-label="Массовое планирование">
        <div>
          <b>Массовый диапазон по каналам</b>
          <small>Каждый канал строит собственную сетку с собственным интервалом/timezone. Время только :00 / :15 / :30 / :45.</small>
        </div>
        <label>Дата диапазона<input aria-label="Дата диапазона" type="date" value={bulkSchedule.date} onChange={(event) => setBulkSchedule((current) => ({ ...current, date: event.target.value }))}/></label>
        <label>Начало диапазона<input aria-label="Начало диапазона" type="time" step="900" value={bulkSchedule.startTime} onChange={(event) => setBulkSchedule((current) => ({ ...current, startTime: event.target.value }))}/></label>
        <label>Конец диапазона<input aria-label="Конец диапазона" type="time" step="900" value={bulkSchedule.endTime} onChange={(event) => setBulkSchedule((current) => ({ ...current, endTime: event.target.value }))}/></label>
        <label>Максимум роликов на канал<input aria-label="Максимум роликов на канал" type="number" min="1" value={bulkSchedule.maxPerChannel} onChange={(event) => setBulkSchedule((current) => ({ ...current, maxPerChannel: Math.max(1, Number(event.target.value) || 1) }))}/></label>
        <div className="nf-bulk-channel-list" aria-label="Каналы диапазона">
          {rules.filter((channel) => channel.enabled).map((channel) => <label key={channel.channelId}>
            <input
              type="checkbox"
              checked={bulkSchedule.channelIds.includes(channel.channelId)}
              onChange={(event) => setBulkSchedule((current) => ({
                ...current,
                channelIds: event.target.checked
                  ? [...current.channelIds, channel.channelId]
                  : current.channelIds.filter((id) => id !== channel.channelId),
              }))}
            />
            {channel.name}
          </label>)}
        </div>
        <UiButton variant="secondary" disabled={!bulkSchedule.date || !bulkSchedule.startTime || !bulkSchedule.endTime || !bulkSchedule.channelIds.length} onClick={() => void buildPreview(bulkSchedule)}><Clock3 size={15}/>Показать диапазон</UiButton>
      </section>

      {distribution.length ? <>
        <DistributionHealth rows={distribution}/>
        <DistributionTable rows={distribution} channels={rules} onChange={updateDistribution}/>
      </> : <div className="nf-empty-small"><b>Preview ещё не построен</b><span>Сохраните правила каналов и нажмите «Распределить».</span></div>}
    </section> : null}

    {tab === "dayplan" ? <PublicationDayPlan rows={dayPlanRows} channels={rules}/> : null}

    {tab === "queue" ? <PublicationQueue
      rows={model.queue}
      channelName={name}
      paused={model.paused}
      uploadConcurrency={uploadConcurrency}
      onConcurrency={(value) => {
        setUploadConcurrency(value);
        void command("save-publication-settings", { uploadConcurrency: value });
      }}
      onPause={() => void command("set-publication-v2-paused", { paused: !model.paused })}
      onStart={(ids) => void start(ids)}
      starting={uploadStarting}
      onContinue={(ids) => void continueFormatting(ids)}
      continuing={continuing}
      onReconcile={reconcile}
      onRetry={(snapshotId, stage) => void command("retry-publication-v2-stage", { snapshotId, stage })}
      onCancel={(snapshotId) => void command("cancel-publication-v2-execution", { snapshotId })}
      onThumbnail={(snapshotId) => void command("run-publication-v2-thumbnails", { snapshotIds: [snapshotId] })}
    /> : null}

    {tab === "history" ? <PublicationHistory rows={model.receipts}/> : null}

    <ChannelSettingsSheet channel={editingChannel} onClose={() => setEditingChannel(null)} onChange={updateChannel} onSave={saveChannel}/>
  </div>;
}
