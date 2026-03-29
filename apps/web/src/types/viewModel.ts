/** Mirrors `ViewModel` / `ActionCandidate` JSON from the control API. */

export type ActionStyle = "primary" | "secondary" | "danger" | "success";

export interface ActionDTO {
  label: string;
  command: string;
  style: ActionStyle;
  card_uuid_token?: string | null;
  hand_index?: number | null;
  monster_index?: number | null;
}

export interface HeaderDTO {
  "class"?: string;
  floor?: string;
  gold?: string;
  hp_display?: string;
  energy?: string;
  turn?: string;
}

/** Non-combat UI: ``state_processor._build_screen`` → ``{ type, title, content }``. */
export interface GameScreenDTO {
  type?: string;
  title?: string;
  content?: Record<string, unknown>;
}

export interface ViewModelDTO {
  schema_version?: number;
  in_game: boolean;
  header?: HeaderDTO | null;
  actions: ActionDTO[];
  /**
   * Combat snapshot when `combat_state` is present. May include `player_orbs` (Defect): slot list where
   * index 0 is the right-most / first in stack order.
   */
  combat?: Record<string, unknown> | null;
  screen?: GameScreenDTO | null;
  inventory?: Record<string, unknown> | null;
  map?: Record<string, unknown> | null;
  sidebar?: Record<string, unknown> | null;
  last_action?: unknown;
}

export interface PendingApprovalDTO {
  interrupt?: {
    state_id?: string | null;
    command?: string | null;
    /** Remaining steps after `command`, executed after approve (same bundle). */
    command_queue?: string[] | null;
  };
  thread_id?: string | null;
}

/** Agent proposal envelope (LLM + hygiene); extra keys allowed via index signature pattern. */
export interface ProposalDTO {
  status?: string;
  for_state_id?: string | null;
  command?: string | null;
  /** Same user message the agent sent to the LLM (from trace / replay sidecar). */
  user_prompt?: string | null;
  /** Text from the model JSON (LLM / mock), not the resolver tag. */
  rationale?: string | null;
  /** Post-parse pipeline tag, e.g. `resolved:direct`. */
  resolve_tag?: string | null;
  error_reason?: string | null;
  llm_raw?: string | null;
  parsed_model?: Record<string, unknown> | null;
}

export interface AgentSnapshotDTO {
  pending_approval?: PendingApprovalDTO | null;
  /** Post-step queue tail (e.g. after approve); may mirror interrupt.command_queue while awaiting HITL. */
  command_queue?: string[] | null;
  emitted_command?: string | null;
  proposal?: ProposalDTO | Record<string, unknown> | null;
  failure_streak?: number;
  decision_trace?: string[];
  awaiting_interrupt?: boolean;
  agent_mode?: string;
  thread_id?: string | null;
  run_seed?: string | null;
  ingress_derived_thread_id?: string | null;
  pending_graph_thread_id?: string | null;
  proposer?: string;
  llm_backend?: string;
  agent_error?: string;
  /** Mirrors ``ai_runtime`` / ``POST /api/ai/status`` from the game process. */
  ai_enabled?: boolean;
  ai_system_status?: string;
  ai_system_message?: string;
  /** True while ``main.py`` has a running ``agent.propose`` future (before final trace lands). */
  proposal_in_flight?: boolean;
  proposal_for_state_id?: string | null;
  /** Server-built tactical user message (trace when state matches, else ``build_user_prompt`` preview). */
  llm_user_prompt?: string | null;
}

export interface DebugSnapshotPayload {
  view_model: ViewModelDTO | null;
  state_id: string | null;
  ingress: unknown;
  /** From latest CommunicationMod envelope: ``state.ready_for_command``. */
  ingress_ready_for_command?: boolean | null;
  error: string | null;
  agent?: AgentSnapshotDTO | null;
  /** False when no feed or last ``/update_state`` older than ``DASHBOARD_INGRESS_MAX_AGE_SECONDS``. */
  live_ingress?: boolean;
  /** Seconds since last ingress touch (game line or debug paste); omit if unknown. */
  ingress_age_seconds?: number | null;
}

export interface WsMessage {
  type: string;
  /** Game snapshot when ``type === "snapshot"``; other event types may use a different shape. */
  payload?: DebugSnapshotPayload;
  detail?: string;
}

/** Response from ``GET /api/ai/state`` (live agent traces for debugging). */
export interface AiStateResponse {
  mode?: string;
  system_prompt?: string;
  latest_state_id?: string;
  latest_trace?: Record<string, unknown> | null;
  sequence_preview?: string[];
  trace_history?: Record<string, unknown>[];
  ai_enabled?: boolean;
  ai_status?: string;
  ai_api_style?: string;
  ai_status_message?: string;
}

export interface HistoryThreadSummaryDTO {
  thread_id: string;
  event_count: number;
  last_step_seq?: number;
}

export interface HistoryCheckpointDTO {
  checkpoint_id?: string | null;
  checkpoint_ns?: string | null;
  parent_checkpoint_id?: string | null;
  created_at?: string | null;
  state_id?: string | null;
  next?: string[];
  metadata?: Record<string, unknown>;
  interrupts?: unknown[];
  values?: Record<string, unknown>;
}

export interface HistoryCheckpointDetailResponse {
  thread_id: string;
  checkpoint: HistoryCheckpointDTO;
}
