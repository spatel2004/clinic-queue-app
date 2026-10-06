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

def get_appointment_or_404(appt_id):
    """Fetch an appointment, and block patients from touching anyone else's."""
    appt = db.get_or_404(Appointment, appt_id)
    if current_user.role == "patient" and appt.patient_id != current_user.patient.id:
        abort(403)
    if current_user.role == "doctor" and appt.doctor_id != current_user.doctor.id:
        abort(403)
    return appt


@appointments_bp.route("/<int:appt_id>/cancel", methods=["POST"])
@login_required
def cancel_appointment(appt_id):
    appt = get_appointment_or_404(appt_id)

    if appt.status != "scheduled":
        flash("Only scheduled appointments can be cancelled.", "warning")
    else:
        appt.status = "cancelled"
        db.session.commit()
        flash("Appointment cancelled.", "success")

    return redirect(url_for("appointments.list_appointments"))

@appointments_bp.route("/<int:appt_id>/edit", methods=["GET", "POST"])
@login_required

def edit_appointment(appt_id):
    if current_user.role == "doctor":
        abort(403)  # doctors can't reschedule patients' appointments

    appt = get_appointment_or_404(appt_id)

    if appt.status != "scheduled":
        flash("Only scheduled appointments can be edited.", "warning")
        return redirect(url_for("appointments.list_appointments"))

    form = AppointmentForm(obj=appt)  # pre-fills the form with the current values
    form.doctor_id.choices = [
        (d.id, f"{d.user.full_name} ({d.speciality})") for d in Doctor.query.all()
    ]

    if form.validate_on_submit():
        start = form.start_time.data
        end = start + timedelta(minutes=SLOT_MINUTES)

        if start <= datetime.now():
            flash("Please choose a time in the future.", "danger")
        elif has_conflict(form.doctor_id.data, start, end, exclude_id=appt.id):
            flash("That doctor is already booked at that time.", "danger")
        else:
            appt.doctor_id = form.doctor_id.data
            appt.start_time = start
            appt.end_time = end
            appt.reason = form.reason.data
            db.session.commit()
            flash("Appointment updated.", "success")
            return redirect(url_for("appointments.list_appointments"))

    return render_template("appointments/form.html", form=form, title="Edit appointment")