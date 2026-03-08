
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class HybridMerger:
    """
    Intelligently merges financial data from Document Intelligence (PDF) 
    and Research Agent (Web).
    """

    def merge(self, pdf_intel: Dict[str, Any], research_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cross-verifies PDF data with Web data and merges them.
        """
        merged_doc_intel = pdf_intel.copy()
        pdf_fins = pdf_intel.get("financials", {})
        web_fins = research_data.get("web_financials", {})
        
        flags = []
        discrepancies = []
        
        # Keys to cross-check
        keys_to_check = {
            "revenue_cr": "Operating Revenue",
            "net_profit_cr": "Net Profit",
            "ebitda_cr": "EBITDA"
        }
        
        for key, label in keys_to_check.items():
            pdf_val = float(pdf_fins.get(key, 0) or 0)
            web_val = float(web_fins.get(key, 0) or 0)
            
            # Scenario 1: PDF is zero, but Web has data -> Fill the gap
            if pdf_val == 0 and web_val > 0:
                logger.info(f"Hybrid Fusion: Filling missing {label} from Web source.")
                pdf_fins[key] = web_val
                flags.append(f"Web-Assisted: {label} sourced from online records (PDF missing).")
                
            # Scenario 2: Both have data -> Verify
            elif pdf_val > 0 and web_val > 0:
                diff_pct = abs(pdf_val - web_val) / max(pdf_val, 1)
                if diff_pct > 0.15: # 15% discrepancy threshold
                    logger.warning(f"Hybrid Fusion: Discrepancy in {label}! PDF: {pdf_val}, Web: {web_val}")
                    discrepancies.append(f"Verification Caution: Significant difference in {label} between PDF and Web.")
                    # Keep PDF but flag it
                    
        # Update flags in research_data or back into doc_intel
        merged_doc_intel["financials"] = pdf_fins
        merged_doc_intel["fusion_flags"] = flags
        merged_doc_intel["discrepancies"] = discrepancies
        
        return merged_doc_intel
