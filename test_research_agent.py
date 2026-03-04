import json
import os
import sys

# Main entry point for testing the Research Agent (Module 2)
# This script is designed to run within the project's venv.

from modules.research_agent.research_pipeline import run_research

def test_research_agent():
    print("\n" + "="*50)
    print("🚀 INTELLI-CREDIT: Interactive Research Agent")
    print("="*50)
    
    # 1. User Inputs
    company_name = input("\nEnter Company Name (e.g., Zomato Limited): ").strip()
    if not company_name:
        print("❌ Error: Company name is required.")
        return

    promoters_raw = input("Enter Promoter Names (Optional, comma separated. Press Enter to auto-discover): ").strip()
    promoter_list = [p.strip() for p in promoters_raw.split(",") if p.strip()]

    print("\n[Optional] Primary Insight Integration")
    officer_note = input("Enter Credit Officer Notes (e.g., 'Factory visit found low capacity'): ").strip()
    
    image_path = input("Enter Path to Site Visit Photo (Optional, e.g., site.jpg): ").strip()
    if image_path and not os.path.exists(image_path):
        print(f"⚠️ Warning: Image path '{image_path}' not found. Carrying on without Vision.")
        image_path = None

    demo_mode_input = input("\nEnable Demo Mode? (Pre-cached data for Apex Textiles) [y/N]: ").lower().strip()
    demo_mode = demo_mode_input == 'y'

    print("\n" + "-"*30)
    print(f"🔍 Initializing deep search for: {company_name}")
    print("-"*30)

    # 2. Run Pipeline
    try:
        report = run_research(
            company_name=company_name, 
            promoter_names=promoter_list, 
            primary_insights=officer_note, 
            image_path=image_path,
            demo_mode=demo_mode
        )
        
        # 3. Display Results
        print(f"\n✅ RESEARCH COMPLETED for: {report.get('company_name')}")
        print(f"   MCA Status: {report.get('mca_data', {}).get('status')}")
        print(f"   Litigation: {'⚠️ YES' if report.get('litigation', {}).get('found') else '✅ None'}")
        
        if report.get("pdf_report_path"):
            print(f"   📄 PREMIUM PDF MEMO: {report.get('pdf_report_path')}")

        print("\n" + "="*50)
        print("💡 DIGITAL CREDIT MANAGER: ELITE RISK NARRATIVE")
        print("="*50)
        print(report.get("agent_summary", "Agent summary placeholder"))
        print("="*50)
        
        # Save output
        filename = f"research_report_{company_name.replace(' ', '_').lower()}.json"
        with open(filename, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n💾 Full analysis saved to: {filename}")
        
    except Exception as e:
        print(f"\n❌ Research failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_research_agent()
