from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, RadioField, BooleanField


# Een dynamische veld waarmee meerdere Forms tegelijk opgeslagen kunnen worden. Deze wordt met name gebruikt binnen de
# vragenlijst voor de RadioFields. De reden voor het gebruik van deze dynamische form is omdat bij sommige gedeeltes van
# de vragenlijst (zoals de hoeveelheid vragen binnen een kernvariabele en hoeveel demografische informatie opgeslagen)
# door de gebruiker zelf bepaald worden en dus de hoeveelheid onbepaald is voor de programmeur voorafgaand.
def QuestionnaireForm(questions, *args, **kwargs):
    class TestForm(FlaskForm):
        submit = SubmitField('Go to next page')

    for name, value in questions.items():
        setattr(TestForm, name, value)

    return TestForm(*args, **kwargs)


# De Form welke gebruikt wordt voor enkel opslaan en verwijzen.
class SubmitForm(FlaskForm):
    submit = SubmitField('Submit')


# De knop om te starten met de vragenlijst.
class StartQuestionnaireForm(FlaskForm):
    submit = SubmitField('Start questionnaire')
