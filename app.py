
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect

from extensions import db, login_manager

from datetime import datetime
from flask_login import login_required, current_user
from models import DoctorAvailability, Doctor

app = Flask(__name__)

app.config["SECRET_KEY"] = "dev-secret-change-me"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///clinic.db"

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "login"

CSRFProtect(app)

import models
from models import User, Patient, Doctor, Appointment, Queue

from appointments import appointments_bp

app.register_blueprint(appointments_bp)


def role_required(role):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role != role:
                flash(
                    "You do not have permission to access this page.",
                    "danger",
                )
                return redirect(url_for("dashboard"))

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def get_today_range():
    """Return today's local date range for appointment queries."""

    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    return today, datetime.combine(today, datetime.min.time()), datetime.combine(
        tomorrow,
        datetime.min.time(),
    )


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

        if role not in ["patient", "doctor", "admin"]:
            flash("Invalid role selected.", "danger")
            return redirect(url_for("register"))

        if not full_name:
            flash("Full name is required.", "danger")
            return redirect(url_for("register"))

        if not email:
            flash("Email is required.", "danger")
            return redirect(url_for("register"))

        if not password:
            flash("Password is required.", "danger")
            return redirect(url_for("register"))

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("An account with this email already exists.", "danger")
            return redirect(url_for("register"))

        user = User(
            email=email,
            full_name=full_name,
            role=role,
        )

        user.set_password(password)

        db.session.add(user)
        db.session.flush()

        if role == "patient":
            patient = Patient(user_id=user.id)
            db.session.add(patient)

        elif role == "doctor":
            doctor = Doctor(user_id=user.id)
            db.session.add(doctor)

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

            flash(
                f"Welcome back, {user.full_name}!",
                "success",
            )

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

    logout_user()

    return redirect(url_for("index"))


@app.route("/patient/dashboard")
@role_required("patient")
def patient_dashboard():
    if not current_user.patient:
        flash("Patient profile not found.", "danger")
        return redirect(url_for("logout"))

    today, start_of_day, start_of_tomorrow = get_today_range()

    patient_id = current_user.patient.id

    appointments_today = (
        Appointment.query
        .filter(
            Appointment.patient_id == patient_id,
            Appointment.start_time >= start_of_day,
            Appointment.start_time < start_of_tomorrow,
        )
        .order_by(Appointment.start_time.asc())
        .all()
    )

    queue_entry = (
        Queue.query
        .join(Appointment)
        .filter(
            Appointment.patient_id == patient_id,
            Queue.queue_date == today,
        )
        .first()
    )

    patients_ahead = 0

    if queue_entry:
        patients_ahead = (
            Queue.query
            .filter(
                Queue.queue_date == today,
                Queue.queue_number < queue_entry.queue_number,
                Queue.status.in_(["waiting", "in-progress"]),
            )
            .count()
        )

    return render_template(
        "patient_dashboard.html",
        appointments_today=appointments_today,
        queue_entry=queue_entry,
        patients_ahead=patients_ahead,
    )


@app.route("/doctor/dashboard")
@role_required("doctor")
def doctor_dashboard():
    if not current_user.doctor:
        flash("Doctor profile not found.", "danger")
        return redirect(url_for("logout"))

    today, start_of_day, start_of_tomorrow = get_today_range()

    doctor_id = current_user.doctor.id

    appointments_today = (
        Appointment.query
        .filter(
            Appointment.doctor_id == doctor_id,
            Appointment.start_time >= start_of_day,
            Appointment.start_time < start_of_tomorrow,
        )
        .order_by(Appointment.start_time.asc())
        .all()
    )

    queue_entries = (
        Queue.query
        .join(Appointment)
        .filter(
            Appointment.doctor_id == doctor_id,
            Queue.queue_date == today,
        )
        .order_by(Queue.queue_number.asc())
        .all()
    )

    return render_template(
        "doctor_dashboard.html",
        appointments_today=appointments_today,
        queue_entries=queue_entries,
    )


@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    today, start_of_day, start_of_tomorrow = get_today_range()

    appointments_today = (
        Appointment.query
        .filter(
            Appointment.start_time >= start_of_day,
            Appointment.start_time < start_of_tomorrow,
        )
        .order_by(Appointment.start_time.asc())
        .all()
    )

    # Patients who have appointments today but have not checked in.
    pending_checkin = (
        Appointment.query
        .filter(
            Appointment.start_time >= start_of_day,
            Appointment.start_time < start_of_tomorrow,
            Appointment.status.in_(["scheduled", "booked"]),
        )
        .order_by(Appointment.start_time.asc())
        .all()
    )

    # The complete clinic-wide queue for today.
    queue_entries = (
        Queue.query
        .filter_by(queue_date=today)
        .order_by(Queue.queue_number.asc())
        .all()
    )

    waiting_count = sum(
        1 for entry in queue_entries if entry.status == "waiting"
    )

    in_progress_count = sum(
        1 for entry in queue_entries if entry.status == "in-progress"
    )

    completed_count = sum(
        1 for entry in queue_entries if entry.status == "completed"
    )

    return render_template(
        "admin_dashboard.html",
        appointments_today=appointments_today,
        pending_checkin=pending_checkin,
        queue_entries=queue_entries,
        waiting_count=waiting_count,
        in_progress_count=in_progress_count,
        completed_count=completed_count,
    )


# View all availability slots for the logged-in doctor
@app.route("/doctor/availability")
@login_required
def doctor_availability():
    if current_user.role != "doctor":
        flash("Only doctors can manage availability.", "danger")
        return redirect(url_for("dashboard"))

    doctor = current_user.doctor

    if doctor is None:
        flash("Doctor profile not found.", "danger")
        return redirect(url_for("dashboard"))

    slots = (
        DoctorAvailability.query
        .filter_by(doctor_id=doctor.id)
        .order_by(DoctorAvailability.start_time)
        .all()
    )

    return render_template("doctor_availability.html", slots=slots)


# Add a new availability slot
@app.route("/doctor/availability/add", methods=["POST"])
@login_required
def add_availability():
    if current_user.role != "doctor" or current_user.doctor is None:
        flash("You are not authorized to do this.", "danger")
        return redirect(url_for("dashboard"))

    try:
        start_time = datetime.fromisoformat(request.form["start_time"])
        end_time = datetime.fromisoformat(request.form["end_time"])
    except (ValueError, KeyError):
        flash("Please enter valid start and end times.", "danger")
        return redirect(url_for("doctor_availability"))

    if start_time >= end_time:
        flash("The end time must be after the start time.", "danger")
        return redirect(url_for("doctor_availability"))

    doctor_id = current_user.doctor.id

    # Prevent overlapping availability slots for the same doctor
    overlap = DoctorAvailability.query.filter(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.start_time < end_time,
        DoctorAvailability.end_time > start_time
    ).first()

    if overlap:
        flash("This slot overlaps with an existing availability slot.", "danger")
        return redirect(url_for("doctor_availability"))

    slot = DoctorAvailability(
        doctor_id=doctor_id,
        start_time=start_time,
        end_time=end_time
    )

    db.session.add(slot)
    db.session.commit()

    flash("Availability slot added successfully.", "success")
    return redirect(url_for("doctor_availability"))


# Edit an existing availability slot
@app.route("/doctor/availability/edit/<int:slot_id>", methods=["POST"])
@login_required
def edit_availability(slot_id):
    if current_user.role != "doctor" or current_user.doctor is None:
        flash("You are not authorized to do this.", "danger")
        return redirect(url_for("dashboard"))

    slot = db.session.get(DoctorAvailability, slot_id)

    # A doctor can only edit their own slots
    if slot is None or slot.doctor_id != current_user.doctor.id:
        flash("Availability slot not found.", "danger")
        return redirect(url_for("doctor_availability"))

    try:
        start_time = datetime.fromisoformat(request.form["start_time"])
        end_time = datetime.fromisoformat(request.form["end_time"])
    except (ValueError, KeyError):
        flash("Please enter valid start and end times.", "danger")
        return redirect(url_for("doctor_availability"))

    if start_time >= end_time:
        flash("The end time must be after the start time.", "danger")
        return redirect(url_for("doctor_availability"))

    overlap = DoctorAvailability.query.filter(
        DoctorAvailability.doctor_id == current_user.doctor.id,
        DoctorAvailability.id != slot.id,
        DoctorAvailability.start_time < end_time,
        DoctorAvailability.end_time > start_time
    ).first()

    if overlap:
        flash("This slot overlaps with another availability slot.", "danger")
        return redirect(url_for("doctor_availability"))

    slot.start_time = start_time
    slot.end_time = end_time
    db.session.commit()

    flash("Availability updated successfully.", "success")
    return redirect(url_for("doctor_availability"))


# Delete an availability slot
@app.route("/doctor/availability/delete/<int:slot_id>", methods=["POST"])
@login_required
def delete_availability(slot_id):
    if current_user.role != "doctor" or current_user.doctor is None:
        flash("You are not authorized to do this.", "danger")
        return redirect(url_for("dashboard"))

    slot = db.session.get(DoctorAvailability, slot_id)

    if slot is None or slot.doctor_id != current_user.doctor.id:
        flash("Availability slot not found.", "danger")
        return redirect(url_for("doctor_availability"))

    db.session.delete(slot)
    db.session.commit()

    flash("Availability slot deleted.", "success")
    return redirect(url_for("doctor_availability"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)
