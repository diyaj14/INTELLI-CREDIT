"""
INTELLI-CREDIT — Pillar 3 Test Suite
=====================================
Three representative applicant profiles:
  1. Healthy SME        → expected LEND
  2. Borderline Firm    → expected CONDITIONS
  3. Distressed Entity  → expected REJECT
"""

from scorecard_model import (
    ScorecardModel,
    FinancialMetrics,
    GSTReport,
    ResearchReport,
    QualitativeNotes,
)

model = ScorecardModel()


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Healthy SME  (expected: LEND ≥ 70)
# ─────────────────────────────────────────────────────────────────────────────
def test_lend_case():
    fm = FinancialMetrics(
        current_ratio=2.4,
        quick_ratio=1.8,
        debt_to_equity=0.4,
        interest_coverage=7.2,
        net_profit_margin=0.18,
        return_on_assets=0.12,
        ebitda_margin=0.22,
        asset_turnover=1.6,
        receivables_turnover=9.0,
        revenue_growth_yoy=0.14,
    )
    gst = GSTReport(
        filing_compliance_pct=98.0,
        revenue_mismatch_pct=1.5,
        itc_mismatch_pct=2.0,
        penalty_amount_inr=0,
        notices_count=0,
    )
    res = ResearchReport(
        news_sentiment_score=0.6,
        sector_headwind_score=0.2,
        negative_news_count=1,
        regulatory_risk_flag=False,
        peer_percentile=75.0,
    )
    qual = QualitativeNotes(
        litigation_cases=0,
        mca_active_charges=0,
        director_disqualified=False,
        officer_override_score=2.0,
        officer_override_reason="Promoters have 15 yrs sector experience; management depth is strong.",
    )

    report = model.score(fm, gst, res, qual)
    print("=" * 60)
    print("TEST 1 — Healthy SME")
    print("=" * 60)
    print(report.summary)
    print()
    assert report.decision == "LEND", f"Expected LEND, got {report.decision}"
    assert report.total_score >= 70, f"Expected ≥70, got {report.total_score}"
    print("✅ PASSED\n")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — Borderline Firm  (expected: CONDITIONS 50–69)
# ─────────────────────────────────────────────────────────────────────────────
def test_conditions_case():
    fm = FinancialMetrics(
        current_ratio=1.5,
        quick_ratio=1.1,
        debt_to_equity=1.2,
        interest_coverage=2.8,
        net_profit_margin=0.07,
        return_on_assets=0.06,
        ebitda_margin=0.12,
        asset_turnover=1.0,
        receivables_turnover=5.5,
        revenue_growth_yoy=0.05,
    )
    gst = GSTReport(
        filing_compliance_pct=88.0,
        revenue_mismatch_pct=6.0,
        itc_mismatch_pct=8.0,
        penalty_amount_inr=150_000,
        notices_count=1,
    )
    res = ResearchReport(
        news_sentiment_score=0.1,
        sector_headwind_score=0.45,
        negative_news_count=3,
        regulatory_risk_flag=False,
        peer_percentile=45.0,
    )
    qual = QualitativeNotes(
        litigation_cases=1,
        mca_active_charges=1,
        director_disqualified=False,
        officer_override_score=0.0,
        officer_override_reason="",
    )

    report = model.score(fm, gst, res, qual)
    print("=" * 60)
    print("TEST 2 — Borderline Firm")
    print("=" * 60)
    print(report.summary)
    print()
    assert report.decision == "CONDITIONS", f"Expected CONDITIONS, got {report.decision}"
    assert 50 <= report.total_score < 70, f"Expected 50–69, got {report.total_score}"
    print("✅ PASSED\n")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — Distressed Entity  (expected: REJECT < 50)
# ─────────────────────────────────────────────────────────────────────────────
def test_reject_case():
    fm = FinancialMetrics(
        current_ratio=0.7,
        quick_ratio=0.4,
        debt_to_equity=3.5,
        interest_coverage=0.9,
        net_profit_margin=-0.05,
        return_on_assets=-0.02,
        ebitda_margin=0.02,
        asset_turnover=0.4,
        receivables_turnover=2.5,
        revenue_growth_yoy=-0.12,
    )
    gst = GSTReport(
        filing_compliance_pct=55.0,
        revenue_mismatch_pct=22.0,
        itc_mismatch_pct=35.0,
        penalty_amount_inr=2_500_000,
        notices_count=5,
    )
    res = ResearchReport(
        news_sentiment_score=-0.7,
        sector_headwind_score=0.85,
        negative_news_count=12,
        regulatory_risk_flag=True,
        peer_percentile=10.0,
    )
    qual = QualitativeNotes(
        litigation_cases=4,
        mca_active_charges=3,
        director_disqualified=True,
        officer_override_score=-8.0,
        officer_override_reason="Director has prior fraud conviction. Site visit revealed significant stock discrepancy.",
    )

    report = model.score(fm, gst, res, qual)
    print("=" * 60)
    print("TEST 3 — Distressed Entity")
    print("=" * 60)
    print(report.summary)
    print()
    assert report.decision == "REJECT", f"Expected REJECT, got {report.decision}"
    assert report.total_score < 50, f"Expected <50, got {report.total_score}"
    print("✅ PASSED\n")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4 — Missing financial data (robustness)
# ─────────────────────────────────────────────────────────────────────────────
def test_missing_data():
    fm  = FinancialMetrics()          # all None
    gst = GSTReport()
    res = ResearchReport()
    qual = QualitativeNotes()

    report = model.score(fm, gst, res, qual)
    print("=" * 60)
    print("TEST 4 — Missing / Default Data (robustness)")
    print("=" * 60)
    print(report.summary)
    print()
    assert report.total_score >= 0, "Score must be non-negative"
    assert report.decision in ("LEND", "CONDITIONS", "REJECT")
    print("✅ PASSED\n")


if __name__ == "__main__":
    test_lend_case()
    test_conditions_case()
    test_reject_case()
    test_missing_data()
    print("=" * 60)
    print("ALL TESTS PASSED ✅")
    print("=" * 60)
