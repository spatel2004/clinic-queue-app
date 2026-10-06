from flask import Flask, render_template
from extensions import db, login_manager

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-change-me"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///clinic.db"

db.init_app(app)
login_manager.init_app(app)

import models
from appointments import appointments_bp
app.register_blueprint(appointments_bp)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)


