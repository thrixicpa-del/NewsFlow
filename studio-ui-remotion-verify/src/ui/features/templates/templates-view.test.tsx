import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Agents, App, fallback, TemplateEditor } from "../../App";

describe("Template writing desk", () => {
  afterEach(() => {
    delete window.newsflowDesktop;
  });
  it("presents agent capabilities as an editorial routing workspace", () => {
    const go = vi.fn();
    render(<Agents data={fallback} go={go} />);

    expect(screen.getByLabelText("Editorial agent workspace")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Возможности агентов" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Открыть сценарии" }));
    expect(go).toHaveBeenCalledWith("scenarios");
  });

  it("keeps the current save-template contract inside the prompt studio", async () => {
    const command = vi.fn(async () => fallback);
    render(<TemplateEditor data={fallback} command={command} />);

    expect(screen.getByLabelText("Writing prompt studio")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Базовый шаблон сценария"), {
      target: { value: "Новый шаблон {title}" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить шаблон" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-template", {
      template: "Новый шаблон {title}",
      targetChars: 0,
      allowedMin: 0,
      allowedMax: 0,
      ranges: fallback.templateSettings.ranges,
    }));
  });

  it("sends the template character target to Core and persists it with a preset", async () => {
    const command = vi.fn(async () => fallback);
    render(<TemplateEditor data={fallback} command={command} />);

    fireEvent.change(screen.getByLabelText("Цель знаков шаблона"), {
      target: { value: "10000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить шаблон" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-template", {
      template: fallback.templateSettings.template,
      targetChars: 10000,
      allowedMin: 0,
      allowedMax: 0,
      ranges: fallback.templateSettings.ranges,
    }));

    fireEvent.change(screen.getByPlaceholderText("Название нового пресета"), {
      target: { value: "Десять тысяч" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить пресет" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-template-preset", {
      name: "Десять тысяч",
      template: fallback.templateSettings.template,
      targetChars: 10000,
      allowedMin: 0,
      allowedMax: 0,
      ranges: fallback.templateSettings.ranges,
    }));
  });

  it("restores a preset-specific character target into the editor", () => {
    const data = {
      ...fallback,
      templateSettings: {
        ...fallback.templateSettings,
        presets: [{
          name: "Пятнадцать тысяч",
          template: "Большой сценарий {title}",
          targetChars: 15000,
          allowedMin: 14000,
          allowedMax: 16000,
          ranges: [],
        }],
      },
    };
    render(<TemplateEditor data={data} command={vi.fn(async () => data)} />);

    fireEvent.change(screen.getByLabelText("Сохранённый пресет"), {
      target: { value: "Пятнадцать тысяч" },
    });

    expect((screen.getByLabelText("Цель знаков шаблона") as HTMLInputElement).value).toBe("15000");
    expect((screen.getByLabelText("Минимум знаков шаблона") as HTMLInputElement).value).toBe("14000");
    expect((screen.getByLabelText("Максимум знаков шаблона") as HTMLInputElement).value).toBe("16000");
    expect((screen.getByLabelText("Базовый шаблон сценария") as HTMLTextAreaElement).value).toBe(
      "Большой сценарий {title}",
    );
  });

  it("saves a distinctive operator prompt and returns Prompt Studio to a clean state", async () => {
    const template = "USER_PROMPT_MARKER :: Напиши сценарий по теме {title}. Сохрани мой стиль.";
    const command = vi.fn().mockResolvedValue(fallback);
    const onDirtyChange = vi.fn();
    render(<TemplateEditor data={fallback} command={command} onDirtyChange={onDirtyChange} />);

    fireEvent.change(screen.getByLabelText("Базовый шаблон сценария"), { target: { value: template } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить шаблон" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-template", {
      template,
      targetChars: 0,
      allowedMin: 0,
      allowedMax: 0,
      ranges: fallback.templateSettings.ranges,
    }));
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(false));
    expect(screen.getByText("Все изменения сохранены")).toBeTruthy();
  });

  it("keeps a failed Prompt Studio save dirty with the operator prompt visible", async () => {
    const template = "USER_PROMPT_MARKER :: Напиши сценарий по теме {title}. Сохрани мой стиль.";
    const command = vi.fn().mockResolvedValue(undefined);
    const onDirtyChange = vi.fn();
    render(<TemplateEditor data={fallback} command={command} onDirtyChange={onDirtyChange} />);

    fireEvent.change(screen.getByLabelText("Базовый шаблон сценария"), { target: { value: template } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить шаблон" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-template", {
      template,
      targetChars: 0,
      allowedMin: 0,
      allowedMax: 0,
      ranges: fallback.templateSettings.ranges,
    }));
    expect((screen.getByLabelText("Базовый шаблон сценария") as HTMLTextAreaElement).value).toBe(template);
    expect(onDirtyChange).toHaveBeenLastCalledWith(true);
    expect(screen.getByText("Не удалось сохранить изменения")).toBeTruthy();
  });

  it("reports dirty prompt text and returns to clean only after the current save command succeeds", async () => {
    const command = vi.fn(async () => fallback);
    const onDirtyChange = vi.fn();
    render(<TemplateEditor data={fallback} command={command} onDirtyChange={onDirtyChange} />);

    fireEvent.change(screen.getByLabelText("Базовый шаблон сценария"), {
      target: { value: "Обновлённый шаблон {title}" },
    });
    expect(onDirtyChange).toHaveBeenLastCalledWith(true);
    expect(screen.getByText("Есть несохранённые изменения")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Сохранить шаблон" }));
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(false));
  });

  it("guards workspace navigation until a dirty template is saved, discarded, or kept open", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Шаблоны" }));
    fireEvent.change(screen.getByLabelText("Базовый шаблон сценария"), {
      target: { value: "Черновик шаблона" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Центр управления" }));
    expect(screen.getByText("Несохранённые изменения")).toBeTruthy();
    expect(screen.getByLabelText("Writing prompt studio")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Не сохранять" }));
    expect(screen.getByRole("heading", { name: "Центр управления" })).toBeTruthy();
  });

  it("uses the existing save-template command before navigating away with Save", async () => {
    const command = vi.fn(async () => fallback);
    window.newsflowDesktop = {
      snapshot: vi.fn(async () => fallback),
      command,
    } as unknown as Window["newsflowDesktop"];
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Шаблоны" }));
    fireEvent.change(screen.getByLabelText("Базовый шаблон сценария"), {
      target: { value: "Черновик для сохранения" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Центр управления" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить и перейти" }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "Центр управления" })).toBeTruthy());
    expect(command).toHaveBeenCalledWith("save-template", {
      template: "Черновик для сохранения",
      targetChars: 0,
      allowedMin: 0,
      allowedMax: 0,
      ranges: fallback.templateSettings.ranges,
    });
  });

  it("saves only the active dirty template through Ctrl+S and retains the current command contract", async () => {
    const command = vi.fn(async () => fallback);
    window.newsflowDesktop = {
      snapshot: vi.fn(async () => fallback),
      command,
    } as unknown as Window["newsflowDesktop"];
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Шаблоны" }));
    fireEvent.change(screen.getByLabelText("Базовый шаблон сценария"), {
      target: { value: "Ctrl+S шаблон" },
    });

    fireEvent.keyDown(window, { key: "s", ctrlKey: true });

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-template", {
      template: "Ctrl+S шаблон",
      targetChars: 0,
      allowedMin: 0,
      allowedMax: 0,
      ranges: fallback.templateSettings.ranges,
    }));
  });

  it("does not intercept Ctrl+S while an IME composition is active", () => {
    const command = vi.fn(async () => fallback);
    window.newsflowDesktop = {
      snapshot: vi.fn(async () => undefined),
      command,
    } as unknown as Window["newsflowDesktop"];
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Шаблоны" }));
    fireEvent.change(screen.getByLabelText("Базовый шаблон сценария"), {
      target: { value: "Черновик во время ввода" },
    });

    fireEvent.keyDown(window, { key: "s", ctrlKey: true, isComposing: true });

    expect(command).not.toHaveBeenCalled();
  });

  it("prevents the desktop window from closing while a template draft is unsaved", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Шаблоны" }));
    fireEvent.change(screen.getByLabelText("Базовый шаблон сценария"), {
      target: { value: "Черновик перед закрытием окна" },
    });

    const closeEvent = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(closeEvent);

    expect(closeEvent.defaultPrevented).toBe(true);
  });

  it("does not block a desktop window close when no editor draft is dirty", () => {
    render(<App />);

    const closeEvent = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(closeEvent);

    expect(closeEvent.defaultPrevented).toBe(false);
  });
});
