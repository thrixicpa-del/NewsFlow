import { useMemo, useState } from "react";
import type { ChannelRow, DistributionRow } from "./types";

function minuteOfDay(value: string) {
  const match = value.match(/T(\d{2}):(\d{2})/);
  return match ? Number(match[1]) * 60 + Number(match[2]) : 0;
}
function labelForMinute(value: number) {
  const hours = Math.floor(value / 60) % 24;
  const minutes = value % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function PublicationDayPlan({ rows, channels }: { rows: DistributionRow[]; channels: ChannelRow[] }) {
  const dated = useMemo(() => rows.filter((row) => row.channelId && row.publishAt && !row.warning), [rows]);
  const dates = useMemo(() => [...new Set(dated.map((row) => row.publishAt.slice(0, 10)))].sort(), [dated]);
  const [selectedDate, setSelectedDate] = useState("");
  const activeDate = dates.includes(selectedDate) ? selectedDate : dates[0] || "";
  const dayRows = useMemo(() => dated.filter((row) => row.publishAt.slice(0, 10) === activeDate), [activeDate, dated]);
  const slots = useMemo(() => {
    if (!dayRows.length) return [];
    const minutes = dayRows.map((row) => minuteOfDay(row.publishAt));
    const first = Math.floor(Math.min(...minutes) / 15) * 15;
    const last = Math.ceil(Math.max(...minutes) / 15) * 15;
    const result: number[] = [];
    for (let value = first; value <= last; value += 15) result.push(value);
    return result;
  }, [dayRows]);
  const activeChannels = channels.filter((channel) => dayRows.some((row) => row.channelId === channel.channelId));

  if (!dated.length) {
    return <section className="nf-workspace-panel nf-day-plan-empty"><b>План на сутки появится после расчёта времени</b><small>Назначьте каналы и постройте расписание по 15-минутной сетке.</small></section>;
  }
  return <section className="nf-workspace-panel nf-day-plan" aria-label="План публикаций на сутки">
    <header>
      <div><b>План на сутки</b><small>Каждый канал имеет собственный тайминг; пустые 15-минутные слоты остаются видимыми.</small></div>
      <label>Дата<select aria-label="Дата плана публикаций" value={activeDate} onChange={(event) => setSelectedDate(event.target.value)}>{dates.map((date) => <option key={date}>{date}</option>)}</select></label>
    </header>
    <div className="nf-day-plan-scroll">
      <table>
        <thead><tr><th>Канал</th>{slots.map((slot) => <th key={slot}>{labelForMinute(slot)}</th>)}</tr></thead>
        <tbody>{activeChannels.map((channel) => <tr key={channel.channelId}>
          <th><b>{channel.name}</b><small>{channel.timezone}</small></th>
          {slots.map((slot) => {
            const cell = dayRows.filter((row) => row.channelId === channel.channelId && minuteOfDay(row.publishAt) === slot);
            return <td key={slot} className={cell.length ? "filled" : ""}>{cell.map((row) => <span key={row.productionItemId} title={`${row.title} · ${row.productionItemId}`} data-production-item-id={row.productionItemId}>{row.title}</span>)}</td>;
          })}
        </tr>)}</tbody>
      </table>
    </div>
  </section>;
}

export function DistributionHealth({ rows }: { rows: DistributionRow[] }) {
  const assigned = rows.filter((row) => row.channelId).length;
  const unassigned = rows.filter((row) => !row.channelId);
  const conflicts = rows.filter((row) => row.warning);
  const quota = unassigned.filter((row) => row.reason === "quota_exhausted").length;
  const eligibility = unassigned.filter((row) => row.reason === "eligibility_mismatch").length;
  const locked = rows.filter((row) => row.locked).length;
  return <section className="nf-distribution-health" aria-label="Сводка распределения">
    <span><b>{assigned}</b> назначено</span>
    <span><b>{locked}</b> защищено</span>
    <span className={unassigned.length ? "warn" : ""}><b>{unassigned.length}</b> без канала</span>
    <span className={conflicts.length ? "danger" : ""}><b>{conflicts.length}</b> конфликтов времени</span>
    {quota ? <small>Квота закончилась для {quota} роликов — увеличьте квоту или включите ещё канал.</small> : null}
    {eligibility ? <small>{eligibility} роликов не проходят диапазон номера/длительности — проверьте правила каналов.</small> : null}
    {conflicts.length ? <small>Конфликты расписания надо исправить до подтверждения.</small> : null}
  </section>;
}
