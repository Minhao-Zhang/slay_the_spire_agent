from __future__ import annotations

from src.domain.models.game import GameSnapshot


class StateNormalizer:
    """Converts a raw CommunicationMod payload into a typed internal snapshot."""

    def normalize(self, raw_payload: dict, run_id: str) -> GameSnapshot:
        raise NotImplementedError("StateNormalizer.normalize() is part of the v2 rewrite scaffold.")
