import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { ChevronDown, ChevronRight, Filter, MoreHorizontal, Search } from "lucide-react";
import { Badge, type BadgeTone } from "../components/badge";
import { DataTable } from "../components/data-table";
import { UiButton } from "../components/button";
import type { VideoRow } from "./types";

const tone = (status: VideoRow["status"]): BadgeTone => status === "Готово" || status === "Готов" ? "success" : status === "Требует внимания" || status === "Ошибка" ? "danger" : status === "Загружается" || status === "Оформляется" ? "info" : status === "Требует канала" ? "warning" : "neutral";
const mark = (ready: boolean, readyText: string, missingText: string) => <Badge tone={ready ? "success" : "warning"}>{ready ? readyText : missingText}</Badge>;

export function VideosTable({ rows, onSelectionChange, onPriorityChange }: { rows: VideoRow[]; onSelectionChange?(ids: string[]): void; onPriorityChange?(id: string, priority: number): void }) {
  const [query, setQuery] = useState(""); const [status, setStatus] = useState("all"); const [channel, setChannel] = useState("all"); const [selected, setSelected] = useState<string[]>([]); const [expanded, setExpanded] = useState<string[]>([]);
  const filtered = useMemo(() => rows.filter((row) => (!query || row.title.toLocaleLowerCase("ru-RU").includes(query.toLocaleLowerCase("ru-RU"))) && (status === "all" || row.status === status) && (channel === "all" || row.channelId === channel)), [rows, query, status, channel]);
  const select = (id: string) => { const next = selected.includes(id) ? selected.filter((value) => value !== id) : [...selected, id]; setSelected(next); onSelectionChange?.(next); };
  const columns = useMemo<ColumnDef<VideoRow>[]>(() => [
    { id: "select", header: () => <input aria-label="Выбрать все ролики" type="checkbox" checked={filtered.length > 0 && filtered.every((row) => selected.includes(row.id))} onChange={() => { const next = filtered.every((row) => selected.includes(row.id)) ? selected.filter((id) => !filtered.some((row) => row.id === id)) : [...new Set([...selected, ...filtered.map((row) => row.id)])]; setSelected(next); onSelectionChange?.(next); }} />, cell: ({ row }) => <input aria-label={`Выбрать ${row.original.title}`} type="checkbox" checked={selected.includes(row.original.id)} onChange={() => select(row.original.id)} /> },
    { accessorKey: "number", header: "№", cell: ({ row }) => <span className="nf-number">{row.original.number}</span> },
    { id: "priority", header: "Приоритет", cell: ({ row }) => <input className="nf-priority-input" aria-label={`Приоритет ${row.original.title}`} type="number" min="-10" max="10" step="1" value={row.original.priority} onChange={(event) => onPriorityChange?.(row.original.id, Math.max(-10, Math.min(10, Number(event.target.value) || 0)))}/> },
    { accessorKey: "title", header: "Ролик", cell: ({ row }) => <div className="nf-title-cell"><button className="nf-expand" aria-label="Раскрыть детали" onClick={() => setExpanded((items) => items.includes(row.original.id) ? items.filter((id) => id !== row.original.id) : [...items, row.original.id])}>{expanded.includes(row.original.id) ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</button><div><b title={row.original.title}>{row.original.title}</b><small>{row.original.duration}</small></div></div> },
    { id: "readiness", header: "Готовность", cell: ({ row }) => <div className="nf-artifact-strip">{mark(row.original.mp4Ready, "MP4", "MP4 отсутствует")}{mark(row.original.coverReady, "Обложка", "Нет обложки")}{mark(row.original.seoReady, "SEO", "Нет SEO")}</div> },
    { accessorKey: "channelName", header: "Канал", cell: ({ row }) => <span>{row.original.channelName}</span> },
    { accessorKey: "publishAt", header: "Выход", cell: ({ row }) => <small>{row.original.publishAt || "—"}</small> },
    { accessorKey: "status", header: "Статус", cell: ({ row }) => <Badge tone={tone(row.original.status)}>{row.original.status}</Badge> },
    { id: "actions", header: "", cell: () => <UiButton size="icon" variant="ghost" aria-label="Действия"><MoreHorizontal size={17} /></UiButton> },
  ], [expanded, filtered, onPriorityChange, onSelectionChange, selected]);
  const channels = [...new Map(rows.filter((row) => row.channelId).map((row) => [row.channelId, row.channelName])).entries()];
  return <section className="nf-workspace-panel"><div className="nf-table-toolbar"><label className="nf-search"><Search size={16}/><input aria-label="Поиск роликов" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск по названию…" /></label><label><Filter size={14}/><select aria-label="Статус ролика" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">Все статусы</option>{[...new Set(rows.map((row) => row.status))].map((value) => <option key={value}>{value}</option>)}</select></label><label><select aria-label="Канал ролика" value={channel} onChange={(event) => setChannel(event.target.value)}><option value="all">Все каналы</option>{channels.map(([id, name]) => <option value={id} key={id}>{name}</option>)}</select></label><span className="nf-selection-count">Выбрано: {selected.length}</span><UiButton variant="ghost" onClick={() => { setQuery(""); setStatus("all"); setChannel("all"); }}>Сбросить</UiButton></div>
  <DataTable data={filtered} columns={columns} expanded={(row) => expanded.includes(row.id) ? <VideoDetails row={row} /> : null} /></section>;
}

function VideoDetails({ row }: { row: VideoRow }) {
  return <div className="nf-video-details"><div><small>АРТЕФАКТЫ</small><p>{mark(row.mp4Ready, "MP4 есть", "MP4 отсутствует")}{mark(row.coverReady, "Обложка есть", "Обложки нет")}{mark(row.seoReady, "SEO готов", "SEO нет")}{mark(row.mp3Ready, "MP3 есть", "MP3 нет")}</p></div><div><small>МЕТАДАННЫЕ</small><p>{mark(row.metadataReady, "Заголовок/описание", "Метаданные")}</p></div><div><small>ПУБЛИКАЦИЯ</small><p>{row.channelName} · {row.publishAt || "не назначено"} · {row.assignmentType}</p></div><div><small>ProductionItem ID</small><p>{row.id}</p></div></div>;
}
