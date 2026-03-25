"""Ingress helpers for the CommunicationMod ↔ Python boundary."""

from __future__ import annotations

import json


def parse_communication_mod_json_line(line: str) -> dict:
    """Parse one JSON object line; raises ``json.JSONDecodeError`` if invalid."""
    return json.loads(line)


def is_state_object(obj: object) -> bool:
    return isinstance(obj, dict)
