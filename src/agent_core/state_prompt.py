"""Serialize KB-enriched view_model fields for tactical LLM user prompts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.domain.card_token import card_uuid_token


def _compact_text(text: str, *, limit: int = 160) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _card_line(card: dict[str, Any], index: int, show_token: bool = False) -> str:
    parts = [f"{index}. {card.get('name', '?')}"]
    if card.get("cost") is not None:
        parts.append(f"cost={card.get('cost')}")
    if card.get("upgrades", 0):
        parts.append(f"upgrades={card.get('upgrades')}")
    if card.get("has_target"):
        parts.append("targeted")
    if not card.get("is_playable", True):
        parts.append("unplayable")
    if show_token:
        token = card_uuid_token(str(card.get("uuid") or "") or None)
        if token:
            parts.append(f"play=PLAY {token}")
    kb = card.get("kb") or {}
    if kb.get("description"):
        parts.append(f"desc={kb['description']}")
    return " | ".join(parts)


def _power_line(power: dict[str, Any]) -> str:
    name = power.get("name", "?")
    amount = power.get("amount", "?")
    kb = power.get("kb") or {}
    effect = kb.get("effect", "")
    if effect:
        return f"{name}({amount}) | effect={_compact_text(str(effect), limit=120)}"
    return f"{name}({amount})"


def _monster_line(monster: dict[str, Any], index: int) -> str:
    parts = [
        f"{index}. {monster.get('name', '?')}",
        f"hp={monster.get('hp_display', '?')}",
        f"block={monster.get('block', 0)}",
        f"intent={monster.get('intent_display', monster.get('intent', '?'))}",
    ]
    powers = monster.get("powers") or []
    if powers:
        power_parts = [_power_line(p) for p in powers]
        parts.append("powers=" + "; ".join(power_parts))
    kb = monster.get("kb") or {}
    if kb.get("moves"):
        moves = kb["moves"][:3]
        parts.append("known_moves=" + ", ".join(str(m) for m in moves))
    if kb.get("notes"):
        parts.append(f"notes={_compact_text(str(kb['notes']))}")
    if kb.get("ai"):
        parts.append(f"ai={_compact_text(str(kb['ai']))}")
    return " | ".join(parts)


def _relic_line(relic: dict[str, Any]) -> str:
    kb = relic.get("kb") or {}
    desc = kb.get("description", "")
    if desc:
        return f"{relic.get('name', '?')} | desc={desc}"
    return str(relic.get("name", "?"))


def _potion_line(idx: int, potion: dict[str, Any]) -> str:
    kb = potion.get("kb") or {}
    effect = kb.get("effect", "")
    name = potion.get("name", "?")
    if effect:
        return f"{idx}. {name} | effect={_compact_text(str(effect), limit=120)}"
    return f"{idx}. {name}"


def build_tactical_state_summary(view_model: dict[str, Any]) -> str:
    """Human-readable state block using the same enriched ``kb`` fields as the UI."""
    lines: list[str] = []
    h = view_model.get("header") or {}
    lines.append(
        f"class={h.get('class', '?')} floor={h.get('floor', '?')} "
        f"hp={h.get('hp_display', '?')} gold={h.get('gold', '?')} "
        f"energy={h.get('energy', '?')} turn={h.get('turn', '?')}"
    )

    inv = view_model.get("inventory") or {}
    if inv.get("relics"):
        lines.append("relics:")
        for r in inv["relics"]:
            lines.append(f"  - {_relic_line(r)}")
    if inv.get("potions"):
        lines.append("potions:")
        for i, p in enumerate(inv["potions"], start=1):
            if isinstance(p, dict):
                lines.append(f"  - {_potion_line(i, p)}")

    com = view_model.get("combat")
    if com:
        lines.append(f"player_block={com.get('player_block', 0)}")
        if com.get("player_powers"):
            lines.append("player_powers:")
            for pw in com["player_powers"]:
                if isinstance(pw, dict):
                    lines.append(f"  - {_power_line(pw)}")
        if com.get("hand"):
            lines.append("hand:")
            for i, c in enumerate(com["hand"], start=1):
                if isinstance(c, dict):
                    lines.append(f"  - {_card_line(c, i, show_token=True)}")
        if com.get("monsters"):
            lines.append("monsters:")
            idx = 0
            for m in com["monsters"]:
                if not isinstance(m, dict) or m.get("is_gone"):
                    continue
                idx += 1
                lines.append(f"  - {_monster_line(m, idx)}")

    return "\n".join(lines)


def optional_strategy_corpus_block() -> str:
    """Append curated strategy text when ``SLAY_STRATEGY_CORPUS=1`` and file exists."""
    v = os.environ.get("SLAY_STRATEGY_CORPUS", "0").strip().lower()
    if v not in ("1", "true", "yes", "on"):
        return ""
    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "strategy" / "curated_strategy.md"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) > 16_000:
        text = text[:16_000] + "\n…"
    return f"\n\n## Strategy notes (curated)\n{text}\n"


__all__ = ["build_tactical_state_summary", "optional_strategy_corpus_block"]
