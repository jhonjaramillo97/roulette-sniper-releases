import os
import sys
import time
import queue
import threading
import subprocess
import webbrowser
import platform
import urllib.request
from PIL import Image
import customtkinter as ctk

# Ensure bot_ruleta is in the path if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_ruleta.gui_credentials import save_credentials, load_saved_credentials, has_saved_credentials, delete_saved_credentials
from bot_ruleta.config import set_runtime_config, load_credentials
from bot_ruleta.debug_logger import attach_gui_queue, get_logger
from bot_ruleta.scanner import run_bot
from bot_ruleta.launcher import _start_cloudflared, get_cf_env_vars, TUNNEL_FILE
from bot_ruleta.logic import send_telegram_msg

from bot_ruleta.updater import check_for_updates, perform_update
import tkinter.messagebox as messagebox

# Global config
ctk.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("green")  # Themes: "blue" (standard), "green", "dark-blue"

log = get_logger("gui")

def resource_path(relative_path):
    """Resuelve rutas de archivos empaquetados (PyInstaller) o de desarrollo."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

class RouletteApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Roulette Sniper Pro")
        self.geometry("800x750")
        self.minsize(800, 750)
        
        # Configurar icono de ventana
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # Center the window
        self.update_idletasks()
        width = self.winfo_width()
        frm_width = self.winfo_rootx() - self.winfo_x()
        win_width = width + 2 * frm_width
        height = self.winfo_height()
        titlebar_height = self.winfo_rooty() - self.winfo_y()
        win_height = height + titlebar_height + frm_width
        x = self.winfo_screenwidth() // 2 - win_width // 2
        y = self.winfo_screenheight() // 2 - win_height // 2
        self.geometry(f'{width}x{height}+{x}+{y}')

        # Force Native Dark Title Bar on Windows 10/11
        if platform.system() == "Windows":
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                value = ctypes.c_int(2)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)
            except Exception:
                pass

        # Shared state
        self.log_queue = queue.Queue()
        self.bot_thread = None
        self.cf_proc = None
        self.stop_event = threading.Event()
        self.dashboard_proc = None
        self.public_url = "Generando..."

        # Container for screens
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True, padx=20, pady=20)

        self.frames = {}
        
        for F in (PrerequisitesScreen, LoginScreen, LoadingScreen, DashboardScreen, UpdateScreen):
            frame = F(parent=self.container, controller=self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        # Connect logger to GUI
        attach_gui_queue(self.log_queue)

        # Start polling log queue
        self.after(100, self.process_log_queue)

        self.show_frame(PrerequisitesScreen)

        # Cleanup on close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def show_frame(self, cont):
        frame = self.frames[cont]
        frame.tkraise()
        if hasattr(frame, 'on_show'):
            frame.on_show()

    def process_log_queue(self):
        while not self.log_queue.empty():
            try:
                msg_type, level, msg = self.log_queue.get_nowait()
                if msg_type == "log":
                    dashboard = self.frames[DashboardScreen]
                    dashboard.append_log(level, msg)
            except queue.Empty:
                break
        self.after(100, self.process_log_queue)

    def start_background_services(self):
        # 1. Start Flask Dashboard in a separate process
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            self.dashboard_proc = subprocess.Popen(
                [sys.executable, "--run-dashboard"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
        except Exception as e:
            pass

        # 2. Start Cloudflared Watchdog
        self.cf_watchdog_thread = threading.Thread(target=self.cloudflared_watchdog, daemon=True)
        self.cf_watchdog_thread.start()

    def cloudflared_watchdog(self):
        while not self.stop_event.is_set():
            try:
                token, domain = get_cf_env_vars()
                log.info("🌐 Iniciando túnel Cloudflare...")
                self.cf_proc = _start_cloudflared(token)
                
                if token:
                    # Link fijo permanente
                    display_url = "https://botstake.shop"
                    old_url = self.public_url
                    self.public_url = display_url
                    self.frames[DashboardScreen].update_cf_url(display_url)
                    
                    try:
                        with open(TUNNEL_FILE, "w") as f:
                            f.write(display_url)
                    except Exception:
                        pass
                    
                    # Notificar por Telegram
                    if display_url != old_url:
                        try:
                            _, _, tg_token, chat_id, _, _ = load_credentials()
                            if tg_token and chat_id and tg_token.strip() != "":
                                tg_msg = (
                                    f"🌐 *Dashboard Activo*\n\n"
                                    f"El bot acaba de encenderse. Panel permanente disponible en:\n\n{display_url}"
                                )
                                send_telegram_msg(tg_token, chat_id, tg_msg)
                        except Exception as e:
                            log.warning(f"Error enviando URL a Telegram: {e}")
                    
                    log.info(f"🌐 Túnel Zero Trust conectado: {display_url}")
                    
                    # Consumir stderr para que el proceso no se bloquee
                    for line in iter(self.cf_proc.stderr.readline, b''):
                        if self.stop_event.is_set():
                            break
                else:
                    # Flujo de desarrollo (random trycloudflare)
                    import re
                    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
                    log.info("🌐 Iniciando túnel aleatorio para desarrollo...")
                    for line in iter(self.cf_proc.stderr.readline, b''):
                        if self.stop_event.is_set():
                            break
                        line_str = line.decode('utf-8', errors='ignore')
                        match = url_pattern.search(line_str)
                        if match:
                            found_url = match.group(0)
                            old_url = self.public_url
                            self.public_url = found_url
                            self.frames[DashboardScreen].update_cf_url(found_url)
                            
                            try:
                                with open(TUNNEL_FILE, "w") as f:
                                    f.write(found_url)
                            except Exception:
                                pass
                                
                            log.info(f"🌐 Túnel temporal establecido: {found_url}")
                            
                            # Avisar a Telegram del túnel temporal
                            if found_url != old_url:
                                try:
                                    _, _, tg_token, chat_id, _, _ = load_credentials()
                                    if tg_token and chat_id and tg_token.strip() != "":
                                        tg_msg = (
                                            f"⚙️ <b>[MODO DESARROLLADOR]</b> Bot iniciado.\n\n"
                                            f"Dashboard temporal: {found_url}"
                                        )
                                        send_telegram_msg(tg_token, chat_id, tg_msg)
                                except Exception:
                                    pass
                
                if self.stop_event.is_set():
                    break
                    
                self.cf_proc.wait()
                log.warning("⚠️ Cloudflared se cayó. Reiniciando en 10 segundos...")
                self.frames[DashboardScreen].update_cf_url("⏳ Reconectando...")
                time.sleep(10)
                
            except FileNotFoundError:
                log.error("❌ cloudflared no está instalado")
                self.frames[DashboardScreen].update_cf_url("ERROR: No instalado")
                break
            except Exception as e:
                log.warning(f"⚠️ Error en túnel Cloudflare: {e}")
                time.sleep(10)

    def on_closing(self):
        self.stop_event.set()
        
        if self.dashboard_proc:
            try: self.dashboard_proc.terminate()
            except: pass
            
        if self.cf_proc:
            try: self.cf_proc.terminate()
            except: pass

        self.destroy()


class PrerequisitesScreen(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Title
        lbl_title = ctk.CTkLabel(self, text="Verificación del Sistema", font=ctk.CTkFont(size=24, weight="bold"))
        lbl_title.pack(pady=(40, 20))

        # Status Frame
        self.status_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.status_frame.pack(pady=20, padx=50, fill="x")

        self.lbl_chrome = ctk.CTkLabel(self.status_frame, text="⏳ Comprobando Chrome...", font=ctk.CTkFont(size=16))
        self.lbl_chrome.pack(pady=10, anchor="w")

        self.lbl_cf = ctk.CTkLabel(self.status_frame, text="⏳ Comprobando Cloudflared...", font=ctk.CTkFont(size=16))
        self.lbl_cf.pack(pady=10, anchor="w")

        self.lbl_net = ctk.CTkLabel(self.status_frame, text="⏳ Comprobando Internet...", font=ctk.CTkFont(size=16))
        self.lbl_net.pack(pady=10, anchor="w")

        # Action Button
        self.btn_continue = ctk.CTkButton(self, text="Continuar", state="disabled", width=220, height=45, corner_radius=25,
                                          font=ctk.CTkFont(size=14, weight="bold"),
                                          command=lambda: controller.show_frame(LoginScreen))
        self.btn_continue.pack(pady=40)

        self.btn_download_cf = ctk.CTkButton(self, text="Descargar Cloudflared", width=220, height=45, corner_radius=25, 
                                             font=ctk.CTkFont(size=14, weight="bold"), fg_color="#ff9900", hover_color="#cc7a00",
                                             command=lambda: webbrowser.open("https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"))
        
    def on_show(self):
        # Run checks in background
        threading.Thread(target=self.run_checks, daemon=True).start()

    def run_checks(self):
        all_ok = True
        
        # 1. Check Chrome
        chrome_ok = False
        try:
            if platform.system() == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                version, _ = winreg.QueryValueEx(key, "version")
                self.lbl_chrome.configure(text=f"✅ Chrome instalado (v{version})", text_color="#00FF88")
                chrome_ok = True
            else:
                self.lbl_chrome.configure(text="✅ Sistema no-Windows (Asumiendo Chrome OK)", text_color="#00FF88")
                chrome_ok = True
        except:
            self.lbl_chrome.configure(text="❌ Chrome NO encontrado", text_color="#FF4444")
            all_ok = False

        # 2. Check Cloudflared
        try:
            subprocess.run(["cloudflared", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            self.lbl_cf.configure(text="✅ Cloudflared instalado", text_color="#00FF88")
        except:
            self.lbl_cf.configure(text="❌ Cloudflared NO encontrado", text_color="#FF4444")
            self.btn_download_cf.pack(pady=10, before=self.btn_continue)
            all_ok = False

        # 3. Check Internet
        try:
            # Primero intentar con Stake
            import urllib.error
            try:
                urllib.request.urlopen("https://stake.com.co", timeout=5)
                self.lbl_net.configure(text="✅ Conexión a Internet OK", text_color="#00FF88")
            except urllib.error.HTTPError as e:
                if e.code in (403, 401, 503): # Cloudflare protection, pero significa que hay internet
                    self.lbl_net.configure(text="✅ Conexión a Internet OK (Protegido)", text_color="#00FF88")
                else:
                    raise e
        except Exception:
            # Fallback a google.com
            try:
                urllib.request.urlopen("https://google.com", timeout=5)
                self.lbl_net.configure(text="✅ Conexión a Internet OK (Google)", text_color="#00FF88")
            except:
                self.lbl_net.configure(text="❌ Sin conexión a Internet", text_color="#FF4444")
                all_ok = False

        # 4. Check for Updates
        def on_update_checked(new_version):
            if new_version:
                res = messagebox.askyesno("Actualización Disponible", f"¡Hay una nueva versión disponible (v{new_version})!\n\n¿Deseas descargarla e instalarla ahora?")
                if res:
                    self.controller.show_frame(UpdateScreen)
                    self.controller.frames[UpdateScreen].start_update(new_version)
                    return
            
            # Continue normally
            if all_ok:
                self.btn_continue.configure(state="normal")
                self.after(2000, lambda: self.controller.show_frame(LoginScreen))

        check_for_updates(lambda v: self.after(0, on_update_checked, v))


def get_cropped_image(img_path, target_width, target_height):
    img = Image.open(img_path)
    img_ratio = img.width / img.height
    target_ratio = target_width / target_height

    if target_ratio > img_ratio:
        # Target is wider than image (crop top and bottom)
        new_height = int(img.width / target_ratio)
        offset = (img.height - new_height) // 2
        img = img.crop((0, offset, img.width, offset + new_height))
    else:
        # Target is taller than image (crop left and right)
        new_width = int(img.height * target_ratio)
        offset = (img.width - new_width) // 2
        img = img.crop((offset, 0, offset + new_width, img.height))
    
    return img

class LoginScreen(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller

        # Main Layout: 1 Row, 1 Column (Full Screen Login)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Login Form Container ---
        self.form_container = ctk.CTkFrame(self, fg_color="#1e1e1e", corner_radius=0)
        self.form_container.grid(row=0, column=0, sticky="nsew")
        
        # Center the actual form inside the container
        self.form = ctk.CTkFrame(self.form_container, fg_color="transparent")
        self.form.place(relx=0.5, rely=0.5, anchor="center")

        # Logo
        try:
            logo_path = resource_path(os.path.join("dashboard", "static", "logo.png"))
            img = Image.open(logo_path)
            self.logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=(100, 100))
            lbl_logo = ctk.CTkLabel(self.form, image=self.logo_image, text="")
            lbl_logo.pack(anchor="center", pady=(0, 20))
        except Exception as e:
            print(f"Error loading logo: {e}")

        # Title
        lbl_title = ctk.CTkLabel(self.form, text="Welcome Back!", font=ctk.CTkFont(size=34, weight="bold"), text_color="#00C853")
        lbl_title.pack(anchor="center", pady=(0, 5))
        
        lbl_subtitle = ctk.CTkLabel(self.form, text="Sign in to your bot instance", font=ctk.CTkFont(size=14), text_color="gray")
        lbl_subtitle.pack(anchor="center", pady=(0, 20))

        # Stake Credentials
        lbl_email = ctk.CTkLabel(self.form, text="Email de Stake:", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00C853")
        lbl_email.pack(anchor="w", pady=(0, 5))
        self.ent_email = ctk.CTkEntry(self.form, placeholder_text="ejemplo@correo.com", width=320, height=45, corner_radius=8, border_width=1)
        self.ent_email.pack(anchor="w", pady=(0, 15))
        
        lbl_pass = ctk.CTkLabel(self.form, text="Contraseña:", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00C853")
        lbl_pass.pack(anchor="w", pady=(0, 5))
        self.ent_pass = ctk.CTkEntry(self.form, placeholder_text="••••••••", width=320, height=45, corner_radius=8, border_width=1, show="*")
        self.ent_pass.pack(anchor="w", pady=(0, 15))

        # Telegram Settings (Side by side)
        lbl_tg = ctk.CTkLabel(self.form, text="Telegram (Token / ID):", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray")
        lbl_tg.pack(anchor="w", pady=(0, 5))

        tg_frame = ctk.CTkFrame(self.form, fg_color="transparent")
        tg_frame.pack(anchor="w", pady=(0, 15))
        self.ent_token = ctk.CTkEntry(tg_frame, placeholder_text="Token", width=155, height=40, corner_radius=8, border_width=1)
        self.ent_token.pack(side="left", padx=(0, 10))
        self.ent_chat_id = ctk.CTkEntry(tg_frame, placeholder_text="Chat ID", width=155, height=40, corner_radius=8, border_width=1)
        self.ent_chat_id.pack(side="left")

        # Switches
        chk_frame = ctk.CTkFrame(self.form, fg_color="transparent")
        chk_frame.pack(anchor="w", pady=(0, 15), fill="x")
        
        self.chk_headless = ctk.CTkSwitch(chk_frame, text="Modo Oculto", width=120, progress_color="#00C853", button_color="#FFFFFF")
        self.chk_headless.select()
        self.chk_headless.pack(side="left")

        self.chk_diagnostics = ctk.CTkSwitch(chk_frame, text="Guardar Logs/Fotos", width=140, progress_color="#00C853", button_color="#FFFFFF")
        self.chk_diagnostics.deselect() # Apagado por defecto para ahorrar memoria
        self.chk_diagnostics.pack(side="left", padx=10)

        self.chk_remember = ctk.CTkSwitch(chk_frame, text="Recordar Datos", width=120, progress_color="#00C853", button_color="#FFFFFF")
        self.chk_remember.select()
        self.chk_remember.pack(side="right")

        # Settings
        self.lbl_threshold = ctk.CTkLabel(self.form, text="Alerta a partir de: 12 giros sin salir", font=ctk.CTkFont(size=12), text_color="gray")
        self.lbl_threshold.pack(anchor="center", pady=(0, 5))
        
        self.slider_thresh = ctk.CTkSlider(self.form, from_=5, to=25, number_of_steps=20, width=320, command=self.update_thresh_lbl, progress_color="#00C853", button_color="#00C853")
        self.slider_thresh.set(12)
        self.slider_thresh.pack(anchor="center", pady=(0, 20))

        # Button (Pill shaped)
        self.btn_start = ctk.CTkButton(self.form, text="INICIAR BOT", width=320, height=50, 
                                       font=ctk.CTkFont(size=15, weight="bold"),
                                       corner_radius=25,
                                       fg_color="#00C853", hover_color="#00E676", text_color="black",
                                       command=self.start_bot)
        self.btn_start.pack(anchor="center", pady=(0, 0))

    def on_show(self):
        # Load saved credentials if any
        creds = load_saved_credentials()
        if creds:
            self.ent_email.insert(0, creds.get("email", ""))
            self.ent_pass.insert(0, creds.get("password", ""))
            self.ent_token.insert(0, creds.get("tg_token", ""))
            self.ent_chat_id.insert(0, creds.get("tg_chat_id", ""))
            
            thresh = creds.get("threshold", 12)
            self.slider_thresh.set(thresh)
            self.update_thresh_lbl(thresh)
            
            if not creds.get("headless", True):
                self.chk_headless.deselect()
            
            if creds.get("diagnostics", False):
                self.chk_diagnostics.select()

    def update_thresh_lbl(self, val):
        self.lbl_threshold.configure(text=f"Alerta a partir de: {int(val)} giros sin salir")

    def start_bot(self):
        email = self.ent_email.get().strip()
        password = self.ent_pass.get().strip()
        tg_token = self.ent_token.get().strip()
        tg_chat_id = self.ent_chat_id.get().strip()
        threshold = int(self.slider_thresh.get())
        headless = bool(self.chk_headless.get())
        diagnostics = bool(self.chk_diagnostics.get())

        if not email or not password:
            log.error("Por favor ingresa correo y contraseña.")
            return

        # Handle saving
        if self.chk_remember.get():
            save_credentials(email, password, tg_token, tg_chat_id, threshold, headless, diagnostics)
        else:
            delete_saved_credentials()

        # Set runtime config overrides
        set_runtime_config(
            email=email, 
            password=password, 
            tg_token=tg_token, 
            tg_chat_id=tg_chat_id, 
            threshold=threshold, 
            headless=headless
        )
        
        # Aplicar toggle de diagnósticos al logger
        from bot_ruleta.debug_logger import set_diagnostics
        set_diagnostics(diagnostics)

        # Transition to LoadingScreen
        self.controller.show_frame(LoadingScreen)
        self.controller.frames[LoadingScreen].start_loading()


class LoadingScreen(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=0)
        
        self.lbl_info = ctk.CTkLabel(container, text="Inicializando sistema y conectando servidor...", font=ctk.CTkFont(size=18, weight="bold"), text_color="#00C853")
        self.lbl_info.pack(pady=(0, 20))
        
        self.progressbar = ctk.CTkProgressBar(container, width=300, progress_color="#00C853")
        self.progressbar.set(0)
        self.progressbar.pack()
        
        self.lbl_percent = ctk.CTkLabel(container, text="0%", font=ctk.CTkFont(size=14))
        self.lbl_percent.pack(pady=(10, 0))
        
        self.progress = 0
        self.timer_id = None

    def start_loading(self):
        self.progress = 0
        self.progressbar.set(0)
        self.lbl_percent.configure(text="0%")
        self.update_progress()
        
    def update_progress(self):
        self.progress += 0.02  # 50 steps * 200ms = 10000ms = 10 seconds
        if self.progress > 1.0:
            self.progress = 1.0
            
        self.progressbar.set(self.progress)
        self.lbl_percent.configure(text=f"{int(self.progress * 100)}%")
        
        if self.progress < 1.0:
            self.timer_id = self.after(200, self.update_progress)
        else:
            # Transition to Dashboard
            self.controller.show_frame(DashboardScreen)
            self.controller.frames[DashboardScreen].start_services()

class DashboardScreen(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Top Bar
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=10)

        self.lbl_status = ctk.CTkLabel(top_frame, text="● INICIANDO...", font=ctk.CTkFont(size=18, weight="bold"), text_color="#FFCC00")
        self.lbl_status.pack(side="left", padx=10)

        btn_stop = ctk.CTkButton(top_frame, text="⏹ DETENER", width=120, height=40, fg_color="#FF4444", hover_color="#CC0000",
                                 corner_radius=20, font=ctk.CTkFont(size=13, weight="bold"),
                                 command=self.stop_bot)
        btn_stop.pack(side="right", padx=10)

        # Cloudflare URL Card
        cf_frame = ctk.CTkFrame(self, corner_radius=15)
        cf_frame.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(cf_frame, text="Link Web:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10, pady=10)
        self.ent_cf_url = ctk.CTkEntry(cf_frame, width=300, state="normal")
        self.ent_cf_url.insert(0, "Generando link...")
        self.ent_cf_url.configure(state="readonly")
        self.ent_cf_url.pack(side="left", padx=10, pady=10)
        
        btn_copy = ctk.CTkButton(cf_frame, text="📋 Copiar", width=80, command=self.copy_url)
        btn_copy.pack(side="left", padx=5, pady=10)
        
        self.btn_open = ctk.CTkButton(cf_frame, text="🌐 Abrir", width=80, fg_color="#3B82F6", hover_color="#2563EB", command=self.open_url)
        # Se oculta inicialmente, se mostrará 10s después de obtener la URL

        # Toggle Logs Button
        self.btn_toggle_logs = ctk.CTkButton(self, text="▼ Ver Logs", width=120, fg_color="transparent", border_width=1, text_color="gray", command=self.toggle_logs)
        self.btn_toggle_logs.pack(pady=(10, 0))

        # Logs Console
        self.log_frame = ctk.CTkFrame(self)
        # Not packed initially
        
        ctk.CTkLabel(self.log_frame, text="Logs del Sistema", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        
        self.textbox = ctk.CTkTextbox(self.log_frame, wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        self.textbox.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Configure tags for colors
        self.textbox.tag_config("INFO", foreground="#FFFFFF")
        self.textbox.tag_config("DEBUG", foreground="#AAAAAA")
        self.textbox.tag_config("WARNING", foreground="#FFCC00")
        self.textbox.tag_config("ERROR", foreground="#FF4444")
        self.textbox.tag_config("CRITICAL", foreground="#FF0000", background="#FFCCCC")
        
        self.logs_visible = False

    def toggle_logs(self):
        if self.logs_visible:
            self.log_frame.pack_forget()
            self.btn_toggle_logs.configure(text="▼ Ver Logs")
            self.logs_visible = False
        else:
            self.log_frame.pack(fill="both", expand=True, padx=20, pady=10)
            self.btn_toggle_logs.configure(text="▲ Ocultar Logs")
            self.logs_visible = True

    def update_cf_url(self, url):
        self.ent_cf_url.configure(state="normal")
        self.ent_cf_url.delete(0, "end")
        self.ent_cf_url.insert(0, url)
        self.ent_cf_url.configure(state="readonly")
        
        # Ocultar el botón si estamos reconectando o generando
        self.btn_open.pack_forget()
        
        # Schedule the open button to appear after 10 seconds
        if url.startswith("http"):
            self.after(10000, self.show_open_button)

    def show_open_button(self):
        self.btn_open.pack(side="left", padx=5, pady=10)

    def copy_url(self):
        url = self.ent_cf_url.get()
        if url and "http" in url:
            self.clipboard_clear()
            self.clipboard_append(url)

    def open_url(self):
        url = self.ent_cf_url.get()
        if url and "http" in url:
            import webbrowser
            import os
            
            # Intentar forzar navegadores que no sean Chrome
            browsers_to_try = [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
            ]
            
            opened = False
            for browser_path in browsers_to_try:
                if os.path.exists(browser_path):
                    try:
                        webbrowser.register('alt_browser', None, webbrowser.BackgroundBrowser(browser_path))
                        webbrowser.get('alt_browser').open(url)
                        opened = True
                        break
                    except Exception:
                        pass
            
            if not opened:
                # Fallback al navegador por defecto
                webbrowser.open(url)

    def append_log(self, level, msg):
        self.textbox.insert("end", msg + "\n", level)
        self.textbox.see("end")
        
        # Update status based on log
        if "REINICIANDO BOT" in msg:
            self.lbl_status.configure(text="● REINICIANDO...", text_color="#FFCC00")
        elif "Comienza escaneo continuo" in msg:
            self.lbl_status.configure(text="● BOT ACTIVO", text_color="#00FF88")

    def start_services(self):
        # Start background services (flask, cloudflared)
        self.controller.start_background_services()
        
        # Start the actual bot
        self.controller.stop_event.clear()
        self.controller.bot_thread = threading.Thread(target=run_bot, args=(self.controller.stop_event,), daemon=True)
        self.controller.bot_thread.start()

    def stop_bot(self):
        self.lbl_status.configure(text="● DETENIENDO...", text_color="#FF4444")
        self.controller.stop_event.set()
        log.info("Señal de detención enviada. El bot se detendrá en breve.")

class UpdateScreen(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=0)
        
        self.lbl_title = ctk.CTkLabel(container, text="Descargando Actualización...", font=ctk.CTkFont(size=24, weight="bold"), text_color="#00C853")
        self.lbl_title.pack(pady=(0, 20))
        
        self.progressbar = ctk.CTkProgressBar(container, width=350, progress_color="#00C853")
        self.progressbar.set(0)
        self.progressbar.pack()
        
        self.lbl_percent = ctk.CTkLabel(container, text="0%", font=ctk.CTkFont(size=14))
        self.lbl_percent.pack(pady=(10, 0))
        
        self.lbl_status = ctk.CTkLabel(container, text="Conectando con GitHub...", font=ctk.CTkFont(size=12), text_color="gray")
        self.lbl_status.pack(pady=(5, 0))

    def start_update(self, new_version):
        self.lbl_title.configure(text=f"Descargando v{new_version}...")
        
        def update_progress(percent):
            self.progressbar.set(percent / 100.0)
            self.lbl_percent.configure(text=f"{percent}%")
            self.lbl_status.configure(text="Descargando ejecutable...")
            
        def update_complete(success, message):
            if success:
                self.lbl_status.configure(text="Reiniciando...", text_color="#FFCC00")
                self.lbl_title.configure(text="Bot Actualizado", text_color="#00FF88")
            else:
                self.lbl_status.configure(text=f"Error: {message}", text_color="#FF4444")
                self.lbl_title.configure(text="Actualización Fallida", text_color="#FF4444")

        # Run updater
        perform_update(new_version, 
                       lambda p: self.after(0, update_progress, p), 
                       lambda s, m: self.after(0, update_complete, s, m))


if __name__ == "__main__":
    import multiprocessing
    import sys
    multiprocessing.freeze_support()
    
    # Check if we should just run the dashboard process
    if len(sys.argv) > 1 and sys.argv[1] == "--run-dashboard":
        import os
        if getattr(sys, 'stdout', None) is None:
            sys.stdout = open(os.devnull, 'w')
        if getattr(sys, 'stderr', None) is None:
            sys.stderr = open(os.devnull, 'w')
            
        from bot_ruleta.dashboard.app import app as flask_app
        import logging
        log_werkzeug = logging.getLogger('werkzeug')
        log_werkzeug.setLevel(logging.ERROR)
        
        # Usar waitress (producción) para evitar deadlocks de Werkzeug en modo --windowed
        from waitress import serve
        serve(flask_app, host='0.0.0.0', port=5050, clear_untrusted_proxy_headers=False)
        sys.exit(0)

    app = RouletteApp()
    app.mainloop()
