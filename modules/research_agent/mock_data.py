import datetime

# CONTRACT 2 -- ResearchReport (output of M2)
# This mock data represents the "Apex Textiles Pvt Ltd" scenario for integration testing.

research_report = {
    "company_name": "Apex Textiles Pvt Ltd",
    "mca_data": {
        "cin": "U17200MH2010PTC123456",
        "status": "Active",
        "incorporation_date": "2010-04-15",
        "paid_up_capital_cr": 5.0,
        "directors": [
            {"name": "Ramesh Gupta", "din": "00123456", "other_companies": 3}
        ],
        "charges_outstanding": 2,       # existing bank liens on assets
        "struck_off_subsidiaries": 1,
    },
    "litigation": {
        "found": True,
        "cases": [
            {
                "case_id": "2023/NC/142",
                "court": "NCLT Mumbai",
                "parties": "Apex Textiles vs HDFC Bank",
                "status": "Dismissed",
                "source": "eCourts Portal, retrieved 01 Mar 2026"
            }
        ],
        "litigation_score_deduction": 15,
    },
    "news_sentiment": {
        "score": -0.3,                  # -1 (very bad) to +1 (very good)
        "headlines": [
            "Apex Textiles faces supplier payment delays - Economic Times, Jan 2026"
        ],
    },
    "sector_headwinds": "Textile sector NPA at 7.2% (RBI, Q3 FY2024)",
    "promoter_score": 9,                # out of 20
    "research_timestamp": datetime.datetime.now().isoformat(),
}

def get_mock_research_report():
    return research_report
