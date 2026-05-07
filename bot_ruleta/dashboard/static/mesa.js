const API_URL = "/api/data";
const TABLES_URL = "/api/mesas";
const POLLING_INTERVAL = 1000; // 1 segundo

// Leer mesa de URL: /mesa?mesa=ruleta_latina
const urlParams = new URLSearchParams(window.location.search);
let currentTable = urlParams.get("mesa") || "ruleta_latina";
let audioContext = null;
let soundEnabled = true;

let currentThreshold = 12; // Default

// Elementos DOM
const tableSelect = document.getElementById("table-select");
const statusDot = document.querySelector(".status-dot");
const soundBtn = document.getElementById("sound-toggle");
const historyContainer = document.getElementById("history-container");

// Inicialización
document.addEventListener("DOMContentLoaded", () => {
    loadTables();
    startPolling();

    // Configurar audio en primer clic
    document.body.addEventListener("click", initAudio, { once: true });

    soundBtn.addEventListener("click", () => {
        soundEnabled = !soundEnabled;
        soundBtn.textContent = soundEnabled ? "🔊" : "🔇";
        soundBtn.style.opacity = soundEnabled ? "1" : "0.5";
    });

    tableSelect.addEventListener("change", (e) => {
        currentTable = e.target.value;
        // Limpiar UI
        document.querySelectorAll(".counter-value").forEach(el => el.textContent = "--");
        document.getElementById('backtest-body').innerHTML = '<tr><td colspan="4" class="loading-td">Cargando historial...</td></tr>';
        document.getElementById('backtest-color-body').innerHTML = '<tr><td colspan="4" class="loading-td">Cargando historial...</td></tr>';
        fetchBacktest();
        fetchColorBacktest();
    });

    // Tab switching para historial
    document.querySelectorAll('#backtest-tabs .tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const tab = btn.dataset.tab;
            document.querySelectorAll('#backtest-tabs .tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            document.getElementById('panel-' + tab).classList.add('active');
        });
    });
});

async function loadTables() {
    try {
        const res = await fetch(TABLES_URL);
        const data = await res.json();

        tableSelect.innerHTML = "";
        data.forEach(mesa => {
            const opt = document.createElement("option");
            opt.value = mesa.value;
            opt.textContent = mesa.name;
            if (mesa.value === currentTable) opt.selected = true;
            tableSelect.appendChild(opt);
        });
    } catch (e) {
        console.error("Error cargando mesas:", e);
    }
}

function startPolling() {
    updateDashboard();
    fetchBacktest();
    fetchColorBacktest();
    setInterval(updateDashboard, POLLING_INTERVAL);
    setInterval(fetchBacktest, 5000);
    setInterval(fetchColorBacktest, 5000);
}

async function fetchBacktest() {
    try {
        const res = await fetch(`/api/backtest?mesa=${currentTable}`);
        if (!res.ok) return;
        const data = await res.json();

        const tbody = document.getElementById('backtest-body');
        tbody.innerHTML = '';

        if (!data.history || data.history.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="loading-td">No hay historial de señales registrado aún.</td></tr>';
            return;
        }

        const zoneMap = {
            "docena_1": "1ª Docena", "docena_2": "2ª Docena", "docena_3": "3ª Docena",
            "columna_1": "Columna 1", "columna_2": "Columna 2", "columna_3": "Columna 3"
        };

        data.history.forEach(evt => {
            const tr = document.createElement('tr');
            const zoneLabel = zoneMap[evt.zone_name] || evt.zone_name;

            let delayClass = "";
            if (evt.max_delay >= 20) delayClass = "delay-extreme";
            else if (evt.max_delay >= 15) delayClass = "delay-high";

            // SQLite datetime string: 'YYYY-MM-DD HH:MM:SS'
            const start = evt.start_time.split(' ')[1] || evt.start_time; // Solo hora
            const end = evt.end_time ? (evt.end_time.split(' ')[1] || evt.end_time) : '-';

            tr.innerHTML = `
                <td>${evt.start_time.slice(5, 16)}</td>
                <td><strong>${zoneLabel}</strong></td>
                <td class="max-delay-col ${delayClass}">${evt.max_delay} giros</td>
                <td>${end}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Error cargando backtest:", e);
    }
}

async function fetchColorBacktest() {
    try {
        const res = await fetch(`/api/backtest_color?mesa=${currentTable}`);
        if (!res.ok) return;
        const data = await res.json();

        const tbody = document.getElementById('backtest-color-body');
        tbody.innerHTML = '';

        if (!data.history || data.history.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="loading-td">No hay historial de rachas de color registrado aún.</td></tr>';
            return;
        }

        data.history.forEach(evt => {
            const tr = document.createElement('tr');
            const isRed = evt.streak_color === 'Red';
            const emoji = isRed ? '🔴' : '⚫';
            const colorLabel = isRed ? 'Rojos' : 'Negros';
            const end = evt.end_time ? (evt.end_time.split(' ')[1] || evt.end_time) : 'En progreso';

            tr.innerHTML = `
                <td>${evt.start_time.slice(5, 16)}</td>
                <td><span class="color-streak-badge ${isRed ? 'red' : 'black'}">${emoji} ${colorLabel}</span></td>
                <td class="max-delay-col" style="color: ${isRed ? '#ff6b6b' : '#e0e0e0'}">${evt.streak_count} consecutivos</td>
                <td>${end}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Error cargando color backtest:", e);
    }
}

async function updateDashboard() {
    try {
        const res = await fetch(`${API_URL}?mesa=${currentTable}`);
        if (!res.ok) throw new Error("API Error");

        const data = await res.json();

        // Actualizar threshold global
        if (data.threshold) {
            currentThreshold = data.threshold;
        }

        // Actualizar estado conexión basado en frescura de datos
        const statusText = document.getElementById("status-text");
        if (data.last_update_seconds > 180) {
            // Datos viejos (desconectado o reiniciando scraper)
            statusDot.style.boxShadow = "0 0 8px var(--color-warn)";
            statusDot.style.backgroundColor = "var(--color-warn)";
            statusText.textContent = "⚠️ Reconectando...";
            statusText.style.color = "var(--color-warn)";
        } else {
            // Datos frescos
            statusDot.style.boxShadow = "0 0 8px var(--color-safe)";
            statusDot.style.backgroundColor = "var(--color-safe)";
            statusText.textContent = "Conectado";
            statusText.style.color = "var(--text-primary)";
        }

        // Actualizar contadores
        const delays = data.delays;
        let alertTriggered = false;

        for (const [key, value] of Object.entries(delays)) {
            updateCard(key, value);
            if (value >= currentThreshold) alertTriggered = true;
        }

        // Actualizar historial
        renderHistory(data.ultimos);

        // Señal de racha de color
        const banner = document.getElementById("color-streak-banner");
        const bannerText = document.getElementById("color-streak-text");
        const csThreshold = data.color_streak_threshold || 5;
        
        if (data.color_streak && data.color_streak.streak >= csThreshold) {
            const isRed = data.color_streak.color === "Red";
            const emoji = isRed ? "🔴" : "⚫";
            const colorName = isRed ? "Rojos" : "Negros";
            const opposite = isRed ? "Negro" : "Rojo";
            
            banner.style.display = "flex";
            banner.className = "color-streak-banner " + (isRed ? "streak-red" : "streak-black");
            bannerText.innerHTML = `${emoji} <strong>${data.color_streak.streak} ${colorName}</strong> consecutivos — Señal para apostar al <strong>${opposite}</strong>`;
        } else {
            banner.style.display = "none";
        }

        // Sonido si hay alerta activa (DESACTIVADO EN DETALLE, SOLO EN OVERVIEW)
        // if (alertTriggered && soundEnabled) {
        //     playAlertSound();
        // }

    } catch (e) {
        console.error("Polling error:", e);
        statusDot.style.boxShadow = "0 0 8px var(--color-danger)";
        statusDot.style.backgroundColor = "var(--color-danger)";
        document.getElementById("status-text").textContent = "Error de Red";
        document.getElementById("status-text").style.color = "var(--color-danger)";
    }
}

function updateCard(key, value) {
    const card = document.getElementById(`card-${key}`);
    const valEl = document.getElementById(`val-${key}`);
    const progEl = document.getElementById(`prog-${key}`);

    valEl.textContent = value;

    // Calcular porcentaje (max 20 para visualizar que sigue subiendo)
    const percentage = Math.min((value / 20) * 100, 100);
    progEl.style.width = `${percentage}%`;

    // Colores dinámicos
    card.classList.remove("alert-active");

    if (value < 6) {
        progEl.style.backgroundColor = "var(--color-safe)";
        valEl.style.color = "var(--text-primary)";
    } else if (value < (currentThreshold - 2)) {
        // WARN (< 10 si th=12)
        progEl.style.backgroundColor = "var(--color-warn)";
        valEl.style.color = "var(--color-warn)";
    } else if (value < currentThreshold) {
        // DANGER (< 12 si th=12)
        progEl.style.backgroundColor = "var(--color-danger)";
        valEl.style.color = "var(--color-danger)";
    } else {
        // ALERTA >= currentThreshold
        progEl.style.backgroundColor = "var(--color-critical)";
        valEl.style.color = "var(--color-critical)";
        card.classList.add("alert-active");
    }
}

function renderHistory(nums) {
    historyContainer.innerHTML = "";
    nums.forEach(n => {
        const div = document.createElement("div");
        div.className = "history-item";
        div.textContent = n.numero;

        if (n.color === "Red") div.classList.add("num-red");
        else if (n.color === "Black") div.classList.add("num-black");
        else div.classList.add("num-green"); // Green

        historyContainer.appendChild(div);
    });
}

// --- AUDIO ---
function initAudio() {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContext.state === 'suspended') {
        audioContext.resume();
    }
}

let lastAlertTime = 0;
function playAlertSound() {
    // Evitar sonar demasiado seguido (máx 1 vez cada 2 seg)
    const now = Date.now();
    if (now - lastAlertTime < 2000) return;
    lastAlertTime = now;

    if (!audioContext) initAudio();
    if (audioContext) {
        const osc = audioContext.createOscillator();
        const gain = audioContext.createGain();

        osc.type = "sine";
        osc.frequency.setValueAtTime(660, audioContext.currentTime); // Tono alto
        osc.frequency.exponentialRampToValueAtTime(440, audioContext.currentTime + 0.5);

        gain.gain.setValueAtTime(0.3, audioContext.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);

        osc.connect(gain);
        gain.connect(audioContext.destination);

        osc.start();
        osc.stop(audioContext.currentTime + 0.5);
    }
}
