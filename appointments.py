from datetime import datetime, timedelta

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    abort
)

from flask_login import login_required, current_user

from sqlalchemy import or_

from extensions import db

from models import (
    Appointment,
    Doctor,
    Patient
)

from appointment_forms import AppointmentForm


appointments_bp = Blueprint(
    "appointments",
    __name__,
    url_prefix="/appointments"
)


SLOT_MINUTES = 30


def has_conflict(
    doctor_id,
    patient_id,
    start,
    end,
    exclude_id=None
):
    """
    Prevent double-booking for either:
    - the selected doctor
    - the selected patient

    Cancelled appointments do not count as conflicts.
    """

    query = Appointment.query.filter(
        Appointment.status != "cancelled",
        Appointment.start_time < end,
        Appointment.end_time > start,
        or_(
            Appointment.doctor_id == doctor_id,
            Appointment.patient_id == patient_id
        )
    )

    if exclude_id is not None:
        query = query.filter(
            Appointment.id != exclude_id
        )

    return query.first() is not None


@appointments_bp.route("/")
@login_required
def list_appointments():
    """
    Patients see their own appointments.
    Doctors see appointments assigned to them.
    Admin/receptionist sees all appointments.
    """

    query = Appointment.query

    if current_user.role == "patient":

        if not current_user.patient:
            flash(
                "Patient profile not found.",
                "danger"
            )

            return redirect(
                url_for("dashboard")
            )

        query = query.filter_by(
            patient_id=current_user.patient.id
        )

    elif current_user.role == "doctor":

        if not current_user.doctor:
            flash(
                "Doctor profile not found.",
                "danger"
            )

            return redirect(
                url_for("dashboard")
            )

        query = query.filter_by(
            doctor_id=current_user.doctor.id
        )

    elif current_user.role == "admin":
        # Admin = receptionist.
        # Admin sees all appointments.
        pass

    else:
        abort(403)

    appointments = query.order_by(
        Appointment.start_time.desc()
    ).all()

    return render_template(
        "appointments/list.html",
        appointments=appointments
    )


@appointments_bp.route(
    "/new",
    methods=["GET", "POST"]
)
@login_required
def create_appointment():

    # Patients and admins/receptionists can create appointments.
    if current_user.role not in ["patient", "admin"]:
        abort(403)

    form = AppointmentForm()

    # Populate doctor dropdown.
    form.doctor_id.choices = [
        (
            doctor.id,
            f"{doctor.user.full_name} "
            f"({doctor.speciality or 'General'})"
        )
        for doctor in Doctor.query.order_by(
            Doctor.id
        ).all()
    ]

    # Admin/receptionist selects the patient.
    if current_user.role == "admin":

        form.patient_id.choices = [
            (
                patient.id,
                patient.user.full_name
            )
            for patient in Patient.query.order_by(
                Patient.id
            ).all()
        ]

    else:
        # Patient books an appointment for themselves.
        form.patient_id.choices = [
            (
                current_user.patient.id,
                current_user.full_name
            )
        ]

    if form.validate_on_submit():

        start = form.start_time.data

        end = start + timedelta(
            minutes=SLOT_MINUTES
        )

        # Determine which patient the appointment belongs to.
        if current_user.role == "patient":
            patient_id = current_user.patient.id
        else:
            patient_id = form.patient_id.data

        # Appointment must be in the future.
        if start <= datetime.now():

            flash(
                "Please choose a time in the future.",
                "danger"
            )

        # Prevent doctor OR patient double-booking.
        elif has_conflict(
            form.doctor_id.data,
            patient_id,
            start,
            end
        ):

            flash(
                "The selected doctor or patient already has an appointment at that time.",
                "danger"
            )

        else:

            appointment = Appointment(
                patient_id=patient_id,
                doctor_id=form.doctor_id.data,
                start_time=start,
                end_time=end,
                reason=form.reason.data,
                status="scheduled"
            )

            db.session.add(appointment)
            db.session.commit()

            flash(
                "Appointment booked successfully.",
                "success"
            )

            return redirect(
                url_for(
                    "appointments.list_appointments"
                )
            )

    return render_template(
        "appointments/form.html",
        form=form,
        title="Book an Appointment"
    )


def get_appointment_or_404(appt_id):

    appointment = db.get_or_404(
        Appointment,
        appt_id
    )

    # Patients can only access their own appointments.
    if current_user.role == "patient":

        if (
            not current_user.patient
            or appointment.patient_id
            != current_user.patient.id
        ):
            abort(403)

    # Doctors can only access appointments assigned to them.
    elif current_user.role == "doctor":

        if (
            not current_user.doctor
            or appointment.doctor_id
            != current_user.doctor.id
        ):
            abort(403)

    # Admin/receptionist can access all appointments.
    elif current_user.role == "admin":
        pass

    else:
        abort(403)

    return appointment


@appointments_bp.route(
    "/<int:appt_id>/cancel",
    methods=["POST"]
)
@login_required
def cancel_appointment(appt_id):

    appointment = get_appointment_or_404(
        appt_id
    )

    if appointment.status != "scheduled":

        flash(
            "Only scheduled appointments can be cancelled.",
            "warning"
        )

    else:

        appointment.status = "cancelled"

        db.session.commit()

        flash(
            "Appointment cancelled successfully.",
            "success"
        )

    return redirect(
        url_for(
            "appointments.list_appointments"
        )
    )


@appointments_bp.route(
    "/<int:appt_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit_appointment(appt_id):

    # Doctors cannot reschedule/edit appointments.
    if current_user.role == "doctor":
        abort(403)

    appointment = get_appointment_or_404(
        appt_id
    )

    if appointment.status != "scheduled":

        flash(
            "Only scheduled appointments can be edited.",
            "warning"
        )

        return redirect(
            url_for(
                "appointments.list_appointments"
            )
        )

    form = AppointmentForm(
        obj=appointment
    )

    form.doctor_id.choices = [
        (
            doctor.id,
            f"{doctor.user.full_name} "
            f"({doctor.speciality or 'General'})"
        )
        for doctor in Doctor.query.order_by(
            Doctor.id
        ).all()
    ]

    form.patient_id.choices = [
        (
            patient.id,
            patient.user.full_name
        )
        for patient in Patient.query.order_by(
            Patient.id
        ).all()
    ]

    if form.validate_on_submit():

        start = form.start_time.data

        end = start + timedelta(
            minutes=SLOT_MINUTES
        )

        # Admin can change the patient.
        # Patients remain assigned to themselves.
        if current_user.role == "admin":
            patient_id = form.patient_id.data
        else:
            patient_id = appointment.patient_id

        if start <= datetime.now():

            flash(
                "Please choose a time in the future.",
                "danger"
            )

        elif has_conflict(
            form.doctor_id.data,
            patient_id,
            start,
            end,
            exclude_id=appointment.id
        ):

            flash(
                "The selected doctor or patient already has an appointment at that time.",
                "danger"
            )

        else:

            appointment.doctor_id = (
                form.doctor_id.data
            )

            appointment.start_time = start

            appointment.end_time = end

            appointment.reason = (
                form.reason.data
            )

            # Only admin/receptionist can change
            # which patient the appointment belongs to.
            if current_user.role == "admin":
                appointment.patient_id = (
                    form.patient_id.data
                )

            db.session.commit()

            flash(
                "Appointment updated successfully.",
                "success"
            )

            return redirect(
                url_for(
                    "appointments.list_appointments"
                )
            )

    return render_template(
        "appointments/form.html",
        form=form,
        title="Edit Appointment"
    )