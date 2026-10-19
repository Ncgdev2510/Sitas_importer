"""
Entidades de dominio. Independientes de Clupik: si mañana cambiamos
de fuente de datos, estas clases no deberían cambiar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TournamentPhase(str, Enum):
    FASE_REGULAR = "FASE_REGULAR"
    COPA_ORO = "COPA_ORO"
    COPA_PLATA = "COPA_PLATA"
    COPA_BRONCE = "COPA_BRONCE"


@dataclass(frozen=True)
class Club:
    clupik_id: int | None
    name: str


@dataclass(frozen=True)
class Tournament:
    clupik_id: int
    name: str
    season: str
    category: str
    modality: str = ""
    sex: str = ""
    status: str = ""  # texto tal cual lo da Clupik: "Finalizada" | "En curso"

    @property
    def is_finished(self) -> bool:
        return self.status.strip().lower().startswith("final")

    @property
    def is_in_progress(self) -> bool:
        return "curso" in self.status.strip().lower()


@dataclass(frozen=True)
class Standing:
    tournament_id: int
    phase_id: int
    phase_name: str
    position: int
    club: Club
    played: int
    won: int
    drawn: int
    lost: int
    points: int
    goals_for: int = 0
    goals_against: int = 0
    goal_diff: int = 0


@dataclass
class Match:
    clupik_id: int | None
    tournament_id: int
    phase_id: int | None
    phase_name: str
    round_name: str | None
    scheduled_at: datetime | None
    home_club: Club
    away_club: Club
    home_score: int | None = None
    away_score: int | None = None
    venue: str | None = None
    played: bool = False

    def involves(self, club_name: str) -> bool:
        needle = club_name.strip().lower()
        return (
            needle in self.home_club.name.strip().lower()
            or needle in self.away_club.name.strip().lower()
        )
