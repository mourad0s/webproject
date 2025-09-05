from flask import Flask, render_template, request
from flask_socketio import SocketIO
import paramiko
import config


app = Flask(__name__)
app.config.from_object(config)
socketio = SocketIO(app)

# Dictionnaire pour garder en mémoire la connexion SSH de chaque visiteur
ssh_sessions = {}

background_task_started = False

# --- ROUTES HTTP CLASSIQUES ---
@app.route('/')
def home():
    return render_template('index.html', active_page='home', title='Tableau de Bord')

@app.route('/grafana')
def grafana_page():
    return render_template('iframe_page.html', active_page='grafana', title='Grafana',
                           iframe_url="http://localhost:3000/d/rYdddlPWk/node-exporter-full?orgId=1&from=now-24h&to=now&timezone=browser&var-DS_PROMETHEUS=aex1uf2yfydj4c&var-job=serveurs_linux&var-nodename=dhcp&var-node=srv-dhcp.servers:9100&var-diskdevices=%5Ba-z%5D%2B%7Cnvme%5B0-9%5D%2Bn%5B0-9%5D%2B%7Cmmcblk%5B0-9%5D%2B&refresh=1m", service_name='Grafana')

@app.route('/stork')
def stork_page():
    return render_template('iframe_page.html', active_page='stork', title='Stork',
                           iframe_url="http://remplacer-par-url-stork", service_name='Stork')

@app.route('/terminal')
def terminal_page():
    servers = app.config["SERVERS"]
    return render_template('terminal.html', active_page='terminal', title='Terminal SSH', servers=servers)

# --- GESTION DES ÉVÉNEMENTS WEBSOCKET POUR LE TERMINAL ---

@socketio.on('connect', namespace='/terminal')
def terminal_connect():
    # ON LANCE LA TÂCHE DE FOND ICI
    global background_task_started
    if not background_task_started:
        socketio.start_background_task(target=read_ssh_output)
        background_task_started = True
    print(f"Client connecté : {request.sid}")


@socketio.on('start_ssh', namespace='/terminal')
def start_ssh(data):
    """Reçoit l'ID du serveur choisi et utilise config.py pour se connecter."""
    sid = request.sid
    try:
        # 1. On récupère l'ID envoyé par le navigateur
        server_id = data['server_id']

        # 2. On cherche le dictionnaire correspondant à cet ID dans notre liste SERVERS
        server_config = next((s for s in app.config['SERVERS'] if s['id'] == server_id), None)

        if not server_config:
            raise Exception("Serveur non trouvé dans la configuration.")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # 3. On utilise les informations du dictionnaire trouvé pour se connecter
        client.connect(
            hostname=server_config['host'],
            port=server_config.get('port', 22),
            username=server_config['user'],
            password=server_config['password']
        )

        channel = client.invoke_shell(term='xterm')
        ssh_sessions[sid] = (client, channel)

        socketio.emit('ssh_output', f"Connexion à {server_config['name']} réussie !\r\n", namespace='/terminal', to=sid)
        print(f"Connexion SSH à {server_config['name']} établie pour {sid}")

    except Exception as e:
        error_message = f"Erreur de connexion : {type(e).__name__} - {e}\r\n"
        socketio.emit('ssh_output', error_message, namespace='/terminal', to=sid)
        print(f"Erreur SSH DÉTAILLÉE pour {sid}: {type(e).__name__} - {e}")

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
    print(">>> TÂCHE DE FOND DÉMARRÉE <<<")
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
    socketio.run(app, debug=True)