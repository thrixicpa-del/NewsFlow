import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PublicationPage } from "./PublicationPage";

const base = {
  channels: [{ id: "channel-a", channel: "channel-a", name: "Первый канал", subscribers: "30 000", status: "Подключён", oauthConnected: true, monetaryAccess: true }],
  publication: { uploadConcurrency: 6, v2: {
    items: {
      "item-ready": { productionItemId: "item-ready", metadata: { title: "Готовый ролик" }, readiness: { state: "VIDEO_READY" }, artifacts: { video: { path: "D:/ready.mp4", exists: true } } },
      "item-uploaded": { productionItemId: "item-uploaded", metadata: { title: "Уже загруженный ролик" }, readiness: { state: "VIDEO_READY" }, artifacts: { video: { path: "D:/uploaded.mp4", exists: true } } },
    },
    queue: [
      { snapshotId: "snapshot-ready", productionItemId: "item-ready", title: "Готовый ролик", channelId: "channel-a", currentStage: "WAITING", status: "WAITING", active: false, completion: { completed: 0, total: 8 }, steps: {} },
      { snapshotId: "snapshot-uploaded", productionItemId: "item-uploaded", title: "Уже загруженный ролик", channelId: "channel-a", currentStage: "THUMBNAIL", status: "PARTIAL", active: false, youtubeVideoId: "yt-123", completion: { completed: 4, total: 8 }, steps: { VIDEO_UPLOAD: { status: "SUCCESS" }, THUMBNAIL: { status: "FAILED" } } },
    ], counters: {}, paused: false, uploadConcurrency: 6, channelRules: {}, assignments: {},
  } },
} as unknown as NewsFlowSnapshot;

describe("PublicationPage interactions", () => {
  it("opens compact channel settings with range and quarter-hour scheduling controls", () => {
    render(<PublicationPage data={base} command={vi.fn().mockResolvedValue(undefined)} />);
    fireEvent.click(screen.getByRole("tab", { name: "Каналы" }));
    expect(screen.getByRole("columnheader", { name: "Действия" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Действия канала Первый канал" }));
    expect(screen.getByText("Количество роликов")).toBeInTheDocument();
    expect(screen.getByLabelText("Ролики с №")).toBeInTheDocument();
    expect(screen.getByLabelText("Ролики по №")).toBeInTheDocument();
    expect(screen.getByLabelText("Первый выход")).toHaveAttribute("step", "900");
    expect(screen.getByLabelText("Окно: начало")).toHaveAttribute("step", "900");
    expect(screen.getByText(/:00 \/ :15 \/ :30 \/ :45/)).toBeInTheDocument();
    expect(screen.getByText("Реклама / монетизация")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeInTheDocument();
  });

  it("starts only snapshots without a known YouTube video ID", async () => {
    const command = vi.fn().mockResolvedValue(undefined);
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("tab", { name: "Очередь" }));
    fireEvent.click(screen.getByRole("button", { name: "Запустить очередь" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("upload-publication-v2-snapshots", { snapshotIds: ["snapshot-ready"] }));
  });

  it("starts only explicitly selected queue snapshots", async () => {
    const command = vi.fn().mockResolvedValue(undefined);
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("tab", { name: "Очередь" }));
    fireEvent.click(screen.getByLabelText("Выбрать публикацию Готовый ролик"));
    fireEvent.click(screen.getByRole("button", { name: "Запустить выбранные (1)" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "upload-publication-v2-snapshots",
      { snapshotIds: ["snapshot-ready"] },
    ));
  });


  it("does not submit the current publication upload twice while it is pending", async () => {
    let releaseUpload: (() => void) | undefined;
    const command = vi.fn(() => new Promise<NewsFlowSnapshot | undefined>((resolve) => {
      releaseUpload = () => resolve(undefined);
    }));
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("tab", { name: "Очередь" }));
    const start = screen.getByRole("button", { name: "Запустить очередь" });
    fireEvent.click(start);
    fireEvent.click(start);

    await Promise.resolve();
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("upload-publication-v2-snapshots", { snapshotIds: ["snapshot-ready"] });
    releaseUpload?.();
    await waitFor(() => expect(screen.getByRole("button", { name: "Запустить очередь" })).toBeEnabled());
  });

  it("sends only selected production items to smart distribution preview", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [] } });
    render(<PublicationPage data={base} command={command} />);

    fireEvent.click(screen.getByLabelText("Выбрать Готовый ролик"));
    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "preview-publication-v2-distribution",
      { productionItemIds: ["item-ready"] },
    ));
  });

  it("opens non-uploading distribution preview and preserves its manual lock affordance", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [{ productionItemId: "item-ready", channelId: "channel-a", source: "auto", locked: false, reason: "Квота", publishAt: "" }] } });
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "Распределение" })).toHaveAttribute("aria-selected", "true"));
    expect(screen.getByText("AUTO")).toBeInTheDocument();
    expect(command).toHaveBeenCalledWith("preview-publication-v2-distribution");
  });

  it("sends an operator-selected time range to the non-uploading distribution preview", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [] } });
    render(<PublicationPage data={base} command={command} />);

    fireEvent.click(screen.getByRole("tab", { name: "Распределение" }));
    fireEvent.change(screen.getByLabelText("Дата диапазона"), { target: { value: "2026-11-15" } });
    fireEvent.change(screen.getByLabelText("Начало диапазона"), { target: { value: "04:00" } });
    fireEvent.change(screen.getByLabelText("Конец диапазона"), { target: { value: "10:00" } });
    fireEvent.change(screen.getByLabelText("Максимум роликов на канал"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Показать диапазон" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("preview-publication-v2-distribution", {
      bulkSchedule: {
        date: "2026-11-15", startTime: "04:00", endTime: "10:00", timezone: "Europe/Minsk",
        channelIds: ["channel-a"], maxPerChannel: 4,
      },
    }));
  });

  it("explains channel-capacity exhaustion in Russian instead of exposing the raw runtime code", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [{ productionItemId: "item-ready", channelId: "", source: "", locked: false, reason: "quota_exhausted", publishAt: "" }] } });
    render(<PublicationPage data={base} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));

    await waitFor(() => expect(screen.getByText("Нет свободной квоты у выбранных каналов")).toBeInTheDocument());
    expect(screen.queryByText("quota_exhausted")).not.toBeInTheDocument();
  });

  it("blocks confirmation in the UI when preview reports a scheduling conflict", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [{ productionItemId: "item-ready", channelId: "channel-a", source: "manual", locked: true, reason: "Ручное назначение", publishAt: "2026-09-11T22:00:00", scheduleWarning: "Вне окна публикации" }] } });
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));
    await waitFor(() => expect(screen.getByText("Вне окна публикации")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Подтвердить назначения" })).toBeDisabled();
  });
});
