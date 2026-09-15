import { Button } from "../components/button";
import { Progress } from "../components/progress";
import { StatusBadge } from "../components/status-badge";
import type { TaskCenterEntry } from "../features/task-center/task-model";

export function ContextInspector({ entry, width, density, onDensityChange, onWidthChange, onClose }: {
  entry: TaskCenterEntry | null;
  width: number;
  density: "comfortable" | "compact";
  onDensityChange(density: "comfortable" | "compact"): void;
  onWidthChange(width: number): void;
  onClose(): void;
}) {
  return <section className="nf-context-inspector" aria-label="Контекстный инспектор">
    <header>
      <div><span>CONTEXT INSPECTOR</span><h2>{entry?.title || "Выберите задачу"}</h2></div>
      {entry ? <Button size="icon" variant="ghost" onClick={onClose} aria-label="Закрыть контекст задачи">×</Button> : null}
    </header>
    {entry ? <div className="nf-context-inspector-body">
      <StatusBadge status={entry.status} />
      <dl>
        <div><dt>Источник</dt><dd>{entry.source}</dd></div>
        <div><dt>Task ID</dt><dd>{entry.id}</dd></div>
        <div><dt>Состояние</dt><dd>{entry.detail}</dd></div>
      </dl>
      {typeof entry.progress === "number" ? <Progress value={entry.progress} label={`Прогресс задачи ${entry.title}: ${entry.progress}%`} /> : null}
      <p>Артефакт, provider и физический путь появляются только после того, как текущий snapshot действительно их отдаёт.</p>
    </div> : <p className="nf-context-inspector-empty">Выберите строку в Центре задач, чтобы увидеть её текущий статус. Инспектор не создаёт задачи и не меняет очередь.</p>}
    <footer>
      <div className="nf-density-toggle" aria-label="Плотность рабочего пространства">
        <Button size="sm" variant={density === "comfortable" ? "primary" : "ghost"} onClick={() => onDensityChange("comfortable")}>Комфортный режим</Button>
        <Button size="sm" variant={density === "compact" ? "primary" : "ghost"} onClick={() => onDensityChange("compact")}>Компактный режим</Button>
      </div>
      <label>Ширина инспектора<input aria-label="Ширина инспектора" type="range" min="280" max="640" step="20" value={width} onChange={(event) => onWidthChange(Number(event.target.value))} /></label>
    </footer>
  </section>;
}
