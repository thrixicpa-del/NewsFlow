import { Progress } from "../../components/progress";
import { StatusBadge } from "../../components/status-badge";
import { buildTaskCenterEntries, type TaskCenterEntry } from "./task-model";

export function TaskCenter({ data, onSelect }: { data: NewsFlowSnapshot; onSelect?: (entry: TaskCenterEntry) => void }) {
  const entries = buildTaskCenterEntries(data);
  const visible = entries.filter((entry) => entry.status !== "READY").slice(0, 8);
  const running = entries.filter((entry) => entry.status === "RUNNING").length;
  const failed = entries.filter((entry) => entry.status === "FAILED").length;
  const ready = entries.filter((entry) => entry.status === "READY").length;
  return <section className="panel task-center" aria-label="Центр задач">
    <div className="panel-title">
      <div><b>Центр задач</b><small>Статусы приходят из очередей и worker-снимков, а не из нажатых кнопок.</small></div>
      <span className="task-center-summary">В работе: {running} · ошибок: {failed} · готово: {ready}</span>
    </div>
    {visible.length ? <div className="task-center-list">{visible.map((entry) => <button key={entry.id} type="button" onClick={() => onSelect?.(entry)} aria-label={`Открыть задачу: ${entry.title}`}>
      <div><b>{entry.title}</b><small>{entry.source} · {entry.detail}</small></div>
      {typeof entry.progress === "number" ? <Progress value={entry.progress} /> : null}
      <StatusBadge status={entry.status} />
    </button>)}</div> : <div className="task-center-empty">Нет активных или ошибочных задач.</div>}
  </section>;
}
