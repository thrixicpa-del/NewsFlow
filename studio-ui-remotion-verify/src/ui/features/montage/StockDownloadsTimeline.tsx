import './stock-downloads.css';

const events: Record<string, string> = {
  started: 'Запуск', queued: 'Добавлено в очередь', downloading: 'Загрузка',
  completed: 'Файл готов', failed: 'Ошибка загрузки', cancelled: 'Отменено',
  stopped: 'Остановлено', progress: 'Получение данных', search: 'Поиск', validation: 'Проверка кадров',
};

export function StockDownloadsTimeline({ status }: { status?: StockDownloadStatus }) {
  if (!status?.runId) return null;
  const mb = (value: number) => (Math.max(0, value || 0) / 1048576).toFixed(1);
  const label = status.running ? 'Работает' : status.interrupted ? 'Прервано · сохранённые данные' : 'Остановлено · сохранённые данные';
  return (
    <div className="stock-download-timeline" aria-label="Загрузка стоков">
      <b>Загрузка стоков · {label}</b>
      <p>{status.running ? 'В очереди' : 'Ожидали'}: {status.queued} · {status.running ? 'Скачиваются' : 'Скачивались'}: {status.active} / {status.limit} · Готово: {status.completed} · Ошибки: {status.failed}</p>
      <p>Получено: {mb(status.bytesDownloaded)} МБ · Средняя с начала запуска: {mb(status.bytesPerSecond)} МБ/с · Отменено: {status.cancelled}</p>
      <p>Суммарное время потоков: поиск {status.phaseSeconds.search.toFixed(1)} с · проверка кадров {status.phaseSeconds.validation.toFixed(1)} с</p>
      <p>Это очередь найденных файлов, а не число всех сцен. Готовые файлы ещё проходят проверку пригодности для монтажа.</p>
      <details>
        <summary>История загрузок</summary>
        <div className="task-timeline">
          {(status.history || []).map((event, index) => (
            <small className="task-timeline-entry" key={index}>
              <b>{new Date(event.updatedAt * 1000).toLocaleTimeString()}</b> {events[event.event] || 'Состояние'} · в очереди {event.queued} · загрузок {event.active} · готово {event.completed} · ошибок {event.failed}
            </small>
          ))}
        </div>
      </details>
    </div>
  );
}
