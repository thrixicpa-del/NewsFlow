import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fallback, VoiceQueue } from "../../App";

const data: NewsFlowSnapshot = {
  ...fallback,
  scenarios: Array.from({ length: 84 }, (_, index) => ({ index, title: `Тема ${index + 1}`, state: "Готово", result: "Текст", error: "" })),
  voiceItems: Array.from({ length: 84 }, (_, index) => ({ index, title: `Тема ${index + 1}`, state: "Готово", path: "", voiceStatus: "WProject: создаёт озвучку", voiceProgress: 8 })),
};

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("Voice queue background refresh", () => {
  it("shows completed MP3 after reopening a running queue without another generation command", async () => {
    vi.useFakeTimers();
    const command = vi.fn();
    let reads = 0;
    function Queue() {
      const [snapshot, setSnapshot] = useState(data);
      return <VoiceQueue data={snapshot} go={vi.fn()} command={command} refresh={async () => {
        reads += 1;
        setSnapshot({ ...data, voiceItems: data.voiceItems.map((item) => item.index === 0 ? { ...item, path: "D:/test/001.mp3", voiceStatus: "Готово", voiceProgress: 100 } : item) });
      }} />;
    }
    const first = render(<Queue />);
    first.unmount();
    render(<Queue />);
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(reads).toBe(1);
    expect(screen.getByText("001.mp3")).toBeTruthy();
    expect(command).not.toHaveBeenCalled();
  });

  it("keeps selection responsive and allows only one pending refresh for 84 rows", async () => {
    vi.useFakeTimers();
    let finish: (() => void) | undefined;
    const refresh = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    render(<VoiceQueue data={data} go={vi.fn()} command={vi.fn()} refresh={refresh} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(refresh).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "84. Тема 84" }));
    expect(screen.getByText("Выбрано: 1")).toBeTruthy();
    await act(async () => { finish?.(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it("continues polling after a read failure and stops when the view is closed", async () => {
    vi.useFakeTimers();
    const refresh = vi.fn().mockRejectedValueOnce(new Error("temporary read failure")).mockResolvedValue(undefined);
    const view = render(<VoiceQueue data={data} go={vi.fn()} command={vi.fn()} refresh={refresh} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(refresh).toHaveBeenCalledTimes(2);
    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it("does not restart polling on every returned snapshot or callback identity", async () => {
    vi.useFakeTimers();
    const refresh = vi.fn(async () => undefined);
    const view = render(<VoiceQueue data={data} go={vi.fn()} command={vi.fn()} refresh={() => refresh()} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    view.rerender(<VoiceQueue data={{ ...data }} go={vi.fn()} command={vi.fn()} refresh={() => refresh()} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
