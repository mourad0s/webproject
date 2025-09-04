from flask import Flask, render_template

app = Flask(__name__)


@app.route('/')
def home():  # put application's code here
    return render_template('index.html', active_page="home", title='Accueil')

@app.route('/a-propos')
def about():
    return render_template('a-propos.html', active_page="about", title='A propos')

if __name__ == '__main__':
    app.run(debug=True)