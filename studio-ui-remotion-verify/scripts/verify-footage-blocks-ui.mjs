// Real source Electron journey. Only native chooser/confirmation responses are
// deterministic adapters; renderer, preload, trusted IPC and Python stay real.
import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import assert from "node:assert/strict";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

assert.equal(process.env.NEWSFLOW_TEST_MODE, "1");
assert(process.env.NEWSFLOW_TEST_ROOT);
const root = path.resolve(process.env.NEWSFLOW_TEST_ROOT);
const repo = path.resolve(process.env.NEWSFLOW_REPO_ROOT);
const phase = process.argv[2];
assert(
  ["configure", "restart-off", "restart-on-queue", "reexport"].includes(phase),
);
for (const name of ["LOCALAPPDATA", "APPDATA", "TEMP", "TMP"]) {
  assert(process.env[name]);
  const relative = path.relative(root, path.resolve(process.env[name]));
  assert(relative && !relative.startsWith("..") && !path.isAbsolute(relative));
}
const artifacts = path.join(
  root,
  "artifacts",
  ...(phase === "reexport" ? ["after-tail-fix"] : []),
);
if (phase === "reexport") {
  assert(!existsSync(artifacts), "Preserve previous re-export evidence");
  mkdirSync(artifacts);
}
assert(existsSync(artifacts));
const fixture = JSON.parse(
  readFileSync(path.join(root, "fixture.json"), "utf8"),
);
const savedFile = path.join(root, "artifacts", "ui-identities.json");
const evidence = {
  status: "RUNNING",
  phase,
  scope: fixture.fixture,
  commands: [],
  choosers: [],
  externalRequests: [],
  confirmations: [],
};
const allowed = new Set([
  "save-footage-block",
  "delete-footage-block",
  "preview-footage-block-import",
  "import-footage-block-pairs",
  "assign-footage-block",
  "save-montage-settings",
  "run-montage-queue",
  ...(phase === "reexport" ? ["render-montage"] : []),
]);
const results = [];
const originalHandle = ipcMain.handle.bind(ipcMain);
ipcMain.handle = (channel, handler) =>
  originalHandle(channel, async (event, ...args) => {
    if (channel === "newsflow:command") {
      assert(allowed.has(args[0]), `Unexpected command: ${args[0]}`);
      evidence.commands.push({ name: args[0], payload: args[1] });
    }
    try {
      const result = await handler(event, ...args);
      if (channel === "newsflow:command")
        results.push({ name: args[0], result });
      return result;
    } catch (error) {
      if (channel === "newsflow:command")
        results.push({ name: args[0], error: String(error.stack || error) });
      throw error;
    }
  });
const chooserQueue = [];
dialog.showOpenDialog = async (...args) => {
  const options = args.at(-1);
  const selected = chooserQueue.shift();
  assert(selected, "Unexpected native chooser");
  const relative = path.relative(root, selected);
  assert(relative && !relative.startsWith("..") && !path.isAbsolute(relative));
  assert(existsSync(selected));
  evidence.choosers.push({ options, selected });
  return { canceled: false, filePaths: [selected] };
};
app.disableHardwareAcceleration();
mkdirSync(path.join(root, "electron-user-data"), { recursive: true });
app.setPath("userData", path.join(root, "electron-user-data"));
app.setPath("sessionData", path.join(root, "electron-user-data"));
app.on("session-created", (session) =>
  session.webRequest.onBeforeRequest(
    { urls: ["http://*/*", "https://*/*"] },
    (details, done) => {
      evidence.externalRequests.push(details.url);
      done({ cancel: true });
    },
  ),
);
shell.openExternal = async () => {
  throw Error("External launch forbidden by isolated fixture");
};
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const until = async (label, predicate, timeout = 30000) => {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await delay(150);
  }
  throw Error(`Timed out: ${label}`);
};
let win;
const evaluate = (fn, value) =>
  win.webContents.executeJavaScript(
    `(${fn.toString()})(${JSON.stringify(value) ?? ""})`,
  );
const visible = (name) =>
  evaluate(
    (name) =>
      [...document.querySelectorAll("button")].some(
        (button) =>
          button.offsetParent !== null &&
          (button.textContent.trim() === name ||
            button.getAttribute("aria-label") === name),
      ),
    name,
  );
const click = (name) =>
  until(`click ${name}`, () =>
    evaluate((name) => {
      const surface =
        document.querySelector('[role="dialog"][data-state="open"]') ||
        document;
      const button = [...surface.querySelectorAll("button")].find(
        (item) =>
          item.offsetParent !== null &&
          !item.disabled &&
          (item.textContent.trim() === name ||
            item.getAttribute("aria-label") === name),
      );
      if (!button) return false;
      button.click();
      return true;
    }, name),
  );
const rowClick = (section, identity, name) =>
  until(`row action ${identity} ${name}`, () =>
    evaluate(
      ({ section, identity, name }) => {
        if (document.querySelector('[role="dialog"][data-state="open"]'))
          return false;
        const row = [
          ...document.querySelectorAll(
            `section[aria-label="${section}"] tbody tr`,
          ),
        ].find((row) => row.textContent.includes(identity));
        const button =
          row &&
          [...row.querySelectorAll("button")].find(
            (item) => item.textContent.trim() === name && !item.disabled,
          );
        if (!button) return false;
        button.click();
        return true;
      },
      { section, identity, name },
    ),
  );
const field = (name, value) =>
  evaluate(
    ({ name, value }) => {
      const label = [...document.querySelectorAll("label")].find(
        (label) =>
          [...label.childNodes]
            .filter((node) => node.nodeType === Node.TEXT_NODE)
            .map((node) => node.textContent.trim())
            .join("") === name ||
          label.querySelector("span")?.textContent.trim() === name,
      );
      const control = label?.querySelector("input,select,textarea");
      if (!control || control.disabled) throw Error(`Missing field ${name}`);
      const prototype =
        control.tagName === "SELECT"
          ? HTMLSelectElement.prototype
          : control.tagName === "TEXTAREA"
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, "value").set.call(
        control,
        value,
      );
      control.dispatchEvent(
        new Event(control.tagName === "SELECT" ? "change" : "input", {
          bubbles: true,
        }),
      );
    },
    { name, value },
  );
const checkbox = (value) =>
  evaluate((value) => {
    const label = [...document.querySelectorAll("label")].find(
      (label) =>
        label.textContent.trim() === "Использовать блоки футажей при монтаже",
    );
    const control = label?.querySelector("input");
    if (!control || control.disabled) throw Error("Missing mode checkbox");
    if (control.checked !== value) control.click();
  }, value);
const snapshot = () => evaluate(() => window.newsflowDesktop.snapshot());
const waitCommand = async (name, action) => {
  const previous = results.length;
  await action();
  await until(
    `real response ${name}`,
    () => results.slice(previous).some((row) => row.name === name),
    90000,
  );
  const result = results.slice(previous).find((row) => row.name === name);
  assert(!result.error, result.error);
  return result.result;
};
const capture = async (name) => {
  await evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      writeFileSync(
        path.join(artifacts, `${phase}-${name}.png`),
        (
          await win.webContents.capturePage(undefined, { stayAwake: true })
        ).toPNG(),
      );
      return;
    } catch (error) {
      if (attempt === 3) throw error;
      await delay(300);
    }
  }
};
const navigate = async (name) => {
  if (!(await visible(name))) await click("ПРОИЗВОДСТВО");
  await click(name);
};
const mode = async (enabled) => {
  if (!(await visible("Сохранить выбор"))) await click("Настроить монтаж");
  await checkbox(enabled);
  const saved = await waitCommand("save-montage-settings", () =>
    click("Сохранить выбор"),
  );
  assert.equal(saved.montageSettings.useFootageBlocks, enabled);
  await click("Закрыть");
};
const confirmDecision = (decision) =>
  evaluate((decision) => {
    window.__fixtureConfirmDecision = decision;
  }, decision);
const createBlock = async (name, folder) => {
  await click("Создать блок");
  await field("Название блока", name);
  chooserQueue.push(path.join(root, folder));
  await click("Выбрать папку блока");
  await until("chosen block folder", () =>
    evaluate(
      (folder) =>
        [...document.querySelectorAll("input")].some(
          (input) => input.value === folder,
        ),
      path.join(root, folder),
    ),
  );
  const saved = await waitCommand("save-footage-block", () =>
    click("Сохранить блок"),
  );
  return saved.footageBlocks.find((block) => block.name === name);
};
const previewTxt = async () => {
  await click("Импортировать TXT");
  chooserQueue.push(path.join(root, "inputs", "pairs.txt"));
  await click("Открыть TXT");
  await until("chosen TXT rendered", () =>
    evaluate(() =>
      document
        .querySelector("textarea")
        ?.value.includes("Заявления Алиева о протестах"),
    ),
  );
  return waitCommand("preview-footage-block-import", () =>
    click("Предпросмотр"),
  );
};
const assign = async (id, blockId, cancel = false) => {
  await rowClick("Блоки по темам", id, "Изменить блок");
  await field("Блок для темы", blockId);
  if (cancel) {
    await click("Отмена");
    return snapshot();
  }
  return waitCommand("assign-footage-block", () =>
    click("Сохранить назначение"),
  );
};

async function main() {
  try {
    await import(
      pathToFileURL(
        path.join(repo, "studio-ui-remotion-verify/dist-electron/main.js"),
      ).href
    );
    await app.whenReady();
    await until("real app window", () =>
      Boolean((win = BrowserWindow.getAllWindows()[0])),
    );
    win.setSize(1600, 1100);
    win.webContents.setZoomFactor(0.8);
    win.webContents.setBackgroundThrottling(false);
    assert(win.getTitle().includes("[TEST]"));
    await until("real persisted renderer snapshot", () =>
      evaluate(
        () =>
          document.querySelector('input[aria-label="Цель выпуска"]')?.value ===
          "137",
      ),
    );
    await evaluate(() => {
      window.__fixtureConfirmLog = [];
      window.__fixtureConfirmDecision = true;
      window.confirm = (message) => {
        window.__fixtureConfirmLog.push(message);
        return window.__fixtureConfirmDecision;
      };
    });
    if (phase === "reexport") {
      evidence.scope =
        "Saved immutable block plans re-exported through real renderer preload, trusted Electron IPC and Python. No new selection or CRUD; original artifacts retained.";
      evidence.exports = [];
      for (const [index, format] of ["landscape", "portrait"].entries()) {
        const original = path.resolve(
          process.argv[3 + index] ||
            path.join(root, "artifacts", `${format}.newsflow`),
        );
        assert(original.startsWith(root + path.sep) && existsSync(original));
        const saved = JSON.parse(readFileSync(original, "utf8"));
        const selected = path.join(artifacts, `${format}.newsflow`);
        copyFileSync(original, selected);
        const result = await evaluate(
          async (projectPath) =>
            window.newsflowDesktop.command("render-montage", { projectPath }),
          selected,
        );
        assert.equal(result.operationResult.kind, "render");
        assert.equal(result.operationResult.count, 1);
        const after = JSON.parse(readFileSync(selected, "utf8"));
        assert.deepEqual(
          after.clips,
          saved.clips,
          "Saved selection/order must remain unchanged",
        );
        assert.deepEqual(
          after.source_policy,
          saved.source_policy,
          "Saved block policy must remain unchanged",
        );
        assert.equal(after.aspect_ratio, saved.aspect_ratio);
        assert(after.output_path && existsSync(after.output_path));
        const output = path.join(artifacts, `${format}.mp4`);
        copyFileSync(after.output_path, output);
        evidence.exports.push({
          original,
          project: selected,
          output,
          aspectRatio: after.aspect_ratio,
          operationResult: result.operationResult,
        });
        // This export intentionally invokes the existing preload API directly;
        // reload the real renderer to inspect the resulting persisted snapshot.
        win.reload();
        await until(
          "renderer reload after saved-plan export",
          () =>
            !win.webContents.isLoadingMainFrame() &&
            evaluate(() =>
              Boolean(
                window.newsflowDesktop &&
                document.querySelector(".nf-page-header h1"),
              ),
            ),
        );
        await navigate("Монтаж");
        await until("persisted montage project visible", () =>
          evaluate(
            () => document.querySelectorAll(".project-list button").length > 0,
          ),
        );
        await capture(`${format}-saved-plan-export`);
      }
    } else if (phase === "configure") {
      await navigate("Футажи — поиск");
      const a = await createBlock("Алиев протесты", "block-a");
      const b = await createBlock("Армения политика", "block-b");
      assert.equal(a.videoCount, 1);
      assert.equal(b.videoCount, 2);
      const discarded = await createBlock("Удаляемый блок", "unused");
      await rowClick("Ручные блоки футажей", "Удаляемый блок", "Изменить блок");
      await field("Название блока", "Переименованный блок");
      chooserQueue.push(path.join(root, "unused-new"));
      await click("Выбрать папку блока");
      await until("changed folder", () =>
        evaluate(
          (folder) =>
            [...document.querySelectorAll("input")].some(
              (input) => input.value === folder,
            ),
          path.join(root, "unused-new"),
        ),
      );
      const renamed = await waitCommand("save-footage-block", () =>
        click("Сохранить блок"),
      );
      assert.equal(
        renamed.footageBlocks.find((block) => block.id === discarded.id).name,
        "Переименованный блок",
      );
      await waitCommand("delete-footage-block", () =>
        rowClick(
          "Ручные блоки футажей",
          "Переименованный блок",
          "Удалить запись",
        ),
      );
      assert(existsSync(path.join(root, "unused", "technical-black.mp4")));
      assert(existsSync(path.join(root, "unused-new", "technical-white.mp4")));

      const preview = await previewTxt();
      assert.equal(preview.footageBlockImportPreview.length, 3);
      assert.equal(
        preview.footageBlockImportPreview[0].productionItemId,
        fixture.productionItemId,
      );
      assert(preview.footageBlockImportToken);
      const ids = preview.footageBlockImportPreview.map(
        (row) => row.productionItemId,
      );
      assert.equal(new Set(ids).size, 3);
      await capture("01-exact-preview");
      const applied = await waitCommand("import-footage-block-pairs", () =>
        click("Применить назначения"),
      );
      assert.equal(applied.montageSettings.useFootageBlocks, false);
      assert.deepEqual(
        applied.footageBlockTopics.map((row) => row.productionItemId).sort(),
        [...ids].sort(),
      );
      const count = evidence.commands.length;
      await assign(fixture.productionItemId, b.id, true);
      assert.equal(
        evidence.commands.length,
        count,
        "Cancel must issue no write",
      );
      const manual = await assign(fixture.productionItemId, b.id);
      assert.equal(
        manual.footageBlockTopics.find(
          (row) => row.productionItemId === fixture.productionItemId,
        ).blockId,
        b.id,
      );
      assert.equal(
        manual.footageBlockTopics.find((row) => row.productionItemId === ids[2])
          .blockId,
        a.id,
      );
      assert.equal(
        manual.scenarios[0].productionItemId,
        fixture.productionItemId,
      );

      const conflict = await previewTxt();
      assert.equal(conflict.footageBlockImportConflicts.length, 1);
      await capture("02-manual-conflict");
      await confirmDecision(false);
      const beforeCancel = evidence.commands.length;
      await click("Применить назначения");
      await delay(250);
      assert.equal(evidence.commands.length, beforeCancel);
      await confirmDecision(true);
      const overwritten = await waitCommand("import-footage-block-pairs", () =>
        click("Применить назначения"),
      );
      assert.equal(
        overwritten.footageBlockTopics.find(
          (row) => row.productionItemId === fixture.productionItemId,
        ).blockId,
        a.id,
      );
      await assign(fixture.productionItemId, b.id);
      await rowClick("Ручные блоки футажей", "Алиев протесты", "Изменить блок");
      await field("Название блока", "Алиев архив");
      const renamedAssigned = await waitCommand("save-footage-block", () =>
        click("Сохранить блок"),
      );
      assert.equal(
        renamedAssigned.footageBlockTopics.find(
          (row) => row.productionItemId === ids[2],
        ).blockId,
        a.id,
      );
      assert.equal(
        renamedAssigned.footageBlockTopics.find(
          (row) => row.productionItemId === ids[2],
        ).blockName,
        "Алиев архив",
      );
      await capture("03-registry-and-assignments");
      writeFileSync(savedFile, JSON.stringify({ a, b, ids }, null, 2));
      await navigate("Монтаж");
      await mode(true);
      await mode(false);
      await capture("04-mode-off");
    } else {
      const identities = JSON.parse(readFileSync(savedFile, "utf8"));
      const initial = await snapshot();
      assert.equal(initial.footageBlocks.length, 2);
      assert.deepEqual(
        initial.footageBlockTopics.map((row) => row.productionItemId).sort(),
        identities.ids.sort(),
      );
      assert.equal(
        initial.footageBlockTopics.find(
          (row) => row.productionItemId === fixture.productionItemId,
        ).blockId,
        identities.b.id,
      );
      assert.equal(
        initial.footageBlocks.find((row) => row.id === identities.a.id).name,
        "Алиев архив",
      );
      await navigate("Монтаж");
      if (phase === "restart-off") {
        assert.equal(initial.montageSettings.useFootageBlocks, false);
        await capture("05-off-after-restart");
        await mode(true);
        await capture("06-on-saved");
      } else {
        assert.equal(initial.montageSettings.useFootageBlocks, true);
        await capture("07-on-after-restart");
        await waitCommand("run-montage-queue", () =>
          click("Собрать незавершённые"),
        );
        await until(
          "native queue terminal",
          async () => {
            const state = await snapshot();
            evidence.latestQueue = state.montageTasks;
            return (
              state.montageTasks.length === 1 &&
              ["готово", "ошибка", "done", "error"].includes(
                String(state.montageTasks[0].status).toLowerCase(),
              )
            );
          },
          150000,
        );
        assert(
          ["готово", "done"].includes(
            String(evidence.latestQueue[0].status).toLowerCase(),
          ),
          JSON.stringify(evidence.latestQueue),
        );
        evidence.final = await snapshot();
        assert.equal(evidence.final.montageProjects.length, 1);
        await until("landscape result rendered", () =>
          evaluate(
            () =>
              document
                .querySelector(".montage-ready-list em")
                ?.textContent.trim() === "Готово",
          ),
        );
        await capture("08-queue-complete");
        // Keep the accepted landscape bytes before an explicit operator
        // rebuild replaces the topic's output with a portrait render.
        const landscape = evidence.final.montageProjects[0];
        copyFileSync(
          landscape.path,
          path.join(artifacts, "landscape.newsflow"),
        );
        const landscapeProject = JSON.parse(
          readFileSync(landscape.path, "utf8"),
        );
        assert.equal(landscapeProject.aspect_ratio, "16:9");
        const landscapeOutput = evidence.final.montageTasks[0].outputPath;
        assert(landscapeOutput && existsSync(landscapeOutput));
        copyFileSync(landscapeOutput, path.join(artifacts, "landscape.mp4"));
        evidence.landscapeOutput = path.join(artifacts, "landscape.mp4");
        await click("Настроить монтаж");
        await field("Формат", "9:16");
        await waitCommand("save-montage-settings", () =>
          click("Сохранить выбор"),
        );
        await click("Закрыть");
        const previousTask = (await snapshot()).montageTasks[0];
        await waitCommand("run-montage-queue", () =>
          click("Повторить монтаж всех: 1"),
        );
        await until(
          "explicit portrait rebuild terminal",
          async () => {
            const state = await snapshot();
            evidence.portraitQueue = state.montageTasks;
            const task = state.montageTasks[0];
            return (
              task?.updatedAt !== previousTask.updatedAt &&
              ["готово", "ошибка", "done", "error"].includes(
                String(task?.status).toLowerCase(),
              )
            );
          },
          150000,
        );
        assert(
          ["готово", "done"].includes(
            String(evidence.portraitQueue[0].status).toLowerCase(),
          ),
          JSON.stringify(evidence.portraitQueue),
        );
        evidence.final = await snapshot();
        assert.equal(evidence.final.montageSettings.aspectRatio, "9:16");
        await until("portrait result rendered", () =>
          evaluate(
            () =>
              document
                .querySelector(".montage-ready-list em")
                ?.textContent.trim() === "Готово",
          ),
        );
        copyFileSync(
          evidence.final.montageProjects[0].path,
          path.join(artifacts, "portrait.newsflow"),
        );
        const portraitProject = JSON.parse(
          readFileSync(path.join(artifacts, "portrait.newsflow"), "utf8"),
        );
        assert.equal(portraitProject.aspect_ratio, "9:16");
        copyFileSync(
          evidence.final.montageTasks[0].outputPath,
          path.join(artifacts, "portrait.mp4"),
        );
        evidence.portraitOutput = path.join(artifacts, "portrait.mp4");
        await capture("09-explicit-portrait-rebuild");
      }
    }
    evidence.confirmations = await evaluate(
      () => window.__fixtureConfirmLog || [],
    );
    assert.deepEqual(evidence.externalRequests, []);
    assert.equal(chooserQueue.length, 0);
    evidence.status = "PASS";
    console.log(`FOOTAGE_BLOCKS_SOURCE_UI_${phase}=PASS`);
  } catch (error) {
    evidence.status = "FAIL";
    evidence.error = String(error.stack || error);
    console.error(evidence.error);
    if (win && !win.isDestroyed()) {
      try {
        await capture("failure");
      } catch {
        /* Keep primary failure. */
      }
    }
  } finally {
    writeFileSync(
      path.join(artifacts, `${phase}.json`),
      JSON.stringify(evidence, null, 2),
    );
    for (const window of BrowserWindow.getAllWindows()) window.destroy();
    app.exit(evidence.status === "PASS" ? 0 : 1);
  }
}
void main();
