import { useCallback, useEffect, useState } from "react";

import type {
  HistoryCheckpointDTO,
  HistoryCheckpointDetailResponse,
  HistoryThreadSummaryDTO,
} from "../types/viewModel";

export function useHistoryExplorer(initialThreadId: string) {
  const [threads, setThreads] = useState<HistoryThreadSummaryDTO[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState(initialThreadId);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [checkpoints, setCheckpoints] = useState<HistoryCheckpointDTO[]>([]);
  const [detail, setDetail] = useState<HistoryCheckpointDetailResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const refreshThreads = useCallback(async (mergeCheckpoint = true) => {
    const q = mergeCheckpoint
      ? "?merge_checkpoint_threads=true"
      : "";
    const r = await fetch(`/api/history/threads${q}`);
    if (!r.ok) {
      setError("Failed to load threads");
      return;
    }
    const body = (await r.json()) as { threads?: HistoryThreadSummaryDTO[] };
    setThreads(body.threads ?? []);
    setError(null);
  }, []);

  const loadTimeline = useCallback(async (threadId: string) => {
    if (!threadId.trim()) return;
    const [evR, cpR] = await Promise.all([
      fetch(
        `/api/history/events?${new URLSearchParams({ thread_id: threadId, limit: "200", offset: "0" })}`,
      ),
      fetch(
        `/api/history/checkpoints?${new URLSearchParams({ thread_id: threadId, limit: "80" })}`,
      ),
    ]);
    if (!evR.ok || !cpR.ok) {
      setError("Failed to load timeline");
      return;
    }
    const evBody = (await evR.json()) as { events?: Record<string, unknown>[] };
    const cpBody = (await cpR.json()) as { checkpoints?: HistoryCheckpointDTO[] };
    setEvents(evBody.events ?? []);
    setCheckpoints(cpBody.checkpoints ?? []);
    setError(null);
  }, []);

  const loadCheckpointDetail = useCallback(
    async (threadId: string, checkpointId: string | null, checkpointNs = "") => {
      if (!threadId.trim()) return;
      const q = new URLSearchParams({ thread_id: threadId, checkpoint_ns: checkpointNs });
      if (checkpointId) q.set("checkpoint_id", checkpointId);
      const r = await fetch(`/api/history/checkpoint?${q}`);
      if (!r.ok) {
        setError("Failed to load checkpoint detail");
        setDetail(null);
        return;
      }
      const body = (await r.json()) as HistoryCheckpointDetailResponse;
      setDetail(body);
      setError(null);
    },
    [],
  );

  useEffect(() => {
    void refreshThreads();
  }, [refreshThreads]);

  useEffect(() => {
    setSelectedThreadId(initialThreadId);
  }, [initialThreadId]);

  useEffect(() => {
    if (selectedThreadId) void loadTimeline(selectedThreadId);
  }, [selectedThreadId, loadTimeline]);

  return {
    threads,
    selectedThreadId,
    setSelectedThreadId,
    events,
    checkpoints,
    detail,
    error,
    refreshThreads,
    loadTimeline,
    loadCheckpointDetail,
  };
}
