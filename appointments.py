from datetime import datetime, timedelta

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    abort,
)

from flask_login import login_required, current_user
from sqlalchemy import or_

from extensions import db
from models import Appointment, Doctor, Patient
from appointment_forms import AppointmentForm


appointments_bp = Blueprint(
    "appointments",
    __name__,
    url_prefix="/appointments",
)

SLOT_MINUTES = 30

# Existing database compatibility:
# "scheduled" is displayed as "Booked".
STATUS_LABELS = {
    "scheduled": "Booked",
    "booked": "Booked",
    "checked-in": "Checked-in",
    "in-progress": "In progress",
    "complete": "Complete",
    "cancelled": "Cancelled",
}

# Only these forward transitions are permitted.
STATUS_TRANSITIONS = {
    "scheduled": "checked-in",
    "booked": "checked-in",
    "checked-in": "in-progress",
    "in-progress": "complete",
}


def has_conflict(
    doctor_id,
    patient_id,
    start,
    end,
    exclude_id=None,
):
    """Prevent overlapping appointments for a doctor or patient."""

    query = Appointment.query.filter(
        Appointment.status != "cancelled",
        Appointment.start_time < end,
        Appointment.end_time > start,
        or_(
            Appointment.doctor_id == doctor_id,
            Appointment.patient_id == patient_id,
        ),
    )

    if exclude_id is not None:
        query = query.filter(Appointment.id != exclude_id)

    return query.first() is not None


@appointments_bp.route("/")
@login_required
def list_appointments():
    """Patients see their appointments, doctors see theirs, admins see all."""

    query = Appointment.query

    if current_user.role == "patient":
        if not current_user.patient:
            flash("Patient profile not found.", "danger")
            return redirect(url_for("dashboard"))

        query = query.filter_by(
            patient_id=current_user.patient.id
        )

    elif current_user.role == "doctor":
        if not current_user.doctor:
            flash("Doctor profile not found.", "danger")
            return redirect(url_for("dashboard"))

        query = query.filter_by(
            doctor_id=current_user.doctor.id
        )

    elif current_user.role == "admin":
        pass

    else:
        abort(403)

    appointments = query.order_by(
        Appointment.start_time.desc()
    ).all()

    return render_template(
        "appointments/list.html",
        appointments=appointments,
        status_labels=STATUS_LABELS,
        status_transitions=STATUS_TRANSITIONS,
    )


@appointments_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_appointment():
    """Patients and admins/receptionists can create appointments."""

    if current_user.role not in ["patient", "admin"]:
        abort(403)

    form = AppointmentForm()

    form.doctor_id.choices = [
        (
            doctor.id,
            f"{doctor.user.full_name} "
            f"({doctor.speciality or 'General'})",
        )
        for doctor in Doctor.query.order_by(Doctor.id).all()
    ]

    if current_user.role == "admin":
        form.patient_id.choices = [
            (patient.id, patient.user.full_name)
            for patient in Patient.query.order_by(Patient.id).all()
        ]
    else:
        if not current_user.patient:
            flash("Patient profile not found.", "danger")
            return redirect(url_for("dashboard"))

        form.patient_id.choices = [
            (
                current_user.patient.id,
                current_user.full_name,
            )
        ]

    if form.validate_on_submit():
        start = form.start_time.data
        end = start + timedelta(minutes=SLOT_MINUTES)

        if current_user.role == "patient":
            patient_id = current_user.patient.id
        else:
            patient_id = form.patient_id.data

        if start <= datetime.now():
            flash("Please choose a time in the future.", "danger")

        elif has_conflict(
            form.doctor_id.data,
            patient_id,
            start,
            end,
        ):
            flash(
                "The selected doctor or patient already has an "
                "appointment at that time.",
                "danger",
            )

        else:
            appointment = Appointment(
                patient_id=patient_id,
                doctor_id=form.doctor_id.data,
                start_time=start,
                end_time=end,
                reason=form.reason.data,
                status="scheduled",
            )

            db.session.add(appointment)
            db.session.commit()

            flash("Appointment booked successfully.", "success")
            return redirect(url_for("appointments.list_appointments"))

    return render_template(
        "appointments/form.html",
        form=form,
        title="Book an Appointment",
    )


def get_appointment_or_404(appt_id):
    """Fetch an appointment and enforce role-based access."""

    appointment = db.get_or_404(Appointment, appt_id)

    if current_user.role == "patient":
        if (
            not current_user.patient
            or appointment.patient_id != current_user.patient.id
        ):
            abort(403)

    elif current_user.role == "doctor":
        if (
            not current_user.doctor
            or appointment.doctor_id != current_user.doctor.id
        ):
            abort(403)

    elif current_user.role != "admin":
        abort(403)

    return appointment


@appointments_bp.route("/<int:appt_id>/status", methods=["POST"])
@login_required
def advance_appointment_status(appt_id):
    """Advance an appointment by exactly one permitted status transition."""

    # Patients must not change clinical workflow statuses.
    if current_user.role not in ["doctor", "admin"]:
        abort(403)

    appointment = get_appointment_or_404(appt_id)

    current_status = appointment.status

    # Normalize the legacy "booked" status to the existing
    # database value "scheduled" for transition lookup.
    if current_status == "booked":
        current_status = "booked"

    next_status = STATUS_TRANSITIONS.get(current_status)

    if next_status is None:
        flash(
            "This appointment cannot advance to another status.",
            "warning",
        )
        return redirect(url_for("appointments.list_appointments"))

    appointment.status = next_status

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash(
            "Unable to update appointment status. Please try again.",
            "danger",
        )
        return redirect(url_for("appointments.list_appointments"))

    flash(
        f"Appointment status updated to "
        f"{STATUS_LABELS[next_status]}.",
        "success",
    )

    return redirect(url_for("appointments.list_appointments"))


@appointments_bp.route("/<int:appt_id>/cancel", methods=["POST"])
@login_required
def cancel_appointment(appt_id):
    appointment = get_appointment_or_404(appt_id)

    if current_user.role not in ["patient", "admin"]:
        abort(403)

    if appointment.status != "scheduled":
        flash(
            "Only scheduled appointments can be cancelled.",
            "warning",
        )
    else:
        appointment.status = "cancelled"
        db.session.commit()

        flash("Appointment cancelled successfully.", "success")

    return redirect(url_for("appointments.list_appointments"))


@appointments_bp.route("/<int:appt_id>/edit", methods=["GET", "POST"])
@login_required
def edit_appointment(appt_id):
    if current_user.role == "doctor":
        abort(403)

    appointment = get_appointment_or_404(appt_id)

    if appointment.status != "scheduled":
        flash(
            "Only scheduled appointments can be edited.",
            "warning",
        )
        return redirect(url_for("appointments.list_appointments"))

    form = AppointmentForm(obj=appointment)

    form.doctor_id.choices = [
        (
            doctor.id,
            f"{doctor.user.full_name} "
            f"({doctor.speciality or 'General'})",
        )
        for doctor in Doctor.query.order_by(Doctor.id).all()
    ]

    form.patient_id.choices = [
        (patient.id, patient.user.full_name)
        for patient in Patient.query.order_by(Patient.id).all()
    ]

    if form.validate_on_submit():
        start = form.start_time.data
        end = start + timedelta(minutes=SLOT_MINUTES)

        if current_user.role == "admin":
            patient_id = form.patient_id.data
        else:
            patient_id = appointment.patient_id

        if start <= datetime.now():
            flash("Please choose a time in the future.", "danger")

        elif has_conflict(
            form.doctor_id.data,
            patient_id,
            start,
            end,
            exclude_id=appointment.id,
        ):
            flash(
                "The selected doctor or patient already has an "
                "appointment at that time.",
                "danger",
            )

        else:
            appointment.doctor_id = form.doctor_id.data
            appointment.start_time = start
            appointment.end_time = end
            appointment.reason = form.reason.data

            if current_user.role == "admin":
                appointment.patient_id = form.patient_id.data

            db.session.commit()

            flash("Appointment updated successfully.", "success")
            return redirect(url_for("appointments.list_appointments"))

    return render_template(
        "appointments/form.html",
        form=form,
        title="Edit Appointment",
    )
