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

export interface ViewModelDTO {
  schema_version?: number;
  in_game: boolean;
  header?: HeaderDTO | null;
  actions: ActionDTO[];
  combat?: Record<string, unknown> | null;
  screen?: Record<string, unknown> | null;
  inventory?: Record<string, unknown> | null;
  map?: Record<string, unknown> | null;
  sidebar?: Record<string, unknown> | null;
  last_action?: unknown;
}

export interface PendingApprovalDTO {
  interrupt?: { state_id?: string | null; command?: string | null };
  thread_id?: string | null;
}

/** Agent proposal envelope (LLM + hygiene); extra keys allowed via index signature pattern. */
export interface ProposalDTO {
  status?: string;
  for_state_id?: string | null;
  command?: string | null;
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
  emitted_command?: string | null;
  proposal?: ProposalDTO | Record<string, unknown> | null;
  failure_streak?: number;
  decision_trace?: string[];
  awaiting_interrupt?: boolean;
  agent_mode?: string;
  thread_id?: string;
  proposer?: string;
  llm_backend?: string;
  agent_error?: string;
}

export interface DebugSnapshotPayload {
  view_model: ViewModelDTO | null;
  state_id: string | null;
  ingress: unknown;
  error: string | null;
  agent?: AgentSnapshotDTO | null;
}

export interface WsMessage {
  type: string;
  payload?: DebugSnapshotPayload;
  detail?: string;
}
