from flask_wtf import FlaskForm

from wtforms import (
    SelectField,
    StringField,
    SubmitField,
    DateTimeLocalField
)

from wtforms.validators import (
    DataRequired,
    Length
)


class AppointmentForm(FlaskForm):

    patient_id = SelectField(
        "Patient",
        coerce=int,
        validators=[DataRequired()]
    )

    doctor_id = SelectField(
        "Doctor",
        coerce=int,
        validators=[DataRequired()]
    )

    start_time = DateTimeLocalField(
        "Date & Time",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired()]
    )

    reason = StringField(
        "Reason for Visit",
        validators=[
            DataRequired(),
            Length(max=300)
        ]
    )

    submit = SubmitField(
        "Save Appointment"
    )