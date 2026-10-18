import { useEffect, useRef, useState } from "react";
import type { MontageOverlayLayer as Layer, MontageOverlayTemplate as Template, MontageOverlayLibrarySource as LibrarySource } from "../../../contracts/montageOverlays";
import type { CommandRequest, NewsFlowCommand } from "../../../contracts/newsflowCommands";
import { overlayIntervals, overlaySourceTime, overlayTimecode, validOverlayTiming } from "../../../contracts/overlaySchedule";
import "./montage-overlays.css";

type Command = <K extends NewsFlowCommand>(name: K, payload?: CommandRequest<K>) => Promise<NewsFlowSnapshot | undefined>;
type Layout = "16:9" | "9:16";
type NumericField = "x" | "y" | "width" | "height" | "opacity" | "start" | "duration" | "repeatEvery" | "endOffset" | "chromaSimilarity" | "chromaBlend" | "repeatCount" | "rangeEnd";
const emptyTemplate = (): Template => ({ version: 1, layouts: { "16:9": [], "9:16": [] } });
const copyLayer = (layer: Layer): Layer => ({ ...layer, ...(layer.ranges ? { ranges: layer.ranges.map(range => ({ ...range })) } : {}) });
const copyTemplate = (template: Template): Template => ({ ...template, ...(template.librarySources ? { librarySources: template.librarySources.map((source) => ({ ...source })) } : {}), version: 1, layouts: { "16:9": template.layouts["16:9"].map(copyLayer), "9:16": template.layouts["9:16"].map(copyLayer) } });
const videoTime = (time: number, video: HTMLVideoElement) => Number.isFinite(video.duration) && video.duration > 0 ? time % video.duration : time;
const pathKey = (path: string) => /^[A-Za-z]:/.test(path) ? path.replace(/\\/g, "/").toLowerCase() : path;
const sourcePathKey = (path: string, sourceId = "") => JSON.stringify([sourceId, pathKey(path)]);
const bounds: Record<NumericField, [number, number]> = {
  x: [-16384, 16384], y: [-16384, 16384], width: [1, 16384], height: [1, 16384], opacity: [0, 1],
  start: [0, 604800], duration: [0.001, 604800], repeatEvery: [0.001, 604800], endOffset: [0, 604800],
  chromaSimilarity: [0.01, 1], chromaBlend: [0, 1],
  repeatCount: [1, 513], rangeEnd: [0, 604800],
};
const localPath = (path: string) => /^[A-Za-z]:[\\/]/.test(path) || /^\/(?!\/)/.test(path);
const validLayer = (layer: Layer) => localPath(layer.path) && (layer.kind !== "image" || /\.(png|jpe?g)$/i.test(layer.path)) &&
  Object.entries(bounds).every(([field, [min, max]]) => {
    if (field === "repeatCount" || field === "rangeEnd") return true;
    const value = layer[field as NumericField];
    return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
  }) && /^#[0-9a-f]{6}$/i.test(layer.chromaColor) && validOverlayTiming(layer);

// Time is relative to the final output, including any intro. Each occurrence
// returns its own source time; video never resumes from a previous occurrence.
const sourceTime = overlaySourceTime;

// Lightweight RGB preview only. The final FFmpeg chromakey uses its own color
// space; this preview deliberately makes no promise of encoder pixel identity.
export function keyPreviewPixels(pixels: Uint8ClampedArray, color: string, similarity: number, blend: number) {
  const key = [1, 3, 5].map((offset) => parseInt(color.slice(offset, offset + 2), 16));
  for (let offset = 0; offset < pixels.length; offset += 4) {
    const distance = Math.hypot(pixels[offset] - key[0], pixels[offset + 1] - key[1], pixels[offset + 2] - key[2]) / (255 * Math.sqrt(3));
    const alpha = blend > 0 ? Math.max(0, Math.min(1, (distance - similarity) / blend)) : Number(distance > similarity);
    pixels[offset + 3] = Math.round(pixels[offset + 3] * alpha);
  }
}

function PreviewMedia({ layer, src, time, onError, onDimensions }: {
  layer: Layer; src: string; time: number; onError: () => void; onDimensions: (width: number, height: number) => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const image = useRef<HTMLImageElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [unsupported, setUnsupported] = useState(false);
  const mediaStyle = { objectFit: layer.keepAspect ? "contain" as const : "fill" as const, objectPosition: "left top" };
  const draw = () => {
    if (!layer.chromaEnabled || !canvas.current) return;
    const source = layer.kind === "image" ? image.current : video.current;
    const width = layer.kind === "image" ? image.current?.naturalWidth : video.current?.videoWidth;
    const height = layer.kind === "image" ? image.current?.naturalHeight : video.current?.videoHeight;
    if (!source || !width || !height) return;
    try {
      // Preview resolution is bounded so sliders do not key a 4K frame on the
      // renderer thread. Coordinates remain final output pixels above.
      const scale = Math.min(1, 640 / width, 640 / height);
      canvas.current.width = Math.max(1, Math.round(width * scale));
      canvas.current.height = Math.max(1, Math.round(height * scale));
      const context = canvas.current.getContext("2d", { willReadFrequently: true });
      if (!context) { setUnsupported(true); return; }
      context.drawImage(source, 0, 0, canvas.current.width, canvas.current.height);
      const frame = context.getImageData(0, 0, canvas.current.width, canvas.current.height);
      keyPreviewPixels(frame.data, layer.chromaColor, layer.chromaSimilarity, layer.chromaBlend);
      context.putImageData(frame, 0, 0);
      setUnsupported(false);
    } catch {
      // Sandboxed/opaque file origins can prohibit canvas readback. Never show
      // the unkeyed source as though it were a keyed preview.
      setUnsupported(true);
    }
  };
  useEffect(() => {
    if (!video.current) return;
    try { video.current.currentTime = videoTime(time, video.current); } catch { /* Metadata may still be loading. */ }
  }, [time, src]);
  useEffect(() => { draw(); }, [time, src, layer.chromaEnabled, layer.chromaColor, layer.chromaSimilarity, layer.chromaBlend]);
  if (layer.chromaEnabled) return <>
    {layer.kind === "image" ? <img ref={image} src={src} alt="" hidden aria-hidden="true" onError={onError} onLoad={(event) => { onDimensions(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight); draw(); }} /> :
      <video ref={video} src={src} hidden aria-hidden="true" muted preload="auto" onError={onError} onSeeked={draw} onLoadedData={draw}
        onLoadedMetadata={(event) => { event.currentTarget.currentTime = videoTime(time, event.currentTarget); onDimensions(event.currentTarget.videoWidth, event.currentTarget.videoHeight); }} />}
    {unsupported ? <span>Хромакей · {layer.name}<small>Предпросмотр цвета недоступен в этом окружении; настройка сохранена для рендера.</small></span> :
      <canvas ref={canvas} style={mediaStyle} aria-label={`Хромакей ${layer.name}`} />}
  </>;
  return layer.kind === "image" ?
    <img src={src} style={mediaStyle} alt={layer.name} onError={onError} onLoad={(event) => onDimensions(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight)} /> :
    <video ref={video} src={src} style={mediaStyle} muted preload="metadata" playsInline aria-label={layer.name} onError={onError}
      onLoadedMetadata={(event) => { event.currentTarget.currentTime = videoTime(time, event.currentTarget); onDimensions(event.currentTarget.videoWidth, event.currentTarget.videoHeight); }} />;
}

export function MontageOverlays({ data, command, selectedIndices, allIndices, mediaUrl, projectDuration, individualTemplate, onRenderOverlays, queueActive }: {
  data: NewsFlowSnapshot; command: Command; selectedIndices: number[]; allIndices: number[]; mediaUrl: (path: string) => string; projectDuration?: number;
  individualTemplate?: Template; onRenderOverlays: (indices: number[]) => Promise<NewsFlowSnapshot | undefined>; queueActive: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [template, setTemplate] = useState<Template>(() => data.montageSettings.overlayTemplate || emptyTemplate());
  const [layout, setLayout] = useState<Layout>("16:9");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [step, setStep] = useState(1);
  const [time, setTime] = useState(0);
  const [total, setTotal] = useState(projectDuration || 60);
  const [invalid, setInvalid] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmation, setConfirmation] = useState<number[] | null>(null);
  const [pendingLoad, setPendingLoad] = useState<Template | null>(null);
  const [source, setSource] = useState<"defaults" | "individual">("defaults");
  const [failedMedia, setFailedMedia] = useState<Record<string, boolean>>({});
  const autoSize = useRef(new Set<string>());
  const serial = useRef(0);
  useEffect(() => {
    if (!dirty && !saving && source === "defaults") setTemplate(data.montageSettings.overlayTemplate || emptyTemplate());
  }, [data.montageSettings.overlayTemplate, dirty, saving, source]);
  const layers = template.layouts[layout];
  const active = layers.find((item) => item.id === activeId) || layers[0];
  const [frameWidth, frameHeight] = layout === "16:9" ? [1920, 1080] : [1080, 1920];
  const librarySources = template.librarySources || [];
  const sourceById = new Map(librarySources.map((source) => [source.id, source]));
  const activeSource = active?.librarySourceId ? sourceById.get(active.librarySourceId) : undefined;
  const valid = Object.keys(invalid).length === 0 && (!template.libraryRoot || localPath(template.libraryRoot)) && librarySources.every((source) => source.name.trim() && localPath(source.root)) && Object.values(template.layouts).every((items) => items.every((item) => validLayer(item) && (!item.librarySourceId || sourceById.has(item.librarySourceId))));
  const canRender = selectedIndices.length > 0 && selectedIndices.every((index) => data.montageTasks.some((task) => task.index === index && task.projectPath));
  const layerEnabled = (layer: Layer) => {
    if (!layer.enabled) return false;
    if (!layer.librarySourceId) return true;
    const source = sourceById.get(layer.librarySourceId);
    return Boolean(source?.enabled && (source.kind === "all" || source.kind === layer.kind));
  };
  const previewGroup = (layer: Layer) => {
    const group = layer.randomGroup?.trim();
    if (!group) return "";
    if (layer.librarySourceId) return sourceById.get(layer.librarySourceId)?.mode === "all" ? "" : `source:${layer.librarySourceId}`;
    return `manual:${group}`;
  };
  const previewChoices = new Map<string, string>();
  layers.forEach((layer) => { const group = previewGroup(layer); if (layerEnabled(layer) && group && !previewChoices.has(group)) previewChoices.set(group, layer.id); });
  if (active && layerEnabled(active) && previewGroup(active)) previewChoices.set(previewGroup(active), active.id);
  const updateSource = (id: string, patch: Partial<LibrarySource>) => {
    setTemplate((current) => ({ ...current, librarySources: (current.librarySources || []).map((source) => source.id === id ? { ...source, ...patch } : source) }));
    setDirty(true); setMessage(""); setConfirmation(null);
  };
  const addSource = () => {
    const source: LibrarySource = { id: `library-${Date.now()}-${++serial.current}`, name: `Группа ${librarySources.length + 1}`, root: "", enabled: true, mode: "random", kind: "all" };
    setTemplate((current) => ({ ...current, librarySources: [...(current.librarySources || []), source] }));
    setDirty(true); setMessage(""); setConfirmation(null);
  };
  const removeSource = (id: string) => {
    const removedIds = new Set(Object.values(template.layouts).flat().filter((layer) => layer.librarySourceId === id).map((layer) => layer.id));
    setTemplate((current) => ({ ...current, librarySources: (current.librarySources || []).filter((source) => source.id !== id), layouts: { "16:9": current.layouts["16:9"].filter((layer) => layer.librarySourceId !== id), "9:16": current.layouts["9:16"].filter((layer) => layer.librarySourceId !== id) } }));
    setInvalid((current) => Object.fromEntries(Object.entries(current).filter(([key]) => ![...removedIds].some((layerId) => key.startsWith(`16:9:${layerId}:`) || key.startsWith(`9:16:${layerId}:`)))));
    setFailedMedia({}); setDirty(true); setConfirmation(null);
  };
  const setLibraryRoot = (folder: string) => {
    setTemplate((current) => { const next = { ...current }; if (folder.trim()) next.libraryRoot = folder; else delete next.libraryRoot; return next; });
    setDirty(true); setMessage(""); setConfirmation(null);
  };
  const update = (id: string, patch: Partial<Layer>) => {
    setTemplate((current) => ({ ...current, layouts: { ...current.layouts, [layout]: current.layouts[layout].map((item) => item.id === id ? { ...item, ...patch } : item) } }));
    setDirty(true);
    setMessage("");
    setConfirmation(null);
  };
  const changeNumeric = (layer: Layer, field: NumericField, raw: string) => {
    const key = `${layout}:${layer.id}:${field}`;
    const number = Number(raw);
    const [min, max] = bounds[field];
    if (!raw.trim() || !Number.isFinite(number) || number < min || number > max || (field === "repeatCount" && !Number.isInteger(number))) {
      setInvalid((current) => ({ ...current, [key]: raw }));
      setDirty(true);
      setConfirmation(null);
      return;
    }
    const patch: Partial<Layer> = { [field]: number };
    const other = field === "width" ? "height" : "width";
    if ((field === "width" || field === "height") && layer.keepAspect) {
      const dimension = Math.round(number * layer[other] / layer[field]);
      if (dimension < 1 || dimension > 16384) {
        setInvalid((current) => ({ ...current, [key]: raw }));
        return;
      }
      patch[other] = dimension;
    }
    autoSize.current.delete(layer.id);
    setInvalid((current) => { const next = { ...current }; delete next[key]; if (field === "width" || field === "height") delete next[`${layout}:${layer.id}:${other}`]; return next; });
    update(layer.id, patch);
  };
  const numeric = (label: string, field: NumericField, pixels = false) => active && <label className="nf-overlay-number">{label}
    <span><input type="number" aria-label={label} min={bounds[field][0]} max={bounds[field][1]} step={pixels ? step : field === "repeatCount" ? 1 : "any"}
      value={invalid[`${layout}:${active.id}:${field}`] ?? active[field] ?? (field === "repeatCount" ? 1 : total)} aria-invalid={`${layout}:${active.id}:${field}` in invalid}
      onChange={(event) => changeNumeric(active, field, event.target.value)} />
      {pixels && <><button type="button" aria-label={`${label} −${step}`} onClick={() => changeNumeric(active, field, String((active[field] ?? 0) - step))}>−</button>
        <button type="button" aria-label={`${label} +${step}`} onClick={() => changeNumeric(active, field, String((active[field] ?? 0) + step))}>+</button></>}
    </span></label>;
  const createLayer = (path: string, kind: "image" | "video", name = path.split(/[\\/]/).pop() || "Слой"): Layer => {
    const id = `overlay-${Date.now()}-${++serial.current}`;
    autoSize.current.add(id);
    return { id, name, enabled: true, path, kind, x: 0, y: 0, width: Math.round(frameWidth / 3), height: Math.round(frameWidth / 3), keepAspect: true, opacity: 1, start: 0, duration: 5, mode: "once", repeatEvery: 10, endOffset: 5, chromaEnabled: false, chromaColor: "#00FF00", chromaSimilarity: 0.1, chromaBlend: 0.05, audioEnabled: false };
  };
  const choose = async (kind: "image" | "video") => {
    try {
      const paths = kind === "image" ? await window.newsflowDesktop?.chooseImages() : await window.newsflowDesktop?.chooseVideos();
      if (!paths?.length) return;
      if (paths.some((path) => !localPath(path))) throw new Error("Выберите локальный файл изображения или видео.");
      if (kind === "image" && paths.some((path) => !/\.(png|jpe?g)$/i.test(path))) throw new Error("Для наложений выберите PNG или JPG.");
      const additions = paths.map((path) => createLayer(path, kind));
      setTemplate((current) => ({ ...current, layouts: { ...current.layouts, [layout]: [...current.layouts[layout], ...additions] } }));
      setActiveId(additions[additions.length - 1].id);
      setDirty(true); setError(""); setMessage(""); setConfirmation(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось выбрать файл."); }
  };
  const chooseLibrary = async (sourceId?: string) => {
    try {
      const folder = await window.newsflowDesktop?.chooseFolder();
      if (!folder) return;
      if (!localPath(folder)) throw new Error("Выберите локальную папку наложений.");
      if (sourceId) updateSource(sourceId, { root: folder }); else setLibraryRoot(folder);
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось выбрать папку."); }
  };
  const scanLibrary = async (source?: LibrarySource) => {
    const folder = (source?.root || template.libraryRoot)?.trim();
    if (!folder || !localPath(folder) || saving) return;
    setSaving(true); setError(""); setMessage(""); setConfirmation(null);
    try {
      const result = await command("scan-montage-overlays", { folder });
      const library = result?.operationResult;
      if (library?.kind !== "overlay-library" || !Array.isArray(library.assets)) throw new Error("Не удалось прочитать локальную папку наложений.");
      const seen = new Set(layers.map((layer) => sourcePathKey(layer.path, layer.librarySourceId)));
      const additions: Layer[] = [];
      for (const asset of library.assets) {
        if (!localPath(asset.path) || (asset.kind !== "image" && asset.kind !== "video") || (asset.kind === "image" && !/\.(png|jpe?g)$/i.test(asset.path))) throw new Error("Папка вернула неподдерживаемый локальный файл наложения.");
        const key = sourcePathKey(asset.path, source?.id);
        if (source && source.kind !== "all" && source.kind !== asset.kind) continue;
        if (seen.has(key)) continue;
        seen.add(key);
        additions.push({ ...createLayer(asset.path, asset.kind, asset.name), randomGroup: source?.name || "Из папки", ...(source ? { librarySourceId: source.id } : {}) });
      }
      setTemplate((current) => ({ ...current, ...(!source ? { libraryRoot: library.folder || folder } : {}), layouts: { ...current.layouts, [layout]: [...current.layouts[layout], ...additions] } }));
      if (additions.length) setActiveId(additions[additions.length - 1].id);
      setDirty(true);
      setMessage(`Найдено файлов: ${library.assets.length}. Добавлено вариантов: ${additions.length}.${library.skippedSymlinks ? ` Ссылки пропущены: ${library.skippedSymlinks}.` : ""} Существующие параметры сохранены.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось прочитать папку."); }
    finally { setSaving(false); }
  };
  const move = (direction: number) => {
    if (!active) return;
    const index = layers.findIndex((item) => item.id === active.id);
    const next = [...layers];
    if (index + direction < 0 || index + direction >= next.length) return;
    [next[index], next[index + direction]] = [next[index + direction], next[index]];
    setTemplate((current) => ({ ...current, layouts: { ...current.layouts, [layout]: next } }));
    setDirty(true); setConfirmation(null);
  };
  const save = async (scope: "new" | "selected", indices: number[], overwrite = false) => {
    if (!valid || saving || (scope === "selected" && !indices.length)) return;
    if (scope === "selected" && !overwrite) {
      setConfirmation([...indices]); return;
    }
    setSaving(true); setError(""); setMessage(""); setConfirmation(null);
    try {
      const result = await command("save-montage-overlays", { template, scope, indices, overwrite });
      if (!result) throw new Error("Не удалось сохранить наложения. Проверьте сообщение операции и повторите.");
      const skipped = result.operationResult?.kind === "montage-overlays" ? result.operationResult.skippedIndices || [] : [];
      setMessage(scope === "new" ? "Шаблон сохранён для новых задач. Текущая очередь не изменена." : `Применено к выбранным.${skipped.length ? ` Пропущены активные задачи: ${skipped.map((index) => index + 1).join(", ")}.` : ""}`);
      // Applying to existing tasks must not replace the independent defaults.
      setSource(scope === "new" ? "defaults" : "individual");
      setDirty(false);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось сохранить наложения."); }
    finally { setSaving(false); }
  };
  const reset = () => {
    setTemplate(data.montageSettings.overlayTemplate || emptyTemplate()); setDirty(false); setInvalid({});
    setSource("defaults"); setError(""); setMessage(""); setFailedMedia({}); setConfirmation(null); setPendingLoad(null); autoSize.current.clear();
  };
  const loadIndividual = (value: Template) => {
    setTemplate(copyTemplate(value)); setSource("individual"); setDirty(false); setInvalid({});
    setActiveId(null); setPendingLoad(null); setConfirmation(null); setError(""); setMessage("Загружены индивидуальные настройки выбранного ролика."); setFailedMedia({}); autoSize.current.clear();
  };
  const exportOverlays = async () => {
    if (!canRender || saving || dirty || queueActive) return;
    setSaving(true); setError(""); setMessage("");
    try {
      const result = await onRenderOverlays([...selectedIndices]);
      if (!result) throw new Error("Не удалось запустить экспорт наложений. Проверьте сохранённый план.");
      setMessage("Экспорт из сохранённых планов запущен без повторного подбора футажей.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось экспортировать наложения."); }
    finally { setSaving(false); }
  };
  const changeRange = (index: number, field: "start" | "end", raw: string) => {
    if (!active) return;
    const key = `${layout}:${active.id}:range-${index}-${field}`;
    const value = Number(raw);
    if (!raw.trim() || !Number.isFinite(value) || value < 0 || value > 604800) {
      setInvalid(current => ({ ...current, [key]: raw })); setDirty(true); return;
    }
    setInvalid(current => { const next = { ...current }; delete next[key]; return next; });
    update(active.id, { ranges: (active.ranges || []).map((range, i) => i === index ? { ...range, [field]: value } : range) });
  };
  const changeOnceEnd = (raw: string) => {
    if (!active) return;
    const key = `${layout}:${active.id}:onceEnd`;
    const end = Number(raw);
    if (!raw.trim() || !Number.isFinite(end) || end <= active.start || end > 604800) {
      setInvalid(current => ({ ...current, [key]: raw })); setDirty(true); return;
    }
    setInvalid(current => { const next = { ...current }; delete next[key]; return next; });
    update(active.id, { duration: end - active.start });
  };
  const clearTimingDrafts = () => {
    if (!active) return;
    const prefix = `${layout}:${active.id}:`;
    const fields = ["start", "duration", "repeatEvery", "endOffset", "repeatCount", "rangeEnd", "onceEnd"];
    setInvalid(current => Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(prefix) || (!fields.includes(key.slice(prefix.length)) && !key.slice(prefix.length).startsWith("range-")))));
  };
  let schedule: Array<[number, number]> = [], scheduleError = "";
  if (active) {
    try { schedule = overlayIntervals(active, total); }
    catch (cause) { scheduleError = cause instanceof Error ? cause.message : "Проверьте расписание слоя."; }
  }
  const timingSummary = (layer: Layer) => layer.mode === "until-end" ? `С ${overlayTimecode(layer.start)} до конца MP4` :
    layer.mode === "intervals" ? `Своих интервалов: ${layer.ranges?.length || 0}` : layer.mode === "count" ? `Показов: ${layer.repeatCount ?? 1}` :
    layer.mode === "repeat" ? `С ${overlayTimecode(layer.start)}, каждые ${layer.repeatEvery} с` : layer.mode === "end" ? `За ${layer.endOffset} с до конца` :
    `${overlayTimecode(layer.start)}–${overlayTimecode(layer.start + layer.duration)}`;
  return <section className="panel nf-overlay-panel">
    <div className="panel-title"><div><button type="button" className="nf-overlay-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>Наложения</button>
      <small>Картинки, PNG с прозрачностью и видео поверх финального монтажа.</small></div></div>
    {open && <fieldset className="nf-overlay-content" disabled={saving} aria-label="Редактор наложений">
      <p>Координаты от левого верхнего угла в пикселях готового видео. Форматы независимы. Порядок слоёв снизу вверх.</p>
      <div className="nf-overlay-library"><div className="nf-overlay-toolbar"><b>Папки и независимые группы</b><button type="button" onClick={addSource}>Добавить папку / группу</button></div>
        <small>Создайте отдельные группы для PNG-картинок и видео подписки. Группы включаются независимо и могут работать одновременно. «Случайный вариант» выбирает один файл на ролик плюс все отмеченные постоянными; «Все файлы» использует все включённые слои группы. Тип фильтрует импорт и показ; настройки остальных файлов сохраняются.</small>
        {librarySources.map((source, index) => <fieldset className="nf-overlay-source" key={source.id} aria-label={`Папка наложений ${index + 1}`}><legend>Источник {index + 1}</legend>
          <div className="nf-overlay-fields"><label>Название группы<input aria-label="Название группы" value={source.name} onChange={(event) => updateSource(source.id, { name: event.target.value })} /></label>
            <label className="nf-overlay-path">Папка группы<input aria-label="Папка группы" value={source.root} onChange={(event) => updateSource(source.id, { root: event.target.value })} /></label>
            <label>Файлы группы<select aria-label="Файлы группы" value={source.kind} onChange={(event) => updateSource(source.id, { kind: event.target.value as LibrarySource["kind"] })}><option value="all">Изображения и видео</option><option value="image">Только PNG / JPG</option><option value="video">Только видео</option></select></label>
            <label>Режим группы<select aria-label="Режим группы" value={source.mode} onChange={(event) => updateSource(source.id, { mode: event.target.value as LibrarySource["mode"] })}><option value="random">Случайный вариант + постоянные</option><option value="all">Все файлы группы</option></select></label>
            <label className="nf-overlay-check"><input aria-label="Включить группу" type="checkbox" checked={source.enabled} onChange={(event) => updateSource(source.id, { enabled: event.target.checked })} />Включить группу</label>
          </div><div className="nf-overlay-toolbar"><button type="button" onClick={() => void chooseLibrary(source.id)}>Выбрать папку</button><button type="button" disabled={!source.name.trim() || !localPath(source.root)} onClick={() => void scanLibrary(source)}>Добавить файлы группы</button><button type="button" onClick={() => removeSource(source.id)}>Удалить группу и её слои</button></div>
        </fieldset>)}
      </div>
      <div className="nf-overlay-library"><label>Корневая папка наложений<input aria-label="Корневая папка наложений" value={template.libraryRoot || ""} onChange={(event) => setLibraryRoot(event.target.value)} placeholder="D:\\Наложения" /></label>
        <div className="nf-overlay-toolbar"><button type="button" onClick={() => void chooseLibrary()}>Выбрать папку наложений</button><button type="button" disabled={!template.libraryRoot || !localPath(template.libraryRoot)} onClick={() => void scanLibrary()}>Добавить папку как случайные варианты</button></div>
        <small>Каждый файл добавляется отдельным слоем в текущий формат. При новом ролике из каждой непустой случайной группы выбирается один включённый вариант. Пустая группа — постоянный слой. Разные группы, например «Логотип» и «Подписка», выбираются независимо и могут показываться вместе с постоянными слоями.</small>
      </div>
      <div className="nf-overlay-toolbar" role="group" aria-label="Формат наложений">{(["16:9", "9:16"] as Layout[]).map((value) => <button type="button" key={value} aria-pressed={layout === value} onClick={() => { setLayout(value); setActiveId(null); setConfirmation(null); }}>{value}</button>)}
        <span>{frameWidth} × {frameHeight}</span><button type="button" onClick={() => void choose("image")}>Добавить изображения</button><button type="button" onClick={() => void choose("video")}>Добавить видео</button>
      </div>
      <div className="nf-overlay-toolbar"><button type="button" disabled={!individualTemplate} onClick={() => { if (individualTemplate) { if (dirty) setPendingLoad(copyTemplate(individualTemplate)); else loadIndividual(individualTemplate); } }}>Загрузить настройки выбранного ролика</button>
        <span>{source === "defaults" ? "Источник: шаблон новых задач" : "Источник: индивидуальные настройки"}</span></div>
      {pendingLoad && <div className="nf-overlay-confirmation" role="group" aria-label="Загрузка индивидуальных наложений"><p>Загрузить индивидуальные настройки? Несохранённые изменения в редакторе будут отменены.</p>
        <button type="button" onClick={() => loadIndividual(pendingLoad)}>Загрузить и отменить изменения</button><button type="button" onClick={() => setPendingLoad(null)}>Отмена загрузки</button></div>}
      {data.montageSettings.exportDaVinciXml && layers.some(layerEnabled) && <p role="note">DaVinci XML содержит сведённый MP4 с наложениями; слои отдельно не редактируются.</p>}
      <div className="nf-overlay-editor">
        <div className="nf-overlay-layers" role="group" aria-label="Слои снизу вверх">{layers.length ? layers.map((layer, index) => <div key={layer.id}>
          <input type="checkbox" aria-label={`Включить ${layer.name}`} checked={layer.enabled} onChange={(event) => update(layer.id, { enabled: event.target.checked })} />
          <span>{index + 1}</span><button type="button" aria-pressed={active?.id === layer.id} onClick={() => setActiveId(layer.id)}>{layer.name}</button>
          <small className="nf-overlay-layer-group">{layer.librarySourceId ? `${sourceById.get(layer.librarySourceId)?.name || "Группа недоступна"} · ` : ""}{layer.randomGroup?.trim() ? "Случайный вариант" : "Постоянный"}</small>
          <small className="nf-overlay-layer-group">{timingSummary(layer)}</small>
        </div>) : <p>В этом формате пока нет слоёв.</p>}</div>
        <div className="nf-overlay-preview-column">
          <div className="nf-overlay-preview" role="img" aria-label={`Предпросмотр наложений ${layout}`} style={{ aspectRatio: `${frameWidth} / ${frameHeight}` }}>
            <span className="nf-overlay-frame-note">Финальный кадр</span>
            {layers.map((layer) => {
              const offset = sourceTime(layer, time, total);
              const group = previewGroup(layer);
              if (offset === null || !layerEnabled(layer) || !localPath(layer.path) || (group && previewChoices.get(group) !== layer.id)) return null;
              return <div key={layer.id} aria-label={`Слой предпросмотра ${layer.name}`} className="nf-overlay-preview-layer"
                style={{ left: `${layer.x / frameWidth * 100}%`, top: `${layer.y / frameHeight * 100}%`, width: `${layer.width / frameWidth * 100}%`, height: `${layer.height / frameHeight * 100}%`, opacity: layer.opacity }}>
                {failedMedia[layer.id] ? <span>Файл недоступен · {layer.name}</span> : <PreviewMedia layer={layer} src={mediaUrl(layer.path)} time={offset}
                  onError={() => setFailedMedia((current) => ({ ...current, [layer.id]: true }))}
                  onDimensions={(width, height) => { if (!saving && autoSize.current.has(layer.id) && width > 0 && height > 0) { autoSize.current.delete(layer.id); update(layer.id, { height: Math.max(1, Math.min(16384, Math.round(layer.width * height / width))) }); } }} />}
              </div>;
            })}
          </div>
          <div className="nf-overlay-preview-time"><label>Позиция предпросмотра, с<input aria-label="Позиция предпросмотра, с" type="number" min="0" max={total} step="0.1" value={time} onChange={(event) => { const value = Number(event.target.value); if (Number.isFinite(value)) setTime(Math.max(0, Math.min(total, value))); }} /></label>
            <label>Полная длина с заставкой, с<input type="number" min="0.1" max="604800" step="0.1" value={total} onChange={(event) => { const value = Number(event.target.value); if (value > 0 && value <= 604800) { setTotal(value); setTime(Math.min(time, value)); } }} /></label></div>
          <small>Предпросмотр геометрии, времени и хромакея на условном фоне. Звук выключен. Цвет и края могут отличаться от итогового рендера.</small>
          {previewChoices.size > 0 && <small>Для каждой случайной группы показан выбранный в списке вариант, иначе первый включённый. В новом ролике вариант выбирается случайно один раз; повторный экспорт сохранённого проекта сохраняет выбор.</small>}
        </div>
      </div>
      {active && <fieldset className="nf-overlay-properties"><legend>Слой: {active.name}</legend>
        <div className="nf-overlay-toolbar"><button type="button" disabled={layers[0]?.id === active.id} onClick={() => move(-1)}>Слой ниже</button><button type="button" disabled={layers[layers.length - 1]?.id === active.id} onClick={() => move(1)}>Слой выше</button>
          <button type="button" onClick={() => { setTemplate((current) => ({ ...current, layouts: { ...current.layouts, [layout]: layers.filter((layer) => layer.id !== active.id) } })); setInvalid((current) => Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(`${layout}:${active.id}:`)))); setDirty(true); setConfirmation(null); }}>Удалить слой</button>
          <label>Шаг, px<select aria-label="Шаг, px" value={step} onChange={(event) => setStep(Number(event.target.value))}><option value="1">1</option><option value="10">10</option></select></label>
        </div>
        <fieldset className="nf-overlay-timing" aria-label={`Когда показывать: ${active.name}`}>
          <legend>Когда показывать: {active.name}</legend>
          <p>Настройки только этого слоя. Все времена отсчитываются от начала готового MP4, включая заставку.</p>
          <div className="nf-overlay-fields">
            <label>Режим показа<select aria-label="Режим показа" value={active.mode} onChange={(event) => {
              const mode = event.target.value as Layer["mode"];
              clearTimingDrafts();
              update(active.id, { mode, ...(mode === "intervals" && !active.ranges?.length ? { ranges: [{ start: active.start, end: active.start + active.duration }] } : {}),
                ...(mode !== "intervals" && active.ranges && !validOverlayTiming({ ...active, mode: "intervals" }) ? { ranges: undefined } : {}),
                ...(mode === "count" ? { repeatCount: active.repeatCount ?? 3, rangeEnd: active.rangeEnd != null && active.rangeEnd > active.start ? active.rangeEnd : null } : {}) });
            }}>
              <option value="once">Один интервал</option><option value="intervals">Мои интервалы «от–до»</option>
              <option value="count">Заданное количество показов</option><option value="repeat">Повтор каждые N секунд</option>
              <option value="until-end">С указанного времени до конца MP4</option><option value="end">За N секунд до конца</option>
            </select></label>
            {active.mode !== "intervals" && active.mode !== "end" && numeric("Начало, с", "start")}
            {active.mode !== "intervals" && active.mode !== "until-end" && numeric("Длительность, с", "duration")}
            {active.mode === "once" && <label>Конец интервала, с<input aria-label="Конец интервала, с" type="number" min={0} max={604800}
              value={invalid[`${layout}:${active.id}:onceEnd`] ?? active.start + active.duration} onChange={event => changeOnceEnd(event.target.value)} /></label>}
            {active.mode === "repeat" && numeric("Повтор каждые, с", "repeatEvery")}
            {active.mode === "end" && numeric("За сколько до конца, с", "endOffset")}
            {active.mode === "count" && <>
              {numeric("Количество показов", "repeatCount")}
              <label className="nf-overlay-check"><input type="checkbox" aria-label="Диапазон до конца MP4" checked={active.rangeEnd == null}
                onChange={event => { setInvalid(current => { const next = { ...current }; delete next[`${layout}:${active.id}:rangeEnd`]; return next; });
                  update(active.id, { rangeEnd: event.target.checked ? null : Math.max(active.start + active.duration, total) }); }} />Диапазон до конца MP4</label>
              {active.rangeEnd != null && numeric("Конец диапазона, с", "rangeEnd")}
            </>}
          </div>
          {active.mode === "intervals" && <div className="nf-overlay-range-list">
            {(active.ranges || []).map((range, index) => <div className="nf-overlay-range" key={index}>
              <b>Показ {index + 1}</b>
              {(["start", "end"] as const).map(field => <label key={field}>{field === "start" ? "От, с" : "До, с"}
                <input type="number" min={0} max={604800} step="any" aria-label={`Интервал ${index + 1}: ${field === "start" ? "начало" : "конец"}, с`}
                  value={invalid[`${layout}:${active.id}:range-${index}-${field}`] ?? range[field]} onChange={event => changeRange(index, field, event.target.value)} />
              </label>)}
              <span>{overlayTimecode(range.start)}–{overlayTimecode(range.end)}</span>
              <button type="button" aria-label={`Удалить интервал ${index + 1}`} onClick={() => {
                setInvalid(current => {
                  const prefix = `${layout}:${active.id}:range-`;
                  return Object.fromEntries(Object.entries(current).flatMap(([key, value]) => {
                    if (!key.startsWith(prefix)) return [[key, value]];
                    const match = /^(\d+)-(start|end)$/.exec(key.slice(prefix.length));
                    if (!match) return [[key, value]];
                    const oldIndex = Number(match[1]);
                    return oldIndex === index ? [] : [[`${prefix}${oldIndex > index ? oldIndex - 1 : oldIndex}-${match[2]}`, value]];
                  }));
                });
                update(active.id, { ranges: active.ranges?.filter((_range, i) => i !== index) });
              }}>Удалить</button>
            </div>)}
            <button type="button" onClick={() => { const end = Math.max(0, ...(active.ranges || []).map(range => range.end));
              update(active.id, { ranges: [...(active.ranges || []), { start: end + 5, end: end + 10 }] });
            }}>Добавить интервал</button>
          </div>}
          {active.mode === "count" && <small>Укажите диапазон, длительность одного показа и число показов. Они распределятся равномерно: первый начнётся в начале диапазона, последний закончится в его конце.</small>}
          {active.mode === "once" && <small>Один показ: задайте начало и конец интервала в секундах. Длительность пересчитывается автоматически.</small>}
          {active.mode === "repeat" && <small>Первый показ начнётся в указанное время, следующие — через каждые N секунд. Длительность задаётся для одного показа.</small>}
          {active.mode === "end" && <small>Начало отсчитывается назад от фактического конца MP4: например, за 10 секунд до конца. Длительность задаётся для одного показа.</small>}
          {active.mode === "until-end" && <small>Картинка остаётся на экране до фактического конца каждого MP4. Видео-вставка повторяется по кругу с обычной скоростью; основной ролик и озвучка сохраняют длину.</small>}
          {active.mode === "intervals" && <small>Добавьте отдельную строку для каждого показа. Например: 6–12 с, 80–88 с, 180–190 с. Пересечения интервалов одного слоя не допускаются.</small>}
          <p aria-label="Расписание показа" aria-live="polite">Для длины предпросмотра {total} с: {scheduleError || (schedule.length ? `${schedule.length} показ(а): ` + schedule.slice(0, 8).map(([begin, end]) => `${overlayTimecode(begin)}–${overlayTimecode(end)}`).join("; ") + (schedule.length > 8 ? `; ещё ${schedule.length - 8}` : "") : "нет показов внутри ролика")}</p>
          <small>Каждый отдельный показ видео начинается с кадра 0. Выход за конец MP4 обрезается. Сохранение и применение шаблона сохраняет расписание каждого файла.</small>
        </fieldset>
        <div className="nf-overlay-fields"><label>Имя слоя<input value={active.name} onChange={(event) => update(active.id, { name: event.target.value })} /></label>
          {activeSource ? <label className="nf-overlay-check"><input type="checkbox" aria-label="Использовать постоянно" checked={!active.randomGroup?.trim()} onChange={(event) => update(active.id, { randomGroup: event.target.checked ? "" : activeSource.name })} />Использовать постоянно в группе «{activeSource.name}»</label> :
            <label>Случайная группа (пусто = всегда)<input aria-label="Случайная группа (пусто = всегда)" value={active.randomGroup || ""} onChange={(event) => update(active.id, { randomGroup: event.target.value })} /></label>}
          <label className="nf-overlay-path">Файл<input value={active.path} onChange={(event) => { autoSize.current.delete(active.id); update(active.id, { path: event.target.value }); setFailedMedia((current) => ({ ...current, [active.id]: false })); }} /></label>
          <label>Тип<select value={active.kind} onChange={(event) => update(active.id, { kind: event.target.value as Layer["kind"], audioEnabled: false })}><option value="image">Изображение</option><option value="video">Видео</option></select></label>
          {numeric("X, px", "x", true)}{numeric("Y, px", "y", true)}{numeric("Ширина, px", "width", true)}{numeric("Высота, px", "height", true)}
          <label className="nf-overlay-check"><input type="checkbox" checked={active.keepAspect} onChange={(event) => update(active.id, { keepAspect: event.target.checked })} />Сохранять пропорции</label>
          {numeric("Непрозрачность 0–1", "opacity")}
          <label className="nf-overlay-check"><input type="checkbox" aria-label="Хромакей" checked={active.chromaEnabled} onChange={(event) => update(active.id, { chromaEnabled: event.target.checked })} />Хромакей</label>
          {active.chromaEnabled && <><label>Цвет хромакея<input type="color" value={active.chromaColor} onChange={(event) => update(active.id, { chromaColor: event.target.value })} /></label>{numeric("Сходство цвета", "chromaSimilarity")}{numeric("Смягчение края", "chromaBlend")}</>}
          {active.kind === "video" && <label className="nf-overlay-check"><input type="checkbox" aria-label="Звук слоя" checked={active.audioEnabled} onChange={(event) => update(active.id, { audioEnabled: event.target.checked })} />Звук слоя (добавить к озвучке)</label>}
        </div><small>Время учитывает заставку; каждый повтор видео начинается с исходного кадра 0. За границами готового ролика слой обрезается.</small>
      </fieldset>}
      {(!valid || error || Object.keys(failedMedia).some((key) => failedMedia[key])) && <p role="alert">{error || (!valid ? "Укажите локальный файл и допустимые числовые значения для всех слоёв и обоих форматов." : "Некоторые файлы недоступны для предпросмотра. Проверьте путь и поддерживаемый формат.")}</p>}
      <div className="nf-overlay-toolbar"><button type="button" disabled={!valid || saving} onClick={() => void save("new", [])}>Сохранить для новых</button>
        <button type="button" disabled={!valid || saving || !selectedIndices.length} onClick={() => void save("selected", [...selectedIndices])}>Применить к выбранным ({selectedIndices.length})</button>
        <button type="button" disabled={!valid || saving || !allIndices.length} onClick={() => void save("selected", [...allIndices])}>Применить ко всей очереди ({allIndices.length})</button>
        <button type="button" disabled={!canRender || saving || dirty || queueActive} onClick={() => void exportOverlays()}>Экспортировать наложения без подбора</button>
        <button type="button" disabled={saving} onClick={reset}>Сбросить изменения</button>{dirty && <span>Есть несохранённые изменения</span>}</div>
      <small>«Для новых» меняет только будущие задачи. «К выбранным» обновляет выбранные строки. «Ко всей очереди» охватывает все сценарии и задачи, включая строки без MP3. Сохранённые планы обновляются; активные задачи пропускаются.</small>
      <small>Экспорт использует сохранённые настройки выбранных проектов. Сначала примените изменения к выбранным роликам; для экспорта нужен готовый план у каждой выбранной строки. Повторный подбор футажей не запускается.</small>
      {confirmation && <div className="nf-overlay-confirmation" role="group" aria-label="Замена индивидуальных наложений"><p>Применить шаблон к выбранным? Существующие индивидуальные наложения будут заменены; запущенные задачи пропускаются.</p>
        <button type="button" onClick={() => void save("selected", confirmation, true)}>Заменить индивидуальные</button><button type="button" onClick={() => setConfirmation(null)}>Отмена</button></div>}
      {message && <p role="status">{message}</p>}
    </fieldset>}
  </section>;
}
