/**
 * Mirrors `src/domain/play_resolve.py` + display enrichment for the operator UI.
 */

import type { ActionDTO } from "../types/viewModel";

export const CARD_TOKEN_LEN = 8;

export function isNumericPlay(command: string): boolean {
  const parts = command.trim().toUpperCase().split(/\s+/);
  return (
    parts.length >= 2 &&
    parts[0] === "PLAY" &&
    /^\d+$/.test(parts[1]) &&
    parts[1].length <= 2
  );
}

export function normalizeCommandKey(command: string): string {
  return command.trim().split(/\s+/).join(" ").toLowerCase();
}

export function isCommandLegal(actions: ActionDTO[] | undefined, command: string): boolean {
  if (!actions?.length || !command) return false;
  const want = normalizeCommandKey(command);
  for (const a of actions) {
    const c = a.command;
    if (c && normalizeCommandKey(c) === want) return true;
  }
  return false;
}

function monsterIndex(action: ActionDTO): number | null {
  const v = action.monster_index;
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function resolveTokenPlay(command: string, actions: ActionDTO[]): string | null {
  const re = new RegExp(
    `^PLAY\\s+([A-Za-z0-9]{${CARD_TOKEN_LEN}})(?:\\s+(\\d+))?$`,
    "i",
  );
  const m = command.trim().match(re);
  if (!m) return null;
  const token = m[1].toLowerCase();
  const targetIndex = m[2] != null ? Number(m[2]) : null;

  const matches: ActionDTO[] = [];
  for (const action of actions) {
    const cmd = String(action.command ?? "");
    if (!cmd.toUpperCase().startsWith("PLAY ")) continue;
    const actToken = String(action.card_uuid_token ?? "").toLowerCase();
    if (actToken !== token) continue;
    matches.push(action);
  }

  if (matches.length === 0) return null;

  if (targetIndex != null && Number.isFinite(targetIndex)) {
    for (const action of matches) {
      if (monsterIndex(action) === targetIndex) return String(action.command ?? "");
    }
    return null;
  }

  const nonTargeted = matches.filter((a) => monsterIndex(a) == null);
  if (nonTargeted.length === 1)
    return String(nonTargeted[0].command ?? "");
  if (nonTargeted.length > 1)
    return String(nonTargeted[0].command ?? "");

  const targeted = matches.filter((a) => monsterIndex(a) != null);
  if (targeted.length === 1) return String(targeted[0].command ?? "");
  if (targeted.length > 1) {
    targeted.sort(
      (a, b) =>
        (monsterIndex(a) ?? 0) - (monsterIndex(b) ?? 0) ||
        String(a.command ?? "").localeCompare(String(b.command ?? "")),
    );
    return String(targeted[0].command ?? "");
  }

  return null;
}

export function resolvePlayWithToken(
  command: string | null | undefined,
  actions: ActionDTO[],
): string | null {
  if (!command) return null;
  const s = command.trim();
  if (!s.toUpperCase().startsWith("PLAY ") || isNumericPlay(s)) return null;
  return resolveTokenPlay(s, actions);
}

export type CommandStepRow = {
  model: string;
  canonical: string | null;
  resolve_tag: string;
};

/** Client-side parity with `command_steps_for_model_output` when API omits `command_steps`. */
export function commandStepsForDisplay(
  actions: ActionDTO[] | undefined,
  modelCommands: string[],
): CommandStepRow[] {
  if (!actions?.length || !modelCommands.length) return [];
  const out: CommandStepRow[] = [];
  for (const c of modelCommands) {
    const s = String(c).trim();
    if (!s) continue;

    if (
      s.toUpperCase().startsWith("PLAY ") &&
      isNumericPlay(s) &&
      isCommandLegal(actions, s)
    ) {
      out.push({
        model: s,
        canonical: s,
        resolve_tag: "canonical_numeric_play",
      });
      continue;
    }

    if (isCommandLegal(actions, s)) {
      const row = actions.find(
        (a) => a.command && normalizeCommandKey(a.command) === normalizeCommandKey(s),
      );
      out.push({
        model: s,
        canonical: row?.command ?? s,
        resolve_tag: "resolved:direct",
      });
      continue;
    }

    const fromToken = resolvePlayWithToken(s, actions);
    if (fromToken && isCommandLegal(actions, fromToken)) {
      out.push({
        model: s,
        canonical: fromToken,
        resolve_tag: "resolved:play_token",
      });
      continue;
    }

    const want = normalizeCommandKey(s);
    let normalized: string | null = null;
    for (const a of actions) {
      const ac = a.command;
      if (ac && normalizeCommandKey(ac) === want) {
        normalized = ac;
        break;
      }
    }
    if (normalized) {
      out.push({
        model: s,
        canonical: normalized,
        resolve_tag: "resolved:normalized",
      });
      continue;
    }

    out.push({
      model: s,
      canonical: null,
      resolve_tag: "no_legal_match",
    });
  }
  return out;
}
