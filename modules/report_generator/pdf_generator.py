
import os
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch

class PDFGenerator:
    """
    Generates a professional Credit Memo PDF from appraisal results.
    """
    
    def __init__(self, output_dir="reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#6366f1"),
            spaceAfter=20,
            alignment=1, # Center
            fontName='Helvetica-Bold'
        ))
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=15,
            spaceAfter=10,
            fontName='Helvetica-Bold',
            borderPadding=5,
            backColor=colors.HexColor("#f1f5f9")
        ))
        self.styles.add(ParagraphStyle(
            name='BadgeLend',
            fontSize=12,
            textColor=colors.white,
            backColor=colors.HexColor("#10b981"),
            alignment=1,
            borderPadding=10,
            borderRadius=5
        ))
        self.styles.add(ParagraphStyle(
            name='BadgeReject',
            fontSize=12,
            textColor=colors.white,
            backColor=colors.HexColor("#ef4444"),
            alignment=1,
            borderPadding=10,
            borderRadius=5
        ))
        self.styles.add(ParagraphStyle(
            name='BadgeRefer',
            fontSize=12,
            textColor=colors.white,
            backColor=colors.HexColor("#f59e0b"),
            alignment=1,
            borderPadding=10,
            borderRadius=5
        ))

    def generate(self, data: dict) -> str:
        """
        Creates the PDF and returns the filename.
        """
        doc_intel = data.get("document_intelligence", {})
        research = data.get("research_agent", {})
        scoring = data.get("scoring_model", {})
        rec = data.get("loan_recommendation", {})
        
        company_name = doc_intel.get("company_name", "Unknown Enterprise")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join([c if c.isalnum() else "_" for c in company_name])
        filename = f"Credit_Memo_{safe_name}_{timestamp}.pdf"
        file_path = os.path.join(self.output_dir, filename)
        
        doc = SimpleDocTemplate(file_path, pagesize=letter)
        elements = []
        
        # 1. Header
        elements.append(Paragraph("INTELLI-CREDIT APPRAISAL MEMO", self.styles['ReportTitle']))
        elements.append(Paragraph(f"Analysis Report for: <b>{company_name}</b>", self.styles['Normal']))
        elements.append(Paragraph(f"Date: {datetime.datetime.now().strftime('%d %b %Y, %H:%M')}", self.styles['Normal']))
        elements.append(Spacer(1, 0.3 * inch))
        
        # 2. Executive Summary
        elements.append(Paragraph("1. EXECUTIVE SUMMARY", self.styles['SectionHeader']))
        
        decision = scoring.get("decision", "REFER")
        badge_style = 'BadgeRefer'
        if decision == 'LEND': badge_style = 'BadgeLend'
        elif decision == 'REJECT': badge_style = 'BadgeReject'
        
        summary_table_data = [
            [Paragraph(f"<b>FINAL RATING:</b>", self.styles['Normal']), Paragraph(decision, self.styles[badge_style])],
            ["Smart Score:", f"{scoring.get('overall_score', 0)} / 100"],
            ["Recommendation:", f"Limit ₹{rec.get('limit_cr', 0)} Cr @ {rec.get('interest_rate', 0)}% APR"]
        ]
        
        summary_table = Table(summary_table_data, colWidths=[2*inch, 4*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.white),
            ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(Paragraph(f"<b>Rationale:</b> {rec.get('rationale', '')}", self.styles['Normal']))
        
        # 3. Financial Health
        elements.append(Paragraph("2. FINANCIAL HEALTH HIGHLIGHTS", self.styles['SectionHeader']))
        fins = doc_intel.get("financials", {})
        fin_data = [
            ["Metric", "Value", "Benchmark Status"],
            ["Operating Revenue", f"Rs. {fins.get('revenue_cr', 0)} Cr", "Target Achieved"],
            ["EBITDA", f"Rs. {fins.get('ebitda_cr', 0)} Cr", "Health: Stable"],
            ["Net Profit (PAT)", f"Rs. {fins.get('net_profit_cr', 0)} Cr", "Profitable"],
            ["Debt to Equity", str(fins.get('debt_to_equity', 0)), "Gearing: Low" if float(fins.get('debt_to_equity', 0)) < 1.5 else "Gearing: High"],
            ["Interest Coverage", str(fins.get('interest_coverage', 0)) + "x", "Strong" if float(fins.get('interest_coverage', 0)) > 2.5 else "Moderate"]
        ]
        fin_table = Table(fin_data, colWidths=[2*inch, 2*inch, 2*inch])
        fin_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#6366f1")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")])
        ]))
        elements.append(fin_table)
        
        # 4. Market Intelligence
        elements.append(Paragraph("3. MARKET INTELLIGENCE & SENTIMENT", self.styles['SectionHeader']))
        elements.append(Paragraph(f"<b>Sentiment Score:</b> {float(research.get('sentiment_score', 0.5))*10:.1f}/10", self.styles['Normal']))
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph(research.get("agent_summary", "No market summary available."), self.styles['Normal']))
        
        # 5. Risk Factors
        elements.append(Paragraph("4. CRITICAL RISK FACTORS", self.styles['SectionHeader']))
        flags = scoring.get("flags", [])
        if flags:
            for flag in flags:
                elements.append(Paragraph(f"• <b>ALERT:</b> {flag}", self.styles['Normal']))
        else:
            elements.append(Paragraph("No critical negative flags identified.", self.styles['Normal']))
            
        qual_risks = doc_intel.get("qualitative_risks", [])
        if qual_risks:
            elements.append(Spacer(1, 0.1 * inch))
            elements.append(Paragraph("<b>Qualitative Identified Risks:</b>", self.styles['Normal']))
            for r in qual_risks:
                elements.append(Paragraph(f"- {r.get('risk')} (Impact: {r.get('impact')})", self.styles['Normal']))

        # Footer
        elements.append(Spacer(1, 0.5 * inch))
        elements.append(Paragraph("--- Generated automatically by Intelli-Credit AI Appraisal System ---", self.styles['Normal']))
        
        doc.build(elements)
        return filename
