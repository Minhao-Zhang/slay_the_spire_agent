import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useRunMetricsData } from "../hooks/useRunMetricsData";
import { useRunMetricsModel } from "../hooks/useRunMetricsModel";
import {
  fmtFiniteIntLikeEn,
  fmtIntEn,
  fmtNumEn,
  tickFmtIntEn,
  tickFmtNumberEn,
} from "../lib/formatDisplayNumber";
import { chartColors, PIE_COLORS } from "../lib/chartTheme";
import {
  type BinnedNumeric,
  type FloorAiAggRow,
  type FloorStateAggRow,
  type MetricsSummary,
  type StateRow,
} from "../lib/runMetricsDerive";
import {
  TelemetryChartPanel,
  TelemetryTooltipFrame,
} from "./metrics/TelemetryChartPanel";
import { RunMetricsRunBar } from "./RunMetricsRunBar";

const CHART_H = 220;
const HERO_H = 112;
const ESTIMATED_TPS_CHART_CAP = 200;
const CHART_AXIS_TICK = { stroke: chartColors.axis, fontSize: 14 };
const GRID = { stroke: chartColors.grid, strokeDasharray: "3 3" };

const X_AXIS_EVENT_INDEX = {
  ...CHART_AXIS_TICK,
  tickFormatter: tickFmtIntEn,
};
const Y_AXIS_DEFAULT = { ...CHART_AXIS_TICK, tickFormatter: tickFmtNumberEn };

type MetricsTabId = "prog" | "ai" | "dist";

const METRICS_TAB_ORDER: MetricsTabId[] = ["prog", "ai", "dist"];

const METRICS_TAB_META: Record<
  MetricsTabId,
  { tabId: string; panelId: string; label: string }
> = {
  prog: {
    tabId: "spire-metrics-tab-prog",
    panelId: "spire-metrics-panel-prog",
    label: "Progression",
  },
  ai: {
    tabId: "spire-metrics-tab-ai",
    panelId: "spire-metrics-panel-ai",
    label: "AI cost and latency",
  },
  dist: {
    tabId: "spire-metrics-tab-dist",
    panelId: "spire-metrics-panel-dist",
    label: "Distributions",
  },
};

const METRICS_TAB_INACTIVE_CLS =
  "text-[var(--text-label)] hover:text-[var(--text-primary)]";
const METRICS_TAB_ACTIVE_CLS =
  "bg-[color-mix(in_srgb,var(--accent-primary)_28%,transparent)] text-[var(--text-primary)]";
const LEVEL_MODE_SELECTED_CLS =
  "bg-[color-mix(in_srgb,var(--accent-primary)_24%,var(--bg-panel-raised))] text-[var(--text-primary)]";

/** Raw token count with digit grouping (e.g. 1,234,567). */
function fmtTokensCommas(n: number): string {
  return fmtIntEn(Math.round(n));
}

/** Y-axis tick when series values are already in thousands of tokens. */
function yAxisTickKTokens(value: number): string {
  const abs = Math.abs(value);
  const maxFrac = abs < 10 ? 2 : abs < 100 ? 1 : 0;
  return value.toLocaleString("en-US", {
    maximumFractionDigits: maxFrac,
    minimumFractionDigits: 0,
  });
}

function yAxisTickSeconds(value: number): string {
  return value.toLocaleString("en-US", {
    maximumFractionDigits: value >= 100 ? 0 : 2,
    minimumFractionDigits: 0,
  });
}

const CHART_MARGIN_TIGHT = { top: 8, right: 8, left: 0, bottom: 0 };
const CHART_MARGIN_LEFT4 = { top: 8, right: 8, left: 4, bottom: 0 };
const CHART_MARGIN_PIE = { top: 8, right: 8, bottom: 8, left: 8 };
const CHART_MARGIN_BAR = { top: 8, right: 8, left: 0, bottom: 24 };

const Y_LABEL_K_TOKENS = {
  value: "k tokens",
  angle: -90,
  position: "insideLeft" as const,
  fill: chartColors.axis,
  fontSize: 13,
  dx: -4,
};

const Y_LABEL_LATENCY_S = {
  value: "s",
  angle: -90,
  position: "insideLeft" as const,
  fill: chartColors.axis,
  fontSize: 13,
  dx: -4,
};

const Y_LABEL_TPS = {
  value: "tokens/s",
  angle: -90,
  position: "insideLeft" as const,
  fill: chartColors.axis,
  fontSize: 13,
  dx: -4,
};

const X_AXIS_BAR_TICK = { fontSize: 12 };

const X_AXIS_FLOOR_LEVEL = {
  ...CHART_AXIS_TICK,
  dataKey: "floor" as const,
  type: "number" as const,
  tickFormatter: tickFmtIntEn,
  allowDecimals: false,
  domain: ["dataMin - 0.5", "dataMax + 0.5"] as [string, string],
};

function FloorActDividerLines({ xs }: { xs: readonly number[] }) {
  return (
    <>
      {xs.map((x, i) => (
        <ReferenceLine
          key={`floor-act-${i}-${x}`}
          x={x}
          stroke={chartColors.refLine}
          strokeWidth={2}
          strokeOpacity={0.9}
        />
      ))}
    </>
  );
}

function FloorLevelTooltipHeader(props: {
  floor: number | null;
  act: number | null;
  floor_label?: string;
}) {
  const hasFloor =
    typeof props.floor === "number" && Number.isFinite(props.floor);
  return (
    <>
      <div className="font-mono text-[var(--text-primary)]">
        {hasFloor
          ? `Level ${fmtIntEn(Math.round(props.floor!))}`
          : props.floor_label ?? "Unknown"}
      </div>
      {props.act != null && Number.isFinite(props.act) && (
        <div className="text-[13px] text-[var(--text-label)]">
          Act {fmtIntEn(Math.round(props.act))}
        </div>
      )}
    </>
  );
}

type StateTooltipKeys = Array<
  | "hp"
  | "gold"
  | "floor"
  | "legal"
  | "monsters"
  | "hand"
  | "deck"
  | "relic"
>;

const STATE_KEYS_HP: StateTooltipKeys = ["hp"];
const STATE_KEYS_GOLD: StateTooltipKeys = ["gold"];
const STATE_KEYS_FLOOR: StateTooltipKeys = ["floor"];
const STATE_KEYS_LEGAL: StateTooltipKeys = ["legal"];
const STATE_KEYS_MONSTERS: StateTooltipKeys = ["monsters"];
const STATE_KEYS_HAND: StateTooltipKeys = ["hand"];
const STATE_KEYS_DECK: StateTooltipKeys = ["deck"];
const STATE_KEYS_RELIC: StateTooltipKeys = ["relic"];

type TooltipLite = {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: unknown }>;
};

function pieStatusLabel(props: {
  name?: string;
  percent?: number;
}): string {
  return `${props.name ?? ""} ${fmtIntEn(
    Math.round((props.percent ?? 0) * 100),
  )}%`;
}

function HistogramTooltipInput(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const p = tp.payload[0].payload as BinnedNumeric;
  return (
    <TelemetryTooltipFrame>
      <div className="tabular-nums">count: {fmtIntEn(p.count)}</div>
      <div>
        range: {fmtNumEn(p.lo, 2)}–{fmtNumEn(p.hi, 2)} tokens
      </div>
    </TelemetryTooltipFrame>
  );
}

function HistogramTooltipLatency(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const p = tp.payload[0].payload as BinnedNumeric;
  return (
    <TelemetryTooltipFrame>
      <div className="tabular-nums">count: {fmtIntEn(p.count)}</div>
      <div>
        range: {fmtNumEn(p.lo, 1)}–{fmtNumEn(p.hi, 1)} ms
      </div>
    </TelemetryTooltipFrame>
  );
}

export function RunMetricsPage() {
  const [levelMode, setLevelMode] = useState<"event" | "floor">("event");
  const [metricsTab, setMetricsTab] = useState<"prog" | "ai" | "dist">(() => {
    try {
      const t = sessionStorage.getItem("spireMetricsTab");
      if (t === "prog" || t === "ai" || t === "dist") return t;
    } catch {
      /* ignore */
    }
    return "prog";
  });

  useEffect(() => {
    try {
      sessionStorage.setItem("spireMetricsTab", metricsTab);
    } catch {
      /* ignore */
    }
  }, [metricsTab]);

  const eventLevelBtnRef = useRef<HTMLButtonElement>(null);
  const floorLevelBtnRef = useRef<HTMLButtonElement>(null);
  const metricsTabBtnRef = useRef<
    Record<MetricsTabId, HTMLButtonElement | null>
  >({ prog: null, ai: null, dist: null });

  const focusMetricsTabButton = useCallback((id: MetricsTabId) => {
    queueMicrotask(() => {
      metricsTabBtnRef.current[id]?.focus();
    });
  }, []);

  const onMetricsTabListKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        const i = METRICS_TAB_ORDER.indexOf(metricsTab);
        const next = METRICS_TAB_ORDER[(i + 1) % METRICS_TAB_ORDER.length];
        setMetricsTab(next);
        focusMetricsTabButton(next);
        return;
      }
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        const i = METRICS_TAB_ORDER.indexOf(metricsTab);
        const next =
          METRICS_TAB_ORDER[
            (i - 1 + METRICS_TAB_ORDER.length) % METRICS_TAB_ORDER.length
          ];
        setMetricsTab(next);
        focusMetricsTabButton(next);
        return;
      }
      if (e.key === "Home") {
        e.preventDefault();
        setMetricsTab("prog");
        focusMetricsTabButton("prog");
        return;
      }
      if (e.key === "End") {
        e.preventDefault();
        setMetricsTab("dist");
        focusMetricsTabButton("dist");
      }
    },
    [metricsTab, focusMetricsTabButton],
  );

  const onLevelResolutionKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        setLevelMode("floor");
        queueMicrotask(() => floorLevelBtnRef.current?.focus());
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        setLevelMode("event");
        queueMicrotask(() => eventLevelBtnRef.current?.focus());
      }
    },
    [],
  );

  const {
    runs,
    run,
    setRun,
    followLive,
    setFollowLive,
    dashboardSnapshot,
    loading,
    payload,
    frameCount,
    records,
    parseErrors,
  } = useRunMetricsData();

  const {
    stateRows,
    floorStateChartRows,
    floorStateActDividers,
    floorAiActDividers,
    floorCumulative,
    floorAiChart,
    tokenSeries,
    estimatedTpsSeries,
    inputTokBins,
    latencyBins,
    statusPie,
    aiRowCount,
    summary,
    executedInOutTokens,
    playerRunLabelDisplay,
  } = useRunMetricsModel(records, run, payload);

  const statusPieTooltipContent = useCallback(
    (tp: TooltipLite) => {
      if (!tp.active || !tp.payload?.[0]) return null;
      const d = tp.payload[0].payload as { name: string; value: number };
      const pct =
        aiRowCount > 0
          ? fmtNumEn((d.value / aiRowCount) * 100, 1)
          : fmtNumEn(0, 1);
      return (
        <TelemetryTooltipFrame>
          <div className="font-medium text-[var(--text-primary)]">{d.name}</div>
          <div className="tabular-nums">
            count: {fmtIntEn(d.value)} ({pct}%)
          </div>
        </TelemetryTooltipFrame>
      );
    },
    [aiRowCount],
  );

  return (
    <div className="metrics-page-bg min-h-screen text-sm text-[var(--text-primary)]">
      <RunMetricsRunBar
        runs={runs}
        run={run}
        onRunChange={setRun}
        loading={loading}
        frameCount={frameCount}
        recordsLength={records.length}
        metricsReason={
          payload && !payload.ok ? payload.reason : null
        }
        variant="metrics"
        followLive={followLive}
        onFollowLiveChange={setFollowLive}
      />

      <main className="space-y-6 px-4 py-5">
        {followLive &&
        dashboardSnapshot &&
        !dashboardSnapshot.active_log_run?.trim() ? (
          <div
            className="rounded border border-spire-warning/50 bg-spire-warning/15 px-3 py-2 text-xs text-spire-primary"
            role="status"
          >
            <span className="font-semibold">Follow live:</span> dashboard
            reports no active log run yet (between games or logging off).
          </div>
        ) : null}
        {!followLive &&
        dashboardSnapshot?.active_log_run?.trim() &&
        run &&
        dashboardSnapshot.active_log_run !== run &&
        dashboardSnapshot.live_ingress ? (
          <div
            className="flex flex-wrap items-center gap-2 rounded border border-spire-secondary/40 bg-spire-secondary/12 px-3 py-2 text-xs text-spire-primary"
            role="status"
          >
            <span>
              Live session is writing{" "}
              <span className="font-mono">{dashboardSnapshot.active_log_run}</span>
              ; you are viewing <span className="font-mono">{run}</span>.
            </span>
            <Link
              className="font-console font-semibold text-[var(--accent-primary)] underline"
              to={`/metrics?run=${encodeURIComponent(dashboardSnapshot.active_log_run!)}&follow=1`}
            >
              Jump to live run
            </Link>
          </div>
        ) : null}
        {parseErrors.length > 0 ? (
          <div
            className="rounded border border-spire-warning/55 bg-spire-warning/18 px-3 py-2 text-xs text-spire-primary"
            role="alert"
          >
            <span className="font-semibold">Parse warnings: </span>
            {parseErrors.slice(0, 5).join(" · ")}
            {parseErrors.length > 5
              ? ` (+${fmtIntEn(parseErrors.length - 5)} more)`
              : ""}
          </div>
        ) : null}

        {payload?.ok && records.length > 0 ? (
          <div className="flex flex-wrap items-center gap-3 rounded border border-[color-mix(in_srgb,var(--border-strong)_78%,transparent)] bg-[color-mix(in_srgb,var(--bg-canvas)_48%,transparent)] px-3 py-2">
            <span
              className="text-xs font-semibold uppercase tracking-wide text-[var(--text-label)]"
              id="spire-resolution-label"
            >
              Resolution
            </span>
            <div
              role="radiogroup"
              aria-labelledby="spire-resolution-label"
              onKeyDown={onLevelResolutionKeyDown}
              className="inline-flex rounded border border-[var(--border-subtle)] bg-spire-inset p-0.5"
            >
              <button
                ref={eventLevelBtnRef}
                type="button"
                role="radio"
                aria-checked={levelMode === "event"}
                tabIndex={levelMode === "event" ? 0 : -1}
                onClick={() => setLevelMode("event")}
                className={
                  "rounded px-3 py-1 font-console text-xs font-semibold uppercase tracking-wide transition " +
                  (levelMode === "event"
                    ? LEVEL_MODE_SELECTED_CLS
                    : METRICS_TAB_INACTIVE_CLS)
                }
              >
                Event level
              </button>
              <button
                ref={floorLevelBtnRef}
                type="button"
                role="radio"
                aria-checked={levelMode === "floor"}
                tabIndex={levelMode === "floor" ? 0 : -1}
                onClick={() => setLevelMode("floor")}
                className={
                  "rounded px-3 py-1 font-console text-xs font-semibold uppercase tracking-wide transition " +
                  (levelMode === "floor"
                    ? LEVEL_MODE_SELECTED_CLS
                    : METRICS_TAB_INACTIVE_CLS)
                }
              >
                Floor level
              </button>
            </div>
          </div>
        ) : null}

        {summary ? (
          <section className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Kpi
                label="Character"
                value={playerRunLabelDisplay}
                title="Class and ascension from the latest state snapshot (same format as Monitor: class · A0)."
              />
              <Kpi
                label="Input tokens"
                value={
                  executedInOutTokens.hasData
                    ? fmtNumEn(executedInOutTokens.uncached)
                    : "—"
                }
                title={
                  executedInOutTokens.hasData
                    ? `Non-cached prompt tokens (fresh input). API prompt total for this run = ${fmtNumEn(executedInOutTokens.inputTotal)} (= input + cache read).`
                    : "Non-cached prompt tokens on executed calls."
                }
              />
              <Kpi
                label="Cache read"
                value={
                  executedInOutTokens.hasData
                    ? fmtNumEn(executedInOutTokens.cacheRead)
                    : "—"
                }
                title={
                  executedInOutTokens.hasData
                    ? `Prompt tokens served from cache. With input tokens, sums to API prompt total ${fmtNumEn(executedInOutTokens.inputTotal)}.`
                    : "Prompt cache-hit tokens on executed calls."
                }
              />
              <Kpi
                label="Output tokens"
                value={
                  executedInOutTokens.hasData
                    ? fmtNumEn(executedInOutTokens.output)
                    : "—"
                }
                title="Completion tokens on executed calls."
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Kpi
                label="Run outcome"
                value={runOutcomeKpi(summary)}
                title={runOutcomeTitle(summary)}
              />
              <Kpi
                label="Final score"
                value={runScoreKpi(summary)}
                title="From game-over screen (run_metrics run_end row, GAME_OVER snapshot, or run_end_snapshot.json)."
              />
              <Kpi
                label="Latency mean / median (s)"
                value={latencyMeanMedianSecondsKpi(summary)}
                title="Mean and median wall time per executed call."
              />
              <Kpi
                label="Levels reached"
                value={levelsReachedKpi(summary)}
                title="Highest act and floor in recorded progression."
              />
            </div>
          </section>
        ) : null}

        {payload?.ok && records.length > 0 ? (
          <>
            <div className="flex flex-col gap-3 rounded border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-panel)_45%,transparent)] p-3 sm:flex-row sm:items-center sm:justify-between">
              <span className="font-console text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                Metrics groups
              </span>
              <div
                role="tablist"
                aria-label="Metrics chart groups"
                onKeyDown={onMetricsTabListKeyDown}
                className="inline-flex flex-wrap gap-1 rounded border border-[var(--border-subtle)] bg-spire-inset p-0.5"
              >
                {METRICS_TAB_ORDER.map((id) => {
                  const { tabId, panelId, label } = METRICS_TAB_META[id];
                  return (
                    <button
                      key={id}
                      ref={(el) => {
                        metricsTabBtnRef.current[id] = el;
                      }}
                      id={tabId}
                      type="button"
                      role="tab"
                      aria-selected={metricsTab === id}
                      tabIndex={metricsTab === id ? 0 : -1}
                      aria-controls={
                        metricsTab === id ? panelId : undefined
                      }
                      onClick={() => setMetricsTab(id)}
                      className={
                        "rounded px-3 py-1.5 font-console text-xs font-semibold uppercase tracking-wide transition " +
                        (metricsTab === id
                          ? METRICS_TAB_ACTIVE_CLS
                          : METRICS_TAB_INACTIVE_CLS)
                      }
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>

            <TelemetryChartPanel
              title="Run health"
              caption={
                levelMode === "event"
                  ? "HP, gold, and floor vs event index."
                  : "Mean HP, mean gold, and floor from floor aggregates."
              }
            >
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {levelMode === "event" ? (
                  <>
                    <ResponsiveContainer width="100%" height={HERO_H}>
                      <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                        <CartesianGrid {...GRID} />
                        <XAxis dataKey="event_index" type="number" hide {...X_AXIS_EVENT_INDEX} />
                        <YAxis hide width={0} />
                        <Tooltip content={TooltipStateHp} isAnimationActive={false} />
                        <Line
                          type="monotone"
                          dataKey="line_current_hp"
                          stroke={chartColors.hp}
                          dot={false}
                          strokeWidth={1.5}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                    <ResponsiveContainer width="100%" height={HERO_H}>
                      <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                        <CartesianGrid {...GRID} />
                        <XAxis dataKey="event_index" type="number" hide {...X_AXIS_EVENT_INDEX} />
                        <YAxis hide width={0} />
                        <Tooltip content={TooltipStateGold} isAnimationActive={false} />
                        <Line
                          type="monotone"
                          dataKey="line_gold"
                          stroke={chartColors.gold}
                          dot={false}
                          strokeWidth={1.5}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                    <ResponsiveContainer width="100%" height={HERO_H}>
                      <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                        <CartesianGrid {...GRID} />
                        <XAxis dataKey="event_index" type="number" hide {...X_AXIS_EVENT_INDEX} />
                        <YAxis hide width={0} />
                        <Tooltip content={TooltipStateFloor} isAnimationActive={false} />
                        <Line
                          type="stepAfter"
                          dataKey="line_floor"
                          stroke={chartColors.floor}
                          dot={false}
                          strokeWidth={1.5}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </>
                ) : (
                  <>
                    <ResponsiveContainer width="100%" height={HERO_H}>
                      <LineChart data={floorStateChartRows} margin={CHART_MARGIN_TIGHT}>
                        <CartesianGrid {...GRID} />
                        <XAxis {...X_AXIS_FLOOR_LEVEL} hide />
                        <YAxis hide width={0} />
                        <Tooltip content={TooltipFloorStateHp} isAnimationActive={false} />
                        <Line
                          type="monotone"
                          dataKey="mean_current_hp"
                          stroke={chartColors.hp}
                          dot={false}
                          strokeWidth={1.5}
                          isAnimationActive={false}
                        />
                        <FloorActDividerLines xs={floorStateActDividers} />
                      </LineChart>
                    </ResponsiveContainer>
                    <ResponsiveContainer width="100%" height={HERO_H}>
                      <LineChart data={floorStateChartRows} margin={CHART_MARGIN_TIGHT}>
                        <CartesianGrid {...GRID} />
                        <XAxis {...X_AXIS_FLOOR_LEVEL} hide />
                        <YAxis hide width={0} />
                        <Tooltip content={TooltipFloorStateGold} isAnimationActive={false} />
                        <Line
                          type="monotone"
                          dataKey="mean_gold"
                          stroke={chartColors.gold}
                          dot={false}
                          strokeWidth={1.5}
                          isAnimationActive={false}
                        />
                        <FloorActDividerLines xs={floorStateActDividers} />
                      </LineChart>
                    </ResponsiveContainer>
                    <ResponsiveContainer width="100%" height={HERO_H}>
                      <LineChart data={floorStateChartRows} margin={CHART_MARGIN_TIGHT}>
                        <CartesianGrid {...GRID} />
                        <XAxis {...X_AXIS_FLOOR_LEVEL} hide />
                        <YAxis hide width={0} />
                        <Tooltip content={HeroFloorSparkTooltip} isAnimationActive={false} />
                        <Line
                          type="stepAfter"
                          dataKey="floor"
                          stroke={chartColors.floor}
                          dot={false}
                          strokeWidth={1.5}
                          isAnimationActive={false}
                        />
                        <FloorActDividerLines xs={floorStateActDividers} />
                      </LineChart>
                    </ResponsiveContainer>
                  </>
                )}
              </div>
            </TelemetryChartPanel>

            {metricsTab === "prog" ? (
            <section
              id={METRICS_TAB_META.prog.panelId}
              role="tabpanel"
              aria-labelledby={METRICS_TAB_META.prog.tabId}
            >
              <h2 className="mb-3 font-console text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                Progression
              </h2>
              {levelMode === "event" ? (
              <div className="grid gap-6 lg:grid-cols-2">
                <TelemetryChartPanel title="HP & Max HP">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateHp}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="line_current_hp"
                        name="current_hp"
                        stroke={chartColors.hp}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="line_max_hp"
                        name="max_hp"
                        stroke={chartColors.maxHp}
                        dot={false}
                        strokeWidth={1.5}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Gold">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateGold}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="line_gold"
                        name="gold"
                        stroke={chartColors.gold}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Floor">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateFloor}
                        isAnimationActive={false}
                      />
                      <Line
                        type="stepAfter"
                        dataKey="line_floor"
                        name="floor"
                        stroke={chartColors.floor}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Legal actions">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateLegal}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="line_legal_action_count"
                        name="legal_action_count"
                        stroke={chartColors.legal}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Enemy HP (sum)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateMonsters}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="monster_hp_sum"
                        name="enemy_hp_sum"
                        stroke={chartColors.enemy}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Hand size">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateHand}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="hand_size"
                        name="hand_size"
                        stroke={chartColors.hand}
                        dot={false}
                        strokeWidth={2}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Deck size">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateDeck}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="line_deck_size"
                        name="deck_size"
                        stroke={chartColors.deck}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Relics">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateRelic}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="line_relic_count"
                        name="relic_count"
                        stroke={chartColors.relic}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
              </div>
            ) : (
              <div className="grid gap-6 lg:grid-cols-2">
                <TelemetryChartPanel title="HP (mean)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={floorStateChartRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipFloorStateHp}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="mean_current_hp"
                        name="mean_current_hp"
                        stroke={chartColors.hp}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Max HP (mean)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={floorStateChartRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipFloorStateMaxHp}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="mean_max_hp"
                        name="mean_max_hp"
                        stroke={chartColors.maxHp}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Gold (mean)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={floorStateChartRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip content={TooltipFloorStateGold} isAnimationActive={false} />
                      <Line
                        type="monotone"
                        dataKey="mean_gold"
                        name="mean_gold"
                        stroke={chartColors.gold}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Legal Actions (mean)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={floorStateChartRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip content={TooltipFloorStateLegal} isAnimationActive={false} />
                      <Line
                        type="monotone"
                        dataKey="mean_legal"
                        name="mean_legal"
                        stroke={chartColors.legal}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Enemy HP (mean)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={floorStateChartRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip content={TooltipFloorStateMonsters} isAnimationActive={false} />
                      <Line
                        type="monotone"
                        dataKey="mean_monster_hp_sum"
                        name="mean_enemy_hp_sum"
                        stroke={chartColors.enemy}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Hand size (mean)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={floorStateChartRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip content={TooltipFloorStateHand} isAnimationActive={false} />
                      <Line
                        type="monotone"
                        dataKey="mean_hand_size"
                        name="mean_hand_size"
                        stroke={chartColors.hand}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Deck size (min)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={floorStateChartRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip content={TooltipFloorStateDeck} isAnimationActive={false} />
                      <Line
                        type="monotone"
                        dataKey="min_deck_size"
                        name="min_deck_size"
                        stroke={chartColors.deck}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Relics (min)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={floorStateChartRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip content={TooltipFloorStateRelic} isAnimationActive={false} />
                      <Line
                        type="monotone"
                        dataKey="min_relic_count"
                        name="min_relic_count"
                        stroke={chartColors.relic}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
              </div>
            )}
            </section>
            ) : null}

            {metricsTab === "ai" ? (
            <section
              id={METRICS_TAB_META.ai.panelId}
              role="tabpanel"
              aria-labelledby={METRICS_TAB_META.ai.tabId}
            >
              <h2 className="mb-4 font-console text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                AI decisions
              </h2>
              {levelMode === "event" ? (
              <div className="grid gap-6 lg:grid-cols-2">
                <TelemetryChartPanel title="Input (k/call)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={tokenSeries} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis
                        {...Y_AXIS_DEFAULT}
                        tickFormatter={yAxisTickKTokens}
                        width={52}
                        label={Y_LABEL_K_TOKENS}
                      />
                      <Tooltip
                        content={TooltipAiToken}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="input_k"
                        name="input_k"
                        stroke={chartColors.aiInput}
                        dot={false}
                        strokeWidth={2}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Output (k/call)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={tokenSeries} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis
                        {...Y_AXIS_DEFAULT}
                        tickFormatter={yAxisTickKTokens}
                        width={52}
                        label={Y_LABEL_K_TOKENS}
                      />
                      <Tooltip
                        content={TooltipAiToken}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="output_k"
                        name="output_k"
                        stroke={chartColors.aiOutput}
                        dot={false}
                        strokeWidth={2}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Estimated output tokens / s (clipped at 200)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={estimatedTpsSeries} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis
                        {...Y_AXIS_DEFAULT}
                        tickFormatter={yAxisTickSeconds}
                        width={48}
                        label={Y_LABEL_TPS}
                      />
                      <Tooltip
                        content={TooltipEstimatedTps}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="estimated_tps_clipped"
                        name="estimated_tps_clipped"
                        stroke={chartColors.throughput}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Latency (s)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={tokenSeries} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis
                        {...Y_AXIS_DEFAULT}
                        tickFormatter={yAxisTickSeconds}
                        width={48}
                        label={Y_LABEL_LATENCY_S}
                      />
                      <Tooltip
                        content={TooltipLatencySeconds}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="latency_s"
                        name="latency_s"
                        stroke={chartColors.latency}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
              </div>
              ) : (
              <div className="grid gap-6 lg:grid-cols-2">
                <TelemetryChartPanel title="Input total (k/floor)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={floorAiChart} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} tickFormatter={yAxisTickKTokens} width={52} label={Y_LABEL_K_TOKENS} />
                      <Tooltip content={TooltipFloorAiInput} isAnimationActive={false} />
                      <Line
                        type="monotone"
                        dataKey="sum_input_k"
                        name="sum_input_k"
                        stroke={chartColors.aiInput}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorAiActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Output total (k/floor)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={floorAiChart} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} tickFormatter={yAxisTickKTokens} width={52} label={Y_LABEL_K_TOKENS} />
                      <Tooltip content={TooltipFloorAiOutput} isAnimationActive={false} />
                      <Line
                        type="monotone"
                        dataKey="sum_output_k"
                        name="sum_output_k"
                        stroke={chartColors.aiOutput}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorAiActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Cumulative (k) by floor">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <AreaChart data={floorCumulative} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} tickFormatter={yAxisTickKTokens} width={56} label={Y_LABEL_K_TOKENS} />
                      <Tooltip content={TooltipFloorCumulative} isAnimationActive={false} />
                      <Area type="monotone" dataKey="cumulative_total_k" name="cumulative_k" stroke={chartColors.cumulativeStroke} fill={chartColors.cumulativeFill} strokeWidth={2} isAnimationActive={false} />
                      <FloorActDividerLines xs={floorAiActDividers} />
                    </AreaChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Latency mean (s/floor)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={floorAiChart} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} tickFormatter={yAxisTickSeconds} width={48} label={Y_LABEL_LATENCY_S} />
                      <Tooltip content={TooltipFloorLatency} isAnimationActive={false} />
                      <Line
                        type="monotone"
                        dataKey="mean_latency_s"
                        name="mean_latency_s"
                        stroke={chartColors.latency}
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorAiActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
              </div>
              )}
            </section>
            ) : null}

            {metricsTab === "dist" ? (
            <section
              id={METRICS_TAB_META.dist.panelId}
              role="tabpanel"
              aria-labelledby={METRICS_TAB_META.dist.tabId}
            >
              <h2 className="mb-3 font-console text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                Distributions
              </h2>
              <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
                <TelemetryChartPanel title="AI status">
                  {statusPie.length === 0 ? (
                    <p className="py-8 text-center text-xs text-[var(--text-label)]">
                      No AI decision rows.
                    </p>
                  ) : (
                    <ResponsiveContainer width="100%" height={CHART_H}>
                      <PieChart margin={CHART_MARGIN_PIE}>
                        <Pie
                          data={statusPie}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          outerRadius={72}
                          label={pieStatusLabel}
                          isAnimationActive={false}
                        >
                          {statusPie.map((_, i) => (
                            <Cell
                              key={i}
                              fill={PIE_COLORS[i % PIE_COLORS.length]}
                            />
                          ))}
                        </Pie>
                        <Tooltip
                          content={statusPieTooltipContent}
                          isAnimationActive={false}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  )}
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Input tokens (histogram)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <BarChart data={inputTokBins} margin={CHART_MARGIN_BAR}>
                      <CartesianGrid {...GRID} />
                      <XAxis
                        dataKey="label"
                        {...CHART_AXIS_TICK}
                        angle={-25}
                        textAnchor="end"
                        height={48}
                        interval={0}
                        tick={X_AXIS_BAR_TICK}
                      />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={HistogramTooltipInput}
                        isAnimationActive={false}
                      />
                      <Bar
                        dataKey="count"
                        fill={chartColors.histInput}
                        radius={[4, 4, 0, 0]}
                        isAnimationActive={false}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
                <TelemetryChartPanel title="Latency (histogram, ms)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <BarChart data={latencyBins} margin={CHART_MARGIN_BAR}>
                      <CartesianGrid {...GRID} />
                      <XAxis
                        dataKey="label"
                        {...CHART_AXIS_TICK}
                        angle={-25}
                        textAnchor="end"
                        height={48}
                        interval={0}
                        tick={X_AXIS_BAR_TICK}
                      />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={HistogramTooltipLatency}
                        isAnimationActive={false}
                      />
                      <Bar
                        dataKey="count"
                        fill={chartColors.histLatency}
                        radius={[4, 4, 0, 0]}
                        isAnimationActive={false}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </TelemetryChartPanel>
              </div>
            </section>
            ) : null}
          </>
        ) : null}
      </main>
    </div>
  );
}

function latencyMeanMedianSecondsKpi(summary: MetricsSummary): string {
  const m = summary.latency_ms_mean;
  const med = summary.latency_ms_median;
  const meanS =
    typeof m === "number" && Number.isFinite(m) ? m / 1000 : null;
  const medS =
    typeof med === "number" && Number.isFinite(med) ? med / 1000 : null;
  return `${fmtNumEn(meanS, 2)} / ${fmtNumEn(medS, 2)}`;
}

function levelsReachedKpi(summary: {
  max_floor_reached?: number | null;
  max_act_reached?: number | null;
}): string {
  const f = summary.max_floor_reached;
  const a = summary.max_act_reached;
  const fOk = typeof f === "number" && Number.isFinite(f);
  const aOk = typeof a === "number" && Number.isFinite(a);
  if (aOk && fOk) return `Act ${fmtIntEn(a)} · floor ${fmtIntEn(f)}`;
  if (fOk) return `Floor ${fmtIntEn(f)}`;
  if (aOk) return `Act ${fmtIntEn(a)}`;
  return "—";
}

function runOutcomeKpi(summary: MetricsSummary): string {
  const ro = summary.run_outcome;
  if (!ro) return "—";
  if (ro.victory === true) return "Victory";
  if (ro.victory === false) return "Defeated";
  return "Unknown";
}

function runScoreKpi(summary: MetricsSummary): string {
  const sc = summary.run_outcome?.score;
  if (typeof sc === "number" && Number.isFinite(sc)) return fmtNumEn(sc);
  return "—";
}

function runOutcomeTitle(summary: MetricsSummary): string | undefined {
  const parts: string[] = [];
  const ro = summary.run_outcome;
  if (ro?.screen_name) parts.push(`screen_name: ${ro.screen_name}`);
  if (ro?.recorded_at) parts.push(`recorded_at: ${ro.recorded_at}`);
  if (summary.has_run_end_snapshot) parts.push("run_end_snapshot.json on disk");
  return parts.length ? parts.join(" · ") : undefined;
}

function Kpi({
  label,
  value,
  title,
  className = "",
}: {
  label: string;
  value: string;
  title?: string;
  className?: string;
}) {
  return (
    <div
      className={
        "rounded border border-[color-mix(in_srgb,var(--border-strong)_78%,transparent)] bg-[color-mix(in_srgb,var(--bg-canvas)_52%,transparent)] px-3 py-2 " +
        className
      }
      title={title}
    >
      <div className="text-[13px] font-semibold uppercase tracking-wide text-[var(--text-label)]">
        {label}
      </div>
      <div className="font-telemetry mt-0.5 text-lg tabular-nums text-[var(--text-primary)]">
        {value}
      </div>
    </div>
  );
}

function StateTooltip({
  active,
  payload,
  keys,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: unknown }> | undefined;
  keys: StateTooltipKeys;
}) {
  if (!active || !payload?.[0]) return null;
  const row = payload[0].payload as StateRow | undefined;
  if (!row || typeof row.event_index !== "number") return null;
  const sid =
    row.state_id.length > 28
      ? `${row.state_id.slice(0, 28)}…`
      : row.state_id;
  return (
    <TelemetryTooltipFrame>
      <div className="font-mono text-[var(--text-primary)]">
        Event {fmtIntEn(row.event_index)}
      </div>
      <div className="text-[var(--text-muted)]">{row.timestamp}</div>
      <div className="truncate text-[var(--text-label)]" title={row.state_id}>
        State: {sid}
      </div>
      {keys.includes("hp") ? (
        <>
          <div>HP: {fmtNumEn(row.vm.current_hp)}</div>
          <div>Max HP: {fmtNumEn(row.vm.max_hp)}</div>
          <div>
            Floor {fmtNumEn(row.vm.floor)} · Act {fmtNumEn(row.vm.act)}
          </div>
        </>
      ) : null}
      {keys.includes("gold") ? (
        <>
          <div>Gold: {fmtNumEn(row.vm.gold)}</div>
          <div>Floor: {fmtNumEn(row.vm.floor)}</div>
        </>
      ) : null}
      {keys.includes("floor") ? (
        <>
          <div>Floor: {fmtNumEn(row.vm.floor)}</div>
          <div>Act: {fmtNumEn(row.vm.act)}</div>
        </>
      ) : null}
      {keys.includes("legal") ? (
        <>
          <div>Legal actions: {fmtNumEn(row.vm.legal_action_count)}</div>
          <div className="break-all font-mono text-[13px] text-[var(--text-label)]">
            Fingerprint: {row.vm.legal_commands_fingerprint ?? "—"}
          </div>
        </>
      ) : null}
      {keys.includes("monsters") ? (
        <>
          <div>Enemy HP sum: {fmtNumEn(row.monster_hp_sum)}</div>
          {row.monster_tooltip ? (
            <pre className="mt-1 whitespace-pre-wrap text-[13px] text-[var(--text-muted)]">
              {row.monster_tooltip}
            </pre>
          ) : (
            <div className="text-[var(--text-label)]">No enemies in snapshot</div>
          )}
        </>
      ) : null}
      {keys.includes("hand") ? (
        <>
          <div>
            Hand size:{" "}
            {typeof row.hand_size === "number"
              ? fmtIntEn(row.hand_size)
              : String(row.hand_size)}
          </div>
          <div className="text-[13px] text-[var(--text-muted)]">{row.hand_names_preview}</div>
        </>
      ) : null}
      {keys.includes("deck") ? (
        <div>Deck size: {fmtNumEn(row.line_deck_size)}</div>
      ) : null}
      {keys.includes("relic") ? (
        <div>Relics: {fmtNumEn(row.line_relic_count)}</div>
      ) : null}
    </TelemetryTooltipFrame>
  );
}

function AiTokenTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: Record<string, unknown> }> | undefined;
}) {
  if (!active || !payload?.[0]) return null;
  const p = payload[0].payload;
  if (!p) return null;
  const rawIn = Number(p.input_tokens) || 0;
  const rawOut = Number(p.output_tokens) || 0;
  const rawTot = Number(p.total_tokens) || 0;
  const rawCached = Number(p.cached_input_tokens) || 0;
  const rawUncached = Number(p.uncached_input_tokens) || 0;
  return (
    <TelemetryTooltipFrame>
      <div className="font-mono">
        Event {fmtFiniteIntLikeEn(p.event_index)}
      </div>
      <div>Decision: {String(p.decision_id)}</div>
      <div className="mt-1 text-[var(--text-muted)]">This call</div>
      <div className="tabular-nums text-[var(--text-primary)]">
        prompt in (total): {fmtTokensCommas(rawIn)} tokens
      </div>
      <div className="tabular-nums text-[var(--text-primary)]">
        non-cached: {fmtTokensCommas(rawUncached)} tokens
      </div>
      {rawCached > 0 ? (
        <div className="tabular-nums text-[var(--text-primary)]">
          cache hits: {fmtTokensCommas(rawCached)} tokens
        </div>
      ) : null}
      <div className="tabular-nums text-[var(--text-primary)]">
        output: {fmtTokensCommas(rawOut)} tokens
      </div>
      <div className="tabular-nums text-[var(--text-primary)]">
        total: {fmtTokensCommas(rawTot)} tokens
      </div>
      <div className="mt-1 border-t border-[var(--border-subtle)] pt-1 text-[var(--text-muted)]">Latency</div>
      <div className="tabular-nums text-[var(--text-primary)]">
        total (request→done): {fmtTokensCommas(Number(p.latency_ms) || 0)} ms
      </div>
      <div>status: {String(p.status)}</div>
      <div className="truncate" title={String(p.llm_model_used)}>
        model: {String(p.llm_model_used)}
      </div>
      <div className="truncate text-[13px] text-[var(--text-label)]" title={String(p.experiment_id)}>
        experiment: {String(p.experiment_id)}
      </div>
      <div className="text-[13px] text-[var(--text-label)]">
        strategist: {p.strategist_ran ? "yes" : "no"}
      </div>
      <div className="text-[13px] text-[var(--text-label)]">{String(p.timestamp)}</div>
    </TelemetryTooltipFrame>
  );
}

function LatencySecondsTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: Record<string, unknown> }> | undefined;
}) {
  if (!active || !payload?.[0]) return null;
  const p = payload[0].payload;
  if (!p) return null;
  const ms = Number(p.latency_ms) || 0;
  return (
    <TelemetryTooltipFrame>
      <div className="font-mono">
        Event {fmtFiniteIntLikeEn(p.event_index)}
      </div>
      <div>Decision: {String(p.decision_id)}</div>
      <div className="mt-1 text-[var(--text-muted)]">Latency</div>
      <div className="tabular-nums text-[var(--text-primary)]">
        total: {fmtTokensCommas(ms)} ms
      </div>
      <div>status: {String(p.status)}</div>
      <div className="truncate text-[13px] text-[var(--text-label)]" title={String(p.llm_model_used)}>
        {String(p.llm_model_used)}
      </div>
    </TelemetryTooltipFrame>
  );
}

function EstimatedTpsTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: Record<string, unknown> }> | undefined;
}) {
  if (!active || !payload?.[0]) return null;
  const p = payload[0].payload;
  if (!p) return null;
  const raw = p.estimated_tps_raw;
  const clipped = p.estimated_tps_clipped;
  const rawNum = typeof raw === "number" && Number.isFinite(raw) ? raw : null;
  const clippedNum =
    typeof clipped === "number" && Number.isFinite(clipped) ? clipped : null;
  const isClipped =
    rawNum !== null &&
    clippedNum !== null &&
    rawNum > ESTIMATED_TPS_CHART_CAP;
  const ms = Number(p.latency_ms) || 0;
  const out = Number(p.output_tokens) || 0;
  return (
    <TelemetryTooltipFrame>
      <div className="font-mono text-[var(--text-primary)]">
        Event {fmtFiniteIntLikeEn(p.event_index)}
      </div>
      <div className="mt-1 border-t border-[var(--border-subtle)] pt-1 text-[var(--text-muted)]">
        Ballpark throughput (output ÷ latency)
      </div>
      {rawNum === null ? (
        <div className="text-[var(--text-label)]">No estimate (missing latency or tokens).</div>
      ) : (
        <>
          <div className="tabular-nums text-[var(--text-primary)]">
            Raw: {fmtNumEn(rawNum, 1)} t/s
            {isClipped ? (
              <span className="text-spire-warning">
                {" "}
                — chart clipped at {fmtIntEn(ESTIMATED_TPS_CHART_CAP)} t/s
              </span>
            ) : null}
          </div>
          {clippedNum !== null && isClipped ? (
            <div className="tabular-nums text-[var(--text-muted)]">
              Plotted: {fmtNumEn(clippedNum, 1)} t/s
            </div>
          ) : null}
        </>
      )}
      <div className="mt-1 border-t border-[var(--border-subtle)] pt-1 text-[var(--text-muted)]">
        Basis
      </div>
      <div className="tabular-nums text-[var(--text-primary)]">
        Output: {fmtTokensCommas(out)} tok · Latency: {fmtTokensCommas(ms)} ms
      </div>
      <div className="mt-1 text-[13px] text-[var(--text-label)]">
        Full request time, not decode-only speed.
      </div>
      <div className="mt-1 truncate text-[13px] text-[var(--text-label)]" title={String(p.decision_id)}>
        {String(p.decision_id)}
      </div>
    </TelemetryTooltipFrame>
  );
}

function HeroFloorSparkTooltip(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow & { floor: number };
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums text-[var(--text-primary)]">
        Floor {fmtNumEn(Math.round(row.floor))}
      </div>
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorStateHp(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="text-[var(--text-muted)]">HP (mean)</div>
      <div className="tabular-nums">{fmtNumEn(row.mean_current_hp)}</div>
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorStateMaxHp(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="text-[var(--text-muted)]">Max HP (mean)</div>
      <div className="tabular-nums">{fmtNumEn(row.mean_max_hp)}</div>
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorStateGold(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">Gold (mean): {fmtNumEn(row.mean_gold)}</div>
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorStateLegal(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Legal Actions (mean): {fmtNumEn(row.mean_legal)}
      </div>
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorStateMonsters(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Enemy HP (mean): {fmtNumEn(row.mean_monster_hp_sum)}
      </div>
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorStateHand(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Hand (mean): {fmtNumEn(row.mean_hand_size, 2)}
      </div>
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorStateDeck(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Deck size (min): {fmtNumEn(row.min_deck_size)}
      </div>
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorStateRelic(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Relics (min): {fmtNumEn(row.min_relic_count)}
      </div>
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorAiInput(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorAiAggRow & Record<string, unknown>;
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div>Calls: {fmtIntEn(row.decision_count)}</div>
      <div className="tabular-nums text-[var(--text-primary)]">
        Prompt in (total): {fmtTokensCommas(row.sum_input_tokens)} (
        {fmtNumEn(Number(row.sum_input_k), 2)}k)
      </div>
      {row.sum_uncached_input_tokens !== row.sum_input_tokens ? (
        <div className="tabular-nums text-[var(--text-primary)]">
          Non-cached: {fmtTokensCommas(row.sum_uncached_input_tokens)}
        </div>
      ) : null}
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorAiOutput(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorAiAggRow & Record<string, unknown>;
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div>Calls: {fmtIntEn(row.decision_count)}</div>
      <div className="tabular-nums text-[var(--text-primary)]">
        Output: {fmtTokensCommas(row.sum_output_tokens)} tokens (
        {fmtNumEn(Number(row.sum_output_k), 2)}k)
      </div>
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorCumulative(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorAiAggRow & {
    cumulative_total: number;
    cumulative_total_k: number;
  };
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Cumulative: {fmtTokensCommas(row.cumulative_total)} tokens (
        {fmtNumEn(row.cumulative_total_k, 2)}k)
      </div>
      <div className="text-[var(--text-muted)]">
        Floor sum: {fmtTokensCommas(row.sum_total_tokens)}
      </div>
    </TelemetryTooltipFrame>
  );
}

function TooltipFloorLatency(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorAiAggRow & Record<string, unknown>;
  return (
    <TelemetryTooltipFrame>
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div>Calls: {fmtIntEn(row.decision_count)}</div>
      <div className="tabular-nums">
        Latency (mean): {fmtNumEn(Number(row.mean_latency_s), 3)} s (
        {fmtTokensCommas(row.mean_latency_ms ?? 0)} ms)
      </div>
    </TelemetryTooltipFrame>
  );
}

function TooltipStateHp(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_HP} />
  );
}

function TooltipStateGold(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_GOLD} />
  );
}

function TooltipStateFloor(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_FLOOR} />
  );
}

function TooltipStateLegal(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_LEGAL} />
  );
}

function TooltipStateMonsters(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_MONSTERS} />
  );
}

function TooltipStateHand(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_HAND} />
  );
}

function TooltipStateDeck(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_DECK} />
  );
}

function TooltipStateRelic(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_RELIC} />
  );
}

function TooltipAiToken(tp: TooltipLite) {
  return (
    <AiTokenTooltip
      active={tp.active}
      payload={
        tp.payload as ReadonlyArray<{
          payload?: Record<string, unknown>;
        }>
      }
    />
  );
}

function TooltipEstimatedTps(tp: TooltipLite) {
  return (
    <EstimatedTpsTooltip
      active={tp.active}
      payload={
        tp.payload as ReadonlyArray<{
          payload?: Record<string, unknown>;
        }>
      }
    />
  );
}

function TooltipLatencySeconds(tp: TooltipLite) {
  return (
    <LatencySecondsTooltip
      active={tp.active}
      payload={
        tp.payload as ReadonlyArray<{
          payload?: Record<string, unknown>;
        }>
      }
    />
  );
}
