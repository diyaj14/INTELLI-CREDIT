
class Scorecard:
    """
    Computes a credit score (0-100) based on multiple inputs.
    """
    



    def compute(self, doc_intel: dict, research: dict) -> dict:
        def safe_num(val, default=0):
            try:
                if val is None: return default
                return float(val)
            except:
                return default

        fin = doc_intel.get("financials", {})
        trends = doc_intel.get("trends", {})
        multi_year = doc_intel.get("multi_year", {})
        
        # Scoring Categories
        scores = {
            "liquidity": 0,    # Max 20
            "solvency": 0,     # Max 20
            "efficiency": 0,   # Max 20
            "market_intel": 0, # Max 20
            "risk_control": 0  # Max 20
        }
        flags = []

        # 1. Liquidity (Max 20)
        cr = safe_num(fin.get("current_ratio"), 0)
        if cr > 1.5: scores["liquidity"] = 20
        elif cr > 1.2: scores["liquidity"] = 15
        elif cr > 1.0: scores["liquidity"] = 10
        else: flags.append("Weak liquidity position (CR < 1.0)")

        # 2. Solvency (Max 20)
        de = safe_num(fin.get("debt_to_equity"), 5)
        icr = safe_num(fin.get("interest_coverage"), 0)
        if de < 0.5: scores["solvency"] += 10
        elif de < 1.5: scores["solvency"] += 7
        elif de > 3: flags.append("Hyphenated leverage detected")
        
        if icr > 3.0: scores["solvency"] += 10
        elif icr > 1.5: scores["solvency"] += 5
        else: flags.append("Low interest coverage")

        # 3. Operating Efficiency/Trends (Max 20)
        growth = safe_num(trends.get("revenue_growth_pct"), 0)
        if growth > 15: scores["efficiency"] = 20
        elif growth > 5: scores["efficiency"] = 15
        elif growth < 0: 
            scores["efficiency"] = 5
            flags.append("Negative revenue growth")

        # 4. Market Intel (Max 20)
        mca = research.get("mca_data", {})
        status = mca.get("status", "").lower()
        if "active" in status: scores["market_intel"] += 10
        else: flags.append("Non-active MCA status")

        sentiment = safe_num(research.get("sentiment_score"), 0.5)
        if sentiment > 0.7: scores["market_intel"] += 10
        elif sentiment > 0.4: scores["market_intel"] += 5
        else: flags.append("Negative market sentiment")

        # 5. Risk Control (Max 20)
        litigation = research.get("litigation", {})
        if not litigation.get("found"): 
            scores["risk_control"] += 10
        else: 
            flags.append("Pending legal disputes detected")

        qual_risks = doc_intel.get("qualitative_risks", [])
        if len(qual_risks) < 3: scores["risk_control"] += 10
        elif len(qual_risks) < 6: scores["risk_control"] += 5
        else: flags.append("High number of qualitative risks reported")


        total_score = sum(scores.values())
        
        # 6. Hard-Reject Logic (Absolute Blocks)
        critical_fail = False
        mca_fail = any(s in status for s in ["struck off", "liquidated", "dormant"])
        if mca_fail:
            flags.append("Critical: Company Status is inactive (Struck Off/Liquidated)")
            critical_fail = True

        # Standardized Decision Thresholds
        if critical_fail or total_score <= 45:
            decision = "REJECT"   # Red
        elif total_score <= 75:
            decision = "REFER"    # Yellow/Manual Review
        else:
            decision = "LEND"     # Green/Auto-Approve


        return {
            "overall_score": total_score,
            "decision": decision,
            "flags": flags,
            "breakdown": {
                "financial": scores["liquidity"] + scores["solvency"] + scores["efficiency"],
                "market": scores["market_intel"],
                "qualitative": scores["risk_control"]
            },
            "detailed_scores": scores
        }

