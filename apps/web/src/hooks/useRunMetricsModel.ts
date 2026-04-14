import { useMemo } from "react";

import type { MetricsResponse } from "./useRunMetricsData";
import { formatMonitorClassAscension } from "../lib/formatDisplayNumber";
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
  type JsonRecord,
  type MetricsSummary,
  type StateRow,
  uncachedInputTokensForAiRow,
} from "../lib/runMetricsDerive";

const ESTIMATED_TPS_CHART_CAP = 200;

function numOrZero(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  return 0;
}

export type RunMetricsModel = {
  stateRows: StateRow[];
  aiRows: AiRow[];
  aiExec: AiRow[];
  floorStateAggs: FloorStateAggRow[];
  floorStateChartRows: Array<FloorStateAggRow & { floor: number }>;
  floorStateActDividers: readonly number[];
  floorAiRowsNumeric: Array<FloorAiAggRow & { floor: number }>;
  floorAiActDividers: readonly number[];
  floorCumulative: ReturnType<typeof deriveFloorCumulativeTokens>;
  floorAiChart: Array<
    FloorAiAggRow & {
      floor: number;
      sum_input_k: number;
      sum_output_k: number;
      mean_latency_s: number;
    }
  >;
  tokenSeries: Array<{
    event_index: number;
    total_tokens: number;
    input_tokens: number;
    uncached_input_tokens: number;
    output_tokens: number;
    cached_input_tokens: number;
    input_k: number;
    output_k: number;
    total_k: number;
    latency_ms: number;
    latency_s: number;
    decision_id: string;
    status: string;
    llm_model_used: string;
    experiment_id: string;
    strategist_ran: boolean;
    timestamp: string;
  }>;
  estimatedTpsSeries: Array<
    RunMetricsModel["tokenSeries"][number] & {
      estimated_tps_raw: number | null;
      estimated_tps_clipped: number | null;
    }
  >;
  inputTokBins: BinnedNumeric[];
  latencyBins: BinnedNumeric[];
  statusPie: Array<{ name: string; value: number }>;
  aiRowCount: number;
  summary: MetricsSummary | undefined;
  executedInOutTokens: {
    inputTotal: number;
    uncached: number;
    cacheRead: number;
    output: number;
    hasData: boolean;
  };
  playerRunLabelDisplay: string;
};

export function buildRunMetricsModel(
  records: JsonRecord[],
  run: string,
  payload: MetricsResponse | null,
): RunMetricsModel {
  const summary = payload?.ok === true ? payload.summary : undefined;

  const stateRows = deriveStateRows(records);
  const aiRows = deriveAiRows(records);
  const aiExec = aiExecutedForSeries(aiRows);
  const floorStateAggs = deriveFloorStateAggRows(stateRows);
  const eventToFloorKey = buildEventIndexToFloorKey(stateRows);
  const floorAiAggs = deriveFloorAiAggRows(
    aiExec,
    eventToFloorKey,
    floorStateAggs,
  );
  const floorStateChartRows = floorStateAggs.filter(
    (r): r is FloorStateAggRow & { floor: number } =>
      typeof r.floor === "number" && Number.isFinite(r.floor),
  );
  const floorStateActDividers = actTransitionMidXs(floorStateChartRows);
  const floorAiRowsNumeric = floorAiAggs.filter(
    (r): r is FloorAiAggRow & { floor: number } =>
      typeof r.floor === "number" && Number.isFinite(r.floor),
  );
  const floorAiActDividers = actTransitionMidXs(floorAiRowsNumeric);
  const floorCumulative = deriveFloorCumulativeTokens(floorAiRowsNumeric);
  const floorAiChart = floorAiRowsNumeric.map((r) => ({
    ...r,
    sum_input_k: r.sum_input_tokens / 1000,
    sum_output_k: r.sum_output_tokens / 1000,
    mean_latency_s: (r.mean_latency_ms ?? 0) / 1000,
  }));

  const tokenSeries = aiExec
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
        experiment_id: String(r.experiment_id ?? "—"),
        strategist_ran: Boolean(r.strategist_ran),
        timestamp: String(r.timestamp ?? "—"),
      };
    })
    .sort((a, b) => a.event_index - b.event_index);

  const estimatedTpsSeries = tokenSeries.map((p) => {
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
    const clipped = raw === null ? null : Math.min(ESTIMATED_TPS_CHART_CAP, raw);
    return {
      ...p,
      estimated_tps_raw: raw,
      estimated_tps_clipped: clipped,
    };
  });

  const inputTokBins = binNumeric(
    aiExec
      .map((r) =>
        typeof r.input_tokens === "number" ? r.input_tokens : null,
      )
      .filter((x): x is number => x !== null && x >= 0),
    12,
  );

  const latencyBins = binNumeric(
    aiExec
      .map((r) =>
        typeof r.latency_ms === "number" ? r.latency_ms : null,
      )
      .filter((x): x is number => x !== null && x >= 0),
    12,
  );

  const counts: Record<string, number> = {};
  for (const r of aiRows) {
    const k = String(r.status ?? "unknown");
    counts[k] = (counts[k] ?? 0) + 1;
  }
  const statusPie = Object.entries(counts).map(([name, value]) => ({
    name,
    value,
  }));

  const sIn = summary?.input_tokens_executed;
  const sOut = summary?.output_tokens_executed;
  const sCached = summary?.cached_input_tokens_executed;
  const sUncached = summary?.uncached_input_tokens_executed;
  let executedInOutTokens: RunMetricsModel["executedInOutTokens"];
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
    executedInOutTokens = {
      inputTotal: sIn,
      uncached,
      cacheRead,
      output: sOut,
      hasData,
    };
  } else {
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
    executedInOutTokens = {
      inputTotal,
      uncached,
      cacheRead,
      output,
      hasData: aiExec.length > 0,
    };
  }

  const clsRaw = summary?.player_class;
  const cls =
    typeof clsRaw === "string" ? clsRaw.trim() : String(clsRaw ?? "").trim();
  let playerRunLabelDisplay: string;
  if (cls && cls !== "Main Menu" && cls !== "?" && cls !== "-") {
    const asc = summary?.player_ascension;
    const a = typeof asc === "number" && Number.isFinite(asc) ? asc : 0;
    playerRunLabelDisplay = formatMonitorClassAscension(cls, a);
  } else {
    const fromRows = deriveLatestPlayerRunLabel(stateRows);
    if (fromRows) playerRunLabelDisplay = fromRows;
    else {
      const parsed = run.trim() ? parsePlayerClassAscFromRunName(run) : null;
      playerRunLabelDisplay = parsed
        ? formatMonitorClassAscension(parsed.classId, parsed.ascension)
        : "—";
    }
  }

  return {
    stateRows,
    aiRows,
    aiExec,
    floorStateAggs,
    floorStateChartRows,
    floorStateActDividers,
    floorAiRowsNumeric,
    floorAiActDividers,
    floorCumulative,
    floorAiChart,
    tokenSeries,
    estimatedTpsSeries,
    inputTokBins,
    latencyBins,
    statusPie,
    aiRowCount: aiRows.length,
    summary,
    executedInOutTokens,
    playerRunLabelDisplay,
  };
}

export function useRunMetricsModel(
  records: JsonRecord[],
  run: string,
  payload: MetricsResponse | null,
): RunMetricsModel {
  return useMemo(
    () => buildRunMetricsModel(records, run, payload),
    [records, run, payload],
  );
}
