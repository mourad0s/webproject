from flask import Flask, render_template, request
from flask_socketio import SocketIO
import paramiko
import config


app = Flask(__name__)
app.config.from_object(config)
socketio = SocketIO(app)

# Dictionnaire pour garder en mémoire la connexion SSH de chaque visiteur
ssh_sessions = {}

# --- ROUTES HTTP CLASSIQUES ---
@app.route('/')
def home():
    return render_template('index.html', active_page='home', title='Tableau de Bord')

@app.route('/grafana')
def grafana_page():
    return render_template('iframe_page.html', active_page='grafana', title='Grafana',
                           iframe_url="http://127.0.0.1:9100", service_name='Grafana')

@app.route('/stork')
def stork_page():
    return render_template('iframe_page.html', active_page='stork', title='Stork',
                           iframe_url="http://remplacer-par-url-stork", service_name='Stork')

@app.route('/terminal')
def terminal_page():
    servers = app.config["SERVERS"]
    return render_template('terminal.html', active_page='terminal', title='Terminal SSH', servers=servers)

# --- GESTION DES ÉVÉNEMENTS WEBSOCKET POUR LE TERMINAL ---

@socketio.on('start_ssh', namespace='/terminal')
def start_ssh(data):
    """Reçoit la demande de connexion SSH du formulaire."""
    sid = request.sid  # ID unique de la session du navigateur
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=data['host'], username=data['user'], password=data['pass'], timeout=10)

        channel = client.invoke_shell()
        ssh_sessions[sid] = (client, channel)

        socketio.emit('ssh_output', 'Connexion réussie !\r\n', namespace='/terminal', to=sid)
        print(f"Connexion SSH établie pour {sid}")

    except Exception as e:
        socketio.emit('ssh_output', f'Erreur de connexion : {e}\r\n', namespace='/terminal', to=sid)
        print(f"Erreur SSH pour {sid}: {e}")

@socketio.on('ssh_input', namespace='/terminal')
def ssh_input(data):
    """Reçoit ce que l'utilisateur tape et l'envoie au serveur SSH."""
    sid = request.sid
    if sid in ssh_sessions:
        _client, channel = ssh_sessions[sid]
        channel.send(data['command'])

@socketio.on('disconnect', namespace='/terminal')
def terminal_disconnect():
    """Le navigateur a fermé la page, on nettoie la connexion SSH."""
    sid = request.sid
    if sid in ssh_sessions:
        client, _channel = ssh_sessions.pop(sid)
        client.close()
        print(f"Client {sid} déconnecté, connexion SSH fermée.")

# --- TÂCHE DE FOND ---
def read_ssh_output():
    """Tourne en permanence pour lire la sortie du terminal SSH et l'envoyer au navigateur."""
    while True:
        for sid, (_client, channel) in list(ssh_sessions.items()):
            try:
                if channel.recv_ready():
                    output = channel.recv(1024).decode('utf-8', 'ignore')
                    socketio.emit('ssh_output', output, namespace='/terminal', to=sid)
            except Exception:
                # Si la connexion est rompue, on la retire du dictionnaire
                ssh_sessions.pop(sid, None)
        socketio.sleep(0.01) # Petite pause pour ne pas faire tourner le CPU à 100%

# --- LANCEMENT DE L'APPLICATION ---
if __name__ == '__main__':
    socketio.start_background_task(target=read_ssh_output)
    # On utilise socketio.run() au lieu de app.run() pour activer les WebSockets
    socketio.run(app, debug=True)