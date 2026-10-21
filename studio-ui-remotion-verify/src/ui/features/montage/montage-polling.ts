export type PendingMontageLaunch = { index: number; previousUpdatedAt: string };

/** Keep polling only tasks launched in this renderer, not abandoned historical rows. */
export function unsettledMontageLaunches(
  launches: PendingMontageLaunch[],
  tasks: { index: number; status?: string; updatedAt?: string | null }[],
): PendingMontageLaunch[] {
  return launches.filter((launch) => {
    const task = tasks.find((item) => item.index === launch.index);
    if (!task) return true;
    const changed = String(task.updatedAt ?? "") !== launch.previousUpdatedAt;
    return !(
      changed &&
      ["Готово", "Ошибка", "Пауза", "done", "error", "paused"].includes(task.status || "")
    );
  });
}
