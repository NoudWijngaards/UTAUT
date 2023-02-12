import uuid
from datetime import datetime
from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_required
from wtforms import RadioField
from app import db
from app.questionnaire import bp
from app.questionnaire.forms import QuestionnaireForm, SubmitForm
from app.questionnaire.functions import reverse_value, security_check
from app.models import User, Study, Case, Questionnaire, Demographic, DemographicAnswer, DemographicOption, \
    QuestionGroup, Question, QuestionAnswer


@bp.route('/clear_session/<study_code>', methods=['GET', 'POST'])
def clear_session(study_code):
    session.clear()

    return redirect(url_for('questionnaire.intro_questionnaire', study_code=study_code))


@bp.route('/invalid_session', methods=['GET', 'POST'])
def invalid_session():
    return render_template("questionnaire/invalid_session.html", title='Invalid Session')


@bp.route('/intro_questionnaire/e/<study_code>', methods=['GET', 'POST'])
def intro_questionnaire(study_code):
    security_check(study_code)
    # Als de gebruiker nog niet in een sessie zit een nieuwe sessie aanmaken.
    if "user" not in session:
        session["user"] = str(uuid.uuid4())
        session["study"] = study_code

    # Als de gebruiker al in een sessie zit verwijzen naar de vragenlijst.
    if session["user"] in [case.session for case in Case.query.all()]:
        flash('You are currently already in a session. Complete the questionnaire.')  # return eerste blok vragenpagina
        return redirect(url_for('questionnaire.part', study_code=study_code, part_number=0))

    # De Form om aangeven te starten met het onderzoek.
    study = Study.query.filter_by(code=study_code).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    demographics = [demographic for demographic in questionnaire.linked_demographics]

    return render_template('questionnaire/intro_questionnaire.html', title="Intro: {}".format(study.name), study=study,
                           study_code=study_code, demographics=demographics)


@bp.route('/start_questionnaire/e/<study_code>', methods=['GET', 'POST'])
def start_questionnaire(study_code):
    security_check(study_code)

    if session["user"] in [case.session for case in Case.query.all()] and session["study"] == study_code:
        flash('You are currently already in a session. Complete the questionnaire.')
        return redirect(url_for('questionnaire.part', study_code=study_code, part_number=0))

    study = Study.query.filter_by(code=study_code).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()

    # Een dictionary met de demografieken en een "return field" zodat de gebruiker alle demografieken kan invullen en
    # deze ook daadwerkelijk opgeslagen worden.
    demographics_dict = {}
    demographics = [demographic for demographic in questionnaire.linked_demographics]
    for demographic in demographics:
        demographics_dict[demographic.name] = demographic.return_field()
    form = QuestionnaireForm(demographics_dict)

    # Als de gebruiker aangeeft de demografieken ingevuld te hebben.
    if form.validate_on_submit():
        study = Study.query.filter_by(code=study_code).first()
        questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
        # Het toevoegen van een case aan de database.
        case = Case(session=session["user"], questionnaire_id=questionnaire.id)
        db.session.add(case)
        db.session.commit()

        # De antwoorden op de demografieken worden nog niet opgeslagen in de database, maar wel in de sessie. Op deze
        # manier worden de antwoorden pas opgeslagen als de participant de vragenlijst voltooit.
        session["demographic_answers"] = []
        for (demographic, answer) in zip([demographic for demographic in demographics], form.data.values()):
            if answer == [] or answer is None:
                demographic_answer = DemographicAnswer(answer=None, demographic_id=demographic.id, case_id=case.id)
                session["demographic_answers"].append(demographic_answer)
            else:
                demographic_answer = DemographicAnswer(answer=answer, demographic_id=demographic.id, case_id=case.id)
                session["demographic_answers"].append(demographic_answer)

        # Een dictionary met een numerieke key (0 tot en met zoveel) en de vragengroep (questiongroup_dict).
        questiongroup_dict = {}
        questiongroups = [questiongroup for questiongroup in questionnaire.linked_questiongroups]
        keys = range(len(questiongroups))
        for i in keys:
            questiongroup_dict[i] = questiongroups[i]

        # Evenals de demografische antwoorden worden de antwoorden op de vragen nog niet opgeslagen in de database, maar
        # wel in de sessie. De eerste twee sessiedata hieronder zijn om de vragenlijst goed te renderen (de eerste om
        # de vragenlijst op te delen tussen de vragengroepen, de tweede om te gaan naar het eindscherm zodra de laatste
        # is ingevuld).
        session["questionnaire_parts"] = questiongroup_dict
        session["questionnaire_max_part"] = QuestionGroup.query.filter_by(questionnaire_id=questionnaire.id).count()
        session["question_answers"] = []

        return redirect(url_for('questionnaire.part', study_code=study_code, part_number=0))

    return render_template('questionnaire/start_questionnaire.html', title="Start: {}".format(study.name), study=study,
                           form=form)


@bp.route('/questionnaire/e/<study_code>/<part_number>', methods=['GET', 'POST'])
def part(study_code, part_number):
    security_check(study_code)

    # Als de vragengroepnummer groter is dan de hoeveelheid vragengroepen wordt de gebruiker verwezen naar het einde.
    if int(part_number) >= session['questionnaire_max_part']:
        return redirect(url_for('questionnaire.ending_questionnaire', study_code=study_code))

    study = Study.query.filter_by(code=study_code).first()
    case = Case.query.filter_by(session=session["user"]).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    part = session["questionnaire_parts"][int(part_number)]
    questions = part.linked_questions()

    # Een dictionary met de vraag als key en een bijbehorende Field om in te vullen als waarde (questions_dict).
    questions_dict = {}
    for question in questions:
        questions_dict[question.question] = RadioField(question.question,
                                                       choices=[number for number in range(1, questionnaire.scale + 1)])
    form = QuestionnaireForm(questions_dict)

    # De volgende vragengroepnummer voor de verwijzing zodra de gebruiker dit gedeelte van de vragenlijst heeft ingevuld
    next_part_number = int(part_number) + 1

    # Als de gebruiker aangeeft dit gedeelte van de vragenlijst ingevuld te hebben.
    if form.validate_on_submit():
        for (question, value) in zip([question for question in questions], form.data.values()):
            # Deze "isinstance" regel wordt opgeroepen om enkele waarden welke toegevoegd werden en niet binnen de
            # antwoorden horen weg te werken. Dit kan gezien worden als een makkelijke work-around.
            if isinstance(value, str) and len(value) < 4:
                # Als een antwoord op de vraag al gegeven is binnen de sessie.
                if question.id in [answer.question_id for answer in session["question_answers"]]:
                    for answer in session["question_answers"]:
                        # Voor de vraag die inderdaad al beantwoord is.
                        if answer.question_id == question.id:
                            # Als de vraag met "reversed_score" werkt de gegeven score omdraaien.
                            if question.reversed_score:
                                answer.score = reverse_value(value, questionnaire.scale)
                            else:
                                answer.score = value
                # Als nog geen antwoord op de vraag gegeven is binnen de sessie.
                else:
                    # Als de vraag met "reversed_score" werkt de gegeven score omdraaien. Het antwoord sowieso toevoegen
                    # aan de sessie.
                    if question.reversed_score:
                        answer = QuestionAnswer(score=reverse_value(value, questionnaire.scale),
                                                question_id=question.id, case_id=case.id)
                        session["question_answers"].append(answer)
                    else:
                        answer = QuestionAnswer(score=value, question_id=question.id, case_id=case.id)
                        session["question_answers"].append(answer)
        # Naar het volgende onderdeel van de vragenlijst gaan.
        return redirect(
            url_for('questionnaire.part', study_code=study_code, part_number=next_part_number))

    return render_template('questionnaire/part.html', title="Questionnaire part {}: {}".format(str(part_number), study.name),
                           study=study, part=part, form=form)


@bp.route('/ending_questionnaire/e/<study_code>', methods=['GET', 'POST'])
def ending_questionnaire(study_code):
    security_check(study_code)

    study = Study.query.filter_by(code=study_code).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    case = Case.query.filter_by(session=session["user"]).first()
    total_question_number = 0
    for questiongroup in QuestionGroup.query.filter_by(questionnaire_id=questionnaire.id):
        total_question_number += Question.query.filter_by(questiongroup_id=questiongroup.id).count()
    # Voor het geval de gebruiker probeert naar het einde te gaan zonder dat alle vragen zijn beantwoord.
    if len(session["question_answers"]) < total_question_number:
        flash('You have not answered all of the questions yet. Finish the questions.')
        return redirect(url_for('questionnaire.part', study_code=study_code, questionlist_number=0))

    # De Form voor het aangeven dat de gebruiker inderdaad klaar is met de vragenlijst.
    form = SubmitForm()

    # Als de gebruiker aangeeft klaar te zijn met de vragenlijst.
    if form.validate_on_submit():
        # Het opslaan van de antwoorden op de vragen in de database.
        for answer in session["question_answers"]:
            db.session.add(answer)
            db.session.commit()
        # Het opslaan van de demografische antwoorden in de database.
        for answer in session["demographic_answers"]:
            db.session.add(answer)
            db.session.commit()
        # Aangeven dat de vragenlijst voltooid is door de gebruiker/specifieke case.
        case.completed = True
        db.session.commit()
        session.clear()
        return "Thank you for participating."
    return render_template('questionnaire/ending_questionnaire.html', title="Ending questionnaire", form=form)