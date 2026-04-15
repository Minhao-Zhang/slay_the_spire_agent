import type { ActionDTO } from "../types/viewModel";

/**
 * CSS suffix for `.valid-action--*` — matches hand `cardNameClass` hues + potion + neutral UI.
 */
export type ValidActionVariant =
  | "attack"
  | "skill"
  | "power"
  | "status"
  | "potion"
  | "neutral";

/**
 * Map control-plane actions to a visual variant. Uses `card_type` from the server when set
 * (plays, hand-select choose, shop cards); potions by command or `card_type`; everything
 * else (END TURN, map, events, …) uses neutral grey.
 */
export function validActionVariant(a: ActionDTO): ValidActionVariant {
  const cmdUp = (a.command ?? "").trim().toUpperCase();
  const ct = (a.card_type ?? "").trim().toUpperCase();

  if (cmdUp.startsWith("POTION") || ct === "POTION") return "potion";

  if (ct === "ATTACK") return "attack";
  if (ct === "SKILL") return "skill";
  if (ct === "POWER") return "power";
  if (ct === "STATUS" || ct === "CURSE") return "status";

  return "neutral";
}
