from flask import Flask, render_template, request
from flask_socketio import SocketIO
from models import db, Server, NavigationLink
import paramiko



app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
db.init_app(app)

socketio = SocketIO(app)

@app.context_processor
def inject_navigation_links():
    links = NavigationLink.query.order_by(NavigationLink.order).all()
    return dict(navigation_links=links)

# Dictionnaire pour garder en mémoire la connexion SSH de chaque visiteur
ssh_sessions = {}

background_task_started = False

# --- ROUTES HTTP CLASSIQUES ---
@app.route('/')
def home():
    return render_template('index.html', active_page='home', title='Tableau de Bord')

@app.route('/grafana')
def grafana():
    return render_template('iframe_page.html', active_page='grafana', title='Grafana',
                           iframe_url="http://localhost:3000/d/rYdddlPWk/node-exporter-full?orgId=1&from=now-24h&to=now&timezone=browser&var-DS_PROMETHEUS=aex1uf2yfydj4c&var-job=serveurs_linux&var-nodename=dhcp&var-node=srv-dhcp.servers:9100&var-diskdevices=%5Ba-z%5D%2B%7Cnvme%5B0-9%5D%2Bn%5B0-9%5D%2B%7Cmmcblk%5B0-9%5D%2B&refresh=1m", service_name='Grafana')

@app.route('/stork')
def stork():
    return render_template('iframe_page.html', active_page='stork', title='Stork',
                           iframe_url="http://stork.servers:8080", service_name='Stork')

@app.route('/terminal')
def terminal():
    servers = Server.query.all()
    return render_template('terminal.html', active_page='terminal', title='Terminal SSH', servers=servers)

@app.route('/admin')
def admin():
    all_servers = Server.query.order_by(Server.name).all()
    all_links = NavigationLink.query.order_by(NavigationLink.order).all()
    return render_template('admin.html',
                           active_page='admin',
                           title='Administration',
                           servers=all_servers,
                           links=all_links)



@app.route('/admin/add_link', methods=['POST'])
def add_link():
    new_link = NavigationLink(
        name=request.form.get('name'),
        url_endpoint=request.form.get('url_endpoint'),
        icon_class=request.form.get('icon_class'),
        order=int(request.form.get('order')),
        description=request.form.get('description')
    )
    db.session.add(new_link)
    db.session.commit()
    flash(f"Le lien '{new_link.name}' a été ajouté.")
    return redirect(url_for('admin'))


@app.route('/admin/add_server', methods=['POST'])
def add_server():
    new_server = Server(
        server_id=request.form.get('server_id'),
        name=request.form.get('name'),
        host=request.form.get('host'),
        user=request.form.get('user'),
        password=request.form.get('password')
    )
    db.session.add(new_server)
    db.session.commit()
    flash(f"Le serveur '{new_server.name}' a été ajouté.")
    return redirect(url_for('admin'))


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
    """Reçoit l'ID du serveur, le cherche dans la BDD et se connecte."""
    sid = request.sid
    try:
        server_id = data['server_id']

        # ÉTAPE 1 : On cherche le serveur DANS LA BASE DE DONNÉES
        server = Server.query.filter_by(server_id=server_id).first()

        if not server:
            raise Exception("Serveur non trouvé dans la base de données.")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # ÉTAPE 2 : On utilise les infos de l'objet "server" trouvé dans la BDD
        client.connect(
            hostname=server.host,
            port=server.port,
            username=server.user,
            password=server.password
        )

        channel = client.invoke_shell(term='xterm')
        ssh_sessions[sid] = (client, channel)

        socketio.emit('ssh_output', f"Connexion à {server.name} réussie !\r\n", namespace='/terminal', to=sid)
        print(f"Connexion SSH à {server.name} établie pour {sid}")

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