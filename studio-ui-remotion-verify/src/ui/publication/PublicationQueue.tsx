import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { CheckCircle2, Circle, CircleX, ExternalLink, Pause, Play, RefreshCw, Upload } from "lucide-react";
import { Badge, type BadgeTone } from "../components/badge";
import { DataTable } from "../components/data-table";
import { UiButton } from "../components/button";
import { stageLabel } from "./view-model";
import { PublicationTimeline } from "./PublicationTimeline";
import type { QueueRow } from "./types";

const badStates = new Set(["FAILED", "AUTH_REQUIRED", "QUOTA_BLOCKED", "USER_ACTION_REQUIRED"]);
const terminalStates = new Set(["SUCCESS", "SKIPPED", "NOT_REQUIRED"]);
const stepTone = (state: string): BadgeTone => terminalStates.has(state) ? "success" : badStates.has(state) ? "danger" : state === "RUNNING" ? "info" : "neutral";
function stageIcon(state: string) { return terminalStates.has(state) ? <CheckCircle2 size={14}/> : badStates.has(state) ? <CircleX size={14}/> : <Circle size={14}/>; }

function adsState(row: QueueRow) {
  const step = row.steps.ADS || {};
  const status = String(row.ads?.status || step.status || "PENDING").toUpperCase();
  const mode = String(row.ads?.mode || step.providerResult?.mode || "").toUpperCase();
  if (status === "SUCCESS" && mode === "AUTO+MANUAL_39S") return { label: "AUTO + MANUAL 39s", tone: "success" as BadgeTone };
  if (status === "SUCCESS" && mode === "AUTO_ONLY") return { label: "AUTO ONLY", tone: "info" as BadgeTone };
  if (status === "NOT_REQUIRED" || mode === "NONE") return { label: "NONE", tone: "neutral" as BadgeTone };
  if (badStates.has(status)) return { label: "ОШИБКА", tone: "danger" as BadgeTone };
  if (status === "RUNNING") return { label: "НАСТРОЙКА…", tone: "info" as BadgeTone };
  return { label: "ОЖИДАЕТ", tone: "warning" as BadgeTone };
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
  onCancel(snapshotId: string): void;
  onThumbnail(snapshotId: string): void;
}) {
  const [expanded, setExpanded] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const counters = {
    active: rows.filter((row) => row.active).length,
    waiting: rows.filter((row) => !row.active && !row.youtubeVideoId).length,
    processing: rows.filter((row) => ["YOUTUBE_PROCESSING", "PROCESSING"].includes(row.status)).length,
    errors: rows.filter((row) => Object.values(row.steps).some((step) => badStates.has(String(step.status)))).length,
  };
  const allSelected = rows.length > 0 && rows.every((row) => selected.includes(row.snapshotId));
  const toggleAll = () => setSelected(allSelected ? [] : rows.map((row) => row.snapshotId));
  const toggle = (snapshotId: string) => setSelected((current) => current.includes(snapshotId) ? current.filter((id) => id !== snapshotId) : [...current, snapshotId]);
  const actionIds = selected.length ? selected : undefined;

  const columns = useMemo<ColumnDef<QueueRow>[]>(() => [
    {
      id: "select",
      header: () => <input aria-label="Выбрать всю очередь" type="checkbox" checked={allSelected} onChange={toggleAll}/>,
      cell: ({ row }) => <input aria-label={`Выбрать публикацию ${row.original.title}`} type="checkbox" checked={selected.includes(row.original.snapshotId)} onChange={() => toggle(row.original.snapshotId)}/>,
    },
    {
      id: "number",
      header: "",
      cell: ({ row }) => <button className="nf-expand" aria-label="Раскрыть ход публикации" onClick={() => setExpanded((items) => items.includes(row.original.snapshotId) ? items.filter((id) => id !== row.original.snapshotId) : [...items, row.original.snapshotId])}>{expanded.includes(row.original.snapshotId) ? "−" : "+"}</button>,
    },
    { accessorKey: "title", header: "Ролик", cell: ({ row }) => <b>{row.original.title || row.original.productionItemId}</b> },
    { id: "channel", header: "Канал", cell: ({ row }) => channelName(row.original.channelId) },
    { accessorKey: "publishAt", header: "Выход", cell: ({ row }) => <small>{row.original.publishAt || "—"}</small> },
    { id: "upload", header: "Upload", cell: ({ row }) => row.original.youtubeVideoId ? <Badge tone="success">100%</Badge> : <Badge tone={row.original.currentStage === "VIDEO_UPLOAD" ? "info" : "neutral"}>{row.original.currentStage === "VIDEO_UPLOAD" ? "Передача" : "—"}</Badge> },
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
        <UiButton variant="secondary" onClick={() => onReconcile(actionIds)}><RefreshCw size={15}/>Проверить YouTube</UiButton>
        <UiButton variant="secondary" disabled={continuing} onClick={() => onContinue(actionIds)}><RefreshCw size={15}/>{continuing ? "Оформление…" : selected.length ? "Продолжить выбранные" : "Продолжить оформление"}</UiButton>
        <UiButton variant={paused ? "primary" : "secondary"} onClick={onPause}>{paused ? <Play size={15}/> : <Pause size={15}/>}{paused ? "Продолжить" : "Пауза"}</UiButton>
        <UiButton variant="primary" disabled={paused || starting} onClick={() => onStart(actionIds)}><Upload size={15}/>{starting ? "Запуск…" : selected.length ? `Запустить выбранные (${selected.length})` : "Запустить очередь"}</UiButton>
      </div>
    </div>
    <DataTable data={rows} columns={columns} expanded={(row) => expanded.includes(row.snapshotId) ? <PublicationExecutionDetails row={row} channelName={channelName} onRetry={onRetry} onCancel={onCancel} onThumbnail={onThumbnail}/> : null}/>
  </section>;
}

export function PublicationExecutionDetails({ row, channelName, onRetry, onCancel, onThumbnail }: { row: QueueRow; channelName(id: string): string; onRetry(snapshotId: string, stage: string): void; onCancel(snapshotId: string): void; onThumbnail(snapshotId: string): void }) {
  const failed = Object.entries(row.steps).find(([, step]) => badStates.has(String(step.status)));
  const thumbnailPending = Boolean(row.youtubeVideoId) && !terminalStates.has(String(row.steps.THUMBNAIL?.status || "").toUpperCase());
  return <div className="nf-queue-details">
    <div className="nf-detail-meta">
      <div><small>КАНАЛ</small><p>{channelName(row.channelId)}</p></div>
      <div><small>ВЫХОД</small><p>{row.publishAt || "—"}</p></div>
      <div><small>YOUTUBE</small><p>{row.youtubeVideoUrl ? <a href={row.youtubeVideoUrl} target="_blank" rel="noreferrer">{row.youtubeVideoId}<ExternalLink size={13}/></a> : "ещё не загружен"}</p></div>
      <div><small>РЕКЛАМА</small><p><Badge tone={adsState(row).tone}>{adsState(row).label}</Badge></p></div>
    </div>
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
      {failed ? <UiButton variant="secondary" onClick={() => onRetry(row.snapshotId, failed[0])}><RefreshCw size={15}/>Повторить {stageLabel(failed[0])}</UiButton> : null}
      {thumbnailPending ? <UiButton variant="secondary" onClick={() => onThumbnail(row.snapshotId)}>Поставить обложку</UiButton> : null}
      <UiButton variant="destructive" onClick={() => onCancel(row.snapshotId)}>Отменить автоматизацию</UiButton>
    </div>
  </div>;
}
