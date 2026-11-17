"""Canonical immutable order authorization and an offline Moomoo argument adapter."""

from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import os
import re

from .desk_data import instant
from .events import canonical_bytes
from .portfolio import positive
from .fees import estimate_fees


@dataclass(frozen=True)
class OrderTicket:
    decisionId: str
    ticker: str
    side: str
    qty: int
    limitPrice: float
    sleeve: str
    kind: str
    stop: float
    reason: str
    configHash: str
    createdTs: str
    estFees: float
    signalAtr: float | None = None
    preDropClose: float | None = None
    ticketHash: str = ""

    def __post_init__(self):
        if not self.decisionId.strip() or len(self.decisionId.encode("utf-8")) > 100:
            raise ValueError("decisionId must be nonempty and at most 100 UTF-8 bytes")
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", self.ticker):
            raise ValueError("invalid ticker")
        if self.side not in ("BUY", "SELL") or type(self.qty) is not int or self.qty < 1:
            raise ValueError("ticket requires BUY/SELL and positive whole shares")
        positive(self.limitPrice, "limitPrice")
        if Decimal(str(self.limitPrice)) != Decimal(str(self.limitPrice)).quantize(Decimal(".01")):
            raise ValueError("limitPrice must be rounded to cents")
        if self.sleeve not in ("core", "satellite") or self.kind not in ("core", "drift", "bounce"):
            raise ValueError("invalid sleeve or kind")
        if (self.sleeve == "core") != (self.kind == "core"):
            raise ValueError("sleeve and kind disagree")
        if not re.fullmatch(r"[0-9a-f]{64}", self.configHash):
            raise ValueError("configHash must be SHA-256 hex")
        if self.estFees != estimate_fees(self.side, self.qty):
            raise ValueError("estFees mismatch")
        instant(self.createdTs)
        canonical_bytes(asdict(self))
        expected = hashlib.sha256(canonical_bytes(self.body())).hexdigest()
        if self.ticketHash and self.ticketHash != expected:
            raise ValueError("ticketHash mismatch")
        object.__setattr__(self, "ticketHash", expected)

    def body(self):
        return {key: value for key, value in asdict(self).items() if key != "ticketHash"}

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_proposal(cls, proposal, verdict, config_hash, created_ts):
        if verdict["verdict"] not in ("approve", "resize") or not 0 < verdict["qtyAfter"] <= proposal["qty"]:
            raise ValueError("only approved, non-increasing quantities authorize a ticket")
        if verdict["ticker"] != proposal["ticker"]:
            raise ValueError("verdict ticker mismatch")
        return cls(**{key: proposal[key] for key in
                      ("decisionId", "ticker", "side", "limitPrice", "sleeve", "kind", "stop", "reason")},
                   qty=verdict["qtyAfter"], estFees=estimate_fees(proposal["side"], verdict["qtyAfter"]), configHash=config_hash, createdTs=created_ts,
                   signalAtr=proposal.get("signalAtr"), preDropClose=proposal.get("preDropClose"))


def format_symbol(ticker, template="US.{ticker}"):
    if template.count("{ticker}") != 1:
        raise ValueError("symbol template requires one {ticker} placeholder")
    return template.format(ticker=ticker)


def to_sim_order(ticket, acc_id=None, market=None, *, symbol_format="US.{ticker}"):
    account, market_text = os.environ.get("MOOMOO_ACCOUNT_ID"), os.environ.get("MOOMOO_MARKET")
    if not account or not account.strip() or not market_text or not market_text.strip():
        raise ValueError("MOOMOO_ACCOUNT_ID and MOOMOO_MARKET are required")
    try:
        configured_market = int(market_text)
    except ValueError as exc:
        raise ValueError("MOOMOO_MARKET must be an integer") from exc
    if acc_id is not None and (not isinstance(acc_id, str) or acc_id != account):
        raise ValueError("acc_id does not match MOOMOO_ACCOUNT_ID")
    if market is not None and (type(market) is not int or market != configured_market):
        raise ValueError("market does not match MOOMOO_MARKET")
    ticket = OrderTicket(**ticket) if isinstance(ticket, dict) else OrderTicket(**ticket.to_dict())
    return dict(acc_id=account, market=configured_market, symbol=format_symbol(ticket.ticker, symbol_format),
                order_type=1, order_side=1 if ticket.side == "BUY" else 2,
                qty=ticket.qty, price=ticket.limitPrice, text=ticket.decisionId)


def verify_placed(ticket, placed_args, *, symbol_format="US.{ticker}"):
    expected = to_sim_order(ticket, symbol_format=symbol_format)
    mismatches = {}
    for key in sorted(expected.keys() | placed_args.keys()):
        if (key not in expected or key not in placed_args or expected[key] != placed_args[key]
                or isinstance(placed_args.get(key), bool)):
            mismatches[key] = dict(expected=expected.get(key), observed=placed_args.get(key),
                                   missing=key not in placed_args, unexpected=key not in expected)
    return dict(ok=not mismatches, mismatches=mismatches)


def reconcile_fill(ticket, filled_qty, avg_price, status, *, at_session_close=False):
    """Cumulative fills for one ticket; charge the flat fee once, not per partial."""
    ticket = OrderTicket(**ticket) if isinstance(ticket, dict) else OrderTicket(**ticket.to_dict())
    positive(filled_qty, "filled_qty", zero=True)
    if filled_qty > ticket.qty:
        raise ValueError("fill exceeds approved quantity")
    positive(avg_price, "avg_price", zero=filled_qty == 0)
    if not isinstance(status, str) or not status.strip():
        raise ValueError("status is required")
    if filled_qty and ((ticket.side == "BUY" and avg_price > ticket.limitPrice) or
                       (ticket.side == "SELL" and avg_price < ticket.limitPrice)):
        raise ValueError("fill violates limit price")
    outcome = "filled" if filled_qty == ticket.qty else "partial" if filled_qty else "unfilled"
    fees = estimate_fees(ticket.side, filled_qty)
    return dict(status=outcome, brokerStatus=status, filledQty=filled_qty,
                remainingQty=ticket.qty-filled_qty, avgPrice=avg_price, fees=fees,
                cashDelta=(-filled_qty*avg_price-fees if ticket.side == "BUY" else filled_qty*avg_price-fees),
                cancel_leftover=at_session_close and outcome != "filled")
