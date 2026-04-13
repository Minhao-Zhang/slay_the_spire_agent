import json
from pathlib import Path

import pandas as pd

EXCEL_PATH = Path("data/raw/Slay the Spire Reference.xlsx")
OUTPUT_DIR = Path("data/reference")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save_json(data, filename: str):
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {filename}: {len(data)} records")


def clean_str(val) -> str | None:
    if pd.isna(val):
        return None
    s = str(val).strip()
    return s if s else None


def extract_cards(xl: pd.ExcelFile) -> list[dict]:
    df = xl.parse("Cards")

    character_headers = {
        "Ironclad Cards": "Ironclad",
        "Silent Cards": "Silent",
        "Defect Cards": "Defect",
        "Watcher Cards": "Watcher",
        "Colorless Cards": "Colorless",
        "Curse Cards": "Curse",
        "Status Cards": "Status",
    }

    cards = []
    current_character = None

    for _, row in df.iterrows():
        name = clean_str(row.get("Name"))
        card_type = clean_str(row.get("Type"))

        if name in character_headers:
            current_character = character_headers[name]
            continue

        if not name or not card_type:
            continue

        cards.append({
            "name": name,
            "character": current_character,
            "type": card_type,
            "rarity": clean_str(row.get("Rarity")),
            "cost": clean_str(row.get("Cost")),
            "description": clean_str(row.get("Description")),
            "description_upgraded": clean_str(row.get("Description (Upgraded)")),
        })

    return cards


def extract_relics(xl: pd.ExcelFile) -> list[dict]:
    df = xl.parse("Relics")
    relics = []

    for _, row in df.iterrows():
        name = clean_str(row.get("Name"))
        rarity = clean_str(row.get("Rarity"))

        if not name or not rarity:
            continue

        valid_rarities = {"Common", "Uncommon", "Rare", "Shop", "Boss", "Event", "Special"}
        if rarity not in valid_rarities:
            continue

        relics.append({
            "name": name,
            "rarity": rarity,
            "class_specific": clean_str(row.get("Class-Specific")),
            "description": clean_str(row.get("Description")),
            "flavor_text": clean_str(row.get("Flavor Text")),
            "spawn_conditions": clean_str(row.get("Conditions for Spawning")),
        })

    return relics


def _parse_monster_row(row, name_col: str) -> dict | None:
    name = clean_str(row.get(name_col))
    hp = clean_str(row.get("HP"))

    if not name or not hp:
        return None

    moves = []
    for i in range(1, 7):
        move = clean_str(row.get(f"Move {i}"))
        if move:
            moves.append(move)

    return {
        "name": name,
        "hp": hp,
        "moves": moves,
        "notes": clean_str(row.get("Notes")),
        "ai": clean_str(row.get("AI")),
    }


def extract_monsters(xl: pd.ExcelFile) -> list[dict]:
    df = xl.parse("All Monsters (Non-Boss)")
    monsters = []

    for _, row in df.iterrows():
        entry = _parse_monster_row(row, "Unnamed: 0")
        if entry:
            monsters.append(entry)

    return monsters


def extract_bosses(xl: pd.ExcelFile) -> list[dict]:
    df = xl.parse("All Bosses")
    bosses = []

    for _, row in df.iterrows():
        entry = _parse_monster_row(row, "Monster Name")
        if entry:
            ascension_ai = clean_str(row.get("Ascension 20 AI (empty if identical to \nthe normal AI)"))
            entry["ascension_20_ai"] = ascension_ai
            bosses.append(entry)

    return bosses


def extract_events(xl: pd.ExcelFile) -> list[dict]:
    df = xl.parse("All EventsShrines")
    events = []

    for _, row in df.iterrows():
        name = clean_str(row.get("Event Name (ID)"))
        if not name:
            continue

        choices = []
        for i in range(1, 5):
            col = f"Choice {i}" if i < 4 else "Notes (or Choice 4)"
            choice = clean_str(row.get(col))
            if choice:
                choices.append(choice)

        events.append({
            "name": name,
            "choices": choices,
            "is_shrine": clean_str(row.get("Shrine?")) == "Yes",
        })

    return events


def extract_score_bonuses(xl: pd.ExcelFile) -> list[dict]:
    df = xl.parse("Score Bonuses")
    bonuses = []

    for _, row in df.iterrows():
        name = clean_str(row.get("Bonus Name"))
        if not name:
            continue

        bonuses.append({
            "name": name,
            "description": clean_str(row.get("Description")),
            "point_value": clean_str(row.get("Point Value")),
        })

    return bonuses


def extract_global_statistics(xl: pd.ExcelFile) -> list[dict]:
    df = xl.parse("Global Statistics")
    col_name = df.columns[0]
    col_value = df.columns[1]

    stats = []
    header_skipped = False

    for _, row in df.iterrows():
        key = clean_str(row.get(col_name))
        value = clean_str(row.get(col_value))

        if not key:
            continue

        if key == "Statistic Name":
            header_skipped = True
            continue

        if not header_skipped:
            continue

        stats.append({"statistic": key, "value": value})

    return stats


def extract_acts(xl: pd.ExcelFile) -> dict:
    acts = {}
    act_sheets = {
        "act_1": "Act 1 The Exordium",
        "act_2": "Act 2 The City",
        "act_3": "Act 3 The Beyond",
    }

    for key, sheet in act_sheets.items():
        df = xl.parse(sheet)
        rows = []
        for _, row in df.iterrows():
            values = [clean_str(v) for v in row.values if clean_str(v)]
            if values:
                rows.append(values)
        acts[key] = rows

    return acts


def main():
    xl = pd.ExcelFile(EXCEL_PATH)

    save_json(extract_cards(xl), "cards.json")
    save_json(extract_relics(xl), "relics.json")
    save_json(extract_monsters(xl), "monsters.json")
    save_json(extract_bosses(xl), "bosses.json")
    save_json(extract_events(xl), "events.json")


if __name__ == "__main__":
    main()
