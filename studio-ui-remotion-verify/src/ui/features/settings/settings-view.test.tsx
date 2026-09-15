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

  it("keeps session creation in the established command path", () => {
    const command = vi.fn();
    const prompt = vi.spyOn(window, "prompt").mockReturnValue("Рабочая сессия");
    render(<Sessions data={fallback} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Добавить сессию" }));
    expect(command).toHaveBeenCalledWith("add-session", { label: "Рабочая сессия" });
    prompt.mockRestore();
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
