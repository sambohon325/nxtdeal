"""
core/prediction.py — NXTDeal's shared prediction/confidence engine (2026-07-13,
session 37). Sam: "NXTDeal is 100% based on the idea of one database (graph
knowledge) and Prediction scoring... we can predict with a percentage certainty
outcomes based on historical knowledge. When that historical data is not possible, it
will be filled (and noted for reference clearly) on industry / local knowledge... so
when NXTDeal knows that we have enough data to be 90% certain of outcomes... the
department is ready to go live."

Every prediction this module produces separates three things honestly rather than
folding them into one opaque number:
  1. predicted_value  -- computed either from a real pace/moving-average projection
     over real dated graph entities (Vehicle.DateSold, ServiceRecord.ServiceDate,
     FinanceContract.ContractDate, PartSale.SaleDate, Lead.CreatedDate), or, when there
     isn't enough real history yet, an industry rule-of-thumb constant
     (INDUSTRY_BASELINES below -- explicitly a rule-of-thumb estimate, not a cited
     source, since this environment has no live access to a real industry benchmark
     report);
  2. confidence_pct    -- a real, explainable blend of how much real data backs the
     number (sample size vs. VOLUME_TARGET_SAMPLES), how recent that data is relative
     to the horizon being predicted, and how many distinct days in the window actually
     have data (vs. one lucky cluster);
  3. basis             -- "ledger" (real data dominates), "industry_estimate" (real
     data is too thin, the baseline dominates), or "blended" -- the literal "noted for
     reference clearly" Sam asked for, attached to every prediction rather than buried
     in a tooltip.

HORIZONS are the four Sam named verbatim: tomorrow, a week, a month, a quarter.
GO_LIVE_CONFIDENCE_THRESHOLD (90%, Sam's stated default) is the bar a department's
"tomorrow" horizon confidence needs to clear before core/data_connections.py considers
that department ready to go live -- see department_readiness() below.
"""

from datetime import date, timedelta

from core.dealeros import ledger
from core.entity_types import VEHICLE, SERVICE_RECORD, FINANCE_CONTRACT, PART_SALE, LEAD


GO_LIVE_CONFIDENCE_THRESHOLD = 90.0

HORIZONS = {
    "tomorrow": 1,
    "week": 7,
    "month": 30,
    "quarter": 90,
}

# 30 real data points is a common statistics rule-of-thumb floor for a stable average
# (not a NXTDeal-specific invention). Recency targets are "as fresh as the horizon
# itself needs" -- predicting tomorrow needs near-today data, predicting a quarter out
# can tolerate data that's a couple weeks old.
VOLUME_TARGET_SAMPLES = 30

RECENCY_TARGET_DAYS = {
    "tomorrow": 2,
    "week": 5,
    "month": 14,
    "quarter": 30,
}

# Industry rule-of-thumb daily rates per department -- generic, commonly-cited
# dealership-scale benchmarks (e.g. "~12 units/month" for a single rep-level pace),
# used ONLY to seed a brand-new department's prediction before enough real ledger
# history exists. Deliberately NOT presented as sourced from a specific citation --
# this environment has no live access to verify one -- and every prediction that
# leans on this is labeled "industry_estimate" or "blended", never silently folded in
# as if it were real.
INDUSTRY_BASELINES = {
    "sales": {"metric": "units_sold", "daily_rate": 0.4, "unit": "units"},
    "service": {"metric": "repair_orders", "daily_rate": 0.8, "unit": "ROs"},
    "finance": {"metric": "contracts_funded", "daily_rate": 0.35, "unit": "contracts"},
    "parts": {"metric": "parts_sales", "daily_rate": 2.0, "unit": "sales"},
    "marketing": {"metric": "leads_generated", "daily_rate": 1.5, "unit": "leads"},
}

_DEPARTMENT_SOURCES = {
    "sales": (VEHICLE, "DateSold"),
    "service": (SERVICE_RECORD, "ServiceDate"),
    "finance": (FINANCE_CONTRACT, "ContractDate"),
    "parts": (PART_SALE, "SaleDate"),
    "marketing": (LEAD, "CreatedDate"),
}

DEPARTMENTS = list(_DEPARTMENT_SOURCES.keys())


def _today():
    return date.today()


def _real_dates_for(department, window_days):
    """Every real ISO date on this department's dated entity type, within the trailing
    window_days -- the raw historical series everything else here is computed from.
    Returns a sorted list of date objects (may be empty)."""

    entity_type, date_field = _DEPARTMENT_SOURCES[department]
    cutoff = _today() - timedelta(days=window_days)

    dates = []

    for entity in ledger.get_all().values():

        if entity.entity_type != entity_type:
            continue

        raw = entity.attributes.get(date_field)

        if not raw:
            continue

        try:
            parsed = date.fromisoformat(raw[:10])
        except ValueError:
            continue

        if parsed >= cutoff:
            dates.append(parsed)

    return sorted(dates)


def _volume_score(sample_size):
    return min(1.0, sample_size / VOLUME_TARGET_SAMPLES)


def _recency_score(dates, horizon):

    if not dates:
        return 0.0

    days_since_latest = (_today() - dates[-1]).days
    target = RECENCY_TARGET_DAYS[horizon]

    if days_since_latest <= target:
        return 1.0

    # Linear decay to 0 by 4x the target window -- an old-but-not-ancient data point
    # still counts for something, just less.
    return max(0.0, 1.0 - (days_since_latest - target) / (target * 3))


def _completeness_score(dates, window_days):
    """A crude but real completeness signal: what fraction of the trailing window has
    at least one real data point on a distinct day -- steady activity is more
    predictable than the same total count clustered into one burst."""

    if window_days <= 0:
        return 0.0

    distinct_days = len(set(dates))

    return min(1.0, distinct_days / min(window_days, VOLUME_TARGET_SAMPLES))


def predict(department, horizon):
    """Returns a full prediction dict for one department/horizon pair, or None for an
    unknown department/horizon (same "just don't produce it" shape as an unmatched
    core/ai_api.py intent -- no error, just nothing)."""

    if department not in _DEPARTMENT_SOURCES or horizon not in HORIZONS:
        return None

    horizon_days = HORIZONS[horizon]
    window_days = max(horizon_days * 6, 60)

    dates = _real_dates_for(department, window_days)
    sample_size = len(dates)

    baseline = INDUSTRY_BASELINES[department]

    volume = _volume_score(sample_size)
    recency = _recency_score(dates, horizon)
    completeness = _completeness_score(dates, window_days)

    confidence = round(100 * (0.5 * volume + 0.3 * recency + 0.2 * completeness), 1)

    real_daily_rate = (sample_size / window_days) if sample_size else 0.0
    industry_daily_rate = baseline["daily_rate"]

    # The blend weight IS the volume score -- lots of real data means the industry
    # number contributes almost nothing to the final predicted_value; little real data
    # leans on it almost entirely. This is the "filled in by the ledger's own data as
    # it becomes available" blend Sam described, made explicit rather than hidden.
    blended_daily_rate = (volume * real_daily_rate) + ((1 - volume) * industry_daily_rate)
    predicted_value = round(blended_daily_rate * horizon_days, 1)

    if volume >= 0.9:
        basis = "ledger"
    elif volume <= 0.1:
        basis = "industry_estimate"
    else:
        basis = "blended"

    return {
        "department": department,
        "horizon": horizon,
        "horizon_days": horizon_days,
        "metric": baseline["metric"],
        "unit": baseline["unit"],
        "predicted_value": predicted_value,
        "confidence_pct": confidence,
        "basis": basis,
        "sample_size": sample_size,
        "factors": {
            "volume": round(volume, 2),
            "recency": round(recency, 2),
            "completeness": round(completeness, 2),
        },
        "note": _note(basis, sample_size, baseline),
    }


def _note(basis, sample_size, baseline):

    if basis == "ledger":
        return f"Based on {sample_size} real historical data points from the ledger."

    if basis == "industry_estimate":
        return (
            f"Not enough real ledger history yet ({sample_size} data point(s)) -- "
            f"using a general industry rule-of-thumb estimate (~{baseline['daily_rate']} "
            f"{baseline['unit']}/day, not a cited source). This will shift toward real "
            "ledger data automatically as more comes in."
        )

    return (
        f"Blended: {sample_size} real historical data point(s) plus an industry "
        "rule-of-thumb estimate filling in the remaining uncertainty."
    )


def predict_all_horizons(department):

    results = []

    for horizon in HORIZONS:

        result = predict(department, horizon)

        if result:
            results.append(result)

    return results


def department_readiness(department):
    """Whether this department is 'ready to go live' per Sam's stated default: >=90%
    confidence on the 'tomorrow' horizon specifically -- the tightest, most demanding
    horizon, and the one Sam described ("90% will be for the next few days to
    start")."""

    tomorrow = predict(department, "tomorrow")

    if not tomorrow:
        return None

    policy = ledger.get_entity("READINESS-" + department)
    settings = policy.attributes if policy and policy.entity_type == "ReadinessPolicy" else {}
    threshold = settings.get("threshold", GO_LIVE_CONFIDENCE_THRESHOLD)
    ready = tomorrow["confidence_pct"] >= threshold
    enabled = bool(settings.get("enabled", False))
    return {
        "department": department,
        "confidence_pct": tomorrow["confidence_pct"],
        "threshold": threshold,
        "ready": ready,
        "enabled": enabled,
        "active": enabled and ready and tomorrow["basis"] != "industry_estimate",
        "basis": tomorrow["basis"],
    }


def all_departments_readiness():
    return [department_readiness(d) for d in DEPARTMENTS]


# --- Reporting-tab prediction timeline (2026-07-15, session 71) -----------------------
#
# Sam: "all reporting tabs need to have sliding bars next to the view / pop out
# section where they can slide the information back in forth based on predictive
# knowledge with percentages... for now lets do last week / current / tomorrow/ next
# week/ next month/ next quarter, and have a sliding scale percentage next to it. when
# prediction is activated, please put in reference points on what its based on and a
# disclaimer for any knowledge gaps."
#
# The 6 slider positions split into two honestly-different kinds of data rather than
# running all 6 through predict()'s forecast blend:
#   - "last_week"/"current" are REAL, ALREADY-HAPPENED counts straight off the ledger
#     (basis="actual", 100% confidence -- there's nothing to forecast about the past or
#     what's already landed today).
#   - "tomorrow"/"next_week"/"next_month"/"next_quarter" reuse predict() verbatim,
#     mapped onto its existing "tomorrow"/"week"/"month"/"quarter" horizon keys --
#     same confidence blend, same basis labels, same industry-estimate disclaimer note.

PERIOD_LABELS = {
    "last_week": "Last Week",
    "current": "Current",
    "tomorrow": "Tomorrow",
    "next_week": "Next Week",
    "next_month": "Next Month",
    "next_quarter": "Next Quarter",
}

# Trailing real windows backing the two "actual" (non-forecast) periods.
_ACTUAL_WINDOWS = {
    "last_week": 7,
    "current": 1,
}

# Maps the four forward-looking periods onto predict()'s existing horizon keys.
_FORECAST_HORIZONS = {
    "tomorrow": "tomorrow",
    "next_week": "week",
    "next_month": "month",
    "next_quarter": "quarter",
}


def _actual_point(department, period):
    """A real, already-happened count for the trailing window -- not a prediction, so
    it gets its own basis value ("actual") distinct from predict()'s
    ledger/blended/industry_estimate, and a flat 100% confidence since it's known, not
    forecast."""

    window_days = _ACTUAL_WINDOWS[period]
    dates = _real_dates_for(department, window_days)
    baseline = INDUSTRY_BASELINES[department]

    return {
        "period": period,
        "label": PERIOD_LABELS[period],
        "kind": "actual",
        "department": department,
        "metric": baseline["metric"],
        "unit": baseline["unit"],
        "value": len(dates),
        "confidence_pct": 100.0,
        "basis": "actual",
        "sample_size": len(dates),
        "note": (
            f"Real, already-recorded {baseline['metric']} in the ledger over the "
            f"trailing {window_days} day{'s' if window_days != 1 else ''} -- known "
            "history, not a prediction."
        ),
    }


def _predicted_point(department, period):

    horizon = _FORECAST_HORIZONS[period]
    result = predict(department, horizon)

    if not result:
        return None

    return {
        "period": period,
        "label": PERIOD_LABELS[period],
        "kind": "predicted",
        "department": result["department"],
        "metric": result["metric"],
        "unit": result["unit"],
        "value": result["predicted_value"],
        "confidence_pct": result["confidence_pct"],
        "basis": result["basis"],
        "sample_size": result["sample_size"],
        "factors": result["factors"],
        "note": result["note"],
    }


def timeline(department):
    """The full 6-point last-week/current/tomorrow/next-week/next-month/next-quarter
    series for one department, backing the Reporting tab's prediction-horizon slider.
    Returns None for a department with no real prediction source at all (see
    DEPARTMENTS above -- Operations/Inventory/Administration/Network/Readiness have
    none; the caller shows an honest "not available for this department" state rather
    than calling this)."""

    if department not in _DEPARTMENT_SOURCES:
        return None

    points = []

    for period in PERIOD_LABELS:

        if period in _ACTUAL_WINDOWS:
            points.append(_actual_point(department, period))
        else:
            point = _predicted_point(department, period)
            if point:
                points.append(point)

    return {"department": department, "points": points}

# --- Readiness Timeline capstone (2026-07-19, Readiness reframe, item #5 slice) ------
#
# Sam's own spec for this one: "Last 7 Days / Last 30 Days / Last 90 Days / Year To
# Date, to spot trends." Deliberately a NEW, separate function rather than an
# extension of timeline() above -- timeline()'s 6 points are a FORWARD-looking
# forecast-horizon slider (last_week/current/tomorrow/next_week/next_month/
# next_quarter, session 71, already wired to the Reporting tab's own prediction
# slider via core/data_connections_api.py's prediction_timeline_api and the
# "/readiness/timeline/{department}" route). Sam's ask here is purely RETROSPECTIVE
# -- real, already-happened counts across four trailing windows, "to spot trends" --
# a genuinely different question (is performance accelerating or decelerating) from
# timeline()'s forecast-horizon view. Reuses the same real _real_dates_for()
# trailing-window function both already share, but composes it into its own honest
# shape rather than overloading timeline()'s existing consumers.

_TREND_WINDOW_LABELS = {
    "last_7_days": "Last 7 Days",
    "last_30_days": "Last 30 Days",
    "last_90_days": "Last 90 Days",
    "year_to_date": "Year To Date",
}


def _ytd_window_days(today=None):
    today = today or _today()
    jan1 = date(today.year, 1, 1)
    return max((today - jan1).days, 1)


def historical_trend(department):
    """Real trailing-window trend across Last 7 Days / Last 30 Days / Last 90 Days /
    Year To Date for one department -- pure real, already-recorded ledger counts
    (basis="actual" throughout, same label _actual_point() above uses), never a
    forecast or a fabricated number. Also computes a real, simple trend_direction by
    comparing the most recent 7-day daily rate against the trailing-30-day daily rate
    -- an honest momentum signal (>10% change = up/down, else flat), not a fitted
    statistical trend model. Returns None for a department with no real prediction
    source (see DEPARTMENTS above)."""

    if department not in _DEPARTMENT_SOURCES:
        return None

    today = _today()
    baseline = INDUSTRY_BASELINES[department]

    window_days_by_key = {
        "last_7_days": 7,
        "last_30_days": 30,
        "last_90_days": 90,
        "year_to_date": _ytd_window_days(today),
    }

    windows = {}
    for key, window_days in window_days_by_key.items():
        dates = _real_dates_for(department, window_days)
        count = len(dates)
        daily_rate = round(count / window_days, 2) if window_days else 0.0
        windows[key] = {
            "label": _TREND_WINDOW_LABELS[key],
            "window_days": window_days,
            "value": count,
            "daily_rate": daily_rate,
            "basis": "actual",
        }

    recent_rate = windows["last_7_days"]["daily_rate"]
    baseline_rate = windows["last_30_days"]["daily_rate"]

    if baseline_rate == 0 and recent_rate == 0:
        direction = "flat"
    elif baseline_rate == 0:
        direction = "up"
    else:
        change_pct = (recent_rate - baseline_rate) / baseline_rate
        if change_pct > 0.1:
            direction = "up"
        elif change_pct < -0.1:
            direction = "down"
        else:
            direction = "flat"

    return {
        "department": department,
        "metric": baseline["metric"],
        "unit": baseline["unit"],
        "windows": windows,
        "trend_direction": direction,
        "trend_basis": "Last-7-day daily rate vs. trailing-30-day daily rate (>10% change = up/down, else flat) -- a real, simple momentum comparison, not a fitted statistical model.",
        "note": "All values are real, already-recorded ledger counts (basis=\"actual\") -- not a prediction.",
    }


def all_departments_historical_trend():
    return {department: historical_trend(department) for department in DEPARTMENTS}

