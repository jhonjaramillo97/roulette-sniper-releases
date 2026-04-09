document.addEventListener("DOMContentLoaded", () => {
    fetchGlobalData();
});

async function fetchGlobalData() {
    try {
        const res = await fetch("/api/analisis_global");
        if (!res.ok) throw new Error("Error fetching global data");
        const data = await res.json();

        processAndRender(data.history, data.threshold);

        // Ocultar loader y mostrar contenido
        document.getElementById('loader').style.display = 'none';
        document.getElementById('stats-container').style.display = 'flex';
        document.getElementById('charts-container').style.display = 'grid';
        document.getElementById('tables-container').style.display = 'grid';

    } catch (error) {
        console.error("Fetch Analysis Error:", error);
        document.getElementById('loader').innerHTML = `<div style="color:var(--color-danger)">❌ Error al cargar los datos históricos. Asegúrate de que el bot tenga registros guardados en SQLite.</div>`;
    }
}

function processAndRender(history, threshold) {
    if (!history || history.length === 0) {
        document.getElementById('loader').innerHTML = `<div>No hay suficientes datos procesados en la Base de Datos.</div>`;
        return;
    }

    // --- 1. Calcular KPIs Globales ---
    const totalSignals = history.length;
    const maxDelayGlobal = Math.max(...history.map(e => e.max_delay));
    const avgDelayGlobal = history.reduce((acc, curr) => acc + curr.max_delay, 0) / totalSignals;

    document.getElementById('val-total').textContent = totalSignals;
    document.getElementById('val-avg').textContent = avgDelayGlobal.toFixed(2);
    document.getElementById('val-max').textContent = maxDelayGlobal;

    // --- 2. Procesar Datos por Mesa ---
    const tableStats = {};
    history.forEach(evt => {
        const tn = evt.table_name;
        if (!tableStats[tn]) {
            tableStats[tn] = { name: tn, count: 0, max: 0, sum: 0 };
        }
        tableStats[tn].count += 1;
        tableStats[tn].sum += evt.max_delay;
        if (evt.max_delay > tableStats[tn].max) {
            tableStats[tn].max = evt.max_delay;
        }
    });

    const tableNames = Object.keys(tableStats).map(t => formatName(t));
    const tableCounts = Object.keys(tableStats).map(t => tableStats[t].count);

    // Generar Tabla HTML de Mesas
    const tbodyTables = document.getElementById('tbody-tables');
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
        tbodyTables.appendChild(tr);
    });

    // --- 3. Top 10 Señales Más Críticas ---
    const top10 = history.slice().sort((a, b) => b.max_delay - a.max_delay).slice(0, 10);
    const tbodyTop10 = document.getElementById('tbody-top10');

    top10.forEach((evt, index) => {
        const zoneMap = {
            "docena_1": "1ª Docena", "docena_2": "2ª Docena", "docena_3": "3ª Docena",
            "columna_1": "Columna 1", "columna_2": "Columna 2", "columna_3": "Columna 3"
        };
        const zoneLabel = zoneMap[evt.zone_name] || evt.zone_name;
        const end = evt.end_time ? evt.end_time : 'En progreso';

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${index + 1}. ${formatName(evt.table_name)}</strong></td>
            <td>${zoneLabel}</td>
            <td class="max-delay-col delay-extreme">${evt.max_delay} giros</td>
            <td>${end}</td>
        `;
        tbodyTop10.appendChild(tr);
    });

    // --- 4. Renderizar Gráficos (Chart.js) ---
    renderCharts(tableNames, tableCounts, top10);
}

function renderCharts(labels, dataCounts, top10) {
    // defaults
    Chart.defaults.color = '#94a3b8'; // text-secondary
    Chart.defaults.font.family = "'Inter', sans-serif";

    // Grafico 1: Volumen
    const ctxVol = document.getElementById('chartVolume').getContext('2d');
    new Chart(ctxVol, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Señales Disparadas',
                data: dataCounts,
                backgroundColor: 'rgba(34, 197, 94, 0.5)', // Safe green
                borderColor: 'rgba(34, 197, 94, 1)',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } },
                x: { grid: { display: false }, ticks: { display: false } }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });

    // Grafico 2: Top 10 Picos
    const ctxTop = document.getElementById('chartTop10').getContext('2d');
    const topLabels = top10.map((e, i) => `${i + 1}. ${formatName(e.table_name)}`);
    const topData = top10.map(e => e.max_delay);

    new Chart(ctxTop, {
        type: 'line',
        data: {
            labels: topLabels,
            datasets: [{
                label: 'Max Delay Alcanzado',
                data: topData,
                backgroundColor: 'rgba(239, 68, 68, 0.2)', // Danger red
                borderColor: 'rgba(239, 68, 68, 1)',
                borderWidth: 2,
                pointBackgroundColor: 'rgba(239, 68, 68, 1)',
                pointRadius: 6,
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

function formatName(str) {
    return str.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}
