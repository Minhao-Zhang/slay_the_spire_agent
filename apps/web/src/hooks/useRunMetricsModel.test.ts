import { describe, expect, it } from "vitest";

import type { JsonRecord, MetricsSummary } from "../lib/runMetricsDerive";
import type { MetricsResponse } from "./useRunMetricsData";
import { buildRunMetricsModel } from "./useRunMetricsModel";

function okPayload(
  records: JsonRecord[],
  summary: Partial<MetricsSummary>,
): MetricsResponse {
  const full: MetricsSummary = {
    state_row_count: 0,
    ai_row_count: 0,
    ai_executed_row_count: 0,
    status_counts: {},
    total_tokens_executed: 0,
    latency_ms_mean: null,
    latency_ms_median: null,
    event_index_min: null,
    event_index_max: null,
    ...summary,
  };
  return {
    ok: true,
    run: "test_run",
    records,
    summary: full,
  };
}

describe("buildRunMetricsModel", () => {
  it("returns empty derivations for empty records", () => {
    const m = buildRunMetricsModel([], "", null);
    expect(m.stateRows).toEqual([]);
    expect(m.statusPie).toEqual([]);
    expect(m.aiRowCount).toBe(0);
    expect(m.tokenSeries).toEqual([]);
  });

  it("ignores non-state rows for stateRows and still parses AI rows", () => {
    const records = [
      { type: "noise", event_index: 0 },
      {
        type: "state",
        event_index: 1,
        timestamp: "t1",
        state_id: "s1",
        vm_summary: { current_hp: 10, floor: 1, act: 1 },
      },
      {
        type: "ai_decision",
        event_index: 2,
        status: "executed",
        input_tokens: 50,
        output_tokens: 25,
        latency_ms: 100,
      },
    ];
    const m = buildRunMetricsModel(records, "run_dir", null);
    expect(m.stateRows).toHaveLength(1);
    expect(m.stateRows[0]?.line_current_hp).toBe(10);
    expect(m.aiRowCount).toBe(1);
    expect(m.tokenSeries).toHaveLength(1);
    expect(m.tokenSeries[0]?.event_index).toBe(2);
    expect(m.tokenSeries[0]?.input_tokens).toBe(50);
  });

  it("aggregates statusPie by AI row status", () => {
    const records = [
      { type: "ai_decision", event_index: 0, status: "executed" },
      { type: "ai_decision", event_index: 1, status: "executed" },
      { type: "ai_decision", event_index: 2, status: "skipped" },
    ];
    const m = buildRunMetricsModel(records, "", null);
    const byName = Object.fromEntries(
      m.statusPie.map((s) => [s.name, s.value]),
    );
    expect(byName.executed).toBe(2);
    expect(byName.skipped).toBe(1);
  });

  it("uses summary token fields when payload is ok", () => {
    const records: JsonRecord[] = [];
    const payload = okPayload(records, {
      input_tokens_executed: 1000,
      output_tokens_executed: 200,
      uncached_input_tokens_executed: 800,
      cached_input_tokens_executed: 200,
      ai_executed_row_count: 3,
    });
    const m = buildRunMetricsModel(records, "", payload);
    expect(m.executedInOutTokens.hasData).toBe(true);
    expect(m.executedInOutTokens.inputTotal).toBe(1000);
    expect(m.executedInOutTokens.output).toBe(200);
    expect(m.executedInOutTokens.uncached).toBe(800);
    expect(m.executedInOutTokens.cacheRead).toBe(200);
  });

  it("sorts tokenSeries by event_index", () => {
    const records = [
      {
        type: "ai_decision",
        event_index: 10,
        status: "executed",
        input_tokens: 1,
        output_tokens: 1,
        latency_ms: 1,
      },
      {
        type: "ai_decision",
        event_index: 2,
        status: "executed",
        input_tokens: 2,
        output_tokens: 2,
        latency_ms: 2,
      },
    ];
    const m = buildRunMetricsModel(records, "", null);
    expect(m.tokenSeries.map((r) => r.event_index)).toEqual([2, 10]);
  });

  it("formats playerRunLabelDisplay from summary when class is set", () => {
    const records: JsonRecord[] = [];
    const payload = okPayload(records, {
      player_class: "Defect",
      player_ascension: 5,
    });
    const m = buildRunMetricsModel(records, "", payload);
    expect(m.playerRunLabelDisplay).toMatch(/Defect.*A\s*5/);
  });

  it("clips estimated TPS to cap when latency and output are valid", () => {
    const records = [
      {
        type: "ai_decision",
        event_index: 0,
        status: "executed",
        input_tokens: 0,
        output_tokens: 10000,
        latency_ms: 1,
      },
    ];
    const m = buildRunMetricsModel(records, "", null);
    const row = m.estimatedTpsSeries[0];
    expect(row?.estimated_tps_raw).toBeGreaterThan(200);
    expect(row?.estimated_tps_clipped).toBe(200);
  });
});
