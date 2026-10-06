from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from functools import wraps

from extensions import db, login_manager

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-change-me"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///clinic.db"

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "login"

from flask_wtf.csrf import CSRFProtect
CSRFProtect(app)

import models
from models import User
from appointments import appointments_bp
app.register_blueprint(appointments_bp)


def role_required(role):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role != role:
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)

        return decorated_function
    return decorator


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form["email"].strip().lower()
        full_name = request.form["full_name"].strip()
        password = request.form["password"]
        role = request.form["role"]

        if role not in ["patient", "doctor"]:
            flash("Invalid role selected.", "danger")
            return redirect(url_for("register"))

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("An account with this email already exists.", "danger")
            return redirect(url_for("register"))

        user = User(
            email=email,
            full_name=full_name,
            role=role
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "patient":
        return redirect(url_for("patient_dashboard"))

    if current_user.role == "doctor":
        return redirect(url_for("doctor_dashboard"))

    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))

    flash("Invalid user role.", "danger")
    return redirect(url_for("logout"))


@app.route("/patient/dashboard")
@role_required("patient")
def patient_dashboard():
    return render_template("patient_dashboard.html")


@app.route("/doctor/dashboard")
@role_required("doctor")
def doctor_dashboard():
    return render_template("doctor_dashboard.html")


@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    return render_template("admin_dashboard.html")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)