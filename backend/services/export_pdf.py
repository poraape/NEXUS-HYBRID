from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO

def build_pdf(dataset: dict):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, dataset.get("title","Relatório Fiscal")); y -= 30
    c.setFont("Helvetica-Bold", 12); c.drawString(50, y, "KPIs"); y -= 20
    c.setFont("Helvetica", 10)
    for k in dataset.get("kpis", []):
        c.drawString(60, y, f"- {k.get('label')}: {k.get('value')}"); y -= 15
    y -= 10; c.setFont("Helvetica-Bold", 12); c.drawString(50, y, "Inconsistências"); y -= 20
    c.setFont("Helvetica", 10)
    for i in dataset.get("compliance",{}).get("inconsistencies",[]):
        line = f"[{i.get('severity')}] {i.get('field')} - {i.get('code')}: {i.get('message')}"
        c.drawString(60, y, line[:110]); y -= 14
        if y < 80:
            c.showPage(); y = h - 50
    c.showPage(); c.save()
    return buf.getvalue(), "relatorio.pdf"
