from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from svglib.svglib import svg2rlg

TWOPLACES = Decimal("0.01")
RED = colors.HexColor("#c41e3a")  # Rosso vivace per intestazioni e totali
HEADER_BG = colors.HexColor("#f2f2f2")  # Grigio leggero

def _q(value) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

def _eur(value) -> str:
    return f"{_q(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _build_logo_flowable(logo_path: str):
    path = Path(logo_path)
    target_size = 50 * mm  # Logo più grande

    if path.suffix.lower() == ".svg":
        drawing = svg2rlg(str(path))
        if drawing is None:
            raise ValueError("Impossibile leggere il logo SVG selezionato.")

        scale = min(target_size / drawing.width, target_size / drawing.height)
        drawing.width *= scale
        drawing.height *= scale
        drawing.scale(scale, scale)
        return drawing

    logo = Image(str(path))
    logo.drawHeight = target_size
    logo.drawWidth = target_size
    return logo

def generate_quote_pdf(items: List[Dict], data: Dict, output_path: str) -> str:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()
    
    # Stili personalizzati
    center_bold = ParagraphStyle(name="CenterBold", parent=styles["Normal"], alignment=TA_CENTER, fontName="Helvetica-Bold", fontSize=13)
    center_norm = ParagraphStyle(name="CenterNorm", parent=styles["Normal"], alignment=TA_CENTER, fontName="Helvetica", fontSize=9)
    title_style = ParagraphStyle(name="TitleStyle", parent=styles["Normal"], alignment=TA_LEFT, fontName="Helvetica-Bold", fontSize=18, textColor=RED)
    title_date = ParagraphStyle(name="TitleDate", parent=styles["Normal"], alignment=TA_RIGHT, fontName="Helvetica", fontSize=9)
    section_red = ParagraphStyle(name="SectionRed", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10, textColor=RED)
    bold_text = ParagraphStyle(name="BoldText", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9)
    normal_text = ParagraphStyle(name="NormText", parent=styles["Normal"], fontName="Helvetica", fontSize=9)
    bold_large = ParagraphStyle(name="BoldLarge", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=12, textColor=RED)

    story = []

    # 1. HEADER - Logo più grande e visibile
    logo_path = data.get("logo_path", "")
    if logo_path and Path(logo_path).exists():
        try:
            logo = _build_logo_flowable(logo_path)
            
            # Centra il logo in una tabella con dimensione aumentata
            logo_table = Table([[logo]], colWidths=[180 * mm])
            logo_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
            story.append(logo_table)
            story.append(Spacer(1, 6 * mm))
        except (OSError, ValueError):
            pass
    
    # Info Azienda Sotto il Logo (nome in centro e bold)
    company_name = data.get("company_name", "")
    if company_name:
        story.append(Paragraph(company_name, center_bold))
        story.append(Spacer(1, 2 * mm))
    
    c_addr = data.get("company_address", "")
    if c_addr:
        story.append(Paragraph(c_addr, center_norm))
        story.append(Spacer(1, 1 * mm))
    
    # Contatti (P.IVA, Email, Telefono) nella stessa riga
    contacts = []
    if data.get("piva"): contacts.append(f"P.IVA: {data.get('piva')}")
    if data.get("email"): contacts.append(f"Email: {data.get('email')}")
    if data.get("phone"): contacts.append(f"Telefono: {data.get('phone')}")
    if contacts:
        story.append(Paragraph(" - ".join(contacts), center_norm))
    
    story.append(Spacer(1, 12 * mm))

    # 2. TITOLO "PREVENTIVO" CENTRATO IN ROSSO CON DATA A DESTRA
    q_num = data.get("quote_number", "")
    q_ver = data.get("version", 1)
    title_text = "PREVENTIVO"
    if q_num:
        title_text += f" N. {q_num}"
    if q_ver and int(q_ver) > 1:
        title_text += f" (v{q_ver})"

    header_table = Table([
        [Paragraph(title_text, title_style), Paragraph(f"Data: {data.get('quote_date', '')}", title_date)]
    ], colWidths=[140 * mm, 40 * mm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),  # Centra PREVENTIVO
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),   # Destra per la data
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
    ]))
    story.append(header_table)
    
    # Linea divisoria sotto il titolo
    line_table = Table([[""], ], colWidths=[180 * mm])
    line_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (0, 0), 1.5, RED),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 8 * mm))

    # 3. SEZIONE CLIENTE (Non in tabella, ma in blocchi)
    story.append(Paragraph("<b>Cliente</b>", section_red))
    client_lines = []
    if data.get("customer_name"):
        client_lines.append(data.get("customer_name"))
    if data.get("customer_address"):
        client_lines.append(data.get("customer_address"))
    if data.get("contact_person"):
        client_lines.append(data.get("contact_person"))
    
    for line in client_lines:
        story.append(Paragraph(line, normal_text))
    
    story.append(Spacer(1, 6 * mm))

    # 4. OGGETTO IN ROSSO (solo il titolo)
    if data.get("oggetto"):
        story.append(Paragraph("<b>Oggetto:</b>", section_red))
        story.append(Paragraph(data.get("oggetto"), normal_text))
        story.append(Spacer(1, 6 * mm))

    # 5. INTESTAZIONE TABELLA IN ROSSO
    story.append(Paragraph("<b>Dettaglio Preventivo</b>", section_red))
    story.append(Spacer(1, 3 * mm))

    # 6. TABELLA ARTICOLI con righe alternate
    table_data = [[
        "Descrizione",
        "Quantità",
        "Prezzo cad.",
        "Importo Tot",
        "C.Iva %",
        "Totale",
    ]]

    totale_generale = Decimal("0")
    totale_imponibile = Decimal("0")
    row_index = 1

    for item in items:
        unit_price = _q(item["unit_price"])
        quantity = _q(item["quantity"])
        total = _q(item["total"])
        vat_percent = _q(item["vat_percent"])
        total_with_vat = _q(item["total_with_vat"])

        totale_generale += total_with_vat
        totale_imponibile += total
        
        # Formattazione quantità senza decimali se è intero
        qty_str = f"{int(quantity)}" if quantity % 1 == 0 else _eur(quantity)

        table_data.append([
            item["name"],
            qty_str,
            _eur(unit_price),
            _eur(total),
            f"{int(vat_percent)}%" if vat_percent % 1 == 0 else _eur(vat_percent),
            _eur(total_with_vat),
        ])
        row_index += 1

    # Aggiungi riga finale con imponibile e totale sulla stessa linea.
    table_data.append(["", "", "", _eur(totale_imponibile), "", _eur(totale_generale)])
    row_totali = len(table_data) - 1

    col_widths = [70 * mm, 16 * mm, 20 * mm, 20 * mm, 16 * mm, 25 * mm]
    quote_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    # Stili tabella: righe alternate di colore
    table_styles = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        
        # Righe dati - alternare colori molto leggeri
        ("ROWBACKGROUNDS", (0, 1), (-1, row_totali - 1), [colors.white, colors.HexColor("#fafafa")]),
        
        # Riga finale: imponibile nero sotto Importo Tot, totale finale rosso sotto Totale
        ("FONTNAME", (3, row_totali), (3, row_totali), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, row_totali), (3, row_totali), colors.black),
        ("FONTNAME", (5, row_totali), (5, row_totali), "Helvetica-Bold"),
        ("TEXTCOLOR", (5, row_totali), (5, row_totali), RED),
        
        # Allineamento colonne
        ("ALIGN", (0, 1), (0, -1), "LEFT"),     # Descrizione sinistra
        ("ALIGN", (1, 1), (1, -1), "CENTER"),   # Quantità centro
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),   # Prezzi e valute destra
        
        # Bordi
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("LINEABOVE", (3, row_totali), (3, row_totali), 0.5, colors.grey),
        ("LINEABOVE", (5, row_totali), (5, row_totali), 0.8, colors.grey),
    ]
    
    quote_table.setStyle(TableStyle(table_styles))
    story.append(quote_table)
    story.append(Spacer(1, 8 * mm))

    # 7. NOTE FINALI (no totale qui, è già in tabella)
    if data.get("final_notes"):
        story.append(Paragraph(data.get("final_notes"), normal_text))

    doc.build(story)
    return str(output_file)