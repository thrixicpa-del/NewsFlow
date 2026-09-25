import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { CheckCircle2, Circle, CircleX, ExternalLink, Pause, Play, RefreshCw, RotateCcw, ShieldCheck, Upload } from "lucide-react";
import { Badge, type BadgeTone } from "../components/badge";
import { DataTable } from "../components/data-table";
import { UiButton } from "../components/button";
import { stageLabel } from "./view-model";
import { PublicationTimeline } from "./PublicationTimeline";
import type { QueueRow } from "./types";

const badStates = new Set(["FAILED", "AUTH_REQUIRED", "QUOTA_BLOCKED", "USER_ACTION_REQUIRED"]);
const terminalStates = new Set(["SUCCESS", "SKIPPED", "NOT_REQUIRED"]);
const uploadableStates = new Set(["READY", "WAITING", "RETRYING", "SCHEDULED", "REUPLOAD_QUEUED"]);
const activeReuploadStates = new Set(["QUEUED", "RUNNING", "RETRYABLE", "UPLOADED", "PROCESSING"]);
const stepTone = (state: string): BadgeTone => terminalStates.has(state) ? "success" : badStates.has(state) ? "danger" : state === "RUNNING" ? "info" : "neutral";
function stageIcon(state: string) { return terminalStates.has(state) ? <CheckCircle2 size={14}/> : badStates.has(state) ? <CircleX size={14}/> : <Circle size={14}/>; }

function adsState(row: QueueRow) {
  const step = row.steps.ADS || {};
  const status = String(row.ads?.status || step.status || "PENDING").toUpperCase();
  const mode = String(row.ads?.mode || step.providerResult?.mode || "").toUpperCase();

  if (mode === "AUTO+MANUAL") {
    return {
      label: status === "SUCCESS" ? "AUTO + MANUAL 39s" : "AUTO + MANUAL · требует проверки",
      tone: status === "SUCCESS" ? "success" as BadgeTone : "warning" as BadgeTone,
    };
  }
  if (mode === "AUTO_ONLY") {
    return {
      label: status === "SUCCESS" || status === "NOT_REQUIRED" ? "AUTO ONLY" : "AUTO ONLY · ручные не готовы",
      tone: status === "SUCCESS" || status === "NOT_REQUIRED" ? "info" as BadgeTone : "warning" as BadgeTone,
    };
  }
  if (status === "NOT_REQUIRED" || status === "SKIPPED" || mode === "NONE") {
    return { label: "NONE", tone: "neutral" as BadgeTone };
  }
  if (status === "RUNNING") return { label: "НАСТРОЙКА…", tone: "info" as BadgeTone };
  if (status === "FAILED" || badStates.has(status)) return { label: "ОШИБКА", tone: "danger" as BadgeTone };
  return { label: "ОЖИДАЕТ", tone: "warning" as BadgeTone };
}

function errorCategory(step: QueueRow["steps"][string] | undefined) {
  const error = step?.error;
  if (!error || typeof error !== "object") return "";
  return String((error as { category?: unknown }).category || "").toUpperCase();
}

function uploadState(row: QueueRow) {
  const upload = row.steps.VIDEO_UPLOAD || {};
  const processing = row.steps.YOUTUBE_PROCESSING || {};
  const progress = upload.progress;
  const reuploadStatus = String(row.reupload?.status || "").toUpperCase();
  if (!row.youtubeVideoId) {
    if (progress?.state === "transferring" && typeof progress.percent === "number") {
      return { label: `${progress.percent}%`, tone: "info" as BadgeTone };
    }
    if (reuploadStatus === "QUEUED") return { label: "Перезалив в очереди", tone: "warning" as BadgeTone };
    if (reuploadStatus === "RETRYABLE") return { label: "Перезалив · повтор", tone: "warning" as BadgeTone };
    if (row.currentStage === "VIDEO_UPLOAD" || String(upload.status).toUpperCase() === "RUNNING") {
      return { label: "Передача", tone: "info" as BadgeTone };
    }
    return { label: "—", tone: "neutral" as BadgeTone };
  }
  const processingStatus = String(processing.status || "").toUpperCase();
  if (processingStatus === "RUNNING") return { label: "Обработка YouTube", tone: "info" as BadgeTone };
  if (processingStatus === "SUCCESS") return { label: "Обработка завершена", tone: "success" as BadgeTone };
  if (processingStatus === "FAILED" || badStates.has(processingStatus)) {
    return { label: "Ошибка обработки", tone: "danger" as BadgeTone };
  }
  return { label: "Передано 100%", tone: "success" as BadgeTone };
}

function formatReuploadStatus(value?: string) {
  const status = String(value || "").toUpperCase();
  const labels: Record<string, string> = {
    QUEUED: "Перезалив в очереди",
    RUNNING: "Перезалив выполняется",
    RETRYABLE: "Перезалив ждёт повтора",
    UPLOADED: "Новый upload передан",
    PROCESSING: "Новый ролик обрабатывается",
    SUCCEEDED: "Перезалив завершён",
    FAILED: "Перезалив завершён ошибкой",
  };
  return labels[status] || status || "—";
}

export function PublicationQueue({
  rows,
  channelName,
  paused,
  uploadConcurrency,
  onConcurrency,
  onPause,
  onStart,
  starting,
  onContinue,
  continuing,
  onReconcile,
  onRetry,
  onResolveUpload,
  onIdentity,
  onReupload,
  onCancel,
  onThumbnail,
}: {
  rows: QueueRow[];
  channelName(id: string): string;
  paused: boolean;
  uploadConcurrency: number;
  onConcurrency(value: number): void;
  onPause(): void;
  onStart(snapshotIds?: string[]): void;
  starting: boolean;
  onContinue(snapshotIds?: string[]): void;
  continuing: boolean;
  onReconcile(snapshotIds?: string[]): void;
  onRetry(snapshotId: string, stage: string): void;
  onResolveUpload(snapshotId: string, outcome: "found" | "not_found", youtubeVideoId?: string): void;
  onIdentity(snapshotId: string): void;
  onReupload(snapshotIds: string[], reason: string): void;
  onCancel(snapshotId: string): void;
  onThumbnail(snapshotId: string): void;
}) {
  const [expanded, setExpanded] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [reuploadReason, setReuploadReason] = useState("Повторная private-загрузка после проверки результата YouTube");
  const counters = {
    active: rows.filter((row) => row.active).length,
    waiting: rows.filter((row) => !row.active && !row.youtubeVideoId).length,
    processing: rows.filter((row) => ["YOUTUBE_PROCESSING", "PROCESSING"].includes(row.status)).length,
    errors: rows.filter((row) => Object.values(row.steps).some((step) => badStates.has(String(step.status)))).length,
  };
  const allSelected = rows.length > 0 && rows.every((row) => selected.includes(row.snapshotId));
  const toggleAll = () => setSelected(allSelected ? [] : rows.map((row) => row.snapshotId));
  const toggle = (snapshotId: string) => setSelected((current) => current.includes(snapshotId) ? current.filter((id) => id !== snapshotId) : [...current, snapshotId]);
  const actionIds = selected.length ? selected : [];
  const selectedRows = rows.filter((row) => selected.includes(row.snapshotId));
  const actionScope = selected.length ? selectedRows : rows;
  const hasKnownYoutube = actionScope.some((row) => Boolean(row.youtubeVideoId));
  const reuploadRows = selectedRows.filter((row) => {
    const state = String(row.reupload?.status || "").toUpperCase();
    return Boolean(row.youtubeVideoId) && !row.active && !activeReuploadStates.has(state);
  });
  const hasUploadable = actionScope.some((row) =>
    !row.youtubeVideoId && !row.active && uploadableStates.has(String(row.status || "").toUpperCase())
  );
  const channelProgress = [...new Set(rows.map((row) => row.channelId).filter(Boolean))].map((channelId) => {
    const channelRows = rows.filter((row) => row.channelId === channelId);
    return {
      channelId,
      total: channelRows.length,
      uploaded: channelRows.filter((row) => Boolean(row.youtubeVideoId)).length,
      complete: channelRows.filter((row) => ["DONE", "SCHEDULED"].includes(row.status)).length,
      errors: channelRows.filter((row) => row.status === "PARTIAL" || Object.values(row.steps).some((step) => badStates.has(String(step.status)))).length,
    };
  });

  const columns = useMemo<ColumnDef<QueueRow>[]>(() => [
    {
      id: "select",
      header: () => <input aria-label="Выбрать всю очередь" type="checkbox" checked={allSelected} onChange={toggleAll}/>,
      cell: ({ row }) => <input aria-label={`Выбрать публикацию ${row.original.title}`} type="checkbox" checked={selected.includes(row.original.snapshotId)} onChange={() => toggle(row.original.snapshotId)}/>,
    },
    {
      id: "number",
      header: "",
      cell: ({ row }) => <button className="nf-expand" aria-label={`Раскрыть ход публикации ${row.original.title || row.original.productionItemId}`} onClick={() => setExpanded((items) => items.includes(row.original.snapshotId) ? items.filter((id) => id !== row.original.snapshotId) : [...items, row.original.snapshotId])}>{expanded.includes(row.original.snapshotId) ? "−" : "+"}</button>,
    },
    { accessorKey: "title", header: "Ролик", cell: ({ row }) => <b>{row.original.title || row.original.productionItemId}</b> },
    { id: "channel", header: "Канал", cell: ({ row }) => <div><span>{channelName(row.original.channelId)}</span>{activeReuploadStates.has(String(row.original.reupload?.status || "").toUpperCase()) ? <Badge tone="warning">Перезалив</Badge> : null}</div> },
    { accessorKey: "publishAt", header: "Выход", cell: ({ row }) => <small>{row.original.publishAt || "—"}</small> },
    { id: "upload", header: "Upload", cell: ({ row }) => { const value = uploadState(row.original); return <Badge tone={value.tone}>{value.label}</Badge>; } },
    { id: "ads", header: "Реклама", cell: ({ row }) => { const value = adsState(row.original); return <Badge tone={value.tone}>{value.label}</Badge>; } },
    { id: "completion", header: "Оформление", cell: ({ row }) => `${row.original.completion.completed}/${row.original.completion.total}` },
    { id: "stage", header: "Текущий этап", cell: ({ row }) => stageLabel(row.original.currentStage) },
    { accessorKey: "status", header: "Статус", cell: ({ row }) => <Badge tone={badStates.has(row.original.status) || row.original.status === "PARTIAL" ? "danger" : row.original.active ? "info" : "neutral"}>{row.original.status}</Badge> },
  ], [allSelected, channelName, expanded, rows, selected]);

  return <section className="nf-workspace-panel">
    <div className="nf-queue-toolbar">
      <label>Одновременных загрузок<input type="number" min="1" value={uploadConcurrency} onChange={(event) => onConcurrency(Math.max(1, Number(event.target.value) || 1))}/></label>
      <span>Активно: <b>{counters.active}/{uploadConcurrency}</b></span>
      <span>В очереди: <b>{counters.waiting}</b></span>
      <span>YouTube processing: <b>{counters.processing}</b></span>
      <span>Ошибки: <b>{counters.errors}</b></span>
      <span>Выбрано: <b>{selected.length || "все"}</b></span>
      <div>
        <UiButton variant="secondary" disabled={!hasKnownYoutube} onClick={() => onReconcile(actionIds)}><RefreshCw size={15}/>Обновить статусы YouTube</UiButton>
        <UiButton variant="secondary" disabled={continuing || !hasKnownYoutube} onClick={() => onContinue(actionIds)}><RefreshCw size={15}/>{continuing ? "Оформление…" : selected.length ? "Продолжить выбранные" : "Продолжить оформление"}</UiButton>
        <UiButton variant={paused ? "primary" : "secondary"} onClick={onPause}>{paused ? <Play size={15}/> : <Pause size={15}/>}{paused ? "Продолжить" : "Пауза"}</UiButton>
        <UiButton variant="primary" disabled={paused || starting || !hasUploadable} onClick={() => onStart(actionIds)}><Upload size={15}/>{starting ? "Запуск…" : selected.length ? `Запустить выбранные (${selected.length})` : "Запустить очередь"}</UiButton>
      </div>
      <div className="nf-reupload-controls">
        <label>Причина перезалива<input aria-label="Причина перезалива" value={reuploadReason} onChange={(event) => setReuploadReason(event.target.value)}/></label>
        <UiButton
          variant="secondary"
          disabled={!reuploadRows.length || !reuploadReason.trim()}
          onClick={() => {
            const titles = reuploadRows.map((row) => row.title || row.productionItemId).join("\n• ");
            const confirmed = window.confirm(
              `Перезалить выбранные ролики как новые PRIVATE uploads?\n\n• ${titles}\n\nПричина: ${reuploadReason.trim()}\n\nFrozen metadata подтверждается как актуальная. Старые YouTube ID не удаляются и не публикуются; исходное расписание автоматически не переносится.`,
            );
            if (confirmed) onReupload(reuploadRows.map((row) => row.snapshotId), reuploadReason.trim());
          }}
        ><RotateCcw size={15}/>Перезалить выбранные ({reuploadRows.length})</UiButton>
      </div>
    </div>
    {channelProgress.length ? <div className="nf-channel-progress-strip" aria-label="Прогресс по каналам">{channelProgress.map((item) => <div className="nf-channel-progress-card" key={item.channelId}><b>{channelName(item.channelId)}</b><small>Готово {item.complete}/{item.total} · Upload {item.uploaded}/{item.total} · Ошибки {item.errors}</small></div>)}</div> : null}
    <DataTable data={rows} columns={columns} preferenceKey="publication-queue" ariaLabel="Очередь публикации" expanded={(row) => expanded.includes(row.snapshotId) ? <PublicationExecutionDetails row={row} channelName={channelName} onRetry={onRetry} onResolveUpload={onResolveUpload} onIdentity={onIdentity} onCancel={onCancel} onThumbnail={onThumbnail}/> : null}/>
  </section>;
}

export function PublicationExecutionDetails({ row, channelName, onRetry, onResolveUpload, onIdentity, onCancel, onThumbnail }: { row: QueueRow; channelName(id: string): string; onRetry(snapshotId: string, stage: string): void; onResolveUpload(snapshotId: string, outcome: "found" | "not_found", youtubeVideoId?: string): void; onIdentity(snapshotId: string): void; onCancel(snapshotId: string): void; onThumbnail(snapshotId: string): void }) {
  const [reconciledVideoId, setReconciledVideoId] = useState("");
  const failed = Object.entries(row.steps).find(([, step]) => badStates.has(String(step.status)));
  const identityRequired = Object.values(row.steps).some((step) => errorCategory(step) === "STUDIO_IDENTITY_REQUIRED");
  const uploadNeedsReconciliation = String(row.steps.VIDEO_UPLOAD?.status || "").toUpperCase() === "USER_ACTION_REQUIRED" && !row.youtubeVideoId;
  const thumbnailPending = Boolean(row.youtubeVideoId) && !terminalStates.has(String(row.steps.THUMBNAIL?.status || "").toUpperCase());
  return <div className="nf-queue-details">
    <div className="nf-detail-meta">
      <div><small>КАНАЛ</small><p>{channelName(row.channelId)}</p></div>
      <div><small>ВЫХОД</small><p>{row.publishAt || "—"}</p></div>
      <div><small>YOUTUBE</small><p>{row.youtubeVideoUrl ? <a href={row.youtubeVideoUrl} target="_blank" rel="noreferrer">{row.youtubeVideoId}<ExternalLink size={13}/></a> : "ещё не загружен"}</p></div>
      <div><small>РЕКЛАМА</small><p><Badge tone={adsState(row).tone}>{adsState(row).label}</Badge></p></div>
    </div>
    {row.reupload ? <div className="nf-reupload-audit">
      <small>ПЕРЕЗАЛИВ</small>
      <p><b>{formatReuploadStatus(row.reupload.status)}</b></p>
      <p>Старый ID: {row.reupload.oldVideoUrl ? <a href={row.reupload.oldVideoUrl} target="_blank" rel="noreferrer">{row.reupload.oldVideoId}<ExternalLink size={13}/></a> : row.reupload.oldVideoId || "—"}</p>
      <p>Новый ID: {row.youtubeVideoUrl ? <a href={row.youtubeVideoUrl} target="_blank" rel="noreferrer">{row.youtubeVideoId}<ExternalLink size={13}/></a> : row.reupload.newVideoId || "—"}</p>
      <p>Причина: {row.reupload.reason || "—"}</p>
      <p>Последняя проверка: {row.reupload.lastCheckedAt || row.reupload.requestedAt || "—"}</p>
      <p>Исходное расписание: {row.reupload.originalPublishAt || "без расписания"} · автоматически не перенесено</p>
    </div> : null}
    <div className="nf-stage-list">
      <small>ЭТАПЫ · оформление {row.completion.completed}/{row.completion.total}</small>
      {Object.entries(row.steps).map(([stage, step]) => {
        const provider = step.providerResult || {};
        const detail = stage === "ADS" && provider.mode
          ? String(provider.mode)
          : step.durationSeconds
            ? `${step.durationSeconds} сек.`
            : String(step.error || step.detail || "");
        return <div key={stage}><span>{stageIcon(String(step.status))}{stageLabel(stage)}</span><Badge tone={stepTone(String(step.status))}>{String(step.status || "PENDING")}</Badge><small>{detail}</small></div>;
      })}
    </div>
    <PublicationTimeline events={row.timeline}/>
    <div className="nf-detail-actions">
      {uploadNeedsReconciliation ? <div>
        <p role="status">Исход загрузки неизвестен: сначала сверьте канал в YouTube Studio. Обычный retry и отмена заблокированы, чтобы не создать дубликат.</p>
        <label>YouTube video ID<input aria-label={`YouTube video ID для ${row.title || row.productionItemId}`} value={reconciledVideoId} onChange={(event) => setReconciledVideoId(event.target.value)}/></label>
        <UiButton variant="secondary" disabled={!reconciledVideoId.trim()} onClick={() => onResolveUpload(row.snapshotId, "found", reconciledVideoId.trim())}>Привязать найденный YouTube ID</UiButton>
        <UiButton variant="secondary" onClick={() => onResolveUpload(row.snapshotId, "not_found")}>Я проверил канал: видео нет — разрешить повтор</UiButton>
      </div> : null}
      {identityRequired ? <UiButton variant="secondary" onClick={() => onIdentity(row.snapshotId)}><ShieldCheck size={15}/>Пройти 2FA</UiButton> : null}
      {failed && !uploadNeedsReconciliation ? <UiButton variant="secondary" onClick={() => onRetry(row.snapshotId, failed[0])}><RefreshCw size={15}/>Попробовать ещё раз · {stageLabel(failed[0])}</UiButton> : null}
      {thumbnailPending ? <UiButton variant="secondary" onClick={() => onThumbnail(row.snapshotId)}>Поставить обложку</UiButton> : null}
      {!uploadNeedsReconciliation ? <UiButton variant="destructive" onClick={() => onCancel(row.snapshotId)}>Отменить автоматизацию</UiButton> : null}
    </div>
  </div>;
}
