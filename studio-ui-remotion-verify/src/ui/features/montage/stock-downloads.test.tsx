import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Editor, fallback } from '../../App';

describe('Persisted montage download timeline', () => {
  const state = {
    runId: 'fixture', running: true, limit: 30, active: 12, queued: 18,
    completed: 100, failed: 2, cancelled: 0, bytesDownloaded: 10485760,
    bytesPerSecond: 2097152, elapsedSeconds: 5, phaseSeconds: { search: 1, validation: 3 },
    history: [{ event: 'completed', updatedAt: 1792614900, queued: 18, active: 12, completed: 100, failed: 2 }],
  };
  it('shows queue counts, actual byte rate and saved events in the task timeline', () => {
    const data = { ...fallback, stockDownloads: state };
    render(<Editor data={data} command={vi.fn()} refresh={async () => undefined} />);
    expect(screen.getByText('В очереди: 18 · Скачиваются: 12 / 30 · Готово: 100 · Ошибки: 2')).toBeTruthy();
    expect(screen.getByText(/10.0 МБ.*2.0 МБ\/с/)).toBeTruthy();
    expect(screen.getByText('История загрузок')).toBeTruthy();
  });
  it('labels counters from a stopped process as historical rather than live work', () => {
    const data = { ...fallback, stockDownloads: { ...state, running: false, interrupted: true } };
    render(<Editor data={data} command={vi.fn()} refresh={async () => undefined} />);
    expect(screen.getByText(/Прервано.*сохранённые данные/)).toBeTruthy();
    expect(screen.getByText(/Ожидали: 18.*Скачивались: 12/)).toBeTruthy();
  });
});
