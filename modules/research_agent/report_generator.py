from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
import datetime
import os

class CreditReportGenerator:
    """
    Generates a Premium PDF Credit Memo for judges/credit officers.
    """
    
    def generate_pdf(self, report_data: dict, output_path: str):
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Title Section
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.teal,
            alignment=1, # Center
            spaceAfter=20
        )
        
        story.append(Paragraph(f"INTELLI-CREDIT REPORT", title_style))
        story.append(Paragraph(f"Company: {report_data.get('company_name', 'Unknown')}", styles['Heading2']))
        story.append(Paragraph(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
        story.append(Spacer(1, 12))

        # Executive Summary Section
        story.append(Paragraph("1. Executive Risk Narrative", styles['Heading3']))
        summary_text = report_data.get("agent_summary", "Detailed analysis not available.")
        story.append(Paragraph(summary_text.replace("\n", "<br/>"), styles['Normal']))
        story.append(Spacer(1, 12))

        # Data Highlights Table
        story.append(Paragraph("2. Operational Metadata", styles['Heading3']))
        data = [
            ["Metric", "Value"],
            ["MCA Status", report_data.get('mca_data', {}).get('status', 'N/A')],
            ["Litigation Flag", "YES" if report_data.get('litigation', {}).get('found') else "NO"],
            ["News Hits", str(len(report_data.get('news_sentiment', {}).get('headlines', [])))],
            ["Primary Insights", "Integrated" if report_data.get('primary_insights') else "None provided"]
        ]
        
        table = Table(data, colWidths=[150, 300])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.teal),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('GRID', (0,0), (-1,-1), 1, colors.grey),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ]))
        story.append(table)
        story.append(Spacer(1, 12))

        # Headlines Section
        story.append(Paragraph("3. Deep Web Intelligence (Recent Headlines)", styles['Heading3']))
        for headline in report_data.get('news_sentiment', {}).get('headlines', [])[:10]:
            story.append(Paragraph(f"• {headline}", styles['Normal']))
            story.append(Spacer(1, 4))

        # Build PDF
        doc.build(story)
        return output_path
