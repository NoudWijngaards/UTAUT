from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo
from app.models import User


# De Form om in te loggen.
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


# De Form om te registreren binnen de applicatie.
class RegistrationForm(FlaskForm):
    style_email = {'style': 'width:150%;'}
    email = StringField('Email', validators=[DataRequired(), Email()], render_kw=style_email)
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')


# De Form om een wachtwoordreset aan te vragen.
class ResetPasswordRequestForm(FlaskForm):
    style_reset = {'style': 'width:120%;'}
    email = StringField('Email', validators=[DataRequired(), Email()], render_kw=style_reset)
    submit = SubmitField('Request Password Reset')


# De Form om de wachtwoordreset te voltooien.
class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Request Password Reset')
