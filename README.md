# Roulette Sniper - Bot Analítico para Stake 🎰

Un bot automatizado avanzado diseñado para extraer datos en vivo de múltiples mesas de ruleta de Pragmatic Play a través del casino online Stake, calcular los retrasos (delays) estadísticos de docenas y columnas, emitir alertas en Telegram, y proveer un Dashboard visual de monitoreo en tiempo real.

---

## 🚀 Características Principales

- **Web Scraping Dinámico:** Usa Selenium (`undetected_chromedriver`) para rodear medidas Anti-Bot (ej. Cloudflare) y extraer el feed en vivo del Lobby del casino sin abrir múltiples iframes.
- **Multimesa Simultáneo:** Capaz de rastrear 10 mesas simultáneamente:
    - Ruleta Latina / Stake Roulette
    - Mega Roulette / Brazilian Mega Roulette
    - Roulette Macao / Brazilian Roulette
    - Roulette 1 / Roulette 3
    - Roulette 2 Extra Time
    - Lucky 6 Roulette / Auto Roulette
- **Gestión de Sesión Constante:** Reutiliza el perfil de Chrome (cookies) e implementa limpiezas preventivas de LocalStorage/Cookies antes del inicio de sesión para mantener estabilidad. Módulo Anti-AFK integrado.
- **Base de Datos Persistente:** Utiliza **SQLite 3** (`data/ruleta.db`) para ir almacenando cada giro y preservar el histórico sin utilizar RAM desmesurada ni lidiar con bloqueos de CSV concurrentes.
- **Backtesting en Tiempo Real:** Cuenta con una tabla de eventos cerrados y un motor de sincronización incremental (`sync_backtest`) capaz de mostrar rápidamente el historial de retrasos de cualquier mesa para evaluación analítica.
- **Alertas Premium en Telegram:** Envío asíncrono e inteligente de alertas hacia Telegram (cada vez que una docena/columna pasa del `THRESHOLD`). En el mensaje se adjuntan, pre-formateados con Emojis Blue Keycap, los últimos 10 giros que provocaron la alerta para un contexto ultra rápido.
- **Dashboard Interactivo:** Panel web local asincrónico montado en Flask. Funciona en el puerto `:5050` con una UI estética y responsiva: vistas globales resumiendo delays altos en todas las ruletas y vistas detalladas por mesa con gráficos visuales y alarmas sonoras automáticas.

---

## 📋 Requisitos Previos

Necesitarás instalar los siguientes componentes en el sistema (Linux/Windows/macOS):

- **Python 3.9+**
- **Google Chrome** instalado (versión regular de escritorio).
- Administrador de paquetes **pip**.

---

## 🛠️ Instalación y Configuración

1. **Clonar o descargar el proyecto**
2. **Instalar Dependencias de Python**
   Abre una terminal en la ruta del proyecto y ejecuta:
   ```bash
   pip install -r requirements.txt
   ```
   *(Si no hay `requirements.txt`, instalar las principales: `pip install selenium undetected-chromedriver requests flask python-dotenv`)*

3. **Configuración del Archivo Entorno (`.env`)**
   Crea o modifica el archivo `.env` en el directorio principal del proyecto con los siguientes datos esenciales:

   ```env
   tu_email_de_stake@gmail.com
   TuPasswordSecreta123!
   TELEGRAM_TOKEN=123456789:TuTokenBotDeTelegram...
   TELEGRAM_CHAT_ID=00000000
   ALERT_THRESHOLD=10
   HEADLESS=true
   ```

   - **Líneas 1 y 2**: Tu correo electrónico y contraseña en Stake.
   - **TELEGRAM_TOKEN / TELEGRAM_CHAT_ID**: Las credenciales de la API de Telegram para enviar las alertas.
   - **ALERT_THRESHOLD**: El nivel de "Ausencia/Retraso" en una docena o columna al cual se dispara la prevención de apuesta (ej `10`).
   - **HEADLESS**: Ponlo en `true` para que el navegador corra de fondo sin molestarte visualmente. En `false` mostrará la interfaz de Chrome abriéndose (ideal para comprobar fallos/debug).

---

## 🖥️ Uso del Sistema

Este bot posee diferentes scripts ejecutables de acuerdo a lo que necesites:

### 1. Arrancar el Ecosistema Completo
Inicia el Dashboard de métricas, y acto seguido arranca el proceso automático de bot/scrape:
```bash
# En Windows:
start_bot.bat

# En Linux:
./start_bot.sh
```
Una vez iniciado, entra en tu navegador favorito a `http://localhost:5050` para ver la interfaz en tiempo real.

### 2. Comprobar Alertas Manualmente
Si quieres correr una diagnosis instantánea basada en el historial registrado en la Base de Datos para probar si el formato de alertas funciona, puedes correr este script utilitario:
```bash
python3 check_alerts_now.py
```

### 3. Extraer Análisis Detallado (Backtesting Global)
Si necesitas auditar matemáticamente rendimientos profundos sobre otra base de datos o el historial completo actual (promedios de caídas, tops de rachas negativas históricas):
```bash
python3 analyze_analisis_db.py
```
*(Esto deposita un archivo `Reporte_Backtesting.md` con las analíticas del casino calculadas a nivel estadístico).*

---

## 🗂️ Estructura del Proyecto Recomendada

```
bot_stake/
├── .env                              # Archivo clave con contraseñas e IDs de Bot
├── start_bot.bat / .sh               # Lanzador principal
├── Documentacion_Tecnica_Bot_Stake.md # Guía sobre estructura interna
├── analyze_analisis_db.py            # Validador estadístico masivo historico
├── check_alerts_now.py               # Probe para telegram
│
├── bot_ruleta/
│   ├── config.py                     # Motor lectura config .env
│   ├── db.py                         # Conexión local a Base de Datos (SQLite)
│   ├── logic.py                      # Algoritmia matemática y alertas TG
│   ├── driver.py                     # Manejo Selenium
│   ├── scanner.py                    # Scanner de OCR / Parseo DOM pragmátic
│   │
│   ├── data/
│   │   └── ruleta.db                 # ¡Tu Base de datos generada automaticamente!
│   │
│   └── dashboard/
│       ├── app.py                    # Backend Flask Server
│       ├── templates/                # (Opcional) Views de Flask
│       └── static/                   # Frontend de la Vista
│           ├── index.html            # Overivew Page
│           ├── mesa.html             # Detail view y backtest UI
│           ├── style.css             # Styling Dark Web Premium 
│           ├── main.js               # Logic Polling Index
│           └── mesa.js               # Logic Polling Detail
└── ...
```

---

## 🛡️ Aviso de Responsabilidad
Este software es una herramienta estrictamente analítica. Todos los valores presentados están basados en la información expuesta visualmente por los proveedores en vivo. Se recomienda configuraciones de `THRESHOLD` holgadas y usar prudencia; la automatización del sitio interactúa con infraestructuras privadas. El autor de las estrategias asume toda responsabilidad por uso y mantenimiento de las credenciales de conectividad inyectadas al Bot. 
