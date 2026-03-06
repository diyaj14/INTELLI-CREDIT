"""
INTELLI-CREDIT — Pillar 3: Scoring Engine + Explainability
=============================================================
ScorecardModel
  Input : FinancialMetrics, GSTReport, ResearchReport, QualitativeNotes
  Output: CreditScore (0–100), Decision (LEND / CONDITIONS / REJECT),
          ScoreBreakdown (per-pillar), ExplainabilityReport

Score Components
────────────────
  Financial Health   : 35 pts  (ratio-based weighted sum)
  GST Compliance     : 20 pts  (mismatch severity → score)
  Promoter Quality   : 20 pts  (litigation + MCA charges → deductions)
  External Intel     : 15 pts  (news sentiment + sector headwinds)
  Officer Override   :±10 pts  (credit-officer qualitative adjustment)

Decision Thresholds
────────────────────
  LEND        : 70 – 100
  CONDITIONS  : 50 –  69
  REJECT      :  0 –  49
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import math


# ─────────────────────────────────────────────────────────────────────────────
# 1.  INPUT DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FinancialMetrics:
    """
    Key financial ratios extracted / computed from audited financials.
    All values are floats; missing / unavailable fields default to None.
    """
    # Liquidity
    current_ratio:          Optional[float] = None   # current assets / current liab.
    quick_ratio:            Optional[float] = None   # (current assets − inventory) / current liab.

    # Leverage
    debt_to_equity:         Optional[float] = None   # total debt / shareholders equity
    interest_coverage:      Optional[float] = None   # EBIT / interest expense

    # Profitability
    net_profit_margin:      Optional[float] = None   # net profit / revenue  (0–1 fraction)
    return_on_assets:       Optional[float] = None   # net profit / total assets (0–1 fraction)
    ebitda_margin:          Optional[float] = None   # EBITDA / revenue (0–1 fraction)

    # Efficiency
    asset_turnover:         Optional[float] = None   # revenue / avg total assets
    receivables_turnover:   Optional[float] = None   # revenue / avg receivables

    # Growth
    revenue_growth_yoy:     Optional[float] = None   # (rev_t − rev_t-1) / rev_t-1 (fraction)


@dataclass
class GSTReport:
    """
    GST-related compliance data.
    """
    filing_compliance_pct:  float = 100.0   # % of returns filed on time  (0–100)
    revenue_mismatch_pct:   float = 0.0     # abs % gap between GSTR-1 & GSTR-3B declared revenue
    itc_mismatch_pct:       float = 0.0     # % ITC claimed vs eligible
    penalty_amount_inr:     float = 0.0     # total GST penalties (INR)
    notices_count:          int   = 0       # outstanding GST notices


@dataclass
class ResearchReport:
    """
    External-intelligence summary produced by the Research Agent.
    """
    # Sentiment: −1.0 (very negative) … +1.0 (very positive)
    news_sentiment_score:   float = 0.0
    # Sector headwind severity: 0 (none) … 1 (severe)
    sector_headwind_score:  float = 0.0
    # Number of negative news articles in the last 12 months
    negative_news_count:    int   = 0
    # Regulatory risk flag
    regulatory_risk_flag:   bool  = False
    # Peer-comparison percentile (0–100); 50 = average, higher = better
    peer_percentile:        float = 50.0


@dataclass
class QualitativeNotes:
    """
    Promoter background + credit-officer qualitative inputs.
    """
    # Promoter / director litigation cases (civil + criminal)
    litigation_cases:       int   = 0
    # MCA-21 charge filings still active
    mca_active_charges:     int   = 0
    # Director-disqualification flag
    director_disqualified:  bool  = False
    # Credit-officer override: −10 … +10 (signed integer)
    officer_override_score: float = 0.0
    # Free-text reason for override (for explainability)
    officer_override_reason: str  = ""


# ─────────────────────────────────────────────────────────────────────────────
# 2.  OUTPUT DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScoreBreakdown:
    financial_health:   float = 0.0   # 0 – 35
    gst_compliance:     float = 0.0   # 0 – 20
    promoter_quality:   float = 0.0   # 0 – 20
    external_intel:     float = 0.0   # 0 – 15
    officer_override:   float = 0.0   # −10 – +10
    total:              float = 0.0   # 0 – 100


@dataclass
class ExplainabilityReport:
    decision:               str = ""
    total_score:            float = 0.0
    breakdown:              ScoreBreakdown = field(default_factory=ScoreBreakdown)
    financial_detail:       dict = field(default_factory=dict)
    gst_detail:             dict = field(default_factory=dict)
    promoter_detail:        dict = field(default_factory=dict)
    external_detail:        dict = field(default_factory=dict)
    override_detail:        dict = field(default_factory=dict)
    flags:                  list = field(default_factory=list)   # critical red-flags
    summary:                str  = ""


# ─────────────────────────────────────────────────────────────────────────────
# 3.  HELPER — SIGMOID-STYLE NORMALISER
# ─────────────────────────────────────────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _score_ratio(
    value: Optional[float],
    good: float,
    bad: float,
    invert: bool = False,
    weight: float = 1.0,
) -> tuple[float, str]:
    """
    Map a single ratio to a [0, weight] score.

    Parameters
    ----------
    value   : observed ratio
    good    : threshold above which full marks are awarded
    bad     : threshold below which zero marks are awarded
    invert  : True for ratios where lower is better (e.g. debt_to_equity)
    weight  : maximum marks this sub-component contributes
    """
    if value is None:
        # Unknown data → conservative 40 % of weight
        raw = 0.40
        quality = "data_missing"
    else:
        if invert:
            value = -value
            good, bad = -good, -bad

        if value >= good:
            raw = 1.0
        elif value <= bad:
            raw = 0.0
        else:
            raw = (value - bad) / (good - bad)
        quality = (
            "strong" if raw >= 0.75
            else "adequate" if raw >= 0.45
            else "weak"
        )

    return round(raw * weight, 3), quality


# ─────────────────────────────────────────────────────────────────────────────
# 4.  PILLAR SCORERS
# ─────────────────────────────────────────────────────────────────────────────

def _score_financial_health(fm: FinancialMetrics) -> tuple[float, dict]:
    """
    Max 35 pts.  Weighted sub-components:

    Liquidity    10 pts  (current_ratio 5 + quick_ratio 5)
    Leverage     10 pts  (debt_to_equity 5 + interest_coverage 5)
    Profitability 10 pts (net_profit_margin 4 + roa 3 + ebitda_margin 3)
    Efficiency    5 pts  (asset_turnover 3 + receivables_turnover 2)
    """
    detail: dict = {}
    total  = 0.0

    # ── Liquidity ──────────────────────────────────────────────────────────
    s, q = _score_ratio(fm.current_ratio,          good=2.0,  bad=1.0,  weight=5.0)
    detail["current_ratio"]        = {"raw": fm.current_ratio,  "score": s, "quality": q}
    total += s

    s, q = _score_ratio(fm.quick_ratio,            good=1.5,  bad=0.75, weight=5.0)
    detail["quick_ratio"]          = {"raw": fm.quick_ratio,    "score": s, "quality": q}
    total += s

    # ── Leverage ───────────────────────────────────────────────────────────
    s, q = _score_ratio(fm.debt_to_equity,         good=0.5,  bad=2.5,  invert=True, weight=5.0)
    detail["debt_to_equity"]       = {"raw": fm.debt_to_equity, "score": s, "quality": q}
    total += s

    s, q = _score_ratio(fm.interest_coverage,      good=5.0,  bad=1.5,  weight=5.0)
    detail["interest_coverage"]    = {"raw": fm.interest_coverage, "score": s, "quality": q}
    total += s

    # ── Profitability ──────────────────────────────────────────────────────
    s, q = _score_ratio(fm.net_profit_margin,      good=0.15, bad=0.02, weight=4.0)
    detail["net_profit_margin"]    = {"raw": fm.net_profit_margin, "score": s, "quality": q}
    total += s

    s, q = _score_ratio(fm.return_on_assets,       good=0.10, bad=0.01, weight=3.0)
    detail["return_on_assets"]     = {"raw": fm.return_on_assets,  "score": s, "quality": q}
    total += s

    s, q = _score_ratio(fm.ebitda_margin,          good=0.20, bad=0.05, weight=3.0)
    detail["ebitda_margin"]        = {"raw": fm.ebitda_margin,     "score": s, "quality": q}
    total += s

    # ── Efficiency ─────────────────────────────────────────────────────────
    s, q = _score_ratio(fm.asset_turnover,         good=1.5,  bad=0.3,  weight=3.0)
    detail["asset_turnover"]       = {"raw": fm.asset_turnover,    "score": s, "quality": q}
    total += s

    s, q = _score_ratio(fm.receivables_turnover,   good=8.0,  bad=2.0,  weight=2.0)
    detail["receivables_turnover"] = {"raw": fm.receivables_turnover, "score": s, "quality": q}
    total += s

    total = _clamp(round(total, 2), 0.0, 35.0)
    return total, detail


def _score_gst_compliance(gst: GSTReport) -> tuple[float, dict]:
    """
    Max 20 pts.

    Filing compliance      :  8 pts  (% on-time filings)
    Revenue mismatch       :  6 pts  (lower mismatch → higher score)
    ITC mismatch           :  3 pts
    Penalty / notices      :  3 pts  (deductions)
    """
    detail: dict = {}
    total  = 0.0

    # Filing compliance (0–100 %) → 0–8 pts
    filing_score = (gst.filing_compliance_pct / 100.0) * 8.0
    detail["filing_compliance"] = {
        "pct": gst.filing_compliance_pct,
        "score": round(filing_score, 2),
    }
    total += filing_score

    # Revenue mismatch (0 % = 6 pts; ≥20 % = 0 pts)
    rev_score = max(0.0, 6.0 * (1 - gst.revenue_mismatch_pct / 20.0))
    detail["revenue_mismatch"] = {
        "pct": gst.revenue_mismatch_pct,
        "score": round(rev_score, 2),
        "severity": (
            "high" if gst.revenue_mismatch_pct >= 15
            else "medium" if gst.revenue_mismatch_pct >= 5
            else "low"
        ),
    }
    total += rev_score

    # ITC mismatch (0 % = 3 pts; ≥30 % = 0 pts)
    itc_score = max(0.0, 3.0 * (1 - gst.itc_mismatch_pct / 30.0))
    detail["itc_mismatch"] = {
        "pct": gst.itc_mismatch_pct,
        "score": round(itc_score, 2),
    }
    total += itc_score

    # Penalty + notices (full 3 pts minus deductions)
    penalty_deduction = _clamp(gst.penalty_amount_inr / 1_000_000, 0, 1.5)  # up to 1.5 pts
    notice_deduction  = _clamp(gst.notices_count * 0.5, 0, 1.5)             # up to 1.5 pts
    pn_score          = max(0.0, 3.0 - penalty_deduction - notice_deduction)
    detail["penalty_notices"] = {
        "penalty_inr": gst.penalty_amount_inr,
        "notices":     gst.notices_count,
        "deduction":   round(penalty_deduction + notice_deduction, 2),
        "score":       round(pn_score, 2),
    }
    total += pn_score

    total = _clamp(round(total, 2), 0.0, 20.0)
    return total, detail


def _score_promoter_quality(qual: QualitativeNotes) -> tuple[float, dict]:
    """
    Max 20 pts — starts full, then applies deductions.

    Litigation cases    : −3 pts each (max −12)
    MCA active charges  : −2 pts each (max −8)
    Director disqualif  : −10 pts (hard deduction, not capped by above)
    """
    detail: dict = {}
    base   = 20.0

    lit_deduction = _clamp(qual.litigation_cases * 3.0, 0.0, 12.0)
    detail["litigation"] = {
        "count":     qual.litigation_cases,
        "deduction": lit_deduction,
    }

    mca_deduction = _clamp(qual.mca_active_charges * 2.0, 0.0, 8.0)
    detail["mca_charges"] = {
        "count":     qual.mca_active_charges,
        "deduction": mca_deduction,
    }

    disq_deduction = 10.0 if qual.director_disqualified else 0.0
    detail["director_disqualified"] = {
        "flag":      qual.director_disqualified,
        "deduction": disq_deduction,
    }

    total = _clamp(base - lit_deduction - mca_deduction - disq_deduction, 0.0, 20.0)
    detail["total_deduction"] = round(lit_deduction + mca_deduction + disq_deduction, 2)

    return round(total, 2), detail


def _score_external_intel(res: ResearchReport) -> tuple[float, dict]:
    """
    Max 15 pts.

    News sentiment      :  6 pts  (−1…+1 → 0…6)
    Sector headwinds    :  4 pts  (0 = none → 4 pts; 1 = severe → 0 pts)
    Negative news count :  3 pts  (0 articles = 3; ≥10 = 0)
    Peer percentile     :  2 pts  (0 %ile = 0; 100 %ile = 2)
    Regulatory risk     : −2 pts deduction if flagged
    """
    detail: dict = {}
    total  = 0.0

    # News sentiment (−1…+1) → 0…6 pts
    sentiment_score = ((res.news_sentiment_score + 1.0) / 2.0) * 6.0
    detail["news_sentiment"] = {
        "raw":   res.news_sentiment_score,
        "score": round(sentiment_score, 2),
    }
    total += sentiment_score

    # Sector headwinds (0 = no risk → 4 pts)
    headwind_score = (1.0 - res.sector_headwind_score) * 4.0
    detail["sector_headwinds"] = {
        "raw":      res.sector_headwind_score,
        "score":    round(headwind_score, 2),
        "severity": (
            "high"   if res.sector_headwind_score >= 0.7
            else "medium" if res.sector_headwind_score >= 0.4
            else "low"
        ),
    }
    total += headwind_score

    # Negative news count
    neg_score = max(0.0, 3.0 * (1 - res.negative_news_count / 10.0))
    detail["negative_news"] = {
        "count": res.negative_news_count,
        "score": round(neg_score, 2),
    }
    total += neg_score

    # Peer percentile
    peer_score = (res.peer_percentile / 100.0) * 2.0
    detail["peer_percentile"] = {
        "raw":   res.peer_percentile,
        "score": round(peer_score, 2),
    }
    total += peer_score

    # Regulatory risk deduction
    reg_deduction = 2.0 if res.regulatory_risk_flag else 0.0
    detail["regulatory_risk"] = {
        "flag":      res.regulatory_risk_flag,
        "deduction": reg_deduction,
    }
    total -= reg_deduction

    total = _clamp(round(total, 2), 0.0, 15.0)
    return total, detail


def _score_officer_override(qual: QualitativeNotes) -> tuple[float, dict]:
    """
    Credit officer qualitative adjustment: −10 … +10 pts (clamped).
    """
    score = _clamp(qual.officer_override_score, -10.0, 10.0)
    detail = {
        "score":  score,
        "reason": qual.officer_override_reason or "No override applied.",
    }
    return round(score, 2), detail


# ─────────────────────────────────────────────────────────────────────────────
# 5.  DECISION MAPPER
# ─────────────────────────────────────────────────────────────────────────────

def _map_decision(total: float) -> str:
    if total >= 70:
        return "LEND"
    elif total >= 50:
        return "CONDITIONS"
    else:
        return "REJECT"


# ─────────────────────────────────────────────────────────────────────────────
# 6.  SCORECARD MODEL  (main public class)
# ─────────────────────────────────────────────────────────────────────────────

class ScorecardModel:
    """
    Orchestrates all pillar scorers, assembles the total credit score,
    maps to a lending decision, and returns a full ExplainabilityReport.

    Usage
    -----
    model  = ScorecardModel()
    report = model.score(
        financial_metrics = fm,
        gst_report        = gst,
        research_report   = res,
        qualitative_notes = qual,
    )
    print(report.decision, report.total_score)
    """

    def score(
        self,
        financial_metrics: FinancialMetrics,
        gst_report:        GSTReport,
        research_report:   ResearchReport,
        qualitative_notes: QualitativeNotes,
    ) -> ExplainabilityReport:

        # ── Run all pillar scorers ─────────────────────────────────────────
        fin_score,  fin_detail  = _score_financial_health(financial_metrics)
        gst_score,  gst_detail  = _score_gst_compliance(gst_report)
        prom_score, prom_detail = _score_promoter_quality(qualitative_notes)
        ext_score,  ext_detail  = _score_external_intel(research_report)
        ovr_score,  ovr_detail  = _score_officer_override(qualitative_notes)

        # ── Aggregate ─────────────────────────────────────────────────────
        raw_total = fin_score + gst_score + prom_score + ext_score + ovr_score
        total     = _clamp(round(raw_total, 2), 0.0, 100.0)
        decision  = _map_decision(total)

        breakdown = ScoreBreakdown(
            financial_health = fin_score,
            gst_compliance   = gst_score,
            promoter_quality = prom_score,
            external_intel   = ext_score,
            officer_override = ovr_score,
            total            = total,
        )

        # ── Collect red-flags ─────────────────────────────────────────────
        flags = []
        if qualitative_notes.director_disqualified:
            flags.append("🚨 DIRECTOR DISQUALIFICATION: Mandatory enhanced due diligence.")
        if gst_report.revenue_mismatch_pct >= 15:
            flags.append(f"⚠️  HIGH GST REVENUE MISMATCH: {gst_report.revenue_mismatch_pct:.1f}% gap detected.")
        if qualitative_notes.litigation_cases >= 3:
            flags.append(f"⚠️  MULTIPLE LITIGATION CASES: {qualitative_notes.litigation_cases} active cases.")
        if research_report.regulatory_risk_flag:
            flags.append("⚠️  REGULATORY RISK FLAG raised by Research Agent.")
        if research_report.news_sentiment_score <= -0.5:
            flags.append(f"📰 NEGATIVE NEWS SENTIMENT: {research_report.news_sentiment_score:.2f}")
        if financial_metrics.interest_coverage is not None and financial_metrics.interest_coverage < 1.5:
            flags.append(f"💸 INTEREST COVERAGE BELOW 1.5× ({financial_metrics.interest_coverage}×) — debt servicing risk.")
        if gst_report.notices_count >= 3:
            flags.append(f"📋 {gst_report.notices_count} OUTSTANDING GST NOTICES.")

        # ── Narrative summary ─────────────────────────────────────────────
        decision_label = {
            "LEND":       "✅ LEND — creditworthy, proceed with standard terms.",
            "CONDITIONS": "🟡 LEND WITH CONDITIONS — acceptable risk, attach covenants.",
            "REJECT":     "❌ REJECT — risk profile exceeds acceptable threshold.",
        }[decision]

        summary_lines = [
            f"Total Credit Score: {total:.1f} / 100",
            f"Decision          : {decision_label}",
            "",
            "Score Breakdown:",
            f"  Financial Health   : {fin_score:>5.1f} / 35",
            f"  GST Compliance     : {gst_score:>5.1f} / 20",
            f"  Promoter Quality   : {prom_score:>5.1f} / 20",
            f"  External Intel     : {ext_score:>5.1f} / 15",
            f"  Officer Override   : {ovr_score:>+6.1f} / ±10",
            f"  ─────────────────────────────",
            f"  TOTAL              : {total:>5.1f} / 100",
        ]
        if flags:
            summary_lines += ["", "Red Flags:"] + [f"  {f}" for f in flags]
        if qualitative_notes.officer_override_reason:
            summary_lines += [
                "",
                f"Officer Override Reason: {qualitative_notes.officer_override_reason}",
            ]

        return ExplainabilityReport(
            decision         = decision,
            total_score      = total,
            breakdown        = breakdown,
            financial_detail = fin_detail,
            gst_detail       = gst_detail,
            promoter_detail  = prom_detail,
            external_detail  = ext_detail,
            override_detail  = ovr_detail,
            flags            = flags,
            summary          = "\n".join(summary_lines),
        )
