import { Progress } from "../../components/progress";
import { Sheet } from "../../components/sheet";
import { StatusBadge } from "../../components/status-badge";
import type { TaskCenterEntry } from "./task-model";

export function TaskInspector({ entry, onClose }: { entry: TaskCenterEntry | null; onClose: () => void }) {
  return <Sheet open={Boolean(entry)} onOpenChange={(open) => !open && onClose()} title={entry?.title || "Контекст задачи"} description="Снимок текущей очереди NewsFlow">
    {entry ? <div className="nf-task-inspector">
      <StatusBadge status={entry.status} />
      <dl>
        <div><dt>Источник</dt><dd>{entry.source}</dd></div>
        <div><dt>Task ID</dt><dd>{entry.id}</dd></div>
        <div><dt>Текущее состояние</dt><dd>{entry.detail}</dd></div>
      </dl>
      {typeof entry.progress === "number" ? <Progress value={entry.progress} label={`Прогресс задачи ${entry.title}: ${entry.progress}%`} /> : null}
      <p className="nf-task-inspector-note">Артефакт, provider и физический путь показываются только когда они явно доступны в текущем snapshot.</p>
    </div> : null}
  </Sheet>;
}
