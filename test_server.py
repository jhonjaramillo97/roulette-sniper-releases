import http.server
import socketserver

PORT = 5050

class TestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = f"""
        <html>
            <head>
                <title>Prueba Cloudflare</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 80px; background-color: #f3f4f6; color: #333; }}
                    .card {{ background: white; padding: 40px; border-radius: 10px; display: inline-block; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                    h1 {{ color: #f6821f; }} /* Color Cloudflare */
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>✅ ¡Conexión Exitosa!</h1>
                    <h2>El túnel de Cloudflare funciona perfecto.</h2>
                    <p>Estás viendo el puerto <strong>{PORT}</strong> a través de internet.</p>
                    <p>Ya puedes hacer exactamente lo mismo en la PC de tu bot.</p>
                </div>
            </body>
        </html>
        """
        self.wfile.write(bytes(html, "utf8"))

try:
    with socketserver.TCPServer(("", PORT), TestHandler) as my_server:
        print(f"==================================================")
        print(f" Servidor de PRUEBA iniciado en el puerto {PORT}")
        print(f"==================================================")
        print("1. Deja esta ventana abierta.")
        print("2. Abre OTRA consola CMD y ejecuta el comando:")
        print(f"   cloudflared tunnel --url http://localhost:{PORT}")
        print("==================================================")
        my_server.serve_forever()
except OSError as e:
    print(f"Error: El puerto {PORT} ya está en uso. Asegúrate de no tener otro programa usándolo.")
