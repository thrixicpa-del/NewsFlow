export function Progress({ value, label }: { value: number; label?: string }) {
  const safeValue = Math.max(0, Math.min(100, Number(value) || 0));
  return <span className="task-center-progress" aria-label={label || `Прогресс ${safeValue}%`}><i style={{ width: `${safeValue}%` }} /></span>;
}
