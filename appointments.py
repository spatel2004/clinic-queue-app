from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from extensions import db
from models import Appointment, Doctor
from appointment_forms import AppointmentForm

appointments_bp = Blueprint("appointments", __name__, url_prefix="/appointments")

SLOT_MINUTES = 30


def has_conflict(doctor_id, start, end, exclude_id=None):
    """True if this doctor already has a non-cancelled appointment overlapping start-end."""
    q = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status != "cancelled",
        Appointment.start_time < end,
        Appointment.end_time > start,
    )
    if exclude_id is not None:
        q = q.filter(Appointment.id != exclude_id)
    return q.first() is not None


@appointments_bp.route("/")
@login_required
def list_appointments():
    query = Appointment.query

    if current_user.role == "patient":
        query = query.filter_by(patient_id=current_user.patient.id)
    elif current_user.role == "doctor":
        query = query.filter_by(doctor_id=current_user.doctor.id)
    # admin/receptionist: sees all appointments

    appointments = query.order_by(Appointment.start_time.desc()).all()
    return render_template("appointments/list.html", appointments=appointments)


@appointments_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_appointment():
    if current_user.role != "patient":
        abort(403)  # admin booking on behalf of patients comes later

    form = AppointmentForm()
    form.doctor_id.choices = [
        (d.id, f"{d.user.full_name} ({d.speciality})") for d in Doctor.query.all()
    ]

    if form.validate_on_submit():
        start = form.start_time.data
        end = start + timedelta(minutes=SLOT_MINUTES)

        if start <= datetime.now():
            flash("Please choose a time in the future.", "danger")
        elif has_conflict(form.doctor_id.data, start, end):
            flash("That doctor is already booked at that time.", "danger")
        else:
            appt = Appointment(
                patient_id=current_user.patient.id,
                doctor_id=form.doctor_id.data,
                start_time=start,
                end_time=end,
                reason=form.reason.data,
            )
            db.session.add(appt)
            db.session.commit()
            flash("Appointment booked.", "success")
            return redirect(url_for("appointments.list_appointments"))

    return render_template("appointments/form.html", form=form, title="Book an appointment")