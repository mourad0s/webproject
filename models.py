from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

class Server(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    host = db.Column(db.String(120), nullable=False)
    port = db.Column(db.Integer, default=22)
    user = db.Column(db.String(80), nullable=False)
    password = db.Column(db.String(120), nullable=False)

    def __repr__(self):
        return f'<Server {self.name}>'



class NavigationLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    url_endpoint = db.Column(db.String(50), nullable=False)
    icon_class = db.Column(db.String(50), nullable=False)
    order = db.Column(db.Integer, default=100)
    description = db.Column(db.String(200), nullable=True)

    def __repr__(self):
        return f'<NavigationLink {self.name}>'