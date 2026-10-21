import type { MontageOverlayLayer as Layer } from "./montageOverlays";

const MAX = 604800;
const MAX_SHOWS = 513;
const bounded = (value: number, low = 0) => Number.isFinite(value) && value >= low && value <= MAX;
export function validOverlayTiming(layer: Layer): boolean {
  if (layer.ranges !== undefined) {
    if (!Array.isArray(layer.ranges) || layer.ranges.length > MAX_SHOWS) return false;
    const ranges = [...layer.ranges].sort((a, b) => a.start - b.start);
    if (ranges.some((range, index) => !bounded(range.start) || !bounded(range.end) || range.end <= range.start || (index > 0 && range.start < ranges[index - 1].end))) return false;
  }
  if (layer.mode === "intervals" && !layer.ranges?.length) return false;
  const count = layer.repeatCount ?? 1;
  if (!Number.isInteger(count) || count < 1 || count > MAX_SHOWS) return false;
  if (layer.rangeEnd != null && (!bounded(layer.rangeEnd) || (layer.mode === "count" && layer.rangeEnd <= layer.start))) return false;
  if (layer.mode === "count" && layer.rangeEnd != null && count > 1 && count * layer.duration > layer.rangeEnd - layer.start + 1e-9) return false;
  return ["once", "repeat", "end", "until-end", "intervals", "count"].includes(layer.mode);
}

export function overlayIntervals(layer: Layer, total: number): Array<[number, number]> {
  if (!bounded(total) || !validOverlayTiming(layer)) throw Error("Проверьте интервалы: конец должен быть позже начала, без пересечений; количество показов — целое положительное число.");
  if (!layer.enabled || !total) return [];
  if (layer.mode === "intervals") return [...(layer.ranges || [])].sort((a, b) => a.start - b.start)
    .filter(range => range.start < total).map(range => [range.start, Math.min(total, range.end)]);
  if (layer.mode === "until-end") return layer.start < total ? [[layer.start, total]] : [];
  if (layer.mode === "count") {
    const count = layer.repeatCount ?? 1;
    const end = Math.min(total, layer.rangeEnd ?? total);
    if (end <= layer.start) return [];
    if (count > 1 && count * layer.duration > end - layer.start + 1e-9) throw Error("Показы заданной длительности не помещаются в диапазон. Уменьшите длительность или количество.");
    const gap = count > 1 ? (end - layer.duration - layer.start) / (count - 1) : 0;
    return Array.from({ length: count }, (_, index) => [layer.start + index * gap, Math.min(end, layer.start + index * gap + layer.duration)]);
  }
  const start = layer.mode === "end" ? total - layer.endOffset : layer.start;
  const count = layer.mode === "repeat" ? Math.max(0, Math.ceil((total - start) / layer.repeatEvery)) : 1;
  if (!Number.isFinite(count) || count > MAX_SHOWS) throw Error("Слишком много повторов для предпросмотра; увеличьте интервал.");
  return Array.from({ length: count }, (_, index): [number, number] => {
    const begin = start + index * (layer.mode === "repeat" ? layer.repeatEvery : 0);
    return [Math.max(0, begin), Math.min(total, begin + layer.duration)];
  }).filter(([begin, end]) => end > begin);
}

export function overlaySourceTime(layer: Layer, time: number, total: number): number | null {
  if (time < 0 || time >= total) return null;
  try {
    const interval = overlayIntervals(layer, total).reverse().find(([begin, end]) => time >= begin && time < end);
    return interval ? time - interval[0] : null;
  } catch { return null; } // The editor displays the schedule error separately.
}

export function overlayTimecode(seconds: number): string {
  const milliseconds = Math.round(seconds * 1000);
  const whole = Math.floor(milliseconds / 1000);
  const fraction = milliseconds % 1000;
  const clock = `${Math.floor(whole / 60).toString().padStart(2, "0")}:${(whole % 60).toString().padStart(2, "0")}`;
  return clock + (fraction ? `.${fraction.toString().padStart(3, "0").replace(/0+$/, "")}` : "");
}
