const input = document.querySelector('#text-input');
const analyzeButton = document.querySelector('#analyze-btn');
const countLabel = document.querySelector('#char-count');
const emptyState = document.querySelector('#empty-state');
const reviewView = document.querySelector('#review-view');
const highlightedText = document.querySelector('#highlighted-text');
const dashboard = document.querySelector('#dashboard');
const resultState = document.querySelector('#result-state');
const toast = document.querySelector('#toast');
let latestReport = null;

input.addEventListener('input', () => {
  countLabel.textContent = `${input.value.length.toLocaleString('es-ES')} caracteres`;
});
countLabel.textContent = `${input.value.length.toLocaleString('es-ES')} caracteres`;

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
}

function renderText(report) {
  const marks = [];
  report.errors.forEach(error => marks.push({ ...error, type: 'error' }));
  report.annotations.forEach(annotation => marks.push(annotation));
  marks.sort((left, right) => left.offset - right.offset || right.length - left.length);
  const nonOverlapping = [];
  marks.forEach(mark => {
    const previous = nonOverlapping[nonOverlapping.length - 1];
    if (!previous || mark.offset >= previous.offset + previous.length) nonOverlapping.push(mark);
  });
  let html = '';
  let cursor = 0;
  nonOverlapping.forEach((mark, index) => {
    html += escapeHtml(report.text.slice(cursor, mark.offset));
    const label = mark.type === 'error' ? mark.message : mark.lookup.definition;
    html += `<button class="mark ${mark.type}" data-mark-index="${index}" title="${escapeHtml(label)}">${escapeHtml(report.text.slice(mark.offset, mark.offset + mark.length))}</button>`;
    cursor = mark.offset + mark.length;
  });
  highlightedText.innerHTML = html + escapeHtml(report.text.slice(cursor));
  highlightedText.querySelectorAll('.mark').forEach((button, index) => button.addEventListener('click', () => showMark(nonOverlapping[index])));
}

function showMark(mark) {
  const detail = document.querySelector('#term-detail');
  if (mark.type === 'term') {
    const lookup = mark.lookup;
    detail.innerHTML = `<span class="aside-label">${escapeHtml(lookup.source || 'CONSULTA FACTUAL')}</span><h3>${escapeHtml(lookup.term)}</h3><p>${escapeHtml(lookup.definition)}</p>${lookup.source_url ? `<a class="term-source" href="${escapeHtml(lookup.source_url)}" target="_blank" rel="noreferrer">Abrir fuente oficial ↗</a>` : ''}`;
    return;
  }
  detail.innerHTML = `<span class="aside-label">${escapeHtml(mark.category)}</span><h3>${escapeHtml(mark.text)}</h3><p>${escapeHtml(mark.message)}</p><p class="replacement"><strong>Sugerencia:</strong> ${escapeHtml(mark.suggestions?.join(', ') || 'Sin sugerencia')}</p><small>${escapeHtml(mark.source)}</small>`;
}

function renderDashboard(report) {
  const counterData = [['total', 'Total de hallazgos'], ['Ortografia', 'Ortografía'], ['Gramatica / Puntuacion', 'Gramática / Puntuación'], ['Extranjerismo no adaptado', 'Extranjerismos']];
  document.querySelector('#counters').innerHTML = counterData.map(([key, label]) => `<div class="counter ${key === 'total' ? 'total' : ''}"><strong>${report.counts[key]}</strong><span>${label}</span></div>`).join('');
  document.querySelector('#error-list').innerHTML = report.errors.length ? report.errors.map(error => `<article class="error-card"><i class="error-dot"></i><div><h3>${escapeHtml(error.text)}</h3><p>${escapeHtml(error.message)}</p><p class="replacement"><strong>Reemplazo:</strong> ${escapeHtml(error.suggestions?.join(', ') || 'Sin sugerencia')}</p></div><span class="category">${escapeHtml(error.category)}</span></article>`).join('') : '<article class="error-card"><i class="error-dot" style="background:#63bb78"></i><div><h3>Sin hallazgos</h3><p>El texto no presenta coincidencias con las reglas configuradas.</p></div></article>';
}

function markdownReport(report) {
  const lines = [`## Reporte QA lingüístico`, ``, `**Total:** ${report.counts.total}`, ``, `| Categoría | Texto | Motivo | Sugerencia |`, `|---|---|---|---|`];
  report.errors.forEach(error => lines.push(`| ${error.category} | ${error.text} | ${error.message} | ${error.suggestions?.join(', ') || 'Sin sugerencia'} |`));
  return lines.join('\n');
}

analyzeButton.addEventListener('click', async () => {
  analyzeButton.disabled = true;
  resultState.textContent = 'Analizando...';
  try {
    const response = await fetch('/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: input.value }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No se pudo analizar el texto.');
    latestReport = data;
    emptyState.classList.add('hidden');
    reviewView.classList.remove('hidden');
    dashboard.classList.remove('hidden');
    resultState.textContent = `${data.counts.total} hallazgo${data.counts.total === 1 ? '' : 's'}`;
    document.querySelector('#review-summary').textContent = `${data.text.length.toLocaleString('es-ES')} caracteres revisados`;
    renderText(data);
    renderDashboard(data);
  } catch (error) {
    resultState.textContent = 'Error de análisis';
    showToast(error.message);
  } finally { analyzeButton.disabled = false; }
});

document.querySelector('#copy-report').addEventListener('click', async () => {
  if (!latestReport) return;
  await navigator.clipboard.writeText(markdownReport(latestReport));
  showToast('Reporte Markdown copiado');
});

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2800);
}
