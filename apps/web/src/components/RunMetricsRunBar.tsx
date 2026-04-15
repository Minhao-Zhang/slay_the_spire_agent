import { fmtIntEn } from "../lib/formatDisplayNumber";
import { SpireAgentNav } from "./SpireAgentNav";

export type RunMetricsRunBarProps = {
  runs: string[];
  run: string;
  onRunChange: (run: string) => void;
  loading: boolean;
  frameCount: number | null;
  recordsLength?: number;
  /** When metrics fetch failed, e.g. `no_metrics_file`. */
  metricsReason?: string | null;
  variant: "metrics" | "map";
  mapLoading?: boolean;
  mapError?: string | null;
  /** Keep `?run=` aligned with the bridge’s active log directory (metrics only). */
  followLive?: boolean;
  onFollowLiveChange?: (on: boolean) => void;
};

function metricsReasonLabel(reason: string): string {
  if (reason === "no_metrics_file") {
    return "No run_metrics.ndjson for this run.";
  }
  if (reason === "internal_error") {
    return "Metrics server error; check API logs.";
  }
  if (reason.startsWith("http_")) {
    const code = reason.slice("http_".length);
    return `Metrics request failed (HTTP ${code}). Is the dashboard API running on the Vite proxy target?`;
  }
  if (reason === "invalid_response") {
    return "Metrics response was not in the expected shape.";
  }
  return `Metrics: ${reason}`;
}

export function RunMetricsRunBar({
  runs,
  run,
  onRunChange,
  loading,
  frameCount,
  recordsLength,
  metricsReason,
  variant,
  mapLoading,
  mapError,
  followLive = false,
  onFollowLiveChange,
}: RunMetricsRunBarProps) {
  const runQ = (() => {
    const p = new URLSearchParams();
    if (run) p.set("run", run);
    if (followLive) p.set("follow", "1");
    const s = p.toString();
    return s ? `?${s}` : "";
  })();
  const showFrameRow =
    variant !== "map" &&
    typeof recordsLength === "number" &&
    frameCount !== null;

  const spirePage = variant === "map" ? "map" : "metrics";

  return (
    <header className="flex shrink-0 items-center border-b border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-panel)_88%,transparent)] px-3 py-2 backdrop-blur-sm">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
        <SpireAgentNav page={spirePage} runQuery={runQ} />

        <label className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-spire-label">
            Run
          </span>
          <select
            value={run}
            onChange={(e) => onRunChange(e.target.value)}
            className="font-console h-8 max-w-[18rem] rounded border border-spire-border-subtle bg-spire-inset/80 px-2 text-xs text-spire-primary outline-none"
            aria-label="Log run"
          >
            <option value="">Select run…</option>
            {runs.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>

        {variant !== "map" && onFollowLiveChange ? (
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={followLive}
              onChange={(e) => onFollowLiveChange(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-spire-border-strong"
            />
            <span className="text-xs uppercase tracking-wide text-spire-label">
              Follow live
            </span>
          </label>
        ) : null}

        {variant !== "map" && loading ? (
          <span className="text-xs text-spire-label">Loading…</span>
        ) : null}
        {variant === "map" && mapLoading ? (
          <span className="text-xs text-spire-label">Loading map…</span>
        ) : null}

        {variant !== "map" && metricsReason ? (
          <span className="text-xs text-spire-warning" title={metricsReason}>
            {metricsReasonLabel(metricsReason)}
          </span>
        ) : null}

        {variant === "map" && mapError ? (
          <span className="text-xs text-spire-warning" title={mapError}>
            {mapError}
          </span>
        ) : null}

        {showFrameRow ? (
          <span className="font-telemetry text-xs tabular-nums text-spire-label">
            Frames: {fmtIntEn(frameCount)} · Rows: {fmtIntEn(recordsLength)}
          </span>
        ) : null}

        {variant === "map" && run && frameCount !== null ? (
          <span className="font-telemetry text-xs tabular-nums text-spire-label">
            Frames: {fmtIntEn(frameCount)}
          </span>
        ) : null}
      </div>
    </header>
  );
}
