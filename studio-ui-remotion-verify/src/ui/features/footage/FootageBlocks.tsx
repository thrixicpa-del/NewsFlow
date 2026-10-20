import { useRef, useState } from "react";
import type {
  CommandRequest,
  NewsFlowCommand,
} from "../../../contracts/newsflowCommands";
import { Button } from "../../components/button";
import { Dialog } from "../../components/dialog";
import "./footage-blocks.css";

type Command = <K extends NewsFlowCommand>(
  name: K,
  payload?: CommandRequest<K>,
) => Promise<NewsFlowSnapshot | undefined>;
type Props = { data: NewsFlowSnapshot; command: Command };
type Topic = NonNullable<NewsFlowSnapshot["footageBlockTopics"]>[number];

export function FootageBlockAssignments({ data, command }: Props) {
  const [editing, setEditing] = useState<Topic | null>(null);
  const [blockId, setBlockId] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState("");
  const blocks = data.footageBlocks || [];
  const topics = data.footageBlockTopics || [];
  const selected = blocks.find((block) => block.id === blockId);
  const save = async () => {
    if (!editing || !selected?.available || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const saved = await command("assign-footage-block", {
        productionItemId: editing.productionItemId,
        blockId,
      });
      if (saved) setEditing(null);
      else
        setError(
          "Не удалось сохранить назначение. Проверьте доступность папки и повторите.",
        );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Не удалось сохранить назначение.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return (
    <section className="panel footage-blocks-panel" aria-label="Блоки по темам">
      <div className="panel-title">
        <div>
          <b>Блоки по темам</b>
          <small>
            {data.montageSettings.useFootageBlocks
              ? "Режим блоков включён. До запуска назначьте блок каждой теме."
              : "Действует обычный подбор. Сохранённые назначения применятся после включения блоков в настройках монтажа."}
          </small>
        </div>
      </div>
      {topics.length ? (
        <div className="footage-blocks-table">
          <table>
            <thead>
              <tr>
                <th>Тема / Product ID</th>
                <th>Назначенный блок / папка</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {topics.map((topic) => (
                <tr key={topic.productionItemId}>
                  <td>
                    <b>{topic.title}</b>
                    <small>{topic.productionItemId}</small>
                  </td>
                  <td>
                    {topic.blockId ? (
                      <>
                        <b>{topic.blockName || "Блок удалён"}</b>
                        <small>{topic.root || "Папка недоступна"}</small>
                      </>
                    ) : (
                      <span
                        role={
                          data.montageSettings.useFootageBlocks
                            ? "status"
                            : undefined
                        }
                      >
                        Блок не назначен
                      </span>
                    )}
                  </td>
                  <td>
                    <Button
                      onClick={() => {
                        setEditing(topic);
                        setBlockId(topic.blockId);
                        setError("");
                      }}
                    >
                      Изменить блок
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>Темы появятся после добавления сценариев или импорта TXT.</p>
      )}
      <Dialog
        open={Boolean(editing)}
        onOpenChange={(open) => {
          if (!open && !busy) setEditing(null);
        }}
        title="Назначить блок теме"
        description="Изменение применяется к следующей подготовке этой темы; готовые проекты и выполняющиеся задания сохраняют свои материалы."
      >
        <p>{editing?.title}</p>
        <small>{editing?.productionItemId}</small>
        <label>
          Блок для темы
          <select
            value={blockId}
            disabled={busy}
            onChange={(event) => setBlockId(event.target.value)}
          >
            <option value="">Выберите блок</option>
            {blocks.map((block) => (
              <option
                key={block.id}
                value={block.id}
                disabled={!block.available}
              >
                {block.name} — {block.root}
                {!block.available ? " (папка недоступна)" : ""}
              </option>
            ))}
          </select>
        </label>
        {selected && <p className="footage-blocks-path">{selected.root}</p>}
        {error && <p role="alert">{error}</p>}
        <div className="toolbar">
          <Button
            disabled={busy || !selected?.available}
            onClick={() => void save()}
          >
            Сохранить назначение
          </Button>
          <Button disabled={busy} onClick={() => setEditing(null)}>
            Отмена
          </Button>
        </div>
      </Dialog>
    </section>
  );
}

export function FootageBlocks({ data, command }: Props) {
  const [draft, setDraft] = useState<{
    blockId?: string;
    name: string;
    root: string;
  } | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [text, setText] = useState("");
  const [preview, setPreview] =
    useState<NewsFlowSnapshot["footageBlockImportPreview"]>();
  const [previewToken, setPreviewToken] = useState<string>();
  const [conflicts, setConflicts] = useState<
    NonNullable<NewsFlowSnapshot["footageBlockImportConflicts"]>
  >([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const blocks = data.footageBlocks || [];
  const run = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Не удалось выполнить действие. Повторите попытку.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const resetText = (value: string) => {
    setText(value);
    setPreview(undefined);
    setPreviewToken(undefined);
    setConflicts([]);
    setError("");
  };
  const duplicateName = Boolean(
    draft &&
    blocks.some(
      (block) =>
        block.id !== draft.blockId &&
        block.name.trim().toLocaleLowerCase() ===
          draft.name.trim().toLocaleLowerCase(),
    ),
  );
  const previewImport = () =>
    run(async () => {
      setPreview(undefined);
      setPreviewToken(undefined);
      setConflicts([]);
      const result = await command("preview-footage-block-import", { text });
      if (!result?.footageBlockImportPreview?.length) {
        setError(
          "Не удалось подготовить предпросмотр. Проверьте пары тема — блок, названия блоков и однозначность тем.",
        );
        return;
      }
      setPreview(result.footageBlockImportPreview);
      setPreviewToken(result.footageBlockImportToken);
      setConflicts(result.footageBlockImportConflicts || []);
    });
  const applyImport = () => {
    if (!preview?.length || lock.current) return;
    const manualConflicts = preview.filter((row) =>
      data.footageBlockTopics?.some(
        (topic) =>
          topic.productionItemId === row.productionItemId &&
          topic.origin === "manual" &&
          topic.blockId !== row.blockId,
      ),
    );
    const overwrite = conflicts.length > 0 || manualConflicts.length > 0;
    if (
      overwrite &&
      !window.confirm(
        "TXT изменит индивидуальные назначения блоков. Заменить показанные назначения для этих тем?",
      )
    )
      return;
    void run(async () => {
      const result = await command("import-footage-block-pairs", {
        text,
        ...(previewToken ? { previewToken } : {}),
        ...(overwrite ? { confirmOverwrite: true } : {}),
      });
      if (result) {
        setImportOpen(false);
        setPreview(undefined);
        setConflicts([]);
        setText("");
      } else {
        setPreview(undefined);
        setError(
          "Импорт не применён. Обновите предпросмотр и проверьте конфликты назначений.",
        );
      }
    });
  };
  return (
    <>
      <section
        className="panel footage-blocks-panel"
        aria-label="Ручные блоки футажей"
      >
        <div className="panel-title">
          <div>
            <b>Ручные блоки футажей</b>
            <small>
              Создайте именованный набор из папки с видео и её подпапок.
              Использование включается отдельно в настройках монтажа.
            </small>
          </div>
          <div className="toolbar">
            <Button
              onClick={() => {
                setError("");
                setDraft({ name: "", root: "" });
              }}
            >
              Создать блок
            </Button>
            <Button
              onClick={() => {
                setError("");
                setImportOpen(true);
              }}
            >
              Импортировать TXT
            </Button>
          </div>
        </div>
        {error && !draft && !importOpen && <p role="alert">{error}</p>}
        {blocks.length ? (
          <div className="footage-blocks-table">
            <table>
              <thead>
                <tr>
                  <th>Блок / корневая папка</th>
                  <th>Видео</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {blocks.map((block) => (
                  <tr key={block.id}>
                    <td>
                      <b>{block.name}</b>
                      <small>{block.root}</small>
                      {!block.available && (
                        <small role="status">Папка недоступна</small>
                      )}
                    </td>
                    <td>{block.videoCount.toLocaleString("ru-RU")}</td>
                    <td>
                      <div className="toolbar">
                        <Button
                          disabled={busy}
                          onClick={() => {
                            setError("");
                            setDraft({
                              blockId: block.id,
                              name: block.name,
                              root: block.root,
                            });
                          }}
                        >
                          Изменить блок
                        </Button>
                        <Button
                          disabled={busy}
                          variant="destructive"
                          onClick={() => {
                            if (
                              window.confirm(
                                `Удалить блок «${block.name}» из настроек? Исходные видео останутся на месте.`,
                              )
                            )
                              void run(async () => {
                                if (
                                  !(await command("delete-footage-block", {
                                    blockId: block.id,
                                  }))
                                )
                                  setError("Не удалось удалить запись блока.");
                              });
                          }}
                        >
                          Удалить запись
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>Блоков пока нет. Создайте первый и выберите папку с видео.</p>
        )}
      </section>
      <FootageBlockAssignments data={data} command={command} />
      <Dialog
        open={Boolean(draft)}
        onOpenChange={(open) => {
          if (!open && !busy) setDraft(null);
        }}
        title={
          draft?.blockId ? "Изменить блок футажей" : "Создать блок футажей"
        }
        description="Переименование и смена папки сохраняют ID блока. Исходные файлы остаются на месте."
      >
        <label>
          Название блока
          <input
            value={draft?.name || ""}
            disabled={busy}
            onChange={(event) =>
              setDraft(
                (current) =>
                  current && { ...current, name: event.target.value },
              )
            }
          />
        </label>
        <label>
          Корневая папка блока
          <input
            value={draft?.root || ""}
            disabled={busy}
            onChange={(event) =>
              setDraft(
                (current) =>
                  current && { ...current, root: event.target.value },
              )
            }
          />
        </label>
        <Button
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const root = await window.newsflowDesktop?.chooseFolder();
              if (root) setDraft((current) => current && { ...current, root });
            })
          }
        >
          Выбрать папку блока
        </Button>
        {duplicateName && (
          <p role="alert">
            Блок с таким названием уже существует. Укажите другое название.
          </p>
        )}
        {error && <p role="alert">{error}</p>}
        <div className="toolbar">
          <Button
            disabled={
              busy || !draft?.name.trim() || !draft.root.trim() || duplicateName
            }
            onClick={() =>
              void run(async () => {
                if (!draft) return;
                const saved = await command("save-footage-block", {
                  ...(draft.blockId ? { blockId: draft.blockId } : {}),
                  name: draft.name.trim(),
                  root: draft.root.trim(),
                });
                if (saved) setDraft(null);
                else
                  setError(
                    "Не удалось сохранить блок. Проверьте название и доступность папки.",
                  );
              })
            }
          >
            Сохранить блок
          </Button>
          <Button disabled={busy} onClick={() => setDraft(null)}>
            Отмена
          </Button>
        </div>
      </Dialog>
      <Dialog
        open={importOpen}
        onOpenChange={(open) => {
          if (!busy) setImportOpen(open);
        }}
        title="Импорт назначений из TXT"
        description="Каждый непустой абзац — одно поле: тема, пустая строка, название блока, пустая строка, следующая тема и её блок."
      >
        <Button
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const value =
                await window.newsflowDesktop?.chooseFootageBlockPairs();
              if (value) resetText(value);
            })
          }
        >
          Открыть TXT
        </Button>
        <label>
          Тема и блок из TXT
          <textarea
            rows={9}
            disabled={busy}
            value={text}
            placeholder={
              "Заявления Алиева о протестах\n\nАлиев протесты\n\nПолитическая ситуация в Армении\n\nАрмения политика"
            }
            onChange={(event) => resetText(event.target.value)}
          />
        </label>
        <Button
          disabled={busy || !text.trim()}
          onClick={() => void previewImport()}
        >
          Предпросмотр
        </Button>
        {error && <p role="alert">{error}</p>}
        {preview?.length ? (
          <>
            <div className="footage-blocks-table">
              <table aria-label="Предпросмотр назначений">
                <thead>
                  <tr>
                    <th>Тема / Product ID</th>
                    <th>Блок / полный путь</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.map((row) => (
                    <tr key={row.productionItemId}>
                      <td>
                        <b>{row.title}</b>
                        <small>{row.productionItemId}</small>
                      </td>
                      <td>
                        <b>{row.blockName}</b>
                        <small>{row.root}</small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {conflicts.length > 0 && (
              <p role="alert">
                Конфликт индивидуальных назначений:{" "}
                {conflicts.map((row) => row.title).join(", ")}. Применение
                потребует подтверждения замены.
              </p>
            )}
            <Button disabled={busy} onClick={applyImport}>
              Применить назначения
            </Button>
            <small>
              Назначение не включает режим блоков и не запускает монтаж.
            </small>
          </>
        ) : null}
        <Button disabled={busy} onClick={() => setImportOpen(false)}>
          Отмена
        </Button>
      </Dialog>
    </>
  );
}
