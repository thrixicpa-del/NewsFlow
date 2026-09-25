import { CheckCircle2, CircleAlert, Clock3, Play, RefreshCw, Upload } from "lucide-react";
import type { ReactNode } from "react";
import { UiButton } from "../components/button";
import type { PublicationViewModel } from "./types";

export function PublicationHeader({ model, onReadiness, onPreview, onOpenPlanner, onStart, starting, canStart }: { model: PublicationViewModel; onReadiness(): void; onPreview(): void; onOpenPlanner(): void; onStart(): void; starting: boolean; canStart: boolean }) {
  const counter = (key: string, fallback: number) => Number.isFinite(Number(model.counters[key])) ? Number(model.counters[key]) : fallback;
  const ready = counter("videoReady", model.videos.filter((video) => video.mp4Ready).length);
  const assigned = counter("assigned", model.videos.filter((video) => Boolean(video.channelId)).length);
  const uploading = counter("uploading", model.queue.filter((row) => row.status === "UPLOADING").length);
  const quotaSlotsRemaining = counter("quotaSlotsRemaining", 0);
  const attention = model.videos.filter((video) => video.status === "Требует внимания").length;
  const scheduled = counter("scheduled", model.queue.filter((row) => row.status === "SCHEDULED").length);
  return <><header className="nf-publication-header"><div><span className="nf-eyebrow">YOUTUBE PUBLICATION V2</span><h2>Публикация YouTube</h2><p>Распределение, расписание и безопасная очередь роликов.</p></div><div className="nf-header-actions"><UiButton variant="secondary" onClick={onReadiness}><RefreshCw size={16}/>Проверить готовность</UiButton><UiButton variant="secondary" onClick={onPreview}><CheckCircle2 size={16}/>Распределить</UiButton><UiButton variant="secondary" size="icon" aria-label="Настроить дату и время" title="Настроить дату и время" onClick={onOpenPlanner}><Clock3 size={16}/></UiButton><UiButton variant="primary" disabled={starting || !canStart} onClick={onStart}><Upload size={16}/>{starting ? "Запуск…" : "Старт готовых"}</UiButton></div></header><div className="nf-kpi-strip"><Metric icon={<Play/>} value={model.videos.length} label="Всего"/><Metric icon={<CheckCircle2/>} value={ready} label="MP4 готовы" tone="success"/><Metric icon={<RefreshCw/>} value={model.newPackages} label="Новые packages"/><Metric icon={<Clock3/>} value={assigned} label="Назначено"/><Metric icon={<CheckCircle2/>} value={quotaSlotsRemaining} label="Свободно по квотам"/><Metric icon={<Upload/>} value={uploading} label="Загружается" tone="info"/><Metric icon={<CircleAlert/>} value={attention} label="Требуют внимания" tone="warning"/><Metric icon={<CheckCircle2/>} value={scheduled} label="Запланировано"/></div></>;
}
function Metric({ icon, value, label, tone = "" }: { icon: ReactNode; value: number; label: string; tone?: string }) { return <div className={`nf-kpi ${tone}`}>{icon}<b>{value}</b><small>{label}</small></div>; }
