import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Lock, Unlock } from "lucide-react";
import { Badge } from "../components/badge";
import { DataTable } from "../components/data-table";
import type { ChannelRow, DistributionRow } from "./types";

const distributionReason = (reason: string) => ({
  auto: "Автораспределение",
  balanced: "Равномерно по заполнению квоты",
  longest_monetized: "Длинный ролик → монетизированный канал",
  ordered: "По порядку производственной партии",
  manual_locked: "Ручное назначение",
  confirmed_snapshot: "Уже подтверждено — защищено от перераспределения",
  quota_exhausted: "Нет свободной квоты у выбранных каналов",
  eligibility_mismatch: "Не подходит правило канала: номер, длительность или тема/направление",
}[reason] || reason || "—");

export function DistributionTable({ rows, channels, onChange }: { rows: DistributionRow[]; channels: ChannelRow[]; onChange(id: string, patch: Partial<DistributionRow>): void }) {
  const [channelFilter, setChannelFilter] = useState("all");
  const [videoFilter, setVideoFilter] = useState("all");
  const visibleRows = useMemo(() => rows.filter((row) =>
    (channelFilter === "all" || row.channelId === channelFilter)
    && (videoFilter === "all" || row.productionItemId === videoFilter)
  ), [rows, channelFilter, videoFilter]);
  const videoOptions = useMemo(() => [...rows].sort((left, right) =>
    (left.videoNumber || Number.MAX_SAFE_INTEGER) - (right.videoNumber || Number.MAX_SAFE_INTEGER)
    || left.title.localeCompare(right.title, "ru-RU")
  ), [rows]);
  const columns = useMemo<ColumnDef<DistributionRow>[]>(() => [{ accessorKey: "title", header: "Ролик", cell: ({ row }) => <div><b>{row.original.videoNumber ? `Ролик ${row.original.videoNumber} — ` : ""}{row.original.title}</b><small>{row.original.duration}</small></div> }, { id: "channel", header: "Канал", cell: ({ row }) => <select aria-label={`Канал для ${row.original.title}`} value={row.original.channelId} onChange={(event) => onChange(row.original.productionItemId, { channelId: event.target.value, channelName: channels.find((channel) => channel.channelId === event.target.value)?.name || event.target.value, source: "manual", locked: true })}><option value="">Не назначен</option>{channels.filter((channel) => channel.enabled).map((channel) => <option value={channel.channelId} key={channel.channelId}>Канал {channel.number} — {channel.name}</option>)}</select> }, { id: "time", header: "Время выхода", cell: ({ row }) => <input aria-label={`Время ${row.original.title}`} type="datetime-local" step="900" value={row.original.publishAt ? row.original.publishAt.slice(0, 16) : ""} onChange={(event) => onChange(row.original.productionItemId, { publishAt: event.target.value ? `${event.target.value}:00` : "", source: "manual", locked: true })}/> }, { id: "reason", header: "Причина", cell: ({ row }) => <small>{distributionReason(row.original.reason)}</small> }, { id: "type", header: "Тип", cell: ({ row }) => <Badge tone={row.original.locked ? "warning" : "info"}>{row.original.locked ? <><Lock size={12}/>LOCKED</> : <><Unlock size={12}/>AUTO</>}</Badge> }, { id: "conflict", header: "Конфликт", cell: ({ row }) => row.original.warning ? <Badge tone="danger">{row.original.warning}</Badge> : <span className="nf-ok">—</span> }, { id: "suggestion", header: "Что сделать", cell: ({ row }) => row.original.suggestion ? <small className="nf-conflict-suggestion">{row.original.suggestion}</small> : <span className="nf-ok">—</span> }], [channels, onChange]);
  return <section className="nf-workspace-panel">
    <div className="nf-table-toolbar" aria-label="Фильтр назначений">
      <label><select aria-label="Фильтр назначений по каналу" value={channelFilter} onChange={(event) => setChannelFilter(event.target.value)}><option value="all">Все каналы</option>{channels.map((channel) => <option key={channel.channelId} value={channel.channelId}>Канал {channel.number} — {channel.name}</option>)}</select></label>
      <label><select aria-label="Фильтр назначений по ролику" value={videoFilter} onChange={(event) => setVideoFilter(event.target.value)}><option value="all">Все ролики</option>{videoOptions.map((row, index) => <option key={row.productionItemId} value={row.productionItemId}>Ролик {row.videoNumber || index + 1} — {row.title}</option>)}</select></label>
    </div>
    <DataTable data={visibleRows} columns={columns} preferenceKey="publication-distribution" ariaLabel="Распределение роликов" />
  </section>;
}
