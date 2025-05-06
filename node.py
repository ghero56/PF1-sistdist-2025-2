from flask import Flask, request, jsonify, render_template_string, redirect
import threading
import time
import requests
import json
import os
from datetime import datetime
from utils import get_ip, generate_name

PORT = 8080
app = Flask(__name__)
NODE_NAME = generate_name()
NODE_IP = get_ip()
NODE_LIST = {}  # {ip: name}
LOG_FILE = f"log_{NODE_NAME}.txt"

def log_message(data):
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(data) + "\n")

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Red de Nodos</title>
</head>
<body>
    <h1>Enviar Mensaje</h1>
    <form method="POST" action="/send">
        <label>Destino:</label>
        <select name="target_ip">
            {% for ip, name in nodes.items() %}
                <option value="{{ ip }}">{{ name }} ({{ ip }})</option>
            {% endfor %}
        </select><br><br>
        <label>Mensaje:</label>
        <input type="text" name="message" required><br><br>
        <button type="submit">Enviar</button>
    </form>

    <form method="POST" action="/scan" style="margin-top: 20px;">
        <button type="submit">🔍 Escanear Nodos</button>
    </form>

    <h2>Log de Mensajes</h2>
    <pre>{{ log }}</pre>
</body>
</html>
"""

# Ruta principal
@app.route("/")
def index():
    # Leer log.txt
    try:
        with open("log.txt", "r") as f:
            log_content = f.read()
    except FileNotFoundError:
        log_content = "Sin mensajes todavía."

    return render_template_string(HTML_PAGE, nodes=NODE_LIST, log=log_content)

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"name": NODE_NAME})

@app.route("/message", methods=["POST"])
def receive_message():
    data = request.json
    print(f"\n[{data['timestamp']}] {data['sender']}: {data['message']}")
    log_message(data)

    # Solo responder con Ack si el mensaje NO es un Ack
    if not data['message'].startswith("Ack"):
        threading.Thread(target=send_ack, args=(request.remote_addr, data['sender'])).start()
    # O si es un tipo ack
    if not data['type'] == "ack":
        threading.Thread(target=send_ack, args=(request.remote_addr, data['sender'])).start()
    
    # print(f"[✔] Mensaje recibido de {data['sender']} ({NODE_LIST.get(data['sender'])}): {data['message']}")

    return jsonify({"status": "received"})

@app.route("/send", methods=["POST"])
def send_from_web():
    ip = request.form["target_ip"]
    message = request.form["message"]
    timestamp = datetime.now().isoformat()

    try:
        requests.post(f"http://{ip}:{PORT}/message", json={
            "timestamp": timestamp,
            "sender": NODE_NAME,
            "message": message,
            "type": "user"
        }, timeout=2)
        return f"<p>Mensaje enviado a {NODE_LIST[ip]} ({ip})</p><a href='/'>Volver</a>"
    except requests.exceptions.RequestException:
        return f"<p>Error al enviar a {ip}</p><a href='/'>Volver</a>"

@app.route("/scan", methods=["POST"])
def scan_from_web():
    scan_network()
    return redirect("/")

def send_ack(ip, sender):
    try:
        requests.post(f"http://{ip}:{PORT}/message", json={
            "timestamp": datetime.now().isoformat(),
            "sender": NODE_NAME,
            "message": f"Ack: recibido tu mensaje ({sender})",
            "type": "ack"
        }, timeout=2)
    except:
        pass

def scan_network():
    print("[*] Escaneando red en busca de nodos...")
    base_ip = '.'.join(NODE_IP.split('.')[:-1]) + '.'
    for i in range(1, 255):
        ip = base_ip + str(i)
        if ip == NODE_IP:
            continue
        try:
            res = requests.get(f"http://{ip}:{PORT}/ping", timeout=0.5)
            name = res.json()['name']
            NODE_LIST[ip] = name
            print(f"[+] Nodo encontrado: {name} en {ip}")
        except:
            pass
    print("Escaneo completo:", NODE_LIST)

def sender_thread():
    while True:
        if NODE_LIST:
            print("\n--- Nodos disponibles ---")
            for i, (ip, name) in enumerate(NODE_LIST.items()):
                print(f"{i}: {name} ({ip})")
            try:
                idx = int(input("Elige un nodo para mandar mensaje (índice): "))
                ip, name = list(NODE_LIST.items())[idx]
                msg = input("Escribe tu mensaje: ")
                data = {
                    "timestamp": datetime.now().isoformat(),
                    "sender": NODE_NAME,
                    "message": msg,
                    "type": "message" # Tipo de mensaje
                }
                res = requests.post(f"http://{ip}:{PORT}/message", json=data, timeout=2)
                log_message({"sent_to": name, **data})
                print("[✔] Mensaje enviado.")
            except Exception as e:
                print(f"[!] Error al enviar: {e}")
        else:
            print("No hay nodos conectados.")
        time.sleep(2)

def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    print(f"Nodo iniciado: {NODE_NAME} ({NODE_IP})")
    print(f"Log: {LOG_FILE}")

    threading.Thread(target=run_flask, daemon=True).start()
    time.sleep(1)

    scan_network()
    threading.Thread(target=sender_thread).start()
