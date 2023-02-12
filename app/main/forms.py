from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, RadioField, BooleanField
from wtforms.validators import ValidationError, DataRequired, Length
from app.models import User


# De Form voor het aanpassen van het profiel van de eigen gebruiker.
class EditProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=0, max=64)])
    about_me = TextAreaField('About me', validators=[Length(min=0, max=250)])
    submit = SubmitField('Submit')

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user is not None:
                raise ValidationError('This username has already been taken. Please use a different one.')


# De Form voor het creëren van een nieuwe standaardvraag.
class CreateNewQuestionUser(FlaskForm):
    name_question = StringField('Question', validators=[DataRequired(), Length(min=0, max=120)])
    submit = SubmitField('Add question')


# De Form welke gebruikt wordt voor enkel opslaan en verwijzen.
class EmptyForm(FlaskForm):
    submit = SubmitField('Submit')