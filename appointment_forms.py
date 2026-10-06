from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, DateTimeLocalField
from wtforms.validators import DataRequired, Length


class AppointmentForm(FlaskForm):
    doctor_id = SelectField("Doctor", coerce=int, validators=[DataRequired()])
    start_time = DateTimeLocalField(
        "Date & time", format="%Y-%m-%dT%H:%M", validators=[DataRequired()]
    )
    reason = StringField("Reason for visit", validators=[DataRequired(), Length(max=300)])
    submit = SubmitField("Save")