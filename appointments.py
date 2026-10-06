from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import Appointment

appointments_bp = Blueprint("appointments", __name__, url_prefix="/appointments")


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