import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Audio, fallback, VoiceProfiles, VoiceProfilesScreen, VoiceQueue } from "../../App";

describe("Voice Light views", () => {
  it("keeps the voice queue in the Audio Production Console", () => {
    render(<VoiceQueue data={fallback} go={vi.fn()} command={vi.fn()} refresh={async () => undefined} />);

    expect(screen.getByLabelText("Audio Production Console")).toBeTruthy();
    expect(screen.getByLabelText("Действия очереди озвучки")).toBeTruthy();
  });

  it("keeps the current voice generation command", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      scenarios: [{ index: 2, title: "Ормуз", state: "Готово", result: "Текст", error: "" }],
      voiceItems: [{ index: 2, title: "Ормуз", state: "Ожидает", path: "" }],
    };
    render(<VoiceQueue data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    expect(screen.getByRole("table", { name: "Очередь озвучки" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "3. Ормуз" }));
    fireEvent.click(screen.getByRole("button", { name: "Озвучить выбранные" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("generate-voice", { indices: [2] }));
  });

  it("does not submit selected voice generation twice while the current command is pending", async () => {
    let releaseCurrentCommand: (() => void) | undefined;
    const command = vi.fn(() => new Promise<NewsFlowSnapshot | undefined>((resolve) => {
      releaseCurrentCommand = () => resolve(undefined);
    }));
    const data = {
      ...fallback,
      scenarios: [{ index: 2, title: "Ормуз", state: "Готово", result: "Текст", error: "" }],
      voiceItems: [{ index: 2, title: "Ормуз", state: "Ожидает", path: "" }],
    };
    render(<VoiceQueue data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "3. Ормуз" }));
    const start = screen.getByRole("button", { name: "Озвучить выбранные" });
    fireEvent.click(start);
    fireEvent.click(start);

    await Promise.resolve();
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("generate-voice", { indices: [2] });
    await act(async () => {
      releaseCurrentCommand?.();
      await Promise.resolve();
    });
  });

  it("does not submit the current voice-all command twice while it is pending", async () => {
    let releaseCurrentCommand: (() => void) | undefined;
    const command = vi.fn(() => new Promise<NewsFlowSnapshot | undefined>((resolve) => {
      releaseCurrentCommand = () => resolve(undefined);
    }));
    const data = {
      ...fallback,
      scenarios: [{ index: 2, title: "Ормуз", state: "Готово", result: "Текст", error: "" }],
      voiceItems: [{ index: 2, title: "Ормуз", state: "Ожидает", path: "" }],
    };
    render(<VoiceQueue data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    const start = screen.getByRole("button", { name: "Озвучить всё" });
    act(() => {
      fireEvent.click(start);
      fireEvent.click(start);
    });

    await Promise.resolve();
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("generate-voice-queue", {});
    await act(async () => {
      releaseCurrentCommand?.();
      await Promise.resolve();
    });
  });

  it("shares a synchronous voice-generation lock between selected and all queue actions", () => {
    const command = vi.fn(() => new Promise<NewsFlowSnapshot | undefined>(() => {}));
    const data = {
      ...fallback,
      scenarios: [{ index: 2, title: "Ормуз", state: "Готово", result: "Текст", error: "" }],
      voiceItems: [{ index: 2, title: "Ормуз", state: "Ожидает", path: "" }],
    };
    render(<VoiceQueue data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "3. Ормуз" }));
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Озвучить выбранные" }));
      fireEvent.click(screen.getByRole("button", { name: "Озвучить всё" }));
    });

    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("generate-voice", { indices: [2] });
  });

  it("selects a voice item through the table keyboard workflow without starting a job", () => {
    const command = vi.fn();
    const data = {
      ...fallback,
      scenarios: [{ index: 2, title: "Ормуз", state: "Готово", result: "Текст", error: "" }],
      voiceItems: [{ index: 2, title: "Ормуз", state: "Ожидает", path: "" }],
    };
    render(<VoiceQueue data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.keyDown(screen.getAllByRole("row")[1], { key: "Enter" });
    expect(screen.getByText("Выбрано: 1")).toBeTruthy();
    expect(command).not.toHaveBeenCalled();
  });

  it("starts every eligible queue item through the dedicated current command", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      scenarios: [
        { index: 0, title: "Готовый сценарий", state: "Готово", result: "Текст", error: "" },
        { index: 1, title: "В ожидании", state: "Ожидает", result: "", error: "" },
      ],
      voiceItems: [
        { index: 0, title: "Готовый сценарий", state: "Ожидает", path: "" },
        { index: 1, title: "В ожидании", state: "Ожидает", path: "" },
      ],
    };
    render(<VoiceQueue data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Озвучить всё" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("generate-voice-queue", {}));
  });

  it("saves global queue concurrency together with the active voice profile contract", () => {
    const command = vi.fn();
    const data = {
      ...fallback,
      voiceProfiles: [{ id: "voice-1", name: "Новости", provider: "wproject" as const, voice_id: "voice-a" }],
      voiceRanges: [{ id: "range-1", start: 1, end: 10, profile_id: "voice-1", enabled: true }],
      voiceDefaultProfileId: "voice-1",
      voiceQueueConcurrency: 1,
    };
    render(<VoiceProfiles data={data} command={command} go={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Одновременных TTS-задач"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить профили и диапазоны" }));

    expect(command).toHaveBeenCalledWith("save-voice-settings", {
      profiles: data.voiceProfiles,
      ranges: data.voiceRanges,
      defaultProfileId: "voice-1",
      queueConcurrency: 10,
    });
    expect(screen.getByText("Фактический параллелизм = минимум из этого значения и доступных потоков API-ключей; Chrome работает в 1 браузерный поток.")).toBeTruthy();
  });

  it("keeps ready MP3 removal on the current command", () => {
    const command = vi.fn();
    const data = { ...fallback, voiceItems: [{ index: 3, title: "Готовый MP3", state: "Готово", path: "D:/test.mp3" }] };
    render(<Audio data={data} command={command} />);
    expect(screen.getByRole("table", { name: "Готовые MP3" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "4. Готовый MP3" })).not.toBeNull();
  });

  it("shows only snapshot-backed provenance when a ready MP3 is inspected", () => {
    const data = {
      ...fallback,
      voiceItems: [{
        index: 3,
        title: "Готовый MP3",
        state: "Готово",
        path: "D:/test.mp3",
        productionItemId: "item-ormuz",
        voiceProvider: "wproject",
        voiceName: "Новости",
        jobSnapshotId: "voice-job-42",
        voiceUpdatedAt: "2026-09-15T12:00:00Z",
      }],
    };
    render(<Audio data={data} command={vi.fn()} />);

    fireEvent.keyDown(screen.getAllByRole("row")[1], { key: "Enter" });

    expect(screen.getByText("Инспектор MP3")).toBeTruthy();
    expect(screen.getByText("ProductionItem ID")).toBeTruthy();
    expect(screen.getByText("item-ormuz")).toBeTruthy();
    expect(screen.getByText("voice-job-42")).toBeTruthy();
    expect(screen.getByText("Текущий snapshot не сообщает признак устаревания")).toBeTruthy();
  });

  it("uses a profile table before the existing voice-profile editor", () => {
    render(<VoiceProfiles data={fallback} command={vi.fn()} go={vi.fn()} />);

    expect(screen.getByRole("table", { name: "Профили голосов" })).toBeTruthy();
  });

  it("keeps provider readiness out of the profile-editing workspace until requested", () => {
    render(<VoiceProfilesScreen data={fallback} command={vi.fn()} go={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Проверить готовность провайдеров" })).toBeTruthy();
    expect(screen.queryByText("Пул API Secret Voicer")).toBeNull();
  });
});
