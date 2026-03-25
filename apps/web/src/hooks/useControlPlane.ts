import { useCallback, useEffect, useRef, useState } from "react";

import { SAMPLE_INGRESS } from "../data/sampleIngress";
import type {
  AgentSnapshotDTO,
  DebugSnapshotPayload,
  HistoryCheckpointDTO,
  HistoryThreadSummaryDTO,
  WsMessage,
} from "../types/viewModel";

function wsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

export function useControlPlane() {
  const [snapshot, setSnapshot] = useState<DebugSnapshotPayload | null>(null);
  const [connected, setConnected] = useState(false);
  const [logLines, setLogLines] = useState<
    { t: string; kind: string; msg: string }[]
  >([]);
  const [historyThreads, setHistoryThreads] = useState<
    HistoryThreadSummaryDTO[]
  >([]);
  const [historyEvents, setHistoryEvents] = useState<Record<string, unknown>[]>(
    [],
  );
  const [historyCheckpoints, setHistoryCheckpoints] = useState<
    HistoryCheckpointDTO[]
  >([]);
  const [historyThreadFilter, setHistoryThreadFilter] = useState<string>("");
  const wsRef = useRef<WebSocket | null>(null);

  const pushLog = useCallback((kind: string, msg: string) => {
    const t = new Date().toLocaleTimeString();
    setLogLines((prev) => [...prev.slice(-200), { t, kind, msg }]);
  }, []);

  const applyPayload = useCallback(
    (p: DebugSnapshotPayload) => {
      setSnapshot(p);
      if (p.state_id) {
        pushLog("STATE", `state_id ${p.state_id}`);
      }
    },
    [pushLog],
  );

  const fetchSnapshot = useCallback(async () => {
    const r = await fetch("/api/debug/snapshot");
    if (!r.ok) return;
    const data = (await r.json()) as DebugSnapshotPayload;
    applyPayload(data);
  }, [applyPayload]);

  const postIngress = useCallback(
    async (body: Record<string, unknown>) => {
      const r = await fetch("/api/debug/ingress", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        pushLog("ERROR", JSON.stringify(err));
        return;
      }
      const data = (await r.json()) as DebugSnapshotPayload;
      applyPayload(data);
    },
    [applyPayload, pushLog],
  );

  const loadSample = useCallback(() => {
    void postIngress(SAMPLE_INGRESS);
  }, [postIngress]);

  const queueManualCommand = useCallback(
    async (command: string) => {
      const r = await fetch("/api/debug/manual_command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        pushLog("ERROR", JSON.stringify(err));
        return;
      }
      pushLog("ACTION", `Queued for game: ${command}`);
    },
    [pushLog],
  );

  const resumeAgent = useCallback(
    async (
      kind: "approve" | "reject" | "edit",
      editCommand?: string,
    ) => {
      const body: Record<string, unknown> = { kind };
      if (kind === "edit" && editCommand != null) body.command = editCommand;
      const r = await fetch("/api/agent/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        pushLog("ERROR", JSON.stringify(err));
        return;
      }
      const data = (await r.json()) as AgentSnapshotDTO;
      pushLog("SYSTEM", `Agent resume ${kind}: ${JSON.stringify(data)}`);
      void fetchSnapshot();
    },
    [fetchSnapshot, pushLog],
  );

  const refreshHistoryThreads = useCallback(async () => {
    const r = await fetch("/api/history/threads");
    if (!r.ok) {
      pushLog("ERROR", "history/threads failed");
      return;
    }
    const body = (await r.json()) as { threads?: HistoryThreadSummaryDTO[] };
    setHistoryThreads(body.threads ?? []);
    pushLog("SYSTEM", `History: ${body.threads?.length ?? 0} thread(s)`);
  }, [pushLog]);

  const loadHistoryEvents = useCallback(
    async (threadId: string) => {
      const q = new URLSearchParams({
        thread_id: threadId,
        limit: "100",
        offset: "0",
      });
      const r = await fetch(`/api/history/events?${q}`);
      if (!r.ok) {
        pushLog("ERROR", "history/events failed");
        return;
      }
      const body = (await r.json()) as {
        events?: Record<string, unknown>[];
      };
      setHistoryEvents(body.events ?? []);
    },
    [pushLog],
  );

  const loadHistoryCheckpoints = useCallback(
    async (threadId: string) => {
      const q = new URLSearchParams({ thread_id: threadId, limit: "30" });
      const r = await fetch(`/api/history/checkpoints?${q}`);
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        pushLog("ERROR", `checkpoints: ${JSON.stringify(err)}`);
        setHistoryCheckpoints([]);
        return;
      }
      const body = (await r.json()) as {
        checkpoints?: HistoryCheckpointDTO[];
      };
      setHistoryCheckpoints(body.checkpoints ?? []);
    },
    [pushLog],
  );

  const retryAgent = useCallback(async () => {
    const r = await fetch("/api/agent/retry", { method: "POST" });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      pushLog("ERROR", JSON.stringify(err));
      return;
    }
    const data = (await r.json()) as DebugSnapshotPayload;
    applyPayload(data);
    pushLog("SYSTEM", "Agent retry: re-ran graph on current ingress");
  }, [applyPayload, pushLog]);

  useEffect(() => {
    void fetchSnapshot();
  }, [fetchSnapshot]);

  useEffect(() => {
    const ws = new WebSocket(wsUrl());
    wsRef.current = ws;
    ws.onopen = () => {
      setConnected(true);
      pushLog("SYSTEM", "WebSocket connected");
    };
    ws.onclose = () => {
      setConnected(false);
      pushLog("SYSTEM", "WebSocket disconnected");
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data)) as WsMessage;
        if (msg.type === "snapshot" && msg.payload) {
          applyPayload(msg.payload);
        }
      } catch {
        /* ignore */
      }
    };
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [applyPayload, pushLog]);

  return {
    snapshot,
    connected,
    logLines,
    fetchSnapshot,
    postIngress,
    loadSample,
    queueManualCommand,
    resumeAgent,
    retryAgent,
    pushLog,
    historyThreads,
    historyEvents,
    historyCheckpoints,
    historyThreadFilter,
    setHistoryThreadFilter,
    refreshHistoryThreads,
    loadHistoryEvents,
    loadHistoryCheckpoints,
  };
}
