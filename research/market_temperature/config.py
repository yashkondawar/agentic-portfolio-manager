"""Configuration for the Market Temperature research module.

Every threshold here is a *judgement*, not a fitted parameter. They come from the
original countercyclical framework's stated rules. They were NOT optimised on the
data, which is deliberate: an un-tuned weak signal is more trustworthy than a
tuned one. See VALIDATION.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Market:
    """A tracked index.

    `div_yield` is used to convert a price index into an approximate total-return
    index. Price indices understate long-horizon returns, which matters a lot for
    rules phrased as "has the market gone nowhere for N years?" — over 12 years a
    1.3%/yr dividend compounds to ~17pp, wider than the rule's own +/-15pp band.
    """

    key: str
    label: str
    ticker: str
    div_yield: float
    currency: str = "INR"
    note: str = ""


MARKETS: dict[str, Market] = {
    "nifty": Market(
        key="nifty",
        label="NIFTY 50",
        ticker="^NSEI",
        div_yield=0.0130,
        note="Indian large-cap. History from late 2007 on Yahoo.",
    ),
    "sensex": Market(
        key="sensex",
        label="SENSEX",
        ticker="^BSESN",
        div_yield=0.0130,
        note="Longest usable Indian history (1997+). Best sample for evidence tables.",
    ),
    "nasdaq": Market(
        key="nasdaq",
        label="NASDAQ Composite",
        ticker="^IXIC",
        div_yield=0.0090,
        currency="USD",
        note="Included as an out-of-sample control. The signal does NOT work here.",
    ),
}

DEFAULT_MARKET = "sensex"

# Cash / liquid-fund yield used when framing the "park it instead" alternative.
CASH_YIELD = 0.06

# Minimum history before any rule is allowed to speak.
MIN_HISTORY_YEARS = 5


@dataclass(frozen=True)
class RuleSpec:
    """Metadata for one rule. `weight` is the vote weight in the composite."""

    key: str
    label: str
    weight: float
    horizon: str
    question: str
    #: Plain-English meaning of a positive score, for the UI.
    bullish_means: str
    bearish_means: str


RULE_SPECS: dict[str, RuleSpec] = {
    "12y_flat": RuleSpec(
        key="12y_flat",
        label="12-year flat market",
        weight=2.0,
        horizon="12 years",
        question="Has the market gone essentially nowhere for 12 years?",
        bullish_means="A dozen lost years usually precedes a strong decade.",
        bearish_means="n/a — this rule only ever votes bullish.",
    ),
    "10y_hot": RuleSpec(
        key="10y_hot",
        label="10-year run too hot",
        weight=1.5,
        horizon="10 years",
        question="Has the market compounded unusually fast for a decade?",
        bullish_means="n/a — this rule only ever votes bearish.",
        bearish_means="A decade of >20%/yr is rarely repeated from the same base.",
    ),
    "8y_flat": RuleSpec(
        key="8y_flat",
        label="8-year flat market",
        weight=1.5,
        horizon="8 years",
        question="Has the market gone essentially nowhere for 8 years?",
        bullish_means="Extended stagnation tends to resolve upward.",
        bearish_means="n/a — this rule only ever votes bullish.",
    ),
    "5y_vs_cash": RuleSpec(
        key="5y_vs_cash",
        label="5-year return below cash",
        weight=1.0,
        horizon="5 years",
        question="Has equity underperformed a savings account over 5 years?",
        bullish_means="Equity has not been paid for its risk; expectations are low.",
        bearish_means="n/a — this rule only ever votes bullish.",
    ),
    "3y_flat": RuleSpec(
        key="3y_flat",
        label="3-year drift",
        weight=1.0,
        horizon="3 years",
        question="Has the market drifted sideways for 3 years?",
        bullish_means="Sideways consolidation, not collapse — a base may be forming.",
        bearish_means="n/a — this rule only ever votes bullish.",
    ),
    "bubble": RuleSpec(
        key="bubble",
        label="Parabolic move",
        weight=1.5,
        horizon="1-2 years",
        question="Has the market roughly tripled in 1-2 years?",
        bullish_means="n/a — this rule only ever votes bearish.",
        bearish_means="Vertical moves of this size have historically ended badly.",
    ),
    "drawdown": RuleSpec(
        key="drawdown",
        label="Deep active drawdown",
        weight=1.0,
        horizon="12 months",
        question="Is the market *currently* 30-55% below its recent peak?",
        bullish_means="A deep, still-ongoing correction is the classic entry point.",
        bearish_means="n/a — this rule only ever votes bullish.",
    ),
}

#: Rules that empirically never fire on 24y of Indian data. Kept for completeness
#: and transparency, flagged in the UI so you know they are decorative.
DORMANT_RULES = ("12y_flat", "8y_flat", "bubble")


@dataclass(frozen=True)
class TemperatureBand:
    key: str
    label: str
    colour: str
    headline: str
    guidance: str


#: Most of the time no rule fires at all and the composite score is exactly zero.
#: That state is genuinely "no opinion", and it must be reported as such.
#:
#: An earlier version of this module ranked today's score as a percentile of all
#: past scores. Because zero is by far the most common value, a completely silent
#: signal scored in the 82nd percentile and was labelled "Cool - deploy faster".
#: That is precisely the failure mode this module exists to avoid: manufacturing
#: a confident-sounding recommendation out of nothing.
#:
#: So: zero means Neutral, always. Ranking is only used to grade the *intensity*
#: of a score that is genuinely non-zero, and only against other scores of the
#: same sign.
NEUTRAL_TOLERANCE = 1e-9

#: Within same-signed scores, readings at or above this rank are "extreme".
EXTREME_RANK = 0.60

TEMPERATURE_BANDS: dict[str, TemperatureBand] = {
    "hot": TemperatureBand(
        key="hot",
        label="Hot",
        colour="#c62828",
        headline="Strongly stretched by this framework's standards",
        guidance=(
            "Deploy new money slowly. Keep SIPs running — stopping them is how "
            "people miss recoveries — but hold lump sums back and let cash build."
        ),
    ),
    "warm": TemperatureBand(
        key="warm",
        label="Warm",
        colour="#ef6c00",
        headline="Mildly stretched",
        guidance=(
            "Stay invested and keep SIPs running. There is no urgency to add new "
            "money; spreading lump sums over a longer window is reasonable."
        ),
    ),
    "neutral": TemperatureBand(
        key="neutral",
        label="Neutral",
        colour="#616161",
        headline="No signal — nothing unusual is happening",
        guidance=(
            "No rule is firing. This is the normal state roughly four months in "
            "five, and it is not a hedged way of saying 'be careful'. Follow your "
            "existing plan and ignore this page until something changes."
        ),
    ),
    "cool": TemperatureBand(
        key="cool",
        label="Cool",
        colour="#2e7d32",
        headline="Mildly cheap by this framework's standards",
        guidance=(
            "A reasonable moment to deploy idle cash a little faster than your "
            "default pace. Do not sell anything else to fund it."
        ),
    ),
    "cold": TemperatureBand(
        key="cold",
        label="Cold",
        colour="#1b5e20",
        headline="Strongly cheap by this framework's standards",
        guidance=(
            "Historically these have been the best moments to put money to work, "
            "and the hardest. Deploy dry powder faster. Expect it to feel wrong; "
            "that feeling is the price of the return."
        ),
    ),
}


def classify_score(score: float, rank_within_sign: float) -> TemperatureBand:
    """Map a composite score to a band.

    `rank_within_sign` is the score's rank among historical scores of the *same
    sign*, in 0-1. It is ignored when the score is zero.
    """
    if abs(score) <= NEUTRAL_TOLERANCE:
        return TEMPERATURE_BANDS["neutral"]
    if score > 0:
        return TEMPERATURE_BANDS["cold" if rank_within_sign >= EXTREME_RANK else "cool"]
    return TEMPERATURE_BANDS["hot" if rank_within_sign >= EXTREME_RANK else "warm"]


@dataclass(frozen=True)
class DeploymentPlan:
    """Suggested pace for deploying *new* cash. Never a sell instruction."""

    band_key: str
    sip_multiplier: float
    lumpsum_tranches: int
    tranche_note: str


#: The signal is far too weak to justify trading an existing portfolio (turnover
#: costs and capital-gains tax exceed the measured edge). It is strong enough to
#: tilt the *pace* at which new money is deployed, because that decision has to
#: be made anyway and costs nothing extra. See VALIDATION.md section 8.
DEPLOYMENT_PLANS: dict[str, DeploymentPlan] = {
    "hot": DeploymentPlan("hot", 1.0, 6, "Spread a lump sum over ~6 months."),
    "warm": DeploymentPlan("warm", 1.0, 4, "Spread a lump sum over ~4 months."),
    "neutral": DeploymentPlan("neutral", 1.0, 3, "Spread a lump sum over ~3 months."),
    "cool": DeploymentPlan("cool", 1.5, 2, "Spread a lump sum over ~2 months."),
    "cold": DeploymentPlan("cold", 2.0, 1, "Deploying in one or two goes is defensible."),
}

#: Buckets used for the "what happened next" evidence table.
FORWARD_HORIZONS_MONTHS: tuple[int, ...] = (12, 36, 60)

CACHE_NAMESPACE = "market_temperature"
CACHE_TTL_HOURS = 12
