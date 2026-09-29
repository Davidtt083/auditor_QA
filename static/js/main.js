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
const overloadedState = document.querySelector('#overloaded-state');
const retryBtn = document.querySelector('#retry-btn');

let latestReport = null;
let lookupIndex = {};

const CAT = {
  'Título de videojuego': { clave: 'videojuego', etiqueta: 'Título de obra / Videojuego' },
  'Personaje / Entidad de ficción': { clave: 'personaje', etiqueta: 'Personaje de ficción' },
  'Lugar / Universo de ficción': { clave: 'lugar', etiqueta: 'Lugar / Reino' },
  'Marca / Empresa': { clave: 'marca', etiqueta: 'Marca / Plataforma' },
  'Sigla': { clave: 'sigla', etiqueta: 'Sigla extranjera' },
  'Jerga de videojuegos': { clave: 'jerga', etiqueta: 'Jerga / Término genérico' },
  'Ortografia': { clave: 'ortografia', etiqueta: 'Ortografía' },
  'Gramatica / Puntuacion': { clave: 'gramatica', etiqueta: 'Gramática' },
  'Extranjerismo no adaptado': { clave: 'extranjerismo', etiqueta: 'Extranjerismo crudo' },
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

// Genera la caja visual donde se ve claramente la tipografía (cursiva o redonda con mayúsculas)
function bloqueTipografiaVisual(lookup) {
  if (!lookup || !lookup.recommended) return '';
  const esCursiva = lookup.is_italic;
  const textoMuestra = esCursiva
    ? `<em class="preview-italic">${escapeHtml(lookup.recommended)}</em>`
    : `<span class="preview-roman">${escapeHtml(lookup.recommended)}</span>`;
  const badgeTipo = esCursiva
    ? `<span class="typo-badge typo-italic">ESCRITURA EN CURSIVA (ITÁLICA)</span>`
    : `<span class="typo-badge typo-roman">ESCRITURA EN LETRA REDONDA</span>`;

  return `
    <div class="typo-box ${esCursiva ? 'is-italic' : 'is-roman'}">
      <div class="typo-header">
        <strong>Forma correcta de escritura:</strong>
        ${badgeTipo}
      </div>
      <div class="typo-sample">${textoMuestra}</div>
      ${lookup.rule_name ? `<div class="typo-rule-tag">${escapeHtml(lookup.rule_name)}</div>` : ''}
    </div>
  `;
}

function bloqueDetalleFactual(lookup) {
  if (!lookup || !lookup.found) {
    return '<p class="sin-fuente">Sin ficha disponible para este término.</p>';
  }
  let html = bloqueTipografiaVisual(lookup);

  if (lookup.rae_rule) {
    html += `
      <div class="rae-box">
        <strong>Norma ortotipográfica aplicada:</strong>
        <p>${escapeHtml(lookup.rae_rule)}</p>
      </div>
    `;
  }
  html += `
    <p class="definicion">
      <strong>Descripción / Contexto:</strong><br>
      ${escapeHtml(lookup.definition)}
    </p>
  `;
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
  const lookup = error.lookup || definicionDe(error.text) || {};
  const esCursiva = lookup.is_italic;

  const muestraVisual = lookup.recommended
    ? (esCursiva ? `<em>${escapeHtml(lookup.recommended)}</em>` : `${escapeHtml(lookup.recommended)}`)
    : escapeHtml(error.suggestions?.[0] || '');

  const etiquetaTipografia = esCursiva
    ? `<span class="badge-mini-italic">Cursiva</span>`
    : `<span class="badge-mini-roman">Redonda</span>`;

  return `
    <article class="error-card cat-${meta.clave}" onclick='showMark(${JSON.stringify(error)})' style="cursor:pointer">
      <i class="error-dot"></i>
      <div>
        <div class="card-topline">
          <h3>${escapeHtml(error.text)}</h3>
          <span class="card-category-tag tag-${meta.clave}">${escapeHtml(meta.etiqueta)}</span>
        </div>
        <p>${escapeHtml(lookup.definition || error.message)}</p>
        <div class="card-correct-row">
          <span class="lbl-como">Escritura correcta:</span>
          <span class="val-como ${esCursiva ? 'font-italic' : 'font-roman'}">${muestraVisual}</span>
          ${etiquetaTipografia}
        </div>
        ${lookup.rae_rule ? `<div class="card-rae-mini"><strong>Regla:</strong> ${escapeHtml(lookup.rae_rule)}</div>` : ''}
      </div>
    </article>
  `;
}

function renderDashboard(report) {
  const counterData = [
    ['total', 'Total hallazgos'],
    ['Videojuegos', 'Videojuegos (R7)'],
    ['Personajes / Ficción', 'Nombres propios (R3/5)'],
    ['Jerga gaming', 'Extranjerismos / Jerga (R1/8)'],
    ['Ortografia', 'Ortografía'],
    ['Gramatica / Puntuacion', 'Gramática']
  ];
  document.querySelector('#counters').innerHTML = counterData
    .map(([key, label]) => `<div class="counter ${key === 'total' ? 'total' : ''}"><strong>${report.counts[key] ?? 0}</strong><span>${label}</span></div>`)
    .join('');

  const juegos = report.errors.filter(e => e.category === 'Título de videojuego');
  const nombresPropios = report.errors.filter(e => ['Personaje / Entidad de ficción', 'Lugar / Universo de ficción', 'Marca / Empresa'].includes(e.category));
  const jergaYExt = report.errors.filter(e => ['Jerga de videojuegos', 'Extranjerismo no adaptado', 'Sigla'].includes(e.category));
  const ortografia = report.errors.filter(e => ['Ortografia', 'Gramatica / Puntuacion'].includes(e.category));

  let html = '';
  if (juegos.length) html += `<h3 class="grupo-titulo">🎮 Títulos de obras / Videojuegos (Regla 7 - Cursiva) (${juegos.length})</h3>` + juegos.map(tarjeta).join('');
  if (nombresPropios.length) html += `<h3 class="grupo-titulo">🛡️ Nombres propios, personajes y marcas (Reglas 3, 4 y 5 - Redonda) (${nombresPropios.length})</h3>` + nombresPropios.map(tarjeta).join('');
  if (jergaYExt.length) html += `<h3 class="grupo-titulo">⚙️ Extranjerismos crudos y jerga (Reglas 1, 2 y 8) (${jergaYExt.length})</h3>` + jergaYExt.map(tarjeta).join('');
  if (ortografia.length) html += `<h3 class="grupo-titulo">⚠️ Correcciones ortográficas generales (${ortografia.length})</h3>` + ortografia.map(tarjeta).join('');

  if (!html) {
    html = '<article class="error-card"><i class="error-dot" style="background:#63bb78"></i><div><h3>Texto conforme</h3><p>El texto cumple con las normas ortotipográficas y no presenta errores.</p></div></article>';
  }
  document.querySelector('#error-list').innerHTML = html;
}

// ---------------------------------------------------------------------------
// GENERACIÓN DE PDF FORMAL CON ESCRITURA Y TIPOGRAFÍA VISUAL
// ---------------------------------------------------------------------------
function generarPDF(report) {
  if (!window.jspdf) {
    showToast('Error: No se pudo cargar el módulo de PDF.');
    return;
  }
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF('p', 'mm', 'a4');

  // Encabezado
  doc.setFillColor(28, 128, 98);
  doc.rect(0, 0, 210, 25, 'F');
  doc.setTextColor(255, 255, 255);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(14);
  doc.text('REPORTE QA: AUDITORÍA NARRATIVA Y ORTOTIPOGRÁFICA', 14, 15);

  const rows = report.errors.map(err => {
    const meta = CAT[err.category] || { etiqueta: err.category };
    const lk = err.lookup || definicionDe(err.text) || {};
    
    // Guardamos este dato en la fila para usarlo después al renderizar
    return {
      categoria: meta.etiqueta,
      termino: err.text,
      // Usamos un objeto para que la tabla sepa si debe ser cursiva o no
      recomendado: {
        text: lk.recommended || err.text,
        isItalic: lk.is_italic === true
      },
      descripcion: (lk.definition || err.message || '').replace(/\s+/g, ' ').trim(),
      regla: `Regla: ${lk.rule_name || 'Norma ortotipográfica'}\nRAE: ${lk.rae_rule || ''}`
    };
  });

  doc.autoTable({
    startY: 35,
    head: [['Categoría', 'Término', 'Forma Correcta (Visual)', 'Contexto']],
    body: rows.map(r => [r.categoria, r.termino, r.recomendado.text, r.descripcion + '\n\n' + r.regla]),
    theme: 'grid',
    headStyles: { fillColor: [32, 60, 75], fontSize: 8 },
    styles: { fontSize: 8, cellPadding: 3 },
    
    // AQUÍ ESTÁ LA MAGIA: Aplicamos cursiva real celda por celda
    didParseCell: function(data) {
      if (data.section === 'body' && data.column.index === 2) {
        const rowData = rows[data.row.index];
        if (rowData.recomendado.isItalic) {
          // Cambiamos la fuente a cursiva para esta celda específica
          data.cell.styles.fontStyle = 'italic';
        } else {
          data.cell.styles.fontStyle = 'normal';
        }
      }
    }
  });

  doc.save('reporte_qa_normas_rae.pdf');
}

// ---------------------------------------------------------------------------
// EVENTOS Y EJECUCIÓN
// ---------------------------------------------------------------------------
analyzeButton.addEventListener('click', async () => {
  analyzeButton.disabled = true;
  resultState.textContent = 'Aplicando las 8 normas con Gemini...';

  emptyState.classList.add('hidden');
  if (overloadedState) overloadedState.classList.add('hidden');
  reviewView.classList.add('hidden');

  try {
    const response = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: input.value })
    });

    const data = await response.json();

    if (!response.ok) {
      if (data.is_overloaded || response.status === 503) {
        resultState.textContent = 'Servicio saturado';
        overloadedState.classList.remove('hidden');
        showToast('Google Gemini está ocupado. Intenta de nuevo en un par de minutos.');
        return;
      }
      throw new Error(data.error || 'No se pudo analizar el texto.');
    }

    latestReport = data;
    indexarLookups(data);
    reviewView.classList.remove('hidden');
    dashboard.classList.remove('hidden');
    resultState.textContent = `${data.counts.total} elemento${data.counts.total === 1 ? '' : 's'} auditado${data.counts.total === 1 ? '' : 's'}`;
    document.querySelector('#review-summary').textContent = `${data.text.length.toLocaleString('es-ES')} caracteres auditados`;
    renderText(data);
    renderDashboard(data);
  } catch (error) {
    resultState.textContent = 'Error de análisis';
    emptyState.classList.remove('hidden');
    showToast(error.message);
  } finally {
    analyzeButton.disabled = false;
  }
});

if (retryBtn) {
  retryBtn.addEventListener('click', () => {
    analyzeButton.click();
  });
}

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