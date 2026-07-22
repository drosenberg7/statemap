"""Provider registry."""

from __future__ import annotations

from typing import Dict, List, Type

from ..config import Config
from .base import Provider
from .seatgeek import SeatGeekProvider
from .stubhub import StubHubProvider
from .ticketmaster import TicketmasterProvider
from .tickpick import TickPickProvider
from .vividseats import VividSeatsProvider

_REGISTRY: Dict[str, Type[Provider]] = {
    TickPickProvider.name: TickPickProvider,
    SeatGeekProvider.name: SeatGeekProvider,
    TicketmasterProvider.name: TicketmasterProvider,
    VividSeatsProvider.name: VividSeatsProvider,
    StubHubProvider.name: StubHubProvider,
}


def available() -> List[str]:
    return sorted(_REGISTRY)


def build_providers(config: Config) -> List[Provider]:
    providers: List[Provider] = []
    for name in config.providers:
        cls = _REGISTRY.get(name.lower())
        if cls is None:
            raise ValueError(
                f"Unknown provider '{name}'. Available: {available()}"
            )
        providers.append(cls(config))
    return providers
