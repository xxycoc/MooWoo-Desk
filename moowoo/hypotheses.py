"""Preregistered H1-H3 summaries from verified, linked decision records."""

from collections import defaultdict
import math
import random
from statistics import NormalDist, mean

from .fees import realized_pnl
from .outcomes import instant

SEED = 20261117
RESAMPLES = 2000


def wilson(right, count):
    if not count:
        return None
    quantile = NormalDist().inv_cdf(.975)
    rate = right / count
    denominator = 1 + quantile ** 2 / count
    center = (rate + quantile ** 2 / (2 * count)) / denominator
    radius = quantile * math.sqrt(rate * (1-rate) / count + quantile ** 2 / (4 * count ** 2)) / denominator
    return [max(0, center-radius), min(1, center+radius)]


def percentile(values, fraction):
    ordered = sorted(values)
    index = (len(ordered)-1) * fraction
    lower = int(index)
    upper = min(lower+1, len(ordered)-1)
    return ordered[lower] + (ordered[upper]-ordered[lower]) * (index-lower)


def cluster_intervals(rows, fields):
    if not rows:
        return {field: None for field in fields}
    clusters = defaultdict(list)
    for row in rows:
        clusters[row["entrySession"]].append(row)
    groups = [clusters[key] for key in sorted(clusters)]
    rng = random.Random(SEED)
    samples = {field: [] for field in fields}
    for _ in range(RESAMPLES):
        sample = [row for group in rng.choices(groups, k=len(groups)) for row in group]
        for field in fields:
            samples[field].append(mean(row[field] for row in sample))
    return {field: [percentile(values, .025), percentile(values, .975)] for field, values in samples.items()}


def verdict(interval, threshold):
    if interval is None:
        return "can't tell yet"
    if interval[0] > threshold:
        return "supported"
    if interval[1] < threshold:
        return "rejected"
    return "can't tell yet"


def book_excess(record, book, outcome):
    """Finalized satellite book observations, not forecast-horizon price proxies."""
    if not record or record.get("completed") is not True:
        raise ValueError((record or {}).get("reason", "missing completed decision-book record"))
    if record.get("sleeve") != "satellite" or record.get("entryTs") != outcome["entryTs"]:
        raise ValueError("book sleeve or entry opportunity mismatch")
    if (not isinstance(record.get("exitTs"), str)
            or not instant(outcome["entryTs"]) <= instant(record["exitTs"]) <= instant("2026-11-27T18:00:00Z")):
        raise ValueError("invalid book exit timestamp")
    instant(record["exitTs"])
    benchmark = record.get("spyReturn")
    if type(benchmark) not in (int, float) or not math.isfinite(benchmark):
        raise ValueError("missing matched SPY return for book exit")
    if record.get("skipped") is True:
        if not isinstance(record.get("reason"), str) or not record["reason"].strip() or record.get("qty") != 0:
            raise ValueError("cash allocation needs zero quantity and a skip/veto reason")
        return -benchmark
    rising = outcome["class"].endswith("_up")
    eligible = (book == "follow" and rising or book == "fade" and not rising or
                book == "llm" and outcome["class"] in ("explained_up", "unexplained_down"))
    strategy = "drift" if rising else "bounce"
    if not eligible or record.get("exitRule") != strategy:
        raise ValueError("book direction or frozen exit rule mismatch")
    quantity = record.get("qty")
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("book quantity must be positive whole shares")
    net = realized_pnl(quantity, record.get("entryPrice"), record.get("exitPrice"))["returnNet"]
    return net - benchmark


def score(events):
    events = [event for event in events if not event["drill"]]
    ratings, identities = {}, set()
    for event in events:
        if event["type"] != "rating":
            continue
        identity = (event["decisionId"], event.get("secondOpinion", False))
        if identity in identities:
            raise ValueError("duplicate rating decision; resolve ledger before scoring")
        identities.add(identity)
        ratings[event["hash"]] = event
    outcomes = {}
    for event in events:
        if event["type"] != "outcome":
            continue
        rating = ratings.get(event["ratingHash"])
        if rating is None:
            raise ValueError("outcome source rating missing from logs")
        for key in ("decisionId", "ticker", "class", "confidence", "newsCutoff"):
            if event[key] != rating[key]:
                raise ValueError(f"outcome differs from prelogged rating: {key}")
        if (event["ratingTs"] != rating["ts"] or event["sourceRunId"] != rating["runId"]
                or event["secondOpinion"] != rating.get("secondOpinion", False)):
            raise ValueError("outcome provenance mismatch")
        if outcomes.get(event["ratingHash"], {}).get("graded"):
            if event["graded"]:
                raise ValueError("duplicate terminal outcome")
        else:
            outcomes[event["ratingHash"]] = event
    primary = {key: value for key, value in ratings.items() if not value.get("secondOpinion", False)}
    completed = [outcomes[key] for key in primary if outcomes.get(key, {}).get("graded")]
    missing = [dict(decisionId=rating["decisionId"], reason=outcomes.get(key, {}).get("reason", "horizon pending or not yet graded"))
               for key, rating in primary.items() if not outcomes.get(key, {}).get("graded")]
    count = len(completed)
    right = sum(event["right"] for event in completed)
    interval = wilson(right, count)
    h1 = dict(count=count, right=right, hitRate=right/count if count else None,
              interval95=interval, verdict=verdict(interval, .5))
    calibration = [dict(entrySession=event["entryTs"][:10], brier=(event["confidence"]-int(event["right"])) ** 2)
                   for event in completed]
    brier = mean(row["brier"] for row in calibration) if calibration else None
    h3 = dict(count=count, brier=brier, interval95=cluster_intervals(calibration, ["brier"])["brier"],
              verdict="not assessable" if brier is None else "met" if brier < .25 else "not met")
    books = {}
    for event in events:
        if event["type"] == "shadow" and event["book"] in ("llm", "follow", "fade") and "completed" in event:
            key = (event["decisionId"], event["book"])
            if key in books:
                raise ValueError("duplicate decision-book outcome")
            books[key] = event
    paired, unavailable, dispositions = [], [], []
    for key, rating in primary.items():
        outcome = outcomes.get(key)
        if not outcome or not outcome.get("entryTs"):
            unavailable.append(dict(decisionId=rating["decisionId"], reason="entry opportunity not yet resolved"))
            continue
        values = {}
        for book in ("llm", "follow", "fade"):
            record = books.get((outcome["decisionId"], book))
            if record and record.get("reason"):
                dispositions.append(dict(decisionId=outcome["decisionId"], book=book, reason=record["reason"]))
            try:
                values[book] = book_excess(record, book, outcome)
            except (ValueError, TypeError) as exc:
                unavailable.append(dict(decisionId=outcome["decisionId"], book=book, reason=str(exc)))
        if len(values) == 3:
            paired.append(dict(decisionId=outcome["decisionId"], entrySession=outcome["entryTs"][:10],
                               llmExcess=values["llm"], followExcess=values["follow"], fadeExcess=values["fade"],
                               versusFollow=values["llm"]-values["follow"], versusFade=values["llm"]-values["fade"]))
    intervals = cluster_intervals(paired, ("versusFollow", "versusFade"))
    comparisons = {key: dict(mean=mean(row[key] for row in paired) if paired else None, interval95=bounds)
                   for key, bounds in intervals.items()}
    if unavailable or any(bounds is None for bounds in intervals.values()):
        h2_verdict = "can't tell yet"
    elif all(bounds[0] > 0 for bounds in intervals.values()):
        h2_verdict = "supported"
    elif any(bounds[1] < 0 for bounds in intervals.values()):
        h2_verdict = "rejected"
    else:
        h2_verdict = "can't tell yet"
    return dict(schemaVersion=1, seed=SEED, resamples=RESAMPLES, returnUnit="fraction",
                primaryCalls=len(primary), excludedSecondOpinions=len(ratings)-len(primary), missing=missing,
                H1=h1, H2=dict(count=len(paired), comparisons=comparisons, verdict=h2_verdict,
                              unavailable=unavailable, dispositions=dispositions, matched=paired), H3=h3)
