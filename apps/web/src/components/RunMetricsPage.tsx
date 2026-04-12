import { useCallback, useMemo, useState, type ReactNode } from "react";
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
import {
  fmtFiniteIntLikeEn,
  fmtIntEn,
  fmtNumEn,
  formatMonitorClassAscension,
  tickFmtIntEn,
  tickFmtNumberEn,
} from "../lib/formatDisplayNumber";
import {
  actTransitionMidXs,
  aiExecutedForSeries,
  binNumeric,
  buildEventIndexToFloorKey,
  deriveAiRows,
  deriveFloorAiAggRows,
  deriveFloorCumulativeTokens,
  deriveFloorStateAggRows,
  deriveLatestPlayerRunLabel,
  deriveStateRows,
  parsePlayerClassAscFromRunName,
  type AiRow,
  type BinnedNumeric,
  type FloorAiAggRow,
  type FloorStateAggRow,
  type MetricsSummary,
  type StateRow,
  uncachedInputTokensForAiRow,
} from "../lib/runMetricsDerive";
import { RunMetricsRunBar } from "./RunMetricsRunBar";

const CHART_H = 220;
const SLATE_AXIS = { stroke: "#64748b", fontSize: 11 };
const GRID = { stroke: "#334155", strokeDasharray: "3 3" };

const X_AXIS_EVENT_INDEX = {
  ...SLATE_AXIS,
  tickFormatter: tickFmtIntEn,
};
const Y_AXIS_DEFAULT = { ...SLATE_AXIS, tickFormatter: tickFmtNumberEn };

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

const PIE_COLORS = [
  "#38bdf8",
  "#a78bfa",
  "#f472b6",
  "#fbbf24",
  "#34d399",
  "#f87171",
  "#94a3b8",
];

const CHART_MARGIN_TIGHT = { top: 8, right: 8, left: 0, bottom: 0 };
const CHART_MARGIN_LEFT4 = { top: 8, right: 8, left: 4, bottom: 0 };
const CHART_MARGIN_PIE = { top: 8, right: 8, bottom: 8, left: 8 };
const CHART_MARGIN_BAR = { top: 8, right: 8, left: 0, bottom: 24 };

const Y_LABEL_K_TOKENS = {
  value: "k tokens",
  angle: -90,
  position: "insideLeft" as const,
  fill: "#64748b",
  fontSize: 10,
  dx: -4,
};

const Y_LABEL_LATENCY_S = {
  value: "s",
  angle: -90,
  position: "insideLeft" as const,
  fill: "#64748b",
  fontSize: 10,
  dx: -4,
};

const Y_LABEL_TPS = {
  value: "tokens/s",
  angle: -90,
  position: "insideLeft" as const,
  fill: "#64748b",
  fontSize: 10,
  dx: -4,
};

/** Y-axis max for estimated throughput chart (values above are clipped for display). */
const ESTIMATED_TPS_CHART_CAP = 200;

const X_AXIS_BAR_TICK = { fontSize: 9 };

const X_AXIS_FLOOR_LEVEL = {
  ...SLATE_AXIS,
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
          stroke="#64748b"
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
      <div className="font-mono text-slate-200">
        {hasFloor
          ? `Level ${fmtIntEn(Math.round(props.floor!))}`
          : props.floor_label ?? "Unknown"}
      </div>
      {props.act != null && Number.isFinite(props.act) && (
        <div className="text-[10px] text-slate-500">
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
    <div className="rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="tabular-nums">count: {fmtIntEn(p.count)}</div>
      <div>
        range: {fmtNumEn(p.lo, 2)}–{fmtNumEn(p.hi, 2)} tokens
      </div>
    </div>
  );
}

function HistogramTooltipLatency(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const p = tp.payload[0].payload as BinnedNumeric;
  return (
    <div className="rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="tabular-nums">count: {fmtIntEn(p.count)}</div>
      <div>
        range: {fmtNumEn(p.lo, 1)}–{fmtNumEn(p.hi, 1)} ms
      </div>
    </div>
  );
}

export function RunMetricsPage() {
  const [levelMode, setLevelMode] = useState<"event" | "floor">("event");
  const {
    runs,
    run,
    setRun,
    loading,
    payload,
    frameCount,
    records,
    parseErrors,
  } = useRunMetricsData();

  const stateRows = useMemo(() => deriveStateRows(records), [records]);
  const aiRows = useMemo(() => deriveAiRows(records), [records]);
  const aiExec = useMemo(() => aiExecutedForSeries(aiRows), [aiRows]);
  const floorStateAggs = useMemo(
    () => deriveFloorStateAggRows(stateRows),
    [stateRows],
  );
  const eventToFloorKey = useMemo(
    () => buildEventIndexToFloorKey(stateRows),
    [stateRows],
  );
  const floorAiAggs = useMemo(
    () => deriveFloorAiAggRows(aiExec, eventToFloorKey, floorStateAggs),
    [aiExec, eventToFloorKey, floorStateAggs],
  );
  const floorStateChartRows = useMemo(
    () =>
      floorStateAggs.filter(
        (r): r is FloorStateAggRow & { floor: number } =>
          typeof r.floor === "number" && Number.isFinite(r.floor),
      ),
    [floorStateAggs],
  );
  const floorStateActDividers = useMemo(
    () => actTransitionMidXs(floorStateChartRows),
    [floorStateChartRows],
  );
  const floorAiRowsNumeric = useMemo(
    () =>
      floorAiAggs.filter(
        (r): r is FloorAiAggRow & { floor: number } =>
          typeof r.floor === "number" && Number.isFinite(r.floor),
      ),
    [floorAiAggs],
  );
  const floorAiActDividers = useMemo(
    () => actTransitionMidXs(floorAiRowsNumeric),
    [floorAiRowsNumeric],
  );
  const floorCumulative = useMemo(
    () => deriveFloorCumulativeTokens(floorAiRowsNumeric),
    [floorAiRowsNumeric],
  );
  const floorAiChart = useMemo(
    () =>
      floorAiRowsNumeric.map((r) => ({
        ...r,
        sum_input_k: r.sum_input_tokens / 1000,
        sum_output_k: r.sum_output_tokens / 1000,
        mean_latency_s: (r.mean_latency_ms ?? 0) / 1000,
      })),
    [floorAiRowsNumeric],
  );

  const tokenSeries = useMemo(
    () =>
      aiExec
        .filter((r) => typeof r.event_index === "number")
        .map((r) => {
          const row = r as AiRow;
          const input = numOrZero(r.input_tokens);
          const output = numOrZero(r.output_tokens);
          const total = numOrZero(r.total_tokens);
          const cachedIn =
            typeof r.cached_input_tokens === "number" &&
            Number.isFinite(r.cached_input_tokens)
              ? r.cached_input_tokens
              : 0;
          const uncachedIn = uncachedInputTokensForAiRow(row);
          const latMs = numOrZero(r.latency_ms);
          return {
            event_index: r.event_index as number,
            total_tokens: total,
            input_tokens: input,
            uncached_input_tokens: uncachedIn,
            output_tokens: output,
            cached_input_tokens: cachedIn,
            input_k: input / 1000,
            output_k: output / 1000,
            total_k: total / 1000,
            latency_ms: latMs,
            latency_s: latMs / 1000,
            decision_id: String(r.decision_id ?? "—"),
            status: String(r.status ?? "—"),
            llm_model_used: String(r.llm_model_used ?? "—"),
            llm_turn_model_key: String(r.llm_turn_model_key ?? "—"),
            timestamp: String(r.timestamp ?? "—"),
          };
        })
        .sort((a, b) => a.event_index - b.event_index),
    [aiExec],
  );

  /**
   * Ballpark effective output throughput: output_tokens / request latency (not raw decode speed).
   * Chart uses `estimated_tps_clipped` capped at ESTIMATED_TPS_CHART_CAP for display.
   */
  const estimatedTpsSeries = useMemo(
    () =>
      tokenSeries.map((p) => {
        const lat = p.latency_ms;
        const out = p.output_tokens;
        const raw =
          typeof lat === "number" &&
          Number.isFinite(lat) &&
          lat > 0 &&
          typeof out === "number" &&
          Number.isFinite(out) &&
          out >= 0
            ? (out * 1000) / lat
            : null;
        const clipped =
          raw === null ? null : Math.min(ESTIMATED_TPS_CHART_CAP, raw);
        return {
          ...p,
          estimated_tps_raw: raw,
          estimated_tps_clipped: clipped,
        };
      }),
    [tokenSeries],
  );

  const inputTokBins = useMemo(() => {
    const vals = aiExec
      .map((r) =>
        typeof r.input_tokens === "number" ? r.input_tokens : null,
      )
      .filter((x): x is number => x !== null && x >= 0);
    return binNumeric(vals, 12);
  }, [aiExec]);

  const latencyBins = useMemo(() => {
    const vals = aiExec
      .map((r) =>
        typeof r.latency_ms === "number" ? r.latency_ms : null,
      )
      .filter((x): x is number => x !== null && x >= 0);
    return binNumeric(vals, 12);
  }, [aiExec]);

  const statusPie = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of aiRows) {
      const k = String(r.status ?? "unknown");
      counts[k] = (counts[k] ?? 0) + 1;
    }
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [aiRows]);

  const aiRowCount = aiRows.length;
  const statusPieTooltipContent = useCallback(
    (tp: TooltipLite) => {
      if (!tp.active || !tp.payload?.[0]) return null;
      const d = tp.payload[0].payload as { name: string; value: number };
      const pct =
        aiRowCount > 0
          ? fmtNumEn((d.value / aiRowCount) * 100, 1)
          : fmtNumEn(0, 1);
      return (
        <div className="rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
          <div className="font-medium text-slate-200">{d.name}</div>
          <div className="tabular-nums">
            count: {fmtIntEn(d.value)} ({pct}%)
          </div>
        </div>
      );
    },
    [aiRowCount],
  );

  const summary = payload?.ok === true ? payload.summary : undefined;

  const executedInOutTokens = useMemo(() => {
    const sIn = summary?.input_tokens_executed;
    const sOut = summary?.output_tokens_executed;
    const sCached = summary?.cached_input_tokens_executed;
    const sUncached = summary?.uncached_input_tokens_executed;
    if (typeof sIn === "number" && typeof sOut === "number") {
      let cacheRead = typeof sCached === "number" ? sCached : 0;
      if (typeof sCached !== "number") {
        for (const r of aiExec) {
          const tc = r.cached_input_tokens;
          if (typeof tc === "number" && Number.isFinite(tc)) cacheRead += tc;
        }
      }
      let uncached: number;
      if (typeof sUncached === "number" && Number.isFinite(sUncached)) {
        uncached = sUncached;
      } else {
        uncached = 0;
        for (const r of aiExec) {
          uncached += uncachedInputTokensForAiRow(r as AiRow);
        }
      }
      const hasData =
        (summary?.ai_executed_row_count ?? 0) > 0 ||
        sIn > 0 ||
        sOut > 0 ||
        aiExec.length > 0;
      return {
        inputTotal: sIn,
        uncached,
        cacheRead,
        output: sOut,
        hasData,
      };
    }
    let inputTotal = 0;
    let output = 0;
    let cacheRead = 0;
    let uncached = 0;
    for (const r of aiExec) {
      const ti = r.input_tokens;
      const to = r.output_tokens;
      const tc = r.cached_input_tokens;
      if (typeof ti === "number" && Number.isFinite(ti)) inputTotal += ti;
      if (typeof to === "number" && Number.isFinite(to)) output += to;
      if (typeof tc === "number" && Number.isFinite(tc)) cacheRead += tc;
      uncached += uncachedInputTokensForAiRow(r as AiRow);
    }
    return {
      inputTotal,
      uncached,
      cacheRead,
      output,
      hasData: aiExec.length > 0,
    };
  }, [summary, aiExec]);

  const playerRunLabelDisplay = useMemo(() => {
    const clsRaw = summary?.player_class;
    const cls =
      typeof clsRaw === "string" ? clsRaw.trim() : String(clsRaw ?? "").trim();
    if (
      cls &&
      cls !== "Main Menu" &&
      cls !== "?" &&
      cls !== "-"
    ) {
      const asc = summary?.player_ascension;
      const a =
        typeof asc === "number" && Number.isFinite(asc) ? asc : 0;
      return formatMonitorClassAscension(cls, a);
    }
    const fromRows = deriveLatestPlayerRunLabel(stateRows);
    if (fromRows) return fromRows;
    const parsed = run.trim()
      ? parsePlayerClassAscFromRunName(run)
      : null;
    if (parsed)
      return formatMonitorClassAscension(parsed.classId, parsed.ascension);
    return "—";
  }, [summary?.player_class, summary?.player_ascension, stateRows, run]);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-[#0a0d11] to-[#06080a] text-sm text-slate-300">
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
      />

      <main className="space-y-6 px-4 py-5">
        {parseErrors.length > 0 ? (
          <div
            className="rounded border border-amber-800/60 bg-amber-950/40 px-3 py-2 text-xs text-amber-100"
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
          <div className="flex flex-wrap items-center gap-3 rounded border border-slate-700/80 bg-slate-950/40 px-3 py-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Resolution
            </span>
            <div className="inline-flex rounded border border-slate-600 bg-slate-900 p-0.5">
              <button
                type="button"
                onClick={() => setLevelMode("event")}
                className={
                  "rounded px-3 py-1 font-console text-xs font-semibold uppercase tracking-wide transition " +
                  (levelMode === "event"
                    ? "bg-slate-700 text-slate-100"
                    : "text-slate-500 hover:text-slate-300")
                }
              >
                Event level
              </button>
              <button
                type="button"
                onClick={() => setLevelMode("floor")}
                className={
                  "rounded px-3 py-1 font-console text-xs font-semibold uppercase tracking-wide transition " +
                  (levelMode === "floor"
                    ? "bg-slate-700 text-slate-100"
                    : "text-slate-500 hover:text-slate-300")
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
            <section>
              <h2 className="mb-3 font-console text-xs font-semibold uppercase tracking-wide text-slate-400">
                Progression
              </h2>
              {levelMode === "event" ? (
              <div className="grid gap-6 lg:grid-cols-2">
                <ChartCard title="HP & Max HP">
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
                        stroke="#f87171"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="line_max_hp"
                        name="max_hp"
                        stroke="#94a3b8"
                        dot={false}
                        strokeWidth={1.5}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Gold">
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
                        stroke="#fbbf24"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Floor">
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
                        stroke="#38bdf8"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Legal actions">
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
                        stroke="#a78bfa"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Enemy HP (sum)">
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
                        stroke="#f472b6"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Hand size">
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
                        stroke="#34d399"
                        dot={false}
                        strokeWidth={2}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Deck size">
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
                        stroke="#38bdf8"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Relics">
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
                        stroke="#c084fc"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
            ) : (
              <div className="grid gap-6 lg:grid-cols-2">
                <ChartCard title="HP (mean)">
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
                        stroke="#f87171"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Max HP (mean)">
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
                        stroke="#94a3b8"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Gold (mean)">
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
                        stroke="#fbbf24"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Legal Actions (mean)">
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
                        stroke="#a78bfa"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Enemy HP (mean)">
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
                        stroke="#f472b6"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Hand size (mean)">
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
                        stroke="#34d399"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Deck size (min)">
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
                        stroke="#38bdf8"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Relics (min)">
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
                        stroke="#c084fc"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorStateActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
            )}
            </section>

            <section>
              <h2 className="mb-4 font-console text-xs font-semibold uppercase tracking-wide text-slate-400">
                AI decisions
              </h2>
              {levelMode === "event" ? (
              <div className="grid gap-6 lg:grid-cols-2">
                <ChartCard title="Input (k/call)">
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
                        stroke="#818cf8"
                        dot={false}
                        strokeWidth={2}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Output (k/call)">
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
                        stroke="#c084fc"
                        dot={false}
                        strokeWidth={2}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Estimated output tokens / s (clipped at 200)">
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
                        stroke="#22d3ee"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Latency (s)">
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
                        stroke="#fbbf24"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
              ) : (
              <div className="grid gap-6 lg:grid-cols-2">
                <ChartCard title="Input total (k/floor)">
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
                        stroke="#818cf8"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorAiActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Output total (k/floor)">
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
                        stroke="#c084fc"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorAiActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Cumulative (k) by floor">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <AreaChart data={floorCumulative} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis {...X_AXIS_FLOOR_LEVEL} />
                      <YAxis {...Y_AXIS_DEFAULT} tickFormatter={yAxisTickKTokens} width={56} label={Y_LABEL_K_TOKENS} />
                      <Tooltip content={TooltipFloorCumulative} isAnimationActive={false} />
                      <Area type="monotone" dataKey="cumulative_total_k" name="cumulative_k" stroke="#22d3ee" fill="#22d3ee33" strokeWidth={2} isAnimationActive={false} />
                      <FloorActDividerLines xs={floorAiActDividers} />
                    </AreaChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Latency mean (s/floor)">
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
                        stroke="#fbbf24"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <FloorActDividerLines xs={floorAiActDividers} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
              )}
            </section>

            <section>
              <h2 className="mb-3 font-console text-xs font-semibold uppercase tracking-wide text-slate-400">
                Distributions
              </h2>
              <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
                <ChartCard title="AI status">
                  {statusPie.length === 0 ? (
                    <p className="py-8 text-center text-xs text-slate-500">
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
                </ChartCard>
                <ChartCard title="Input tokens (histogram)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <BarChart data={inputTokBins} margin={CHART_MARGIN_BAR}>
                      <CartesianGrid {...GRID} />
                      <XAxis
                        dataKey="label"
                        {...SLATE_AXIS}
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
                        fill="#818cf8"
                        radius={[4, 4, 0, 0]}
                        isAnimationActive={false}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Latency (histogram, ms)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <BarChart data={latencyBins} margin={CHART_MARGIN_BAR}>
                      <CartesianGrid {...GRID} />
                      <XAxis
                        dataKey="label"
                        {...SLATE_AXIS}
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
                        fill="#f472b6"
                        radius={[4, 4, 0, 0]}
                        isAnimationActive={false}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}

function numOrZero(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  return 0;
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
        "rounded border border-slate-700/80 bg-slate-950/50 px-3 py-2 " +
        className
      }
      title={title}
    >
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="font-telemetry mt-0.5 text-lg tabular-nums text-slate-100">
        {value}
      </div>
    </div>
  );
}

function ChartCard({
  title,
  caption,
  children,
  className = "",
}: {
  title: string;
  caption?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded border border-slate-700/80 bg-slate-950/40 p-3 ${className}`}>
      <h3
        className={`font-console text-[11px] font-semibold uppercase tracking-wide text-slate-400 ${caption ? "mb-1" : "mb-2"}`}
      >
        {title}
      </h3>
      {caption ? (
        <p className="mb-2 text-[10px] font-normal normal-case leading-snug text-slate-500">
          {caption}
        </p>
      ) : null}
      {children}
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
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="font-mono text-slate-200">
        Event {fmtIntEn(row.event_index)}
      </div>
      <div className="text-slate-400">{row.timestamp}</div>
      <div className="truncate text-slate-500" title={row.state_id}>
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
          <div className="break-all font-mono text-[10px] text-slate-500">
            Fingerprint: {row.vm.legal_commands_fingerprint ?? "—"}
          </div>
        </>
      ) : null}
      {keys.includes("monsters") ? (
        <>
          <div>Enemy HP sum: {fmtNumEn(row.monster_hp_sum)}</div>
          {row.monster_tooltip ? (
            <pre className="mt-1 whitespace-pre-wrap text-[10px] text-slate-400">
              {row.monster_tooltip}
            </pre>
          ) : (
            <div className="text-slate-500">No enemies in snapshot</div>
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
          <div className="text-[10px] text-slate-400">{row.hand_names_preview}</div>
        </>
      ) : null}
      {keys.includes("deck") ? (
        <div>Deck size: {fmtNumEn(row.line_deck_size)}</div>
      ) : null}
      {keys.includes("relic") ? (
        <div>Relics: {fmtNumEn(row.line_relic_count)}</div>
      ) : null}
    </div>
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
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="font-mono">
        Event {fmtFiniteIntLikeEn(p.event_index)}
      </div>
      <div>Decision: {String(p.decision_id)}</div>
      <div className="mt-1 text-slate-400">This call</div>
      <div className="tabular-nums text-slate-100">
        prompt in (total): {fmtTokensCommas(rawIn)} tokens
      </div>
      <div className="tabular-nums text-slate-100">
        non-cached: {fmtTokensCommas(rawUncached)} tokens
      </div>
      {rawCached > 0 ? (
        <div className="tabular-nums text-slate-100">
          cache hits: {fmtTokensCommas(rawCached)} tokens
        </div>
      ) : null}
      <div className="tabular-nums text-slate-100">
        output: {fmtTokensCommas(rawOut)} tokens
      </div>
      <div className="tabular-nums text-slate-100">
        total: {fmtTokensCommas(rawTot)} tokens
      </div>
      <div className="mt-1 border-t border-slate-700 pt-1 text-slate-400">Latency</div>
      <div className="tabular-nums text-slate-100">
        total (request→done): {fmtTokensCommas(Number(p.latency_ms) || 0)} ms
      </div>
      <div>status: {String(p.status)}</div>
      <div className="truncate" title={String(p.llm_model_used)}>
        model: {String(p.llm_model_used)}
      </div>
      <div className="truncate text-[10px] text-slate-500" title={String(p.llm_turn_model_key)}>
        key: {String(p.llm_turn_model_key)}
      </div>
      <div className="text-[10px] text-slate-500">{String(p.timestamp)}</div>
    </div>
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
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="font-mono">
        Event {fmtFiniteIntLikeEn(p.event_index)}
      </div>
      <div>Decision: {String(p.decision_id)}</div>
      <div className="mt-1 text-slate-400">Latency</div>
      <div className="tabular-nums text-slate-100">
        total: {fmtTokensCommas(ms)} ms
      </div>
      <div>status: {String(p.status)}</div>
      <div className="truncate text-[10px] text-slate-500" title={String(p.llm_model_used)}>
        {String(p.llm_model_used)}
      </div>
    </div>
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
    <div className="max-w-xs rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="font-mono text-slate-200">
        Event {fmtFiniteIntLikeEn(p.event_index)}
      </div>
      <div className="mt-1 border-t border-slate-700 pt-1 text-slate-400">
        Ballpark throughput (output ÷ latency)
      </div>
      {rawNum === null ? (
        <div className="text-slate-500">No estimate (missing latency or tokens).</div>
      ) : (
        <>
          <div className="tabular-nums text-slate-100">
            Raw: {fmtNumEn(rawNum, 1)} t/s
            {isClipped ? (
              <span className="text-amber-400/90">
                {" "}
                — chart clipped at {fmtIntEn(ESTIMATED_TPS_CHART_CAP)} t/s
              </span>
            ) : null}
          </div>
          {clippedNum !== null && isClipped ? (
            <div className="tabular-nums text-slate-400">
              Plotted: {fmtNumEn(clippedNum, 1)} t/s
            </div>
          ) : null}
        </>
      )}
      <div className="mt-1 border-t border-slate-700 pt-1 text-slate-400">
        Basis
      </div>
      <div className="tabular-nums text-slate-100">
        Output: {fmtTokensCommas(out)} tok · Latency: {fmtTokensCommas(ms)} ms
      </div>
      <div className="mt-1 text-[10px] text-slate-500">
        Full request time, not decode-only speed.
      </div>
      <div className="mt-1 truncate text-[10px] text-slate-500" title={String(p.decision_id)}>
        {String(p.decision_id)}
      </div>
    </div>
  );
}

function TooltipFloorStateHp(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="text-slate-400">HP (mean)</div>
      <div className="tabular-nums">{fmtNumEn(row.mean_current_hp)}</div>
    </div>
  );
}

function TooltipFloorStateMaxHp(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="text-slate-400">Max HP (mean)</div>
      <div className="tabular-nums">{fmtNumEn(row.mean_max_hp)}</div>
    </div>
  );
}

function TooltipFloorStateGold(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">Gold (mean): {fmtNumEn(row.mean_gold)}</div>
    </div>
  );
}

function TooltipFloorStateLegal(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Legal Actions (mean): {fmtNumEn(row.mean_legal)}
      </div>
    </div>
  );
}

function TooltipFloorStateMonsters(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Enemy HP (mean): {fmtNumEn(row.mean_monster_hp_sum)}
      </div>
    </div>
  );
}

function TooltipFloorStateHand(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Hand (mean): {fmtNumEn(row.mean_hand_size, 2)}
      </div>
    </div>
  );
}

function TooltipFloorStateDeck(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Deck size (min): {fmtNumEn(row.min_deck_size)}
      </div>
    </div>
  );
}

function TooltipFloorStateRelic(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorStateAggRow;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Relics (min): {fmtNumEn(row.min_relic_count)}
      </div>
    </div>
  );
}

function TooltipFloorAiInput(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorAiAggRow & Record<string, unknown>;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div>Calls: {fmtIntEn(row.decision_count)}</div>
      <div className="tabular-nums text-slate-100">
        Prompt in (total): {fmtTokensCommas(row.sum_input_tokens)} (
        {fmtNumEn(Number(row.sum_input_k), 2)}k)
      </div>
      {row.sum_uncached_input_tokens !== row.sum_input_tokens ? (
        <div className="tabular-nums text-slate-100">
          Non-cached: {fmtTokensCommas(row.sum_uncached_input_tokens)}
        </div>
      ) : null}
    </div>
  );
}

function TooltipFloorAiOutput(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorAiAggRow & Record<string, unknown>;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div>Calls: {fmtIntEn(row.decision_count)}</div>
      <div className="tabular-nums text-slate-100">
        Output: {fmtTokensCommas(row.sum_output_tokens)} tokens (
        {fmtNumEn(Number(row.sum_output_k), 2)}k)
      </div>
    </div>
  );
}

function TooltipFloorCumulative(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorAiAggRow & {
    cumulative_total: number;
    cumulative_total_k: number;
  };
  return (
    <div className="max-w-xs rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <FloorLevelTooltipHeader
        floor={row.floor}
        act={row.act}
        floor_label={row.floor_label}
      />
      <div className="tabular-nums">
        Cumulative: {fmtTokensCommas(row.cumulative_total)} tokens (
        {fmtNumEn(row.cumulative_total_k, 2)}k)
      </div>
      <div className="text-slate-400">
        Floor sum: {fmtTokensCommas(row.sum_total_tokens)}
      </div>
    </div>
  );
}

function TooltipFloorLatency(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const row = tp.payload[0].payload as FloorAiAggRow & Record<string, unknown>;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
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
    </div>
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
