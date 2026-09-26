const input = document.querySelector('#text-input');
const analyzeButton = document.querySelector('#analyze-btn');
const countLabel = document.querySelector('#char-count');
const emptyState = document.querySelector('#empty-state');
const reviewView = document.querySelector('#review-view');
const highlightedText = document.querySelector('#highlighted-text');
const dashboard = document.querySelector('#dashboard');
const resultState = document.querySelector('#result-state');
const toast = document.querySelector('#toast');
const downloadPdfButton = document.querySelector('#download-pdf');

let latestReport = null;
let lookupIndex = {};

const CAT = {
  'Título de videojuego': { clave: 'videojuego', etiqueta: 'Título de videojuego', color: [14, 131, 84] },
  'Personaje / Entidad de ficción': { clave: 'personaje', etiqueta: 'Personaje de ficción', color: [31, 111, 235] },
  'Lugar / Universo de ficción': { clave: 'lugar', etiqueta: 'Lugar / Reino', color: [105, 65, 198] },
  'Jerga de videojuegos': { clave: 'jerga', etiqueta: 'Jerga gaming', color: [217, 119, 6] },
  'Ortografia': { clave: 'ortografia', etiqueta: 'Ortografía', color: [239, 118, 94] },
  'Gramatica / Puntuacion': { clave: 'gramatica', etiqueta: 'Gramática', color: [32, 60, 75] },
  'Extranjerismo no adaptado': { clave: 'extranjerismo', etiqueta: 'Extranjerismo', color: [45, 111, 168] },
};

const normaliza = valor => String(valor || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

input.addEventListener('input', () => {
  countLabel.textContent = `${input.value.length.toLocaleString('es-ES')} caracteres`;
});
countLabel.textContent = `${input.value.length.toLocaleString('es-ES')} caracteres`;

function escapeHtml(value) {
  return String(value || '').replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}

function indexarLookups(report) {
  lookupIndex = {};
  (report.annotations || []).forEach(annotation => {
    if (annotation.lookup) lookupIndex[normaliza(annotation.text)] = annotation.lookup;
  });
  (report.errors || []).forEach(error => {
    if (error.lookup) lookupIndex[normaliza(error.text)] = error.lookup;
  });
}

function definicionDe(texto) {
  return lookupIndex[normaliza(texto)] || null;
}

function renderText(report) {
  const marks = [...report.errors];
  marks.sort((a, b) => a.offset - b.offset || b.length - a.length);

  const nonOverlapping = [];
  marks.forEach(mark => {
    const prev = nonOverlapping[nonOverlapping.length - 1];
    if (!prev || mark.offset >= prev.offset + prev.length) nonOverlapping.push(mark);
  });

  let html = '';
  let cursor = 0;
  nonOverlapping.forEach((mark, index) => {
    html += escapeHtml(report.text.slice(cursor, mark.offset));
    const meta = CAT[mark.category] || { clave: 'ortografia', etiqueta: mark.category };
    const clase = `mark cat-${meta.clave}`;
    html += `<button class="${clase}" data-mark-index="${index}" title="${escapeHtml(meta.etiqueta)}: ${escapeHtml(mark.text)}">${escapeHtml(report.text.slice(mark.offset, mark.offset + mark.length))}</button>`;
    cursor = mark.offset + mark.length;
  });
  highlightedText.innerHTML = html + escapeHtml(report.text.slice(cursor));
  highlightedText.querySelectorAll('.mark').forEach((btn, idx) => {
    btn.addEventListener('click', () => showMark(nonOverlapping[idx]));
  });
}

function bloqueDetalleFactual(lookup) {
  if (!lookup || !lookup.found) {
    return '<p class="sin-fuente">Sin ficha disponible para este término.</p>';
  }
  let html = '';
  if (lookup.recommended) {
    html += `<p class="replacement"><strong>Forma recomendada / Sustituto:</strong> ${escapeHtml(lookup.recommended)}</p>`;
  }
  if (lookup.rae_rule) {
    html += `<div class="rae-box"><strong>Norma ortotipográfica (RAE / Fundéu):</strong><p>${escapeHtml(lookup.rae_rule)}</p></div>`;
  }
  html += `<p class="definicion"><strong>Descripción / Ficha enciclopédica:</strong><br>${escapeHtml(lookup.definition)}</p>`;
  if (lookup.source) {
    html += `<small>Fuente: ${escapeHtml(lookup.source)}</small>`;
  }
  if (lookup.source_url) {
    html += `<a class="term-source" href="${escapeHtml(lookup.source_url)}" target="_blank" rel="noreferrer">Abrir referencia web ↗</a>`;
  }
  return html;
}

function showMark(mark) {
  const detail = document.querySelector('#term-detail');
  const meta = CAT[mark.category] || { etiqueta: mark.category, clave: 'ortografia' };
  const lookup = mark.lookup || definicionDe(mark.text);

  detail.innerHTML = `
    <span class="aside-label badge-${meta.clave}">${escapeHtml(meta.etiqueta)}</span>
    <h3>${escapeHtml(mark.text)}</h3>
    ${bloqueDetalleFactual(lookup)}
  `;
}

function tarjeta(error) {
  const meta = CAT[error.category] || { clave: 'ortografia', etiqueta: error.category };
  const lookup = error.lookup || definicionDe(error.text);
  
  let detalle = '';
  if (lookup && lookup.rae_rule) {
    detalle += `<div class="card-rae-mini"><strong>Escritura según RAE:</strong> ${escapeHtml(lookup.rae_rule)}</div>`;
  }
  if (error.suggestions && error.suggestions.length) {
    detalle += `<p class="replacement"><strong>Recomendación:</strong> ${escapeHtml(error.suggestions.join(', '))}</p>`;
  }

  return `
    <article class="error-card cat-${meta.clave}" onclick='showMark(${JSON.stringify(error)})' style="cursor:pointer">
      <i class="error-dot"></i>
      <div>
        <div class="card-topline">
          <h3>${escapeHtml(error.text)}</h3>
          <span class="card-category-tag tag-${meta.clave}">${escapeHtml(meta.etiqueta)}</span>
        </div>
        <p>${escapeHtml(lookup ? lookup.definition : error.message)}</p>
        ${detalle}
      </div>
    </article>
  `;
}

function renderDashboard(report) {
  const counterData = [
    ['total', 'Total hallazgos'],
    ['Videojuegos', 'Videojuegos'],
    ['Personajes / Ficción', 'Personajes / Ficción'],
    ['Jerga gaming', 'Jerga gaming'],
    ['Ortografia', 'Ortografía'],
    ['Gramatica / Puntuacion', 'Gramática']
  ];
  document.querySelector('#counters').innerHTML = counterData
    .map(([key, label]) => `<div class="counter ${key === 'total' ? 'total' : ''}"><strong>${report.counts[key] ?? 0}</strong><span>${label}</span></div>`)
    .join('');

  const juegos = report.errors.filter(e => e.category === 'Título de videojuego');
  const personajes = report.errors.filter(e => e.category.includes('Personaje') || e.category.includes('Lugar'));
  const jerga = report.errors.filter(e => e.category === 'Jerga de videojuegos');
  const ortografia = report.errors.filter(e => ['Ortografia', 'Gramatica / Puntuacion', 'Extranjerismo no adaptado'].includes(e.category));

  let html = '';
  if (juegos.length) html += `<h3 class="grupo-titulo">🎮 Títulos de videojuegos (${juegos.length})</h3>` + juegos.map(tarjeta).join('');
  if (personajes.length) html += `<h3 class="grupo-titulo">🛡️ Personajes y mundo de ficción (${personajes.length})</h3>` + personajes.map(tarjeta).join('');
  if (jerga.length) html += `<h3 class="grupo-titulo">⚙️ Jerga y mecánicas lúdicas (${jerga.length})</h3>` + jerga.map(tarjeta).join('');
  if (ortografia.length) html += `<h3 class="grupo-titulo">⚠️ Correcciones ortográficas (${ortografia.length})</h3>` + ortografia.map(tarjeta).join('');

  if (!html) {
    html = '<article class="error-card"><i class="error-dot" style="background:#63bb78"></i><div><h3>Texto limpio</h3><p>No se encontraron errores ni elementos a corregir.</p></div></article>';
  }
  document.querySelector('#error-list').innerHTML = html;
}

// ---------------------------------------------------------------------------
// GENERACIÓN PROFESIONAL DE PDF CON jsPDF + AutoTable
// ---------------------------------------------------------------------------
function generarPDF(report) {
  if (!window.jspdf) {
    showToast('Error: No se pudo cargar el módulo de PDF.');
    return;
  }
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });

  const fecha = new Date().toLocaleDateString('es-ES', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' });

  // Encabezado
  doc.setFillColor(28, 128, 98); // Verde institucional
  doc.rect(0, 0, 210, 22, 'F');
  
  doc.setTextColor(255, 255, 255);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(14);
  doc.text('REPORTE QA: AUDITORÍA LINGÜÍSTICA Y NARRATIVA', 14, 14);

  // Subcabecera
  doc.setTextColor(80, 80, 80);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.text(`Fecha de emisión: ${fecha}  |  Total de elementos auditados: ${report.counts.total}`, 14, 30);

  // Resumen cuantitativo
  doc.setFontSize(10);
  doc.setFont('helvetica', 'bold');
  doc.text('Resumen por categorías:', 14, 38);

  const c = report.counts;
  const resumenTexto = `Videojuegos: ${c.Videojuegos || 0}   |   Personajes/Ficción: ${c['Personajes / Ficción'] || 0}   |   Jerga: ${c['Jerga gaming'] || 0}   |   Ortografía: ${c.Ortografia || 0}`;
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(40, 40, 40);
  doc.text(resumenTexto, 14, 44);

  // Preparar filas para la tabla
  const rows = report.errors.map(err => {
    const meta = CAT[err.category] || { etiqueta: err.category };
    const lk = err.lookup || definicionDe(err.text) || {};
    const definicion = (lk.definition || err.message || '').replace(/\s+/g, ' ').trim();
    const reglaRAE = (lk.rae_rule || '').replace(/\s+/g, ' ').trim();
    const recomendado = lk.recommended || (err.suggestions && err.suggestions[0]) || 'N/A';

    return [
      meta.etiqueta,
      err.text,
      definicion,
      `Forma sugerida: ${recomendado}\n\nNorma RAE:\n${reglaRAE}`
    ];
  });

  // Generar tabla formal
  doc.autoTable({
    startY: 50,
    head: [['Categoría', 'Término', 'Descripción / Ficha factual', 'Forma y Norma RAE']],
    body: rows,
    theme: 'grid',
    headStyles: {
      fillColor: [32, 60, 75],
      textColor: [255, 255, 255],
      fontStyle: 'bold',
      fontSize: 9,
      halign: 'left',
    },
    columnStyles: {
      0: { cellWidth: 32, fontStyle: 'bold', fontSize: 8 },
      1: { cellWidth: 30, fontStyle: 'bold', fontSize: 8 },
      2: { cellWidth: 65, fontSize: 8 },
      3: { cellWidth: 55, fontSize: 8 },
    },
    styles: {
      overflow: 'linebreak',
      cellPadding: 3,
      valign: 'top',
      lineColor: [220, 229, 223],
    },
    alternateRowStyles: {
      fillColor: [247, 250, 246],
    },
    didDrawPage: function (data) {
      // Pie de página
      doc.setFontSize(8);
      doc.setTextColor(150, 150, 150);
      const str = 'Página ' + doc.internal.getNumberOfPages();
      doc.text(str, 196, 287, { align: 'right' });
      doc.text('QA Text Auditor - Motor Gemini 3.8 Flash con verificación RAE', 14, 287);
    }
  });

  doc.save('reporte_qa_narrativa.pdf');
  showToast('PDF descargado con éxito');
}

// ---------------------------------------------------------------------------
// EVENTOS Y ANALISIS
// ---------------------------------------------------------------------------
analyzeButton.addEventListener('click', async () => {
  analyzeButton.disabled = true;
  resultState.textContent = 'Auditando con Gemini 3.8...';
  try {
    const response = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: input.value })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No se pudo analizar el texto.');
    latestReport = data;
    indexarLookups(data);
    emptyState.classList.add('hidden');
    reviewView.classList.remove('hidden');
    dashboard.classList.remove('hidden');
    resultState.textContent = `${data.counts.total} elemento${data.counts.total === 1 ? '' : 's'} identificado${data.counts.total === 1 ? '' : 's'}`;
    document.querySelector('#review-summary').textContent = `${data.text.length.toLocaleString('es-ES')} caracteres auditados`;
    renderText(data);
    renderDashboard(data);
  } catch (error) {
    resultState.textContent = 'Error de análisis';
    showToast(error.message);
  } finally {
    analyzeButton.disabled = false;
  }
});

downloadPdfButton.addEventListener('click', () => {
  if (!latestReport || !latestReport.errors || latestReport.errors.length === 0) {
    showToast('No hay hallazgos disponibles para generar el PDF.');
    return;
  }
  generarPDF(latestReport);
});

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3200);
}