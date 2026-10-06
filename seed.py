from datetime import datetime, timedelta
from app import app
from extensions import db
from models import User, Patient, Doctor, Appointment

with app.app_context():
    db.drop_all()
    db.create_all()

    # create an admin
    test_admin1 = User(email="admin@clinic.com", role="admin", full_name="Admin User 1")
    test_admin1.set_password("admin123")

    # create a doctor 
    test_doctor1 = User(email="dr.lee@clinic.com", role="doctor", full_name="Dr.Lee")
    test_doctor1.set_password("doctorpass")
    doctor = Doctor(user=test_doctor1, speciality="General Practice")

    # create a patient
    test_patient1 = User(email="sara@mail.com", role="patient", full_name="Sara Mat")
    test_patient1.set_password("password123")
    patient = Patient(user=test_patient1, phone="416-555-0100")

    # sample appointment 
    start = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    test_appt = Appointment(patient=patient, doctor=doctor, start_time=start, end_time=start + timedelta(minutes=30), reason="Sample Checkup")

    db.session.add_all([test_admin1, test_doctor1, doctor, test_patient1, patient, test_appt])
    db.session.commit()
    print("Database Seeded")