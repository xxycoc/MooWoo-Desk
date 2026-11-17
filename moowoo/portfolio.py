"""Serializable account state; pending tickets reserve capacity, never create fills."""

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
import math

from .events import canonical_bytes


def positive(value, name, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(value) or value < 0 or (not zero and value == 0):
        raise ValueError(f"{name} must be finite and {'nonnegative' if zero else 'positive'}")
    return float(value)


@dataclass
class PortfolioState:
    cash: float
    positions: dict = field(default_factory=dict)
    sessionStartEquity: float = 100000.0
    peakEquity: float = 100000.0
    ordersPlacedThisSession: int = 0
    tier: str = "normal"
    halted: bool = False
    haltReason: str = ""
    dailyLossHalted: bool = False
    sessionDate: str | None = None
    recoverySince: str | None = None
    recoveryTier: str | None = None
    recoveryFromOpen: bool = False
    stepUp: dict = field(default_factory=lambda: dict(enabled=False, invalidated=False))
    ticketedDecisionIds: list = field(default_factory=list)
    pendingTickets: list = field(default_factory=list)
    restartReasons: list = field(default_factory=list)

    def __post_init__(self):
        positive(self.cash, "cash", zero=True)
        positive(self.sessionStartEquity, "sessionStartEquity")
        positive(self.peakEquity, "peakEquity")
        if self.tier not in ("normal", "reduced", "exits_only", "kill"):
            raise ValueError("invalid tier")
        if type(self.ordersPlacedThisSession) is not int or self.ordersPlacedThisSession < 0:
            raise ValueError("ordersPlacedThisSession must be a nonnegative integer")
        for ticker, position in self.positions.items():
            positive(position["qty"], f"{ticker}.qty")
            positive(position["avgCost"], f"{ticker}.avgCost")
            if position["sleeve"] not in ("core", "satellite"):
                raise ValueError("invalid sleeve")
            if position["kind"] not in ("core", "drift", "bounce"):
                raise ValueError("invalid kind")
            if (position["kind"] == "core") != (position["sleeve"] == "core"):
                raise ValueError("kind and sleeve disagree")
        canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, snapshot):
        return cls(**deepcopy(snapshot))

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text))

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return canonical_bytes(self.to_dict()).decode("utf-8")

    def equity(self, prices):
        return self.cash + sum(position["qty"] * positive(prices[ticker], ticker)
                               for ticker, position in self.positions.items())

    def exposure(self, prices, sleeve=None, ticker=None):
        held = sum(position["qty"] * positive(prices[symbol], symbol)
                   for symbol, position in self.positions.items()
                   if (sleeve is None or position["sleeve"] == sleeve)
                   and (ticker is None or symbol == ticker))
        reserved = sum(ticket["qty"] * ticket["limitPrice"] for ticket in self.pendingTickets
                       if ticket["side"] == "BUY"
                       and (sleeve is None or ticket["sleeve"] == sleeve)
                       and (ticker is None or ticket["ticker"] == ticker))
        return held + reserved

    @property
    def reservedCash(self):
        return sum(ticket["qty"] * ticket["limitPrice"] + ticket["estFees"] for ticket in self.pendingTickets
                   if ticket["side"] == "BUY")

    def reserve(self, ticket):
        payload = ticket.to_dict() if hasattr(ticket, "to_dict") else deepcopy(ticket)
        if payload["decisionId"] in self.ticketedDecisionIds:
            raise ValueError("decisionId already ticketed")
        self.ticketedDecisionIds.append(payload["decisionId"])
        self.pendingTickets.append(payload)

    def restart(self, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("restart requires a written reason")
        previous = self.tier
        self.halted, self.haltReason = False, ""
        self.restartReasons.append(reason.strip())
        if previous == "kill":
            self.tier = "exits_only"
        self.recoverySince = self.recoveryTier = None
        return {"type": "halt", "reason": f"Manual restart: {reason.strip()}",
                "scope": "all", "cleared": True, "fromTier": previous, "toTier": self.tier}
