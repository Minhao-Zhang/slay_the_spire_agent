from __future__ import annotations

from typing import Any

from src.agent.vm_shapes import as_dict

from .tag_utils import slugify_token
from .types import ContextTags

_RELIC_CAP = 12


def _int_floor(raw: Any) -> int | None:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        try:
            return int(raw.strip())
        except ValueError:
            return None
    return None


def _infer_act(floor: int | None, header_act: Any) -> str | None:
    if isinstance(header_act, int) and header_act >= 1:
        return f"act{header_act}"
    if isinstance(header_act, str) and header_act.strip().isdigit():
        try:
            a = int(header_act.strip())
            if a >= 1:
                return f"act{a}"
        except ValueError:
            pass
    if floor is None or floor < 1:
        return None
    if floor <= 17:
        return "act1"
    if floor <= 33:
        return "act2"
    return "act3"


def build_context_tags(vm: dict[str, Any]) -> ContextTags:
    header = as_dict(vm.get("header"))
    screen = as_dict(vm.get("screen"))
    combat = vm.get("combat") if isinstance(vm.get("combat"), dict) else None
    inventory = as_dict(vm.get("inventory"))
    map_block = vm.get("map") if isinstance(vm.get("map"), dict) else None

    floor = _int_floor(header.get("floor"))
    act_raw = header.get("act")
    act = _infer_act(floor, act_raw)

    screen_type = str(screen.get("type", "NONE") or "NONE").strip().upper() or "NONE"
    character = str(header.get("class", "") or "").strip()

    asc_raw = header.get("ascension_level", 0)
    ascension: int | None
    if isinstance(asc_raw, int):
        ascension = asc_raw
    elif isinstance(asc_raw, str) and asc_raw.strip().lstrip("-").isdigit():
        ascension = int(asc_raw.strip())
    else:
        ascension = None

    enemies: list[str] = []
    if combat:
        for m in combat.get("monsters") or []:
            if not isinstance(m, dict) or m.get("is_gone"):
                continue
            name = str(m.get("name", "")).strip()
            t = slugify_token(name)
            if t:
                enemies.append(t)

    event_slug = ""
    if screen_type == "EVENT":
        content = as_dict(screen.get("content"))
        ek = content.get("event_kb")
        if isinstance(ek, dict):
            event_slug = slugify_token(str(ek.get("name", "")))

    relic_slugs: list[str] = []
    for r in (inventory.get("relics") or [])[:_RELIC_CAP]:
        if not isinstance(r, dict):
            continue
        t = slugify_token(str(r.get("name", "")))
        if t:
            relic_slugs.append(t)

    boss_slug = ""
    if map_block and isinstance(map_block.get("boss_name"), str):
        boss_slug = slugify_token(map_block["boss_name"])

    flat: set[str] = {
        "general",
        "reference",
        slugify_token(screen_type),
        f"screen_{slugify_token(screen_type)}",
    }
    ch = slugify_token(character)
    if ch:
        flat.add(ch)
        flat.add(f"class_{ch}")
    if act:
        flat.add(act)
    if floor is not None:
        flat.add(f"floor_{floor}")
    if ascension is not None and ascension > 0:
        flat.add(f"asc_{ascension}")
    flat.update(enemies)
    for e in enemies:
        flat.add(f"enemy_{e}")
    if event_slug:
        flat.add(event_slug)
        flat.add(f"event_{event_slug}")
    flat.update(relic_slugs)
    for rs in relic_slugs:
        flat.add(f"relic_{rs}")
    if boss_slug:
        flat.add(boss_slug)
        flat.add(f"boss_{boss_slug}")
    if combat:
        flat.add("combat")
    if screen_type == "MAP":
        flat.add("map")
    if screen_type == "EVENT":
        flat.add("event")

    flat.discard("")
    return ContextTags(
        act=act,
        floor=floor,
        screen_type=screen_type,
        character=character,
        ascension=ascension,
        enemy_slugs=tuple(enemies),
        event_slug=event_slug,
        relic_slugs=tuple(relic_slugs),
        flat_tags=frozenset(flat),
    )
