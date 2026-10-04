from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, login_manager

class User(UserMixin, db.Model):
    # every table will need a unique ID per row. primary_key=True makes this the unique identifier, SQLAlchemy auto incrments by 1 each time
    id = db.Column(db.Integer, primary_key=True)

    # unique=True prevents duplicate accounts and nullable=False prevents empty accounts without email addresses
    email = db.Column(db.String(120), unique=True, nullable=False)

    # storing scrmabled version of real password, hash password is long
    password_hash = db.Column(db.String(256), nullable=False)

    # storing role of each user, can be patient/doctor/admin
    role = db.Column(db.String(20), nullable=False)

    full_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # this user can be linked to a patient or doctor row
    # uselist=False ensures 1-1 relationship, meaning user has at most one patient profile, so user.patient returns single object, not a list
    # backref="user" means if we have a patient or doctor object, patient.user or doctor.user will give us the User object (basically a reverse relationship as well)
    patient = db.relationship("Patient", backref="user", uselist=False)
    doctor = db.relationship("Doctor", backref="user", uselist=False)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)
    
    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # db.ForeignKey("user.id") means this column references the id column in the user table, unique=True ensures 1-1 relationship hence one User cannot have two patient profiles, 
    # nullable=False means every patient must have a user account
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    date_of_birth = db.Column(db.Date)
    phone = db.Column(db.String(30))
    
class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    speciality = db.Column(db.String(100))

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctor.id"), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="scheduled")
    reason = db.Column(db.String(300), nullable=False) # needs to have a proper reason for appointment to be scheduled 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    patient = db.relationship("Patient", backref="appointments") # one to many relationship, appointment.patient gives us the Patient. patient.appointments gives ur list of all Paitient appointments
    doctor = db.relationship("Doctor", backref="appointments") # ^ same as above 

class Queue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointment.id"), nullable=False)
    queue_number = db.Column(db.Integer)
    status = db.Column(db.String(50), default="waiting")
    checked_in_at = db.Column(db.DateTime)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))



