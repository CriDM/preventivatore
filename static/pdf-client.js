/**
 * Preventivatore - Client-Side PDF Generator (jsPDF + AutoTable)
 * Enables 100% offline PDF creation, previewing, and downloading.
 */

function formatEuro(val) {
  const num = parseFloat(val) || 0;
  return num.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
}

/**
 * Generates a PDF blob or downloads/opens preview using jsPDF client-side.
 * @param {Object} data - Quote data (quote_number, version, customer_name, customer_address, contact_person, oggetto, quote_date, final_notes, show_vat, company info)
 * @param {Array} items - List of items [{name, quantity, unit_price, vat_percent, total, total_with_vat}]
 * @param {Object} company - Company metadata (company_name, company_address, piva, email, phone, logo_url)
 * @param {Object} options - { preview: boolean, download: boolean, filename: string }
 */
async function generateClientPdf(data, items, company, options = {}) {
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({
    orientation: 'p',
    unit: 'mm',
    format: 'a4'
  });

  const redColor = [196, 30, 58]; // Hex #c41e3a
  const darkTextColor = [15, 23, 42]; // #0f172a
  const mutedTextColor = [100, 116, 139]; // #64748b

  let y = 12; // Top margin mm

  // 1. Logo Handling (if available)
  const logoDataUrl = company?.logo_data_url || company?.logo_url || '/static/logo.png';
  if (logoDataUrl) {
    try {
      const img = new Image();
      img.crossOrigin = 'Anonymous';
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = resolve; // Continue if logo fails
        img.src = logoDataUrl;
      });

      if (img.complete && img.naturalWidth > 0) {
        const logoWidth = 40; // mm
        const logoHeight = (img.naturalHeight / img.naturalWidth) * logoWidth;
        const logoX = (210 - logoWidth) / 2; // Center horizontally
        doc.addImage(img, 'PNG', logoX, y, logoWidth, Math.min(logoHeight, 25));
        y += Math.min(logoHeight, 25) + 4;
      }
    } catch (e) {
      console.warn('[PDF-Client] Could not render logo:', e);
    }
  }

  // 2. Company Info (Centered)
  const companyName = company?.company_name || 'Croce e Cuore Arte Sacra';
  doc.setFont('Helvetica', 'bold');
  doc.setFontSize(13);
  doc.setTextColor(...darkTextColor);
  doc.text(companyName, 105, y, { align: 'center' });
  y += 5;

  const companyAddress = company?.company_address || '';
  if (companyAddress) {
    doc.setFont('Helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(...mutedTextColor);
    doc.text(companyAddress, 105, y, { align: 'center' });
    y += 4;
  }

  const contacts = [];
  if (company?.piva) contacts.push(`P.IVA: ${company.piva}`);
  if (company?.email) contacts.push(`Email: ${company.email}`);
  if (company?.phone) contacts.push(`Tel: ${company.phone}`);
  if (contacts.length > 0) {
    doc.setFont('Helvetica', 'normal');
    doc.setFontSize(8.5);
    doc.setTextColor(...mutedTextColor);
    doc.text(contacts.join('  |  '), 105, y, { align: 'center' });
    y += 6;
  }

  // Divider Line
  doc.setDrawColor(226, 232, 240);
  doc.setLineWidth(0.4);
  doc.line(12, y, 198, y);
  y += 7;

  // 3. Document Title & Date
  const quoteNum = data.quote_number || 'BOZZA';
  const ver = data.version ? ` v${data.version}` : '';
  const titleText = `PREVENTIVO N. ${quoteNum}${ver}`;

  doc.setFont('Helvetica', 'bold');
  doc.setFontSize(16);
  doc.setTextColor(...redColor);
  doc.text(titleText, 12, y);

  const quoteDate = data.quote_date || new Date().toLocaleDateString('it-IT');
  doc.setFont('Helvetica', 'normal');
  doc.setFontSize(9.5);
  doc.setTextColor(...darkTextColor);
  doc.text(`Data: ${quoteDate}`, 198, y, { align: 'right' });
  y += 8;

  // 4. Customer Info
  if (data.customer_name || data.customer_address || data.contact_person) {
    doc.setFont('Helvetica', 'bold');
    doc.setFontSize(10);
    doc.setTextColor(...redColor);
    doc.text('Spettabile Cliente:', 12, y);
    y += 5;

    doc.setFont('Helvetica', 'bold');
    doc.setFontSize(9.5);
    doc.setTextColor(...darkTextColor);
    doc.text(data.customer_name || '-', 12, y);
    y += 4.5;

    if (data.customer_address) {
      doc.setFont('Helvetica', 'normal');
      doc.setFontSize(9);
      doc.text(data.customer_address, 12, y);
      y += 4.5;
    }

    if (data.contact_person) {
      doc.setFont('Helvetica', 'normal');
      doc.setFontSize(9);
      doc.text(`C.A.: ${data.contact_person}`, 12, y);
      y += 4.5;
    }
    y += 2;
  }

  // 5. Oggetto
  if (data.oggetto) {
    doc.setFont('Helvetica', 'bold');
    doc.setFontSize(10);
    doc.setTextColor(...redColor);
    doc.text('Oggetto:', 12, y);
    y += 4.5;

    doc.setFont('Helvetica', 'normal');
    doc.setFontSize(9.5);
    doc.setTextColor(...darkTextColor);
    const splitOggetto = doc.splitTextToSize(data.oggetto, 186);
    doc.text(splitOggetto, 12, y);
    y += (splitOggetto.length * 4.5) + 3;
  }

  // 6. Items Table
  const showVat = data.show_vat !== undefined ? Boolean(data.show_vat) : true;

  const tableHeaders = showVat
    ? [['Articolo / Descrizione', 'Q.tà', 'Prezzo Unit.', 'IVA', 'Totale (IVA inc.)']]
    : [['Articolo / Descrizione', 'Q.tà', 'Prezzo Unit.', 'Importo Totale']];

  let totalImponibile = 0;
  let totalVatAmount = 0;
  let grandTotal = 0;

  const tableBody = items.map((item) => {
    const qty = parseFloat(item.quantity) || 1;
    const unitPrice = parseFloat(item.unit_price) || 0;
    const itemVatPct = showVat ? (parseFloat(item.vat_percent) ?? 22) : 0;
    const imponibile = qty * unitPrice;
    const vatVal = showVat ? imponibile * (itemVatPct / 100) : 0;
    const totalRow = showVat ? imponibile + vatVal : imponibile;

    totalImponibile += imponibile;
    totalVatAmount += vatVal;
    grandTotal += totalRow;

    if (showVat) {
      return [
        item.name || '',
        qty.toString(),
        formatEuro(unitPrice),
        `${itemVatPct}%`,
        formatEuro(totalRow)
      ];
    } else {
      return [
        item.name || '',
        qty.toString(),
        formatEuro(unitPrice),
        formatEuro(totalRow)
      ];
    }
  });

  const columnStyles = showVat
    ? {
        0: { cellWidth: 'auto', halign: 'left' },
        1: { cellWidth: 20, halign: 'center' },
        2: { cellWidth: 32, halign: 'right' },
        3: { cellWidth: 20, halign: 'center' },
        4: { cellWidth: 40, halign: 'right' }
      }
    : {
        0: { cellWidth: 'auto', halign: 'left' },
        1: { cellWidth: 25, halign: 'center' },
        2: { cellWidth: 40, halign: 'right' },
        3: { cellWidth: 45, halign: 'right' }
      };

  doc.autoTable({
    startY: y,
    head: tableHeaders,
    body: tableBody,
    theme: 'grid',
    margin: { left: 12, right: 12 },
    headStyles: {
      fillColor: [242, 242, 242],
      textColor: [15, 23, 42],
      fontStyle: 'bold',
      fontSize: 9,
      halign: 'center',
      lineWidth: 0.2,
      lineColor: [200, 200, 200]
    },
    bodyStyles: {
      textColor: [15, 23, 42],
      fontSize: 8.5,
      lineWidth: 0.1,
      lineColor: [226, 232, 240]
    },
    columnStyles: columnStyles
  });

  y = doc.lastAutoTable.finalY + 6;

  // Check page overflow for summary & notes
  if (y > 240) {
    doc.addPage();
    y = 15;
  }

  // 7. Totals Summary Box
  const summaryX = 110;
  const summaryWidth = 88;
  let summaryHeight = showVat ? 24 : 12;

  doc.setFillColor(248, 250, 252);
  doc.setDrawColor(226, 232, 240);
  doc.roundedRect(summaryX, y, summaryWidth, summaryHeight, 2, 2, 'FD');

  let sumY = y + 5;
  if (showVat) {
    doc.setFont('Helvetica', 'normal');
    doc.setFontSize(8.5);
    doc.setTextColor(...darkTextColor);
    doc.text('Totale Imponibile:', summaryX + 4, sumY);
    doc.text(formatEuro(totalImponibile), summaryX + summaryWidth - 4, sumY, { align: 'right' });
    sumY += 4.5;

    doc.text('Totale IVA:', summaryX + 4, sumY);
    doc.text(formatEuro(totalVatAmount), summaryX + summaryWidth - 4, sumY, { align: 'right' });
    sumY += 5.5;

    doc.setFont('Helvetica', 'bold');
    doc.setFontSize(10.5);
    doc.setTextColor(...redColor);
    doc.text('Totale Complessivo:', summaryX + 4, sumY);
    doc.text(formatEuro(grandTotal), summaryX + summaryWidth - 4, sumY, { align: 'right' });
  } else {
    doc.setFont('Helvetica', 'bold');
    doc.setFontSize(11);
    doc.setTextColor(...redColor);
    doc.text('Totale Complessivo:', summaryX + 4, sumY + 2);
    doc.text(formatEuro(grandTotal), summaryX + summaryWidth - 4, sumY + 2, { align: 'right' });
  }

  y += summaryHeight + 8;

  // 8. Final Notes
  if (data.final_notes) {
    if (y > 250) {
      doc.addPage();
      y = 15;
    }

    doc.setFont('Helvetica', 'bold');
    doc.setFontSize(9.5);
    doc.setTextColor(...redColor);
    doc.text('Note e Condizioni:', 12, y);
    y += 4.5;

    doc.setFont('Helvetica', 'normal');
    doc.setFontSize(8.5);
    doc.setTextColor(...darkTextColor);
    const splitNotes = doc.splitTextToSize(data.final_notes, 186);
    doc.text(splitNotes, 12, y);
  }

  // Output handling
  const pdfBlob = doc.output('blob');

  if (options.preview) {
    const blobUrl = URL.createObjectURL(pdfBlob);
    window.open(blobUrl, '_blank');
  } else if (options.download) {
    const filename = options.filename || `preventivo_${quoteNum}.pdf`;
    doc.save(filename);
  }

  return pdfBlob;
}
