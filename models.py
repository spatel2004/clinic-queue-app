
from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import UniqueConstraint

from extensions import db, login_manager


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(256),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False
    )

    full_name = db.Column(
        db.String(100),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    patient = db.relationship(
        "Patient",
        backref="user",
        uselist=False
    )

    doctor = db.relationship(
        "Doctor",
        backref="user",
        uselist=False
    )

    def set_password(self, password):
        from werkzeug.security import generate_password_hash

        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash

        return check_password_hash(
            self.password_hash,
            password
        )


class Patient(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        unique=True,
        nullable=False
    )

    date_of_birth = db.Column(db.Date)
    phone = db.Column(db.String(30))


class Doctor(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        unique=True,
        nullable=False
    )

    speciality = db.Column(db.String(100))



class DoctorAvailability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(
        db.Integer,
        db.ForeignKey("doctor.id"),
        nullable=False
    )
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    doctor = db.relationship("Doctor", backref="availability_slots")


class Appointment(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patient.id"),
        nullable=False
    )

    doctor_id = db.Column(
        db.Integer,
        db.ForeignKey("doctor.id"),
        nullable=False
    )

    start_time = db.Column(
        db.DateTime,
        nullable=False
    )

    end_time = db.Column(
        db.DateTime,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="scheduled"
    )

    reason = db.Column(
        db.String(300),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    patient = db.relationship(
        "Patient",
        backref="appointments"
    )

    doctor = db.relationship(
        "Doctor",
        backref="appointments"
    )


class Queue(db.Model):
    __tablename__ = "queue"

    __table_args__ = (
        UniqueConstraint(
            "appointment_id",
            name="uq_queue_appointment"
        ),
        UniqueConstraint(
            "queue_date",
            "queue_number",
            name="uq_daily_queue_number"
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    appointment_id = db.Column(
        db.Integer,
        db.ForeignKey("appointment.id"),
        nullable=False
    )

    queue_number = db.Column(
        db.Integer,
        nullable=False
    )

    queue_date = db.Column(
        db.Date,
        nullable=False,
        default=lambda: datetime.utcnow().date(),
        index=True
    )

    status = db.Column(
        db.String(50),
        nullable=False,
        default="waiting"
    )

    checked_in_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    appointment = db.relationship(
        "Appointment",
        backref=db.backref(
            "queue_entry",
            uselist=False
        )
    )


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
