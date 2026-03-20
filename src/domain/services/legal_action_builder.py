from __future__ import annotations

from src.domain.models.actions import LegalActionSet
from src.domain.models.game import GameSnapshot


class LegalActionBuilder:
    """Derives deterministic legal actions from the normalized snapshot."""

    def build(self, snapshot: GameSnapshot) -> LegalActionSet:
        raise NotImplementedError("LegalActionBuilder.build() is part of the v2 rewrite scaffold.")
