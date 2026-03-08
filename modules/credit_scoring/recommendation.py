
class RecommendationEngine:
    """
    Suggests loan parameters based on the credit score.
    """

    def suggest(self, score_data: dict, financials: dict) -> dict:
        def _to_f(v):
            try: return float(v) if v is not None else 0.0
            except: return 0.0

        score = _to_f(score_data.get("overall_score"))
        ebitda = _to_f(financials.get("ebitda_cr"))
        revenue = _to_f(financials.get("revenue_cr"))

        
        if score < 40:
            return {
                "limit_cr": 0,
                "interest_rate": 0,
                "rationale": "High risk profile. Lending not recommended."
            }
            
        # Capacity limit = 2.5x EBITDA or 20% of Revenue
        capacity = max(ebitda * 2.5, revenue * 0.20)
        
        # Adjust by score
        multiplier = score / 100.0
        limit = capacity * multiplier
        
        # Interest rate (Risk-based)
        # Base 10% + premium (10 - score/10)
        premium = max(0.5, (100 - score) / 10.0)
        rate = round(10.0 + premium, 1)
        
        return {
            "limit_cr": round(limit, 2),
            "interest_rate": rate,
            "tenure_months": 24 if score > 70 else 12,
            "rationale": f"Limit set at {multiplier*100}% of repayment capacity adjusted for {score} score."
        }
