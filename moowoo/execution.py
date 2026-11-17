"""Execution bookkeeping only. This module never contacts a broker or network."""

import hashlib
import os
import re

from .broker import account_context, parse_accounts, parse_placement, snapshot_to_state
from .events import canonical_bytes
from .fees import estimate_fees
from .portfolio import PortfolioState
from .tickets import OrderTicket, reconcile_fill, to_sim_order, verify_placed


def safe_reason(reason):
    account = os.environ.get("MOOMOO_ACCOUNT_ID")
    return str(reason).replace(account, "[account]") if account else str(reason)


def halt(log, reason, **extra):
    log.append("halt", dict(reason=safe_reason(reason), scope="run", **extra))


def note(log, ticket, action, **extra):
    return log.append("reflection_note", dict(prompt="Execution", text=action,
        ticker=ticket.ticker, executionAction=action, **extra), decisionId=ticket.decisionId)


def registered_prompt(text):
    sections = re.split(r"(?m)^#{1,6}\s+([^\n]*[Aa]ddendum[^\n]*)\n", text)
    if len(sections) < 3:
        raise ValueError("prompts not pre-registered")
    heading, body = sections[-2:]
    if not re.search(r"\d{4}-\d{2}-\d{2}", heading):
        raise ValueError("prompt addendum must be dated YYYY-MM-DD")
    hashes = re.findall(r"promptVersion\s*[`|:=\s]*([0-9a-f]{64})\b", body)
    if len(hashes) != 1:
        raise ValueError("prompts not pre-registered")
    return hashes[0]


def preflight(accounts, state, frozen, preregistration, prompt_version, universe, log):
    calculated = hashlib.sha256(canonical_bytes({key: value for key, value in frozen.items()
                                                if key != "configHash"})).hexdigest()
    if calculated != frozen["configHash"]:
        raise ValueError("frozen config hash mismatch")
    account, market = account_context()
    matched = [row for row in parse_accounts(accounts) if row["accountId"] == account]
    if len(matched) != 1:
        raise ValueError("configured account missing or ambiguous")
    row = matched[0]
    if row["accountType"] != 2 or row["market"] != market or "Qoder" not in row["title"]:
        raise ValueError("account is not the configured US Qoder competition account")
    if registered_prompt(preregistration) != prompt_version:
        raise ValueError("promptVersion mismatch")
    if not re.search(r"configHash[^\n]*" + re.escape(frozen["configHash"]), preregistration):
        raise ValueError("preregistered config hash mismatch")
    if state.halted or state.tier == "kill":
        raise ValueError("state is halted")
    require_not_halted(log.read())
    prices = {name: position.get("marketPrice", position["avgCost"])
              for name, position in state.positions.items()}
    log.append("run_started", dict(configHash=frozen["configHash"], promptVersion=prompt_version,
        trdEnv="SIMULATE", tier=state.tier, equity=state.equity(prices), cash=state.cash,
        universe=universe, equityBasis="saved marks, cost when mark unavailable"))


def load_tickets(manifest, log, config_hash):
    if manifest["runId"] != log.runId or manifest["configHash"] != config_hash:
        raise ValueError("ticket manifest run/config mismatch")
    tickets = {}
    for payload in manifest["tickets"]:
        ticket = OrderTicket(**payload)
        if ticket.decisionId != f"{log.runId}:{ticket.ticker}" or ticket.configHash != config_hash:
            raise ValueError("ticket identity/config mismatch")
        if ticket.decisionId in tickets:
            raise ValueError("duplicate ticket decisionId")
        tickets[ticket.decisionId] = ticket
    return tickets


def require_not_halted(events):
    halted = False
    for event in events:
        if event["type"] == "halt" and event["scope"] in ("run", "all") and not event["drill"]:
            halted = not event.get("cleared", False)
    if halted:
        raise ValueError("event log is halted")


def execution_ready(events, config_hash, prompt_version):
    require_not_halted(events)
    starts = [event for event in events if event["type"] == "run_started" and not event["drill"]]
    if not starts or starts[-1]["configHash"] != config_hash or starts[-1]["promptVersion"] != prompt_version:
        raise ValueError("matching preflight run_started required")


def decision_events(log, decision_id):
    return [event for event in log.read() if event["decisionId"] == decision_id and not event["drill"]]


def prepare(tickets, log):
    orders, skipped = [], []
    account_context()
    for ticket in tickets.values():
        events = decision_events(log, ticket.decisionId)
        submitted = any(event["type"] == "order_submitted" for event in events)
        attempts = [event for event in events if event.get("executionAction") == "prepared"]
        results = [event for event in events if event.get("executionAction") == "placement_failed"]
        terminal = any(event.get("executionAction") == "skip" for event in events)
        reason = None
        if submitted:
            reason = "already submitted"
        elif terminal or len(attempts) >= 2:
            reason = "ticker skipped for this session"
        elif attempts and (not results or results[-1]["attempt"] != len(attempts)):
            reason = "awaiting approval/response; reconcile before retry"
        elif results and not results[-1].get("retrySafe", False):
            reason = "uncertain placement; confirm absence in history before retry"
        if reason:
            skipped.append(dict(decisionId=ticket.decisionId, reason=reason))
            continue
        args = to_sim_order(ticket)
        attempt = len(attempts) + 1
        note(log, ticket, "prepared", attempt=attempt, ticketHash=ticket.ticketHash)
        orders.append(dict(decisionId=ticket.decisionId, attempt=attempt,
                           tool="sim_trade_input_order", args=args))
    return dict(orders=orders, skipped=skipped)


def retry_allowed(attempt, status, absence_confirmed=False):
    return attempt < 2 and status != "approval_expired" and (status == "rejected" or absence_confirmed is True)


def record(tickets, responses, log):
    if not isinstance(responses, list):
        raise ValueError("responses must be a list of executor receipt envelopes")
    recorded = []
    for response in responses:
        ticket = tickets[response["decisionId"]]
        events = decision_events(log, ticket.decisionId)
        if response.get("tool") == "sim_trade_cancel_order":
            account, market = account_context()
            submitted = [event for event in events if event["type"] == "order_submitted"]
            if not submitted:
                raise ValueError("cancellation requires a recorded submission")
            order_id = submitted[-1]["orderId"]
            if response["args"] != dict(acc_id=account, market=market, order_id=order_id):
                raise ValueError("cancellation argument mismatch")
            receipt = response["response"]
            if type(receipt.get("ret_code")) is not int or not isinstance(receipt.get("ret_msg"), str):
                raise ValueError("cancellation requires ret_code and ret_msg")
            if receipt["ret_code"] == 0 and parse_placement(receipt)["orderId"] != order_id:
                raise ValueError("cancellation response order ID mismatch")
            action = "cancelled" if receipt["ret_code"] == 0 else "cancel_failed"
            if not any(event.get("executionAction") == action and event.get("orderId") == order_id
                       and event.get("retCode") == receipt["ret_code"] for event in events):
                note(log, ticket, action, orderId=order_id, tool="sim_trade_cancel_order",
                     retCode=receipt["ret_code"], reason=safe_reason(receipt["ret_msg"]))
            continue
        attempts = [event for event in events if event.get("executionAction") == "prepared"]
        attempt = response["attempt"]
        if type(attempt) is not int or not 1 <= attempt <= 2 or attempt > len(attempts):
            raise ValueError("receipt does not identify a prepared attempt")
        if attempts[attempt-1]["ticketHash"] != ticket.ticketHash:
            raise ValueError("ticket changed after preparation")
        verification = verify_placed(ticket, response["args"])
        if not verification["ok"]:
            raise ValueError("placed argument mismatch: " + ", ".join(verification["mismatches"]))
        status = response["status"]
        receipt = response.get("response")
        if isinstance(receipt, dict) and type(receipt.get("ret_code")) is int and receipt["ret_code"] != 0:
            if not isinstance(receipt.get("ret_msg"), str) or not receipt["ret_msg"].strip():
                raise ValueError("failed placement requires ret_msg")
            status = "rejected"
            response = response | dict(reason=receipt["ret_msg"])
        if status == "placed":
            placed = parse_placement(response["response"])
            if "args" in placed and not verify_placed(ticket, placed["args"])["ok"]:
                raise ValueError("broker echoed arguments mismatch")
            previous = [event for event in events if event["type"] == "order_submitted"]
            if previous:
                if previous[-1]["orderId"] != placed["orderId"]:
                    raise ValueError("multiple orders for one decisionId")
                continue
            if any(event["type"] == "order_submitted" and event["orderId"] == placed["orderId"]
                   for event in log.read()):
                raise ValueError("broker order ID reused across tickets")
            log.append("order_submitted", dict(ticker=ticket.ticker, orderId=placed["orderId"],
                qty=ticket.qty, limitPrice=ticket.limitPrice, trdEnv="SIMULATE",
                attempt=attempt, ticketHash=ticket.ticketHash), decisionId=ticket.decisionId)
            recorded.append(ticket.decisionId)
        elif status in ("rejected", "failed", "timeout", "approval_expired"):
            if any(event["type"] == "order_submitted" for event in events):
                raise ValueError("failure contradicts recorded submission")
            failures = [event for event in events if event.get("executionAction") == "placement_failed"
                        and event["attempt"] == attempt]
            retry_safe = retry_allowed(attempt, status, response.get("absenceConfirmed", False))
            reason = safe_reason(response["reason"])
            if not isinstance(response["reason"], str) or not reason.strip():
                raise ValueError("failed placement requires reason")
            if failures:
                if failures[-1]["status"] != status:
                    raise ValueError("contradictory placement receipt")
                if not retry_safe or failures[-1]["retrySafe"]:
                    continue
            note(log, ticket, "placement_failed", attempt=attempt, status=status,
                 reason=reason, retrySafe=retry_safe)
            if attempt == 2 or status == "approval_expired":
                note(log, ticket, "skip", reason=reason, attempt=attempt)
        else:
            raise ValueError("unknown placement status")
    return dict(recorded=recorded)


def reconcile(tickets, history, positions, cash, state, log):
    expected = PortfolioState.from_dict(state.to_dict())
    expected.cash += expected.brokerReserved
    expected.brokerReserved = 0
    checkpoints = expected.execution.setdefault("fills", {})
    submissions = {event["orderId"]: event for event in log.read()
                   if event["type"] == "order_submitted" and not event["drill"]}
    submitted_decisions = {event["decisionId"] for event in submissions.values()}
    skipped_decisions = {event["decisionId"] for event in log.read()
                         if event.get("executionAction") == "skip" and not event["drill"]}
    expected.pendingTickets = [pending for pending in expected.pendingTickets
                               if pending["decisionId"] not in skipped_decisions - submitted_decisions]
    orders = {row["orderId"]: row for row in history}
    if submissions.keys() - orders.keys():
        raise ValueError("history missing submitted orders")
    if any(row["decisionId"].startswith(log.runId + ":") and row["orderId"] not in submissions
           for row in history):
        raise ValueError("history contains an unrecorded order; record its receipt first")
    cancellations, fill_events = [], []
    for order_id, submission in submissions.items():
        ticket = tickets[submission["decisionId"]]
        row = orders[order_id]
        for name in ("ticker", "side", "qty", "limitPrice"):
            if row[name] != getattr(ticket, name):
                raise ValueError(f"order history mismatch: {name}")
        fill = reconcile_fill(ticket, row["filledQty"], row["avgPrice"], row["status"], at_session_close=True)
        old = checkpoints.get(order_id, dict(filledQty=0, cashDelta=0, notional=0))
        delta = fill["filledQty"] - old["filledQty"]
        notional = fill["filledQty"] * fill["avgPrice"]
        if delta < 0 or (delta == 0 and abs(notional-old["notional"]) > .000001):
            raise ValueError("cumulative fill regressed or was revised")
        expected.cash += fill["cashDelta"] - old["cashDelta"]
        if delta:
            current = expected.positions.get(ticket.ticker)
            if ticket.side == "BUY":
                if current and current["decisionId"] != ticket.decisionId:
                    raise ValueError("cannot merge different strategy entry identities")
                if not current:
                    current = dict(qty=0, avgCost=0, kind=ticket.kind, sleeve=ticket.sleeve,
                        stop=ticket.stop, entryDate=ticket.createdTs[:10], decisionId=ticket.decisionId,
                        entryPrice=fill["avgPrice"], signalAtr=ticket.signalAtr,
                        preDropClose=ticket.preDropClose, trailArmed=False, highestClose=fill["avgPrice"])
                current["avgCost"] = (current["qty"]*current["avgCost"] + notional-old["notional"])/(current["qty"]+delta)
                current["entryPrice"] = current["avgCost"]
                current["qty"] += delta
                expected.positions[ticket.ticker] = current
            else:
                if not current or delta > current["qty"]:
                    raise ValueError("sell fill exceeds saved long position")
                current["qty"] -= delta
                if not current["qty"]:
                    del expected.positions[ticket.ticker]
        checkpoints[order_id] = dict(filledQty=fill["filledQty"], cashDelta=fill["cashDelta"], notional=notional)
        event = dict(ticker=ticket.ticker, orderId=order_id, filledQty=fill["filledQty"],
                     avgPrice=fill["avgPrice"], status=fill["status"], source="order_status",
                     brokerStatus=row["status"], fees=fill["fees"])
        if fill["filledQty"]:
            fill_events.append((ticket, event))
        expected.pendingTickets = [pending for pending in expected.pendingTickets
                                   if pending["decisionId"] != ticket.decisionId]
        cancelled = any(event.get("executionAction") == "cancelled" and event.get("orderId") == order_id
                        and event.get("tool") == "sim_trade_cancel_order" and event.get("retCode") == 0
                        for event in decision_events(log, ticket.decisionId))
        if not cancelled and fill["remainingQty"]:
            pending = ticket.to_dict() | dict(qty=fill["remainingQty"],
                estFees=estimate_fees(ticket.side, ticket.qty)-fill["fees"], submitted=True)
            expected.pendingTickets.append(pending)
            account, market = account_context()
            cancellations.append(dict(decisionId=ticket.decisionId, remainingQty=fill["remainingQty"],
                tool="sim_trade_cancel_order", args=dict(acc_id=account, market=market, order_id=order_id)))
    counted_orders = expected.execution.setdefault("orders", {})
    for order_id, submission in submissions.items():
        counted_orders[order_id] = tickets[submission["decisionId"]].createdTs[:10]
    session = expected.sessionDate or log.runId[:10]
    expected.ordersPlacedThisSession = max(expected.ordersPlacedThisSession,
        sum(order_session == session for order_session in counted_orders.values()))
    identities = {}
    for row in history:
        if row["side"] == "BUY" and row["filledQty"]:
            identity = submissions.get(row["orderId"], {}).get("decisionId", row["decisionId"])
            identities.setdefault(row["ticker"], set()).add(identity)
    identities = {name: next(iter(values)) for name, values in identities.items() if len(values) == 1}
    differences = {}
    observed_cash = cash["cash"] + cash.get("reserved", 0)
    if abs(observed_cash-expected.cash) > 1:
        differences["cash"] = dict(expected=expected.cash, observed=observed_cash)
    observed_positions = {row["ticker"]: row for row in positions if row["qty"]}
    for name in expected.positions.keys() | observed_positions.keys():
        wanted = expected.positions.get(name, {})
        observed = observed_positions.get(name, {})
        if wanted.get("qty", 0) != observed.get("qty", 0) or abs(
                wanted.get("qty", 0)*wanted.get("avgCost", 0)-observed.get("qty", 0)*observed.get("avgCost", 0)) > 1:
            differences[name] = dict(expected={key: wanted.get(key, 0) for key in ("qty", "avgCost")},
                                    observed={key: observed.get(key, 0) for key in ("qty", "avgCost")})
    try:
        independent = snapshot_to_state(positions, cash, expected, decisions=identities)
    except ValueError as exc:
        differences["snapshot"] = safe_reason(exc)
    for ticket, event in fill_events:
        prior = [item for item in decision_events(log, ticket.decisionId)
                 if item["type"] == "fill" and item["orderId"] == event["orderId"]]
        if not prior or any(prior[-1].get(key) != value for key, value in event.items()):
            log.append("fill", event, decisionId=ticket.decisionId)
    if differences:
        halt(log, "unexplained broker/book difference", diff=differences)
        expected.halted, expected.haltReason = True, "unexplained broker/book difference"
        return expected, dict(cancel=cancellations, diff=differences, halted=True)
    for row in positions:
        if row["ticker"] in independent.positions:
            independent.positions[row["ticker"]]["marketPrice"] = row["marketPrice"]
    return independent, dict(cancel=cancellations, diff={}, halted=independent.halted)
