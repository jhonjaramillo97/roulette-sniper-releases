document.addEventListener("DOMContentLoaded", () => {
    fetchGlobalData();
    setupModal();
});

let globalData = { history: [], color_history: [], threshold: 5, color_threshold: 5 };
let currentTopLimit = 20;
let chartTerciosInstance = null;
let chartColorInstance = null;

function setupGlobalTabs() {
    document.querySelectorAll('#global-tabs .tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const view = btn.dataset.view; // 'tercios' o 'colores'
            
            // Actualizar estado activo de los botones globales
            document.querySelectorAll('#global-tabs .tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Actualizar paneles visibles
            document.getElementById('chart-panel-tercios').classList.toggle('active', view === 'tercios');
            document.getElementById('chart-panel-colores').classList.toggle('active', view === 'colores');
            
            document.getElementById('signals-panel-tercios').classList.toggle('active', view === 'tercios');
            document.getElementById('signals-panel-colores').classList.toggle('active', view === 'colores');
            
            document.getElementById('tbody-tables-tercios').style.display = view === 'tercios' ? '' : 'none';
            document.getElementById('tbody-tables-colores').style.display = view === 'colores' ? '' : 'none';

            // Actualizar los KPIs y títulos en función de la vista seleccionada
            updateViewContext(view);
        });
    });

    document.querySelectorAll('#top-limit-tabs .tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#top-limit-tabs .tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            currentTopLimit = parseInt(btn.dataset.limit, 10);
            
            // Re-render con el nuevo limite
            processAndRender(globalData.history, globalData.color_history);
        });
    });
}

function updateViewContext(view) {
    const isTercios = view === 'tercios';
    
    // Títulos
    document.getElementById('chart-title').textContent = isTercios 
        ? `Top Rachas identificadas — Tercios` 
        : `Top Rachas identificadas — Rojos / Negros`;
        
    document.getElementById('top-signals-title').textContent = isTercios 
        ? `🏆 Top Señales Críticas — Tercios` 
        : `🏆 Top Señales Críticas — Rojos / Negros`;

    document.getElementById('breakdown-title').textContent = isTercios
        ? '📊 Desglose por Mesa — Tercios'
        : '📊 Desglose por Mesa — Rojos / Negros';

    // Datos para los KPIs
    const dataArray = isTercios ? globalData.history : globalData.color_history;
    const valueKey = isTercios ? 'max_delay' : 'streak_count';
    
    const totalSignals = (dataArray || []).length;
    const allValues = (dataArray || []).map(e => e[valueKey]);
    
    const maxGlobal = allValues.length > 0 ? Math.max(...allValues) : 0;
    const avgGlobal = allValues.length > 0 ? allValues.reduce((a, b) => a + b, 0) / allValues.length : 0;

    // Actualizar KPIs
    document.getElementById('val-total').textContent = totalSignals;
    document.getElementById('val-avg').textContent = avgGlobal.toFixed(2);
    document.getElementById('val-max').textContent = maxGlobal;
}

async function fetchGlobalData() {
    try {
        const res = await fetch("/api/analisis_global");
        if (!res.ok) throw new Error("Error fetching global data");
        const data = await res.json();
        
        globalData = data; // Guardar estado para cambiar vistas sin recargar

        processAndRender(data.history, data.color_history);
        
        setupGlobalTabs();
        updateViewContext('tercios'); // Set initial state

        // Ocultar loader y mostrar contenido
        document.getElementById('loader').style.display = 'none';
        document.getElementById('global-toggle-container').style.display = 'flex';
        document.getElementById('stats-container').style.display = 'flex';
        document.getElementById('charts-container').style.display = 'grid';
        document.getElementById('tables-container').style.display = 'grid';

    } catch (error) {
        console.error("Fetch Analysis Error:", error);
        document.getElementById('loader').innerHTML = `<div style="color:var(--color-danger)">❌ Error al cargar los datos históricos. Asegúrate de que el bot tenga registros guardados en SQLite.</div>`;
    }
}

function renderTableBreakdown(tbodyId, dataArray, valueKey) {
    const tableStats = {};
    (dataArray || []).forEach(evt => {
        const tn = evt.table_name;
        if (!tableStats[tn]) {
            tableStats[tn] = { name: tn, count: 0, max: 0, sum: 0 };
        }
        tableStats[tn].count += 1;
        tableStats[tn].sum += evt[valueKey];
        if (evt[valueKey] > tableStats[tn].max) {
            tableStats[tn].max = evt[valueKey];
        }
    });

    const tbody = document.getElementById(tbodyId);
    tbody.innerHTML = '';
    
    Object.keys(tableStats).forEach(t => {
        const st = tableStats[t];
        const avg = st.sum / st.count;
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${formatName(st.name)}</strong></td>
            <td>${st.count}</td>
            <td>${avg.toFixed(2)}</td>
            <td class="max-delay-col ${st.max >= 20 ? 'delay-extreme' : (st.max >= 15 ? 'delay-high' : '')}">${st.max}</td>
        `;
        tbody.appendChild(tr);
    });
}

function processAndRender(history, colorHistory) {
    const hasHistory = history && history.length > 0;
    const hasColorHistory = colorHistory && colorHistory.length > 0;

    if (!hasHistory && !hasColorHistory) {
        document.getElementById('loader').innerHTML = `<div>No hay suficientes datos procesados en la Base de Datos.</div>`;
        return;
    }

    // --- Generar Desglose por Mesas ---
    renderTableBreakdown('tbody-tables-tercios', history, 'max_delay');
    renderTableBreakdown('tbody-tables-colores', colorHistory, 'streak_count');

    // --- Top N Señales Más Críticas (Tercios) ---
    const topN = (history || []).slice().sort((a, b) => b.max_delay - a.max_delay).slice(0, currentTopLimit);
    const tbodyTop20 = document.getElementById('tbody-top20');

    tbodyTop20.innerHTML = '';
    if (topN.length === 0) {
        tbodyTop20.innerHTML = '<tr><td colspan="4" class="loading-td">No hay señales de tercios registradas aún.</td></tr>';
    } else {
        topN.forEach((evt, index) => {
            const zoneMap = {
                "docena_1": "1ª Docena", "docena_2": "2ª Docena", "docena_3": "3ª Docena",
                "columna_1": "Columna 1", "columna_2": "Columna 2", "columna_3": "Columna 3"
            };
            const zoneLabel = zoneMap[evt.zone_name] || evt.zone_name;
            const end = evt.end_time ? evt.end_time : 'En progreso';

            const tr = document.createElement('tr');
            tr.className = 'clickable-row';
            tr.innerHTML = `
                <td><strong>${index + 1}. ${formatName(evt.table_name)}</strong></td>
                <td>${zoneLabel}</td>
                <td class="max-delay-col delay-extreme">${evt.max_delay} giros</td>
                <td>${end}</td>
            `;
            tr.addEventListener('click', () => {
                openSignalDetail({
                    type: 'tercios',
                    table_name: evt.table_name,
                    zone_name: evt.zone_name,
                    zoneLabel: zoneLabel,
                    max_delay: evt.max_delay,
                    start_time: evt.start_time,
                    end_time: evt.end_time
                });
            });
            tbodyTop20.appendChild(tr);
        });
    }

    // --- Top N Señales Más Críticas (Colores) ---
    const topNColor = (colorHistory || []).slice().sort((a, b) => b.streak_count - a.streak_count).slice(0, currentTopLimit);
    const tbodyTop20Color = document.getElementById('tbody-top20-color');

    tbodyTop20Color.innerHTML = '';
    if (topNColor.length === 0) {
        tbodyTop20Color.innerHTML = '<tr><td colspan="4" class="loading-td">No hay señales de rachas de color registradas aún.</td></tr>';
    } else {
        topNColor.forEach((evt, index) => {
            const isRed = evt.streak_color === 'Red';
            const emoji = isRed ? '🔴' : '⚫';
            const colorLabel = isRed ? 'Rojos' : 'Negros';
            const end = evt.end_time ? evt.end_time : 'En progreso';

            const tr = document.createElement('tr');
            tr.className = 'clickable-row';
            tr.innerHTML = `
                <td><strong>${index + 1}. ${formatName(evt.table_name)}</strong></td>
                <td><span class="color-streak-badge ${isRed ? 'red' : 'black'}">${emoji} ${colorLabel}</span></td>
                <td class="max-delay-col" style="color: ${isRed ? '#ff6b6b' : '#e0e0e0'}">${evt.streak_count} consecutivos</td>
                <td>${end}</td>
            `;
            tr.addEventListener('click', () => {
                openSignalDetail({
                    type: 'color',
                    table_name: evt.table_name,
                    streak_color: evt.streak_color,
                    colorLabel: colorLabel,
                    streak_count: evt.streak_count,
                    start_time: evt.start_time,
                    end_time: evt.end_time
                });
            });
            tbodyTop20Color.appendChild(tr);
        });
    }

    // --- Renderizar Gráficos (Chart.js) ---
    renderCharts(topN, topNColor);
}

function renderCharts(topNTercios, topNColor) {
    // defaults
    Chart.defaults.color = '#94a3b8'; // text-secondary
    Chart.defaults.font.family = "'Inter', sans-serif";

    if (chartTerciosInstance) chartTerciosInstance.destroy();
    if (chartColorInstance) chartColorInstance.destroy();

    // Gráfico 1: Top N Picos — Tercios (rojo)
    const ctxTercios = document.getElementById('chartTop20Tercios').getContext('2d');
    const terciosLabels = topNTercios.map((e, i) => `${i + 1}. ${formatName(e.table_name)}`);
    const terciosData = topNTercios.map(e => e.max_delay);

    chartTerciosInstance = new Chart(ctxTercios, {
        type: 'line',
        data: {
            labels: terciosLabels.length > 0 ? terciosLabels : ['Sin datos'],
            datasets: [{
                label: 'Max Delay Alcanzado',
                data: terciosData.length > 0 ? terciosData : [0],
                backgroundColor: 'rgba(239, 68, 68, 0.2)',
                borderColor: 'rgba(239, 68, 68, 1)',
                borderWidth: 2,
                pointBackgroundColor: 'rgba(239, 68, 68, 1)',
                pointRadius: 5,
                fill: true
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.05)' } },
                x: { grid: { display: false }, ticks: { display: false } }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });

    // Gráfico 2: Top N Picos — Color (naranja)
    const ctxColor = document.getElementById('chartTop20Color').getContext('2d');
    const colorLabels = topNColor.map((e, i) => {
        const emoji = e.streak_color === 'Red' ? '🔴' : '⚫';
        return `${i + 1}. ${emoji} ${formatName(e.table_name)}`;
    });
    const colorData = topNColor.map(e => e.streak_count);

    chartColorInstance = new Chart(ctxColor, {
        type: 'line',
        data: {
            labels: colorLabels.length > 0 ? colorLabels : ['Sin datos'],
            datasets: [{
                label: 'Racha máxima',
                data: colorData.length > 0 ? colorData : [0],
                backgroundColor: 'rgba(255, 159, 64, 0.2)',
                borderColor: 'rgba(255, 159, 64, 1)',
                borderWidth: 2,
                pointBackgroundColor: 'rgba(255, 159, 64, 1)',
                pointRadius: 5,
                fill: true
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.05)' } },
                x: { grid: { display: false }, ticks: { display: false } }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// ═══════════════════════════════════════════════════════
//  MODAL — Detalle de Señal
// ═══════════════════════════════════════════════════════

function setupModal() {
    const modal = document.getElementById('signal-modal');
    const closeBtn = document.getElementById('modal-close-btn');

    closeBtn.addEventListener('click', () => modal.classList.remove('active'));

    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('active');
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') modal.classList.remove('active');
    });
}

async function openSignalDetail(signal) {
    const modal = document.getElementById('signal-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalSubtitle = document.getElementById('modal-subtitle');
    const modalBody = document.getElementById('modal-body');

    // Configurar título y subtítulo según tipo
    if (signal.type === 'tercios') {
        modalTitle.textContent = `📋 ${formatName(signal.table_name)}`;
        modalSubtitle.innerHTML = `
            <strong>Zona:</strong> ${signal.zoneLabel} &nbsp;|&nbsp;
            <strong>Pico:</strong> ${signal.max_delay} giros &nbsp;|&nbsp;
            <strong>Inicio:</strong> ${signal.start_time || '—'} &nbsp;→&nbsp;
            <strong>Fin:</strong> ${signal.end_time || 'En progreso'}
        `;
    } else {
        const emoji = signal.streak_color === 'Red' ? '🔴' : '⚫';
        modalTitle.textContent = `📋 ${formatName(signal.table_name)}`;
        modalSubtitle.innerHTML = `
            <strong>Racha:</strong> ${emoji} ${signal.streak_count} ${signal.colorLabel} &nbsp;|&nbsp;
            <strong>Inicio:</strong> ${signal.start_time || '—'} &nbsp;→&nbsp;
            <strong>Fin:</strong> ${signal.end_time || 'En progreso'}
        `;
    }

    // Mostrar spinner
    modalBody.innerHTML = '<div class="spinner-sm"></div>';
    modal.classList.add('active');

    // Fetch los datos
    try {
        const params = new URLSearchParams({
            mesa: signal.table_name
        });
        
        if (signal.start_time) params.set('start', signal.start_time);
        if (signal.end_time) params.set('end', signal.end_time);
        
        // Usar pico para saber exactamente cuántas jugadas traer hacia atrás
        if (signal.max_delay) params.set('pico', signal.max_delay);
        else if (signal.streak_count) params.set('pico', signal.streak_count);

        const res = await fetch(`/api/signal_detail?${params}`);
        if (!res.ok) throw new Error('Error al obtener detalle');
        const data = await res.json();

        if (!data.plays || data.plays.length === 0) {
            modalBody.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text-secondary)">No se encontraron jugadas en este rango de tiempo.</div>';
            return;
        }

        // Construir tabla de jugadas
        let html = `
            <table class="plays-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Hora</th>
                        <th>Número</th>
                        <th>Color</th>
                    </tr>
                </thead>
                <tbody>
        `;

        data.plays.forEach((play, i) => {
            const colorClass = play.color === 'Red' ? 'red' : (play.color === 'Black' ? 'black' : 'green');
            const colorLabel = play.color === 'Red' ? 'Rojo' : (play.color === 'Black' ? 'Negro' : 'Verde');
            const time = play.timestamp ? play.timestamp.split(' ')[1] || play.timestamp : '—';

            html += `
                <tr>
                    <td style="color:var(--text-secondary)">${i + 1}</td>
                    <td><span class="play-time">${time}</span></td>
                    <td><span class="play-numero ${colorClass}">${play.numero}</span></td>
                    <td>${colorLabel}</td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        modalBody.innerHTML = html;

    } catch (err) {
        console.error('Error fetching signal detail:', err);
        modalBody.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--color-danger)">❌ Error al cargar el detalle de la señal.</div>';
    }
}

function formatName(str) {
    return str.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}
