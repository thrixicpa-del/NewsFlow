import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App, fallback, Keys, Knowledge, Sessions } from "../../App";

describe("Settings Light views", () => {
  afterEach(() => {
    delete window.newsflowDesktop;
  });

  it("keeps credentials and sessions in the structured settings workspace", () => {
    const command = vi.fn();
    const { unmount } = render(<Keys data={fallback} command={command} />);
    expect(screen.getByLabelText("Structured settings: API keys")).toBeTruthy();
    unmount();

    render(<Sessions data={fallback} command={command} />);
    expect(screen.getByLabelText("Structured settings: sessions")).toBeTruthy();
  });

  it("keeps API-key creation on the current secure command contract", async () => {
    const command = vi.fn(async () => fallback);
    render(<Keys data={fallback} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Добавить ключ" }));
    fireEvent.change(screen.getByLabelText("API-ключ"), { target: { value: "test-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить ключ" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("add-api-key", { kind: "fastgen", label: "FastGen основной", secret: "test-key" }));
  });

  it("loads only the selected key on explicit edit and reveals it only on request", async () => {
    const revealApiKey = vi.fn(async () => ({ label: "Existing", secret: "synthetic-old", revision: "old-revision" }));
    window.newsflowDesktop = { revealApiKey } as unknown as Window["newsflowDesktop"];
    const data = { ...fallback, keyStatus: { ...fallback.keyStatus,
      fastgen: [{ label: "Existing", active: true, fingerprint: "old-id" }] } };
    const command = vi.fn(async () => data);
    render(<Keys data={data} command={command} />);
    expect(revealApiKey).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Редактировать ключ Existing" }));
    const input = await screen.findByLabelText("API-ключ");
    expect((input as HTMLInputElement).value).toBe("synthetic-old");
    expect(input.getAttribute("type")).toBe("password");
    expect(revealApiKey).toHaveBeenCalledExactlyOnceWith({ kind: "fastgen", index: 0, fingerprint: "old-id" });
    fireEvent.click(screen.getByRole("button", { name: "Показать ключ" }));
    expect(input.getAttribute("type")).toBe("text");
    fireEvent.click(screen.getByRole("button", { name: "Скрыть ключ" }));
    expect(input.getAttribute("type")).toBe("password");
    fireEvent.change(input, { target: { value: "synthetic-new" } });
    fireEvent.change(screen.getByLabelText("Название ключа"), { target: { value: "Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить ключ" }));
    await waitFor(() => expect(command).toHaveBeenCalledExactlyOnceWith("update-api-key", {
      kind: "fastgen", index: 0, fingerprint: "old-id", revision: "old-revision", label: "Renamed", secret: "synthetic-new",
    }));
    await waitFor(() => expect(screen.queryByLabelText("API-ключ")).toBeNull());
  });

  it("preserves an edited key on save error without leaking the error payload", async () => {
    window.newsflowDesktop = { revealApiKey: vi.fn(async () => ({ label: "Existing", secret: "synthetic-old", revision: "old-revision" })) } as unknown as Window["newsflowDesktop"];
    const data = { ...fallback, keyStatus: { ...fallback.keyStatus,
      fastgen: [{ label: "Existing", active: true, fingerprint: "old-id" }] } };
    const command = vi.fn(async () => { throw new Error("synthetic-new"); });
    render(<Keys data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Редактировать ключ Existing" }));
    fireEvent.change(await screen.findByLabelText("API-ключ"), { target: { value: "synthetic-new" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить ключ" }));
    expect((await screen.findByRole("alert")).textContent).not.toContain("synthetic-new");
    expect((screen.getByLabelText("API-ключ") as HTMLInputElement).value).toBe("synthetic-new");
    fireEvent.click(screen.getByRole("button", { name: "Сохранить ключ" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(2));
  });

  it("locks pending edit fetch and cancels without writing or retaining revealed state", async () => {
    let finish!: (value: { label: string; secret: string; revision: string }) => void;
    const revealApiKey = vi.fn(() => new Promise<{ label: string; secret: string; revision: string }>((resolve) => { finish = resolve; }));
    window.newsflowDesktop = { revealApiKey } as unknown as Window["newsflowDesktop"];
    const data = { ...fallback, keyStatus: { ...fallback.keyStatus,
      fastgen: [{ label: "Existing", active: true, fingerprint: "old-id" }] } };
    const command = vi.fn();
    render(<Keys data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Редактировать ключ Existing" }));
    fireEvent.click(screen.getByRole("button", { name: "Редактировать ключ Existing" }));
    expect(revealApiKey).toHaveBeenCalledTimes(1);
    finish({ label: "Existing", secret: "synthetic-old", revision: "old-revision" });
    await screen.findByLabelText("API-ключ");
    fireEvent.click(screen.getByRole("button", { name: "Показать ключ" }));
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    expect(screen.queryByLabelText("API-ключ")).toBeNull();
    expect(command).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Добавить ключ" }));
    expect((screen.getByLabelText("API-ключ") as HTMLInputElement).value).toBe("");
    expect(screen.getByLabelText("API-ключ").getAttribute("type")).toBe("password");
  });

  it("shows a safe local error when reveal fails and releases its lock", async () => {
    const revealApiKey = vi.fn(async () => { throw new Error("synthetic-sensitive"); });
    window.newsflowDesktop = { revealApiKey } as unknown as Window["newsflowDesktop"];
    const data = { ...fallback, keyStatus: { ...fallback.keyStatus,
      fastgen: [{ label: "Existing", active: true, fingerprint: "old-id" }] } };
    render(<Keys data={data} command={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Редактировать ключ Existing" }));
    expect((await screen.findByRole("alert")).textContent).not.toContain("synthetic-sensitive");
    fireEvent.click(screen.getByRole("button", { name: "Редактировать ключ Existing" }));
    await waitFor(() => expect(revealApiKey).toHaveBeenCalledTimes(2));
    expect(screen.queryByLabelText("API-ключ")).toBeNull();
  });

  it("does not submit twice while credential replacement is pending", async () => {
    window.newsflowDesktop = { revealApiKey: vi.fn(async () => ({ label: "Existing", secret: "synthetic-old", revision: "old-revision" })) } as unknown as Window["newsflowDesktop"];
    const data = { ...fallback, keyStatus: { ...fallback.keyStatus,
      fastgen: [{ label: "Existing", active: true, fingerprint: "old-id" }] } };
    let finish!: (value: typeof data) => void;
    const command = vi.fn(() => new Promise<typeof data>((resolve) => { finish = resolve; }));
    render(<Keys data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Редактировать ключ Existing" }));
    const input = await screen.findByLabelText("API-ключ");
    fireEvent.change(input, { target: { value: "synthetic-new" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(command).toHaveBeenCalledTimes(1);
    expect((input as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Название ключа") as HTMLInputElement).disabled).toBe(true);
    finish(data);
    await waitFor(() => expect(screen.queryByLabelText("API-ключ")).toBeNull());
  });

  it("discards an existing key edit without overwriting the persisted credential", async () => {
    window.newsflowDesktop = { revealApiKey: vi.fn(async () => ({ label: "Existing", secret: "synthetic-old", revision: "old-revision" })) } as unknown as Window["newsflowDesktop"];
    const data = { ...fallback, keyStatus: { ...fallback.keyStatus,
      fastgen: [{ label: "Existing", active: true, fingerprint: "old-id" }] } };
    const command = vi.fn();
    render(<Keys data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Редактировать ключ Existing" }));
    fireEvent.change(await screen.findByLabelText("API-ключ"), { target: { value: "synthetic-new" } });
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    fireEvent.click(screen.getByRole("button", { name: "Не сохранять" }));
    expect(screen.queryByLabelText("API-ключ")).toBeNull();
    expect(command).not.toHaveBeenCalled();
  });

  it("asks before discarding an edited API-key form without writing a secret", () => {
    const command = vi.fn();
    render(<Keys data={fallback} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Добавить ключ" }));
    fireEvent.change(screen.getByLabelText("API-ключ"), { target: { value: "test-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));

    expect(screen.getByRole("dialog", { name: "Несохранённый API-ключ" })).toBeTruthy();
    expect(command).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Не сохранять" }));
    expect(screen.queryByLabelText("API-ключ")).toBeNull();
  });

  it("keeps session creation in the established command path through an in-app dialog", async () => {
    const command = vi.fn().mockResolvedValue(fallback);
    render(<Sessions data={fallback} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Добавить сессию" }));
    expect(screen.getByRole("dialog", { name: "Добавить Chrome-сессию" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Название Chrome-сессии"), {
      target: { value: "Рабочая сессия" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Создать сессию" }));

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("add-session", { label: "Рабочая сессия" }),
    );
  });

  it("keeps a dirty Obsidian connection open until the user discards it before navigation", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "НАСТРОЙКИ" }));
    fireEvent.click(screen.getByRole("button", { name: "База проекта" }));
    fireEvent.change(screen.getByLabelText("Адрес локального Vault MCP"), {
      target: { value: "http://127.0.0.1:4711/mcp" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Центр управления" }));

    expect(screen.getByRole("dialog", { name: "Несохранённые изменения" })).toBeTruthy();
    expect(screen.getByLabelText("Адрес локального Vault MCP").getAttribute("value")).toBe("http://127.0.0.1:4711/mcp");

    fireEvent.click(screen.getByRole("button", { name: "Не сохранять" }));
    expect(screen.getByRole("heading", { name: "Центр управления" })).toBeTruthy();
  });

  it("keeps a dirty API-key form open until the user discards it before navigation", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "НАСТРОЙКИ" }));
    fireEvent.click(screen.getByRole("button", { name: "API-ключи" }));
    fireEvent.click(screen.getByRole("button", { name: "Добавить ключ" }));
    fireEvent.change(screen.getByLabelText("API-ключ"), { target: { value: "test-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Центр управления" }));

    expect(screen.getByRole("dialog", { name: "Несохранённые изменения" })).toBeTruthy();
    expect(screen.getByLabelText("API-ключ").getAttribute("value")).toBe("test-key");

    fireEvent.click(screen.getByRole("button", { name: "Не сохранять" }));
    expect(screen.getByRole("heading", { name: "Центр управления" })).toBeTruthy();
  });

  it("saves only the active dirty API-key form through Ctrl+S", async () => {
    const command = vi.fn(async () => fallback);
    window.newsflowDesktop = {
      snapshot: vi.fn(async () => fallback),
      command,
    } as unknown as Window["newsflowDesktop"];
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "НАСТРОЙКИ" }));
    fireEvent.click(screen.getByRole("button", { name: "API-ключи" }));
    fireEvent.click(screen.getByRole("button", { name: "Добавить ключ" }));
    fireEvent.change(screen.getByLabelText("API-ключ"), { target: { value: "test-key" } });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });

    await waitFor(() => expect(command).toHaveBeenCalledWith("add-api-key", {
      kind: "fastgen",
      label: "FastGen основной",
      secret: "test-key",
    }));
  });

  it("saves a dirty API-key form through the current command before navigation", async () => {
    const command = vi.fn(async () => fallback);
    window.newsflowDesktop = {
      snapshot: vi.fn(async () => fallback),
      command,
    } as unknown as Window["newsflowDesktop"];
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "НАСТРОЙКИ" }));
    fireEvent.click(screen.getByRole("button", { name: "API-ключи" }));
    fireEvent.click(screen.getByRole("button", { name: "Добавить ключ" }));
    fireEvent.change(screen.getByLabelText("API-ключ"), { target: { value: "test-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Центр управления" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить и перейти" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("add-api-key", {
      kind: "fastgen",
      label: "FastGen основной",
      secret: "test-key",
    }));
    expect(screen.getByRole("heading", { name: "Центр управления" })).toBeTruthy();
  });

  it("saves a dirty Obsidian connection through its current command before navigation", async () => {
    const command = vi.fn(async () => fallback);
    window.newsflowDesktop = {
      snapshot: vi.fn(async () => fallback),
      command,
    } as unknown as Window["newsflowDesktop"];
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "НАСТРОЙКИ" }));
    fireEvent.click(screen.getByRole("button", { name: "База проекта" }));
    fireEvent.change(screen.getByLabelText("Адрес локального Vault MCP"), {
      target: { value: "http://127.0.0.1:4711/mcp" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Центр управления" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить и перейти" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-obsidian-settings", {
      vaultPath: fallback.obsidian.vaultPath,
      mcpUrl: "http://127.0.0.1:4711/mcp",
      token: "",
      syncEnabled: fallback.obsidian.syncEnabled,
    }));
    expect(screen.getByRole("heading", { name: "Центр управления" })).toBeTruthy();
  });

  it("saves only the active dirty Obsidian connection through Ctrl+S", async () => {
    const command = vi.fn(async () => fallback);
    window.newsflowDesktop = {
      snapshot: vi.fn(async () => fallback),
      command,
    } as unknown as Window["newsflowDesktop"];
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "НАСТРОЙКИ" }));
    fireEvent.click(screen.getByRole("button", { name: "База проекта" }));
    fireEvent.change(screen.getByLabelText("Адрес локального Vault MCP"), {
      target: { value: "http://127.0.0.1:4711/mcp" },
    });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-obsidian-settings", {
      vaultPath: fallback.obsidian.vaultPath,
      mcpUrl: "http://127.0.0.1:4711/mcp",
      token: "",
      syncEnabled: fallback.obsidian.syncEnabled,
    }));
  });

  it("keeps an Obsidian connection draft open when the current save command has no result", async () => {
    const command = vi.fn(async () => undefined);
    render(<Knowledge data={fallback} command={command} />);

    fireEvent.change(screen.getByLabelText("Адрес локального Vault MCP"), {
      target: { value: "http://127.0.0.1:4711/mcp" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить подключение" }));

    expect(command).toHaveBeenCalledWith("save-obsidian-settings", {
      vaultPath: fallback.obsidian.vaultPath,
      mcpUrl: "http://127.0.0.1:4711/mcp",
      token: "",
      syncEnabled: fallback.obsidian.syncEnabled,
    });
    expect((await screen.findByRole("alert")).textContent).toContain("Черновик остаётся открытым");
    expect(screen.getByLabelText("Адрес локального Vault MCP").getAttribute("value")).toBe("http://127.0.0.1:4711/mcp");
  });
});
