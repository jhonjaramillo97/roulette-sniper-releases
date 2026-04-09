const OVERVIEW_URL = "/api/overview";
const POLLING_INTERVAL = 1000; // 1 segundo

let audioContext = null;
let soundEnabled = true;
let previousAlertCount = 0;  // Para detectar nuevas alertas

let currentThreshold = 12; // Default

// Inicialización
document.addEventListener("DOMContentLoaded", () => {
    fetchOverview();
    setInterval(fetchOverview, POLLING_INTERVAL);

    // Audio necesita interacción del usuario
    document.body.addEventListener("click", initAudio, { once: true });

    // Lógica para View Toggle
    const btnToggle = document.getElementById("btn-view-toggle");
    const gridEl = document.getElementById("overview-grid");
    const iconGrid = document.querySelector(".icon-grid");
    const iconList = document.querySelector(".icon-list");

    // Leer preferencia guardada (por defecto lista si es móvil, cuadrícula si es PC, o simplemente lista)
    let currentView = localStorage.getItem("dashboardView") || "list-view";
    gridEl.classList.add(currentView);
    updateToggleIcon(currentView);

    if (btnToggle) {
        btnToggle.addEventListener("click", () => {
            if (gridEl.classList.contains("list-view")) {
                gridEl.classList.remove("list-view");
                gridEl.classList.add("grid-view");
                currentView = "grid-view";
            } else {
                gridEl.classList.remove("grid-view");
                gridEl.classList.add("list-view");
                currentView = "list-view";
            }
            localStorage.setItem("dashboardView", currentView);
            updateToggleIcon(currentView);
        });
    }

    function updateToggleIcon(view) {
        if (!iconGrid || !iconList) return;
        if (view === "grid-view") {
            iconGrid.style.display = "none";
            iconList.style.display = "inline";
        } else {
            iconGrid.style.display = "inline";
            iconList.style.display = "none";
        }
    }

    const btnBypass = document.getElementById("bypass-loader");
    if (btnBypass) {
        btnBypass.addEventListener("click", () => {
            document.getElementById("loading-overlay").classList.add("hidden");
            window.loaderBypassed = true;
        });
    }
});

async function fetchOverview() {
    const errorText = document.getElementById("loading-text");
    try {
        const res = await fetch(OVERVIEW_URL);
        if (!res.ok) throw new Error("API Error");
        const data = await res.json();

        // Actualizar threshold global
        if (data.threshold) {
            currentThreshold = data.threshold;
        }

        renderGrid(data.tables);

        // --- LÓGICA DE PANTALLA DE CARGA ---
        // Verificar si los datos son "frescos" (al menos una mesa actualizada hace menos de 60s)
        const isFresh = data.tables.some(t => t.last_update_seconds < 60);
        const loader = document.getElementById("loading-overlay");

        if (loader && !loader.classList.contains("hidden")) {
            if (isFresh) {
                // Hay datos frescos, ocultar pantalla de carga
                loader.classList.add("hidden");
            } else if (data.tables.length > 0) {
                if (errorText && !window.loaderBypassed) errorText.textContent = "Reescaneando mesas... (Los últimos datos son inactivos)";
            }
        } else if (loader && loader.classList.contains("hidden") && data.tables.every(t => t.last_update_seconds > 300)) {
            // Opción: Si TODO muere por más de 5mins y el panel estaba abierto, 
            // no lo volvemos a tapar por ahora para dejar ver los últimos datos. Solo tapamos al inicio.
        }

    } catch (e) {
        console.error("Polling error:", e);
        // Si hay error (servidor caído), asegurarnos de que el usuario lo sepa
        const loader = document.getElementById("loading-overlay");
        if (loader && errorText && !window.loaderBypassed) {
            loader.classList.remove("hidden");
            errorText.textContent = "Conexión perdida con el Bot (Servidor Desconectado)... Intentando reconectar...";
        }
    }
}

function renderGrid(tables) {
    const grid = document.getElementById("overview-grid");

    // Contar alertas totales actuales
    let totalAlerts = 0;
    tables.forEach(t => { totalAlerts += t.alertas.length; });

    // Sonido si hay nueva alerta
    if (totalAlerts > previousAlertCount && previousAlertCount >= 0 && soundEnabled) {
        playAlertSound();
    }
    previousAlertCount = totalAlerts;

    // Solo reconstruir si cambió el número de mesas (primera vez o si se agregan)
    // Después solo actualizamos los valores para evitar flickering
    const existingCards = grid.querySelectorAll(".table-card[data-table]");
    if (existingCards.length !== tables.length) {
        buildCards(grid, tables);
    } else {
        updateCards(tables);
    }
}

function buildCards(grid, tables) {
    grid.innerHTML = "";
    tables.forEach(t => {
        const card = document.createElement("div");
        card.className = "table-card list-item" + (t.alertas.length > 0 ? " has-alert" : "");
        card.dataset.table = t.table_name;

        // El clic en la tarjeta entera hace toggle del acordeon SÓLO en vista lista
        card.onclick = (e) => {
            const gridEl = document.getElementById("overview-grid");
            if (gridEl && gridEl.classList.contains("list-view")) {
                card.classList.toggle("expanded");
            } else {
                // En modo cuadrícula, el clic abre la mesa directamente
                window.location.href = `/mesa?mesa=${t.table_name}`;
            }
        };

        const zoneMap = {
            "docena_1": { label: "1ª Doc", cls: "od-d1" },
            "docena_2": { label: "2ª Doc", cls: "od-d2" },
            "docena_3": { label: "3ª Doc", cls: "od-d3" },
            "columna_3": { label: "Col 3", cls: "od-c3" }, // Top
            "columna_2": { label: "Col 2", cls: "od-c2" }, // Mid
            "columna_1": { label: "Col 1", cls: "od-c1" }  // Bot
        };

        let chipsHTML = "";
        const orderedKeys = ["docena_1", "docena_2", "docena_3", "columna_3", "columna_2", "columna_1"];

        orderedKeys.forEach(k => {
            const v = t.delays[k];
            const meta = zoneMap[k];
            const statusCls = getChipClass(v);
            chipsHTML += `
                <div class="delay-chip ${statusCls} ${meta.cls}" data-zone="${k}">
                    <span class="chip-value">${v}</span>
                    <span class="chip-label">${meta.label}</span>
                </div>`;
        });

        let dotColor = 'var(--color-safe)';
        if (t.alertas.length > 0) {
            dotColor = 'var(--color-danger)';
        } else if (t.last_update_seconds > 180) {
            dotColor = 'var(--color-warn)';
        }

        const alertBadge = t.alertas.length > 0
            ? `<span class="alert-badge pulse">🔴 ${t.alertas.length} Señal${t.alertas.length > 1 ? 'es' : ''}</span>`
            : (t.last_update_seconds > 180 ? `<span class="status-badge warn">⚠️ Inactivo</span>` : `<span class="status-badge safe">✅ Normal</span>`);

        const historyHTML = getMiniHistoryHTML(t.last_10);

        card.innerHTML = `
            <div class="accordion-header">
                <div class="header-left">
                    <span class="tc-status-dot" style="background:${dotColor}; box-shadow:0 0 8px ${dotColor}"></span>
                    <span class="tc-name">${t.name}</span>
                    <span class="tc-freshness">${formatTimeAgo(t.last_update_seconds)}</span>
                </div>
                <div class="header-right">
                    ${alertBadge}
                    <span class="chevron">▼</span>
                </div>
            </div>
            <div class="accordion-body">
                <div class="tc-delays">${chipsHTML}</div>
                <div class="tc-footer">
                    ${historyHTML}
                    <a href="/mesa?mesa=${t.table_name}" class="btn-detalles">Abrir ↗</a>
                </div>
            </div>`;

        grid.appendChild(card);
    });
}

function updateCards(tables) {
    tables.forEach(t => {
        const card = document.querySelector(`.table-card[data-table="${t.table_name}"]`);
        if (!card) return;

        if (t.alertas.length > 0) {
            card.classList.add("has-alert");
        } else {
            card.classList.remove("has-alert");
        }

        const dot = card.querySelector(".tc-status-dot");
        if (dot) {
            let dotColor = 'var(--color-safe)';
            if (t.alertas.length > 0) {
                dotColor = 'var(--color-danger)';
            } else if (t.last_update_seconds > 180) {
                dotColor = 'var(--color-warn)';
            }
            dot.style.background = dotColor;
            dot.style.boxShadow = `0 0 8px ${dotColor}`;
        }

        const freshness = card.querySelector(".tc-freshness");
        if (freshness) {
            freshness.textContent = formatTimeAgo(t.last_update_seconds);
        }

        // Usamos querySelector desde card para encontrar header-right y badge
        const headerRight = card.querySelector(".header-right");
        if (headerRight) {
            const currentChevron = headerRight.querySelector(".chevron") ? '<span class="chevron">▼</span>' : '';
            const alertBadge = t.alertas.length > 0
                ? `<span class="alert-badge pulse">🔴 ${t.alertas.length} Señal${t.alertas.length > 1 ? 'es' : ''}</span>`
                : (t.last_update_seconds > 180 ? `<span class="status-badge warn">⚠️ Inactivo</span>` : `<span class="status-badge safe">✅ Normal</span>`);
            headerRight.innerHTML = alertBadge + currentChevron;
        }


        const zoneKeys = ["docena_1", "docena_2", "docena_3", "columna_1", "columna_2", "columna_3"];
        zoneKeys.forEach(k => {
            const chip = card.querySelector(`[data-zone="${k}"]`);
            if (!chip) return;
            const v = t.delays[k];
            chip.querySelector(".chip-value").textContent = v;

            const currentClasses = chip.className.split(" ");
            const positionClass = currentClasses.find(c => c.startsWith("od-"));

            chip.className = `delay-chip ${getChipClass(v)} ${positionClass}`;
        });

        const footer = card.querySelector(".tc-footer");
        if (footer) {
            const historyHTML = getMiniHistoryHTML(t.last_10);
            const btnLink = `<a href="/mesa?mesa=${t.table_name}" class="btn-detalles">Abrir ↗</a>`;
            footer.innerHTML = historyHTML + btnLink;
        }
    });
}

function getMiniHistoryHTML(last5) {
    if (!last5 || last5.length === 0) return '<span class="history-mini-row">-</span>';
    let html = '<div class="history-mini-row">';
    last5.forEach(n => {
        let colorClass = "num-green";
        if (n.col === "Red") colorClass = "num-red";
        else if (n.col === "Black") colorClass = "num-black";

        html += `<div class="mini-chip ${colorClass}">${n.val}</div>`;
    });
    html += '</div>';
    return html;
}

function formatTimeAgo(seconds) {
    if (seconds >= 999999 - 1000) return "Sin datos";
    if (seconds < 60) return `${Math.floor(seconds)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
}

function getChipClass(value) {
    if (value >= currentThreshold) return "chip-critical";
    if (value >= (currentThreshold - 2)) return "chip-danger";
    if (value >= 6) return "chip-warn";
    return "chip-safe";
}

// ─── AUDIO ───
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
    const now = Date.now();
    if (now - lastAlertTime < 3000) return;
    lastAlertTime = now;

    if (!audioContext) initAudio();
    if (!audioContext) return;

    // Sonido "Glass Ping" Profesional (Doble oscilador)
    const t = audioContext.currentTime;

    // Oscilador 1: Tono base (Aclarado)
    const osc1 = audioContext.createOscillator();
    const gain1 = audioContext.createGain();

    osc1.type = "sine";
    osc1.frequency.setValueAtTime(900, t); // ~A5 sharp

    gain1.gain.setValueAtTime(0, t);
    gain1.gain.linearRampToValueAtTime(0.3, t + 0.01); // Attack rápido
    gain1.gain.exponentialRampToValueAtTime(0.001, t + 1.5); // Decay largo y sauve

    osc1.connect(gain1);
    gain1.connect(audioContext.destination);

    // Oscilador 2: Armónico (Brillo metálico)
    const osc2 = audioContext.createOscillator();
    const gain2 = audioContext.createGain();

    osc2.type = "sine";
    osc2.frequency.setValueAtTime(1350, t); // 1.5x frec base (quinta)

    gain2.gain.setValueAtTime(0, t);
    gain2.gain.linearRampToValueAtTime(0.1, t + 0.01);
    gain2.gain.exponentialRampToValueAtTime(0.001, t + 0.5); // Decay más corto

    osc2.connect(gain2);
    gain2.connect(audioContext.destination);

    osc1.start(t);
    osc2.start(t);

    osc1.stop(t + 1.5);
    osc2.stop(t + 1.5);
}
