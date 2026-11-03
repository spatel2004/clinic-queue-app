
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
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Appointment, Doctor, Patient, Queue
from appointment_forms import AppointmentForm


appointments_bp = Blueprint(
    "appointments",
    __name__,
    url_prefix="/appointments",
)

SLOT_MINUTES = 30

STATUS_LABELS = {
    "scheduled": "Booked",
    "booked": "Booked",
    "checked-in": "Checked-in",
    "in-progress": "In progress",
    "complete": "Complete",
    "cancelled": "Cancelled",
}

# Appointments can only start after reception checks the patient in.
STATUS_TRANSITIONS = {
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

    elif current_user.role != "admin":
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


@appointments_bp.route("/<int:appt_id>/check-in", methods=["POST"])
@login_required
def check_in_patient(appt_id):
    """Reception checks in a patient and assigns the next daily queue number."""

    if current_user.role != "admin":
        flash("Only administrators can check patients in.", "warning")
        return redirect(url_for("appointments.list_appointments"))

    appointment = get_appointment_or_404(appt_id)

    if appointment.status not in ["scheduled", "booked"]:
        flash(
            "This appointment cannot be checked in.",
            "warning",
        )
        return redirect(url_for("appointments.list_appointments"))

    # Prevent duplicate queue entries.
    existing_entry = Queue.query.filter_by(
        appointment_id=appointment.id
    ).first()

    if existing_entry:
        flash(
            "This patient has already been checked in.",
            "warning",
        )
        return redirect(url_for("appointments.list_appointments"))

    # Queue numbers reset each calendar day.
    check_in_time = datetime.now()
    queue_date = check_in_time.date()

    if appointment.start_time.date() != queue_date:
        flash(
            "Patients can only be checked in on their appointment date.",
            "warning",
        )
        return redirect(url_for("appointments.list_appointments"))

    # Find the highest queue number assigned today.
    highest_number = (
        db.session.query(db.func.max(Queue.queue_number))
        .filter(Queue.queue_date == queue_date)
        .scalar()
    )

    next_number = (highest_number or 0) + 1

    queue_entry = Queue(
        appointment_id=appointment.id,
        queue_number=next_number,
        queue_date=queue_date,
        status="waiting",
        checked_in_at=check_in_time,
    )

    appointment.status = "checked-in"
    db.session.add(queue_entry)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(
            "Unable to assign a queue number. Please refresh and try again.",
            "danger",
        )
        return redirect(url_for("appointments.list_appointments"))
    except Exception:
        db.session.rollback()
        flash(
            "An error occurred while checking in the patient.",
            "danger",
        )
        return redirect(url_for("appointments.list_appointments"))

    flash(
        f"Patient checked in successfully. Queue number: {next_number}.",
        "success",
    )

    return redirect(url_for("appointments.list_appointments"))


@appointments_bp.route("/<int:appt_id>/status", methods=["POST"])
@login_required
def advance_appointment_status(appt_id):
    """Allow admins and assigned doctors to start and complete appointments."""

    # Both admins and doctors can update appointment statuses.
    if current_user.role not in ["admin", "doctor"]:
        flash(
            "You do not have permission to update appointment status.",
            "warning",
        )
        return redirect(url_for("appointments.list_appointments"))

    appointment = get_appointment_or_404(appt_id)

    next_status = STATUS_TRANSITIONS.get(appointment.status)

    if next_status is None:
        flash(
            "This appointment cannot advance from its current status. "
            "The patient must be checked in first.",
            "warning",
        )
        return redirect(url_for("appointments.list_appointments"))

    # A queue entry must exist before an appointment can start or complete.
    queue_entry = Queue.query.filter_by(
        appointment_id=appointment.id
    ).first()

    if queue_entry is None:
        flash(
            "No queue entry was found for this appointment. "
            "Please contact reception.",
            "danger",
        )
        return redirect(url_for("appointments.list_appointments"))

    # Update appointment and queue statuses together.
    appointment.status = next_status

    if next_status == "in-progress":
        queue_entry.status = "in-progress"
    elif next_status == "complete":
        queue_entry.status = "completed"

    try:
        db.session.commit()
        flash(
            f"Appointment successfully updated to "
            f"{STATUS_LABELS[next_status]}.",
            "success",
        )
    except Exception:
        db.session.rollback()
        flash(
            "Unable to update appointment status. Please try again.",
            "danger",
        )

    return redirect(url_for("appointments.list_appointments"))


@appointments_bp.route("/<int:appt_id>/cancel", methods=["POST"])
@login_required
def cancel_appointment(appt_id):
    """Patients and admins can cancel scheduled appointments."""

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
    """Patients and admins can edit scheduled appointments."""

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
