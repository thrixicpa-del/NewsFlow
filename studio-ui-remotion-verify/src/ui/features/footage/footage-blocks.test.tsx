import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { Editor, fallback, Footage } from "../../App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const blocks = [
  {
    id: "block-a",
    name: "Алиев протесты",
    root: "D:/test/Алиев",
    videoCount: 8,
    available: true,
  },
  {
    id: "block-b",
    name: "Армения политика",
    root: "D:/test/Армения",
    videoCount: 12,
    available: true,
  },
];
const data = () => ({
  ...fallback,
  footageBlocks: blocks,
  footageBlockTopics: [
    {
      productionItemId: "product-42",
      title: "Заявления Алиева",
      blockId: "block-a",
      blockName: blocks[0].name,
      root: blocks[0].root,
      origin: "manual",
    },
    {
      productionItemId: "product-7",
      title: "Новая тема",
      blockId: "",
      blockName: "",
      root: "",
    },
  ],
});

describe("Manual footage blocks", () => {
  it("creates a named block from the native folder picker without indexing or enabling it", async () => {
    const command = vi.fn().mockResolvedValue(data());
    window.newsflowDesktop = {
      chooseFolder: vi.fn().mockResolvedValue("D:/test/New"),
    } as unknown as NonNullable<Window["newsflowDesktop"]>;
    render(
      <Footage
        data={data()}
        command={command}
        refresh={async () => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Создать блок" }));
    fireEvent.change(screen.getByLabelText("Название блока"), {
      target: { value: "Новый блок" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Выбрать папку блока" }),
    );
    await waitFor(() =>
      expect(
        (screen.getByLabelText("Корневая папка блока") as HTMLInputElement)
          .value,
      ).toBe("D:/test/New"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Сохранить блок" }));
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("save-footage-block", {
        name: "Новый блок",
        root: "D:/test/New",
      }),
    );
    expect(command.mock.calls.map(([name]) => name)).toEqual([
      "save-footage-block",
    ]);
  });

  it("cancels a per-topic change and saves only the durable ID when confirmed", async () => {
    const command = vi.fn().mockResolvedValue(data());
    render(
      <Footage
        data={data()}
        command={command}
        refresh={async () => undefined}
      />,
    );
    const row = screen.getByRole("row", { name: /Заявления Алиева/ });
    fireEvent.click(within(row).getByRole("button", { name: "Изменить блок" }));
    fireEvent.change(screen.getByLabelText("Блок для темы"), {
      target: { value: "block-b" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    expect(command).not.toHaveBeenCalled();
    fireEvent.click(within(row).getByRole("button", { name: "Изменить блок" }));
    fireEvent.change(screen.getByLabelText("Блок для темы"), {
      target: { value: "block-b" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Сохранить назначение" }),
    );
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("assign-footage-block", {
        productionItemId: "product-42",
        blockId: "block-b",
      }),
    );
    expect(command.mock.calls).toHaveLength(1);
  });

  it("previews TXT before writing and requires confirmation to overwrite a manual assignment", async () => {
    const state = data();
    const command = vi
      .fn()
      .mockResolvedValue({
        ...state,
        footageBlockImportPreview: [
          {
            title: "Заявления Алиева",
            productionItemId: "product-42",
            blockId: "block-b",
            blockName: blocks[1].name,
            root: blocks[1].root,
          },
        ],
      });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(
      <Footage
        data={state}
        command={command}
        refresh={async () => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Импортировать TXT" }));
    const text = "Заявления Алиева\n\nАрмения политика";
    fireEvent.change(screen.getByLabelText("Тема и блок из TXT"), {
      target: { value: text },
    });
    fireEvent.click(screen.getByRole("button", { name: "Предпросмотр" }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Применить назначения" }),
      ).toBeTruthy(),
    );
    expect(command.mock.calls).toEqual([
      ["preview-footage-block-import", { text }],
    ]);
    fireEvent.click(
      screen.getByRole("button", { name: "Применить назначения" }),
    );
    expect(confirm).toHaveBeenCalled();
    expect(command.mock.calls).toHaveLength(1);
    confirm.mockReturnValue(true);
    fireEvent.click(
      screen.getByRole("button", { name: "Применить назначения" }),
    );
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("import-footage-block-pairs", {
        text,
        confirmOverwrite: true,
      }),
    );
    expect(
      command.mock.calls.some(([name]) => name === "save-montage-settings"),
    ).toBe(false);
  });

  it("defaults the montage mode off and preserves its draft through refresh before saving", async () => {
    const state = data();
    const command = vi.fn().mockResolvedValue(state);
    const view = render(
      <Editor data={state} command={command} refresh={async () => undefined} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Настроить монтаж" }));
    const toggle = screen.getByRole("checkbox", {
      name: "Использовать блоки футажей при монтаже",
    }) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    fireEvent.click(toggle);
    view.rerender(
      <Editor
        data={{ ...state, montageSettings: { ...state.montageSettings } }}
        command={command}
        refresh={async () => undefined}
      />,
    );
    expect(toggle.checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith(
        "save-montage-settings",
        expect.objectContaining({ useFootageBlocks: true }),
      ),
    );
  });

  it("applies the exact preview token and invalidates the preview after text edits", async () => {
    const state = data();
    const command = vi
      .fn()
      .mockResolvedValue({
        ...state,
        footageBlockImportToken: "preview-unique-id",
        footageBlockImportPreview: [
          {
            title: "Новая тема",
            productionItemId: "product-7",
            blockId: "block-b",
            blockName: blocks[1].name,
            root: blocks[1].root,
          },
        ],
      });
    render(
      <Footage
        data={state}
        command={command}
        refresh={async () => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Импортировать TXT" }));
    const text = "Новая тема\n\nАрмения политика";
    fireEvent.change(screen.getByLabelText("Тема и блок из TXT"), {
      target: { value: text },
    });
    fireEvent.click(screen.getByRole("button", { name: "Предпросмотр" }));
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Предпросмотр",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
    fireEvent.change(screen.getByLabelText("Тема и блок из TXT"), {
      target: { value: text + "\n" },
    });
    expect(
      screen.queryByRole("button", { name: "Применить назначения" }),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Предпросмотр" }));
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Предпросмотр",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Применить назначения" }),
    );
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("import-footage-block-pairs", {
        text: text + "\n",
        previewToken: "preview-unique-id",
      }),
    );
  });

  it("launches saved block mode even when the unused stock configuration is incomplete", async () => {
    const state = {
      ...data(),
      montageSettings: {
        ...fallback.montageSettings,
        useFootageBlocks: true,
        sourceMode: "stock" as const,
        stockSources: [],
      },
      scenarios: [
        {
          index: 1,
          productionItemId: "product-42",
          title: "Заявления Алиева",
          state: "Готово",
          result: "Текст",
          error: "",
        },
      ],
      voiceItems: [
        {
          index: 1,
          productionItemId: "product-42",
          title: "Заявления Алиева",
          state: "Готово",
          path: "D:/test/voice.mp3",
        },
      ],
    };
    const command = vi.fn().mockResolvedValue(state);
    render(
      <Editor data={state} command={command} refresh={async () => undefined} />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Собрать незавершённые" }),
    );
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("run-montage-queue", {
        indices: [1],
        replaceOutput: false,
      }),
    );
    expect(command.mock.calls[0]).toEqual([
      "save-montage-settings",
      expect.objectContaining({ useFootageBlocks: true }),
    ]);
  });

  it("reads the chosen TXT without applying assignments or truncating the text", async () => {
    const state = data();
    const text = "\ufeffНовая тема\r\n\r\nАрмения политика\r\n";
    window.newsflowDesktop = {
      chooseFootageBlockPairs: vi.fn().mockResolvedValue(text),
    } as unknown as NonNullable<Window["newsflowDesktop"]>;
    const command = vi.fn().mockResolvedValue(state);
    render(
      <Footage
        data={state}
        command={command}
        refresh={async () => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Импортировать TXT" }));
    fireEvent.click(screen.getByRole("button", { name: "Открыть TXT" }));
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Открыть TXT",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
    expect(command).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Предпросмотр" }));
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("preview-footage-block-import", {
        text,
      }),
    );
  });
});
