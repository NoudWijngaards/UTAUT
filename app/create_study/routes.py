from flask import render_template, flash, redirect, url_for, request
from flask_login import current_user, login_required
import numpy as np
import pandas as pd
import plspm.config as c
import json
from plspm.plspm import Plspm
from plspm.scheme import Scheme
from plspm.mode import Mode
from app import db
from app.create_study import bp
from app.create_study.forms import CreateNewStudyForm, EditStudyForm, CreateNewCoreVariableForm, CreateNewRelationForm, \
    CreateNewDemographicForm, CreateNewQuestionForm, EditQuestionForm, EditScaleForm
from app.create_study.functions import setup_questiongroups, setup_structure_dataframe, cronbachs_alpha, composite_reliability, \
    average_variance_extracted, heterotrait_monotrait, htmt_matrix, outer_vif_values_dict, return_questionlist_and_answerlist, \
    indexes_questiongroups_three, correlation_matrix, check_researchmodel, check_if_used_model
from app.main.functions import security_and_studycheck_stage1, security_and_studycheck_stage2, security_and_studycheck_stage3
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tools.tools import add_constant
from app.models import User, Study, CoreVariable, Relation, ResearchModel, Questionnaire, QuestionGroup, Question, \
    Demographic, DemographicOption, Case, DemographicAnswer


#############################################################################################################
#                                        De studie opzetten
#############################################################################################################


@bp.route('/new_study', methods=['GET', 'POST'])
@login_required
def new_study():
    # De Form voor het aanmaken van een nieuw onderzoek.
    form = CreateNewStudyForm()

    # Als de gebruiker aangeeft een nieuw onderzoek aan te willen maken
    if form.validate_on_submit():
        # Een nieuw onderzoek wordt opgezet.
        # new_study is een "Study"-object (Study is een tabel binnen de database, zie "models.py"). De naam,
        # beschrijving en relevante technologie van de studie worden gehaald uit de "form" die de gebruiker heeft
        # ingeleverd op de pagina. De "data" stelt de antwoorden voor. Na het bepalen van "new_study" wordt deze
        # toegevoegd (db.session.add) en opgeslagen in de database (db.session.commit).
        new_study = Study(name=form.name_of_study.data, description=form.description_of_study.data,
                          technology=form.technology_of_study.data)
        # Een unieke code wordt gegeven aan het onderzoek (gebruikmakend van UUID4).
        new_study.create_code()
        db.session.add(new_study)
        # De huidige gebruiker wordt gelinkt aan het onderzoek.
        current_user.link(new_study)
        db.session.commit()

        # "redirect(url_for)" verwijst de gebruiker naar een andere pagina in het geval dat de Form is gesubmitted.
        return redirect(url_for('create_study.choose_model', study_code=new_study.code))
    # "render_template" toont de relevante HTML-pagina. "Title" is de titel van de pagina. De variabelen die erna worden
    # gegeven is om ervoor te zorgen dat Jinja2 deze variabelen kan renderen binnen de HTML-pagina, in dit geval alleen
    # "form". Deze zullen veel terugkomen. In dat geval zal te zien zijn dat deze variabelen terug te lezen zijn binnen
    # de HTML-pagina.
    return render_template("create_study/new_study.html", title='New Study', form=form)


@bp.route('/edit_study/<study_code>', methods=['GET', 'POST'])
@login_required
def edit_study(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    # "Query" wordt gebruikt om objecten binnen de tabel (Study) te selecteren. filter_by is een manier
    # om te filteren op welke objecten geselecteerd worden. In dit geval dient de "code" gelijk te zijn aan de code van
    # de relevante studie. "first()" werkt net zoals de return-functie in Python; in dit geval wordt het eerste
    # resultaat uit de query gereturned.
    study = Study.query.filter_by(code=study_code).first()

    # De Form voor het aanpassen van het onderzoek. Waarom de attributen van de studie binnen de Form gegeven worden is
    # omdat deze als originele inputs aangegeven worden binnen de Form. Zie "create_study/forms.py".
    form = EditStudyForm()

    # Als de gebruiker aangeeft de onderzoek te willen aanpassen met de gegeven gegevens.
    if form.validate_on_submit():
        # De gegevens van de studie worden aangepast naar de ingegeven data binnen de Form.
        study.name = form.name_of_study.data
        study.description = form.description_of_study.data
        study.technology = form.technology_of_study.data
        db.session.commit()
        flash('Your changes have been saved.')
        return redirect(url_for('create_study.edit_model', study_code=study.code))
    # Voor "GET" worden de originele waarden van de studie gebruikt om aan te geven binnen de Form.
    elif request.method == 'GET':
        form.name_of_study.data = study.name
        form.description_of_study.data = study.description
        form.technology_of_study.data = study.technology
    return render_template('create_study/edit_study.html', title='Edit Profile',
                           form=form, study=study)


#############################################################################################################
#                                      Onderzoeksmodel opstellen
#############################################################################################################


@bp.route('/choose_model/<study_code>', methods=['GET', 'POST'])
@login_required
def choose_model(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()

    if study.researchmodel_id:
        # Checken of er gebruikgemaakt wordt van een bestaand model (in dit geval kan het model niet aangepast worden).
        check_for_existing_model = check_if_used_model(study)
        if check_for_existing_model is not None:
            return check_for_existing_model
        else:
            flash("You already have created a model for this study.")
            redirect(url_for('create_study.edit_model', study_code=study.code))

    # Alle modellen waarvan de "user_id" die van de huidige gebruiker is.
    models = [model for model in ResearchModel.query.filter_by(user_id=current_user.id)]
    amount_of_models = len(models)

    return render_template("create_study/choose_model.html", title='Choose model', study=study, models=models,
                           amount_of_models=amount_of_models)


@bp.route('/add_model/<study_code>/<model_id>', methods=['GET', 'POST'])
@login_required
def add_model(study_code, model_id):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=model_id).first()
    if study.researchmodel_id is None:
        study.researchmodel_id = model.id
        study.used_existing_model = True
        db.session.commit()

    return redirect(url_for('create_study.questionnaire', study_code=study_code))


@bp.route('/create_new_model/<study_code>', methods=['GET', 'POST'])
@login_required
def create_new_model(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    if study.researchmodel_id is None:
        new_model = ResearchModel(name=study.name, user_id=current_user.id)
        db.session.add(new_model)
        db.session.commit()

        study.researchmodel_id = new_model.id
        db.session.commit()

    return redirect(url_for('create_study.edit_model', study_code=study.code))


@bp.route('/edit_model/<study_code>', methods=['GET', 'POST'])
@login_required
def edit_model(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()

    # Checken of er gebruikgemaakt wordt van een bestaand model (in dit geval kan het model niet aangepast worden).
    check_for_existing_model = check_if_used_model(study)
    if check_for_existing_model is not None:
        return check_for_existing_model

    # "Linked_corevariables" zijn de kernvariabelen die horen bij het model. Deze functie is onderdeel van de
    # "ResearchModel"-tabel.
    corevariables = [corevariable for corevariable in model.linked_corevariables]
    relations = [relation for relation in Relation.query.filter_by(model_id=model.id)]

    return render_template("create_study/edit_model.html", title='Edit model', study=study, model=model,
                           corevariables=corevariables, relations=relations)


@bp.route('/edit_model/new_corevariable/<study_code>', methods=['GET', 'POST'])
@login_required
def new_corevariable(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    corevariables = [corevariable for corevariable in CoreVariable.query.filter_by(user_id=current_user.id)]
    amount_of_corevariables = len(corevariables)

    # Checken of er gebruikgemaakt wordt van een bestaand model (in dit geval kan het model niet aangepast worden).
    check_for_existing_model = check_if_used_model(study)
    if check_for_existing_model is not None:
        return check_for_existing_model

    return render_template("create_study/new_corevariable.html", title='New Core Variable', study=study, model=model,
                           corevariables=corevariables, amount_of_corevariables=amount_of_corevariables)


@bp.route('/add_corevariable/<study_code>/<corevariable_id>', methods=['GET', 'POST'])
@login_required
def add_corevariable(study_code, corevariable_id):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    corevariable = CoreVariable.query.filter_by(id=corevariable_id).first()

    # Checken of er gebruikgemaakt wordt van een bestaand model (in dit geval kan het model niet aangepast worden).
    check_for_existing_model = check_if_used_model(study)
    if check_for_existing_model is not None:
        return check_for_existing_model

    corevariable.link(model)
    db.session.commit()

    return redirect(url_for('create_study.edit_model', study_code=study_code))


@bp.route('/edit_model/create_new_corevariable/<study_code>', methods=['GET', 'POST'])
@login_required
def create_new_corevariable(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()

    # Checken of er gebruikgemaakt wordt van een bestaand model (in dit geval kan het model niet aangepast worden).
    check_for_existing_model = check_if_used_model(study)
    if check_for_existing_model is not None:
        return check_for_existing_model

    # De Form voor het aanmaken van een nieuwe kernvariabele.
    form = CreateNewCoreVariableForm()

    # Als de gebruiker aangeeft een nieuwe kernvariabele te willen aanmaken.
    if form.validate_on_submit():
        # De kernvariabele toegevoegd aan de database.
        new_corevariable = CoreVariable(name=form.name_corevariable.data,
                                        abbreviation=form.abbreviation_corevariable.data,
                                        description=form.description_corevariable.data,
                                        user_id=current_user.id)
        db.session.add(new_corevariable)
        db.session.commit()

        # De kernvariabele wordt binnen het onderzoeksmodel geplaatst.
        model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
        new_corevariable.link(model)
        db.session.commit()

        return redirect(url_for('create_study.edit_model', study_code=study_code))

    return render_template("create_study/create_new_corevariable.html", title='Create core variable', study=study,
                           form=form)


@bp.route('/remove_corevariable/<study_code>/<corevariable_id>', methods=['GET', 'POST'])
@login_required
def remove_corevariable(study_code, corevariable_id):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    corevariable = CoreVariable.query.filter_by(id=corevariable_id).first()

    # Checken of er gebruikgemaakt wordt van een bestaand model (in dit geval kan het model niet aangepast worden).
    check_for_existing_model = check_if_used_model(study)
    if check_for_existing_model is not None:
        return check_for_existing_model

    # De kernvariabele uit het onderzoeksmodel halen en alle bijbehorende relaties verwijderen.
    corevariable.unlink(model)
    db.session.commit()
    Relation.query.filter_by(influencer_id=corevariable.id, model_id=model.id).delete()
    db.session.commit()
    Relation.query.filter_by(influenced_id=corevariable.id, model_id=model.id).delete()
    db.session.commit()

    # Als de kernvariabele al een vragenlijstgroep had binnen de vragenlijst deze en de bijbehorende vragen verwijderen.
    if questionnaire:
        questiongroup = QuestionGroup.query.filter_by(corevariable_id=corevariable.id,
                                                      questionnaire_id=questionnaire.id).first()
        Question.query.filter_by(questiongroup_id=questiongroup.id).delete()
        db.session.commit()
        QuestionGroup.query.filter_by(corevariable_id=corevariable.id, questionnaire_id=questionnaire.id).delete()
        db.session.commit()

    return redirect(url_for('create_study.edit_model', study_code=study_code))


@bp.route('/utaut/new_relation/<study_code>', methods=['GET', 'POST'])
@login_required
def new_relation(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    # De Form voor het aanmaken van een nieuwe relatie.
    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()

    # Checken of er gebruikgemaakt wordt van een bestaand model (in dit geval kan het model niet aangepast worden).
    check_for_existing_model = check_if_used_model(study)
    if check_for_existing_model is not None:
        return check_for_existing_model

    form = CreateNewRelationForm()
    # De "choices" zijn er voor de mogelijke keuzes die er zijn voor het kiezen van de "name_influencer" en
    # "name_influenced". De gebruiker kan namelijk niet zelf iets invullen, maar moet uit een keuzeveld kiezen.
    form.name_influencer.choices = [(corevariable.id, corevariable.name) for corevariable in
                                    model.linked_corevariables]
    form.name_influenced.choices = [(corevariable.id, corevariable.name) for corevariable in
                                    model.linked_corevariables]

    # Als de gebruiker aangeeft een nieuwe relatie aan te willen maken.
    if form.validate_on_submit():
        # De ID van de beïnvloedende kernvariabele bepalen.
        id_influencer = [corevariable for corevariable in model.linked_corevariables if corevariable.id ==
                         int(form.name_influencer.data)][0].id
        # De ID van de beïnvloedde kernvariabele bepalen.
        id_influenced = [corevariable for corevariable in model.linked_corevariables if corevariable.id ==
                         int(form.name_influenced.data)][0].id

        if id_influencer == id_influenced:
            flash("The influencing variable is the same as the influenced variable. For the relation, use different"
                  " core variables.")
            return redirect(url_for('create_study.edit_model', study_code=study_code))

        if Relation.query.filter_by(model_id=model.id, influencer_id=id_influenced, influenced_id=id_influencer).first():
            flash("Mutual relations are not allowed within the model.")
            return redirect(url_for('create_study.edit_model', study_code=study_code))

        if Relation.query.filter_by(model_id=model.id, influencer_id=id_influencer,
                                    influenced_id=id_influenced).first() is None:
            # De relatie aanmaken tussen de twee relevante kernvariabelen.
            newrelation = Relation(model_id=model.id,
                                   influencer_id=id_influencer,
                                   influenced_id=id_influenced)
            db.session.add(newrelation)
            db.session.commit()

        return redirect(url_for('create_study.edit_model', study_code=study_code))

    return render_template("create_study/new_relation.html", title='Create New Relation', form=form)


@bp.route('/remove_relation/<study_code>/<id_relation>', methods=['GET', 'POST'])
@login_required
def remove_relation(study_code, id_relation):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()

    # Checken of er gebruikgemaakt wordt van een bestaand model (in dit geval kan het model niet aangepast worden).
    check_for_existing_model = check_if_used_model(study)
    if check_for_existing_model is not None:
        return check_for_existing_model

    # Het verwijderen van de relevante relatie.
    Relation.query.filter_by(id=id_relation).delete()
    db.session.commit()

    return redirect(url_for('create_study.edit_model', study_code=study_code))


#############################################################################################################
#                                        Vragenlijst opstellen
#############################################################################################################


@bp.route('/questionnaire/<study_code>', methods=['GET', 'POST'])
@login_required
def questionnaire(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    setup_questiongroups(study)
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    # Voor het geval nieuwe kernvariabelen zijn toegevoegd aan het onderzoeksmodel nieuwe vragenlijstgroepen aanmaken.
    for corevariable in model.linked_corevariables:
        if corevariable.id not in [questiongroup.corevariable_id for questiongroup
                                   in QuestionGroup.query.filter_by(questionnaire_id=questionnaire.id)]:
            questiongroup = QuestionGroup(questionnaire_id=questionnaire.id,
                                          corevariable_id=corevariable.id)
            db.session.add(questiongroup)
            db.session.commit()

    questiongroups = [questiongroup for questiongroup in questionnaire.linked_questiongroups]

    # Een lijst met sublijsten van alle vragen van iedere kernvariabele.
    questions = []
    for questiongroup in questiongroups:
        questions.append(questiongroup.linked_questions())
    questiongroups_questions = dict(zip(questiongroups, questions))

    # Een lijst met de demographics die bij het onderzoek horen.
    demographics = [demographic for demographic in questionnaire.linked_demographics]

    return render_template("create_study/questionnaire.html", title='Questionnaire', study=study, model=model,
                           questiongroups=questiongroups, questionnaire=questionnaire,
                           questiongroups_questions=questiongroups_questions, demographics=demographics)


@bp.route('/questionnaire/edit_scale/<study_code>', methods=['GET', 'POST'])
@login_required
def edit_scale(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    # De Form voor het aanpassen van het onderzoek.
    form = EditScaleForm(questionnaire.scale)

    if form.validate_on_submit():
        # De gegevens van de studie worden aangepast naar de ingegeven data binnen de Form.
        questionnaire.scale = form.scale_questionnaire.data
        db.session.commit()
        flash('Your changes have been saved.')
        return redirect(url_for('create_study.questionnaire', study_code=study.code))
    elif request.method == 'GET':
        form.scale_questionnaire.data = questionnaire.scale

    return render_template('create_study/edit_scale.html', title='Edit scale', form=form, study=study)


@bp.route('/questionnaire/new_demographic/<study_code>', methods=['GET', 'POST'])
@login_required
def new_demographic(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    demographics = [demographic for demographic in Demographic.query.filter_by(user_id=current_user.id)]
    amount_of_demographics = len(demographics)

    return render_template("create_study/new_demographic.html", title="New Demographic", study=study, model=model,
                           demographics=demographics, amount_of_demographics=amount_of_demographics)


@bp.route('/add_demographic/<study_code>/<demographic_id>', methods=['GET', 'POST'])
@login_required
def add_demographic(study_code, demographic_id):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    demographic = Demographic.query.filter_by(id=demographic_id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    demographic.link(questionnaire)
    db.session.commit()

    return redirect(url_for('create_study.questionnaire', study_code=study_code))


@bp.route('/questionnaire/create_new_demographic/<study_code>', methods=['GET', 'POST'])
@login_required
def create_new_demographic(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    # De Form voor het aanmaken van een nieuwe demografiek.
    form = CreateNewDemographicForm()

    # Als de gebruiker aangeeft een nieuwe demografiek aan te maken met de gegeven gegevens.
    if form.validate_on_submit():
        new_demographic = Demographic(name=form.name_of_demographic.data,
                                      description=form.description_of_demographic.data,
                                      optional=form.optionality_of_demographic.data,
                                      questiontype=form.type_of_demographic.data,
                                      user_id=current_user.id)
        db.session.add(new_demographic)
        new_demographic.link(questionnaire)
        db.session.commit()

        for demographic_option in form.choices_of_demographic.data.split(','):
            new_demographic_option = DemographicOption(name=demographic_option, demographic_id=new_demographic.id)
            db.session.add(new_demographic_option)
            db.session.commit()

        return redirect(url_for("create_study.questionnaire", study_code=study_code))

    return render_template("create_study/create_new_demographic.html", title="New Demographic", form=form)


@bp.route('/remove_demographic/<study_code>/<demographic_id>', methods=['GET', 'POST'])
@login_required
def remove_demographic(study_code, demographic_id):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    demographic = Demographic.query.filter_by(id=demographic_id).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    demographic.unlink(questionnaire)
    db.session.commit()

    return redirect(url_for('create_study.questionnaire', study_code=study_code))


@bp.route('/questionnaire/new_question/<study_code>/<corevariable_id>', methods=['GET', 'POST'])
@login_required
def new_question(study_code, corevariable_id):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    corevariable = CoreVariable.query.filter_by(id=corevariable_id).first()
    corevariables = [corevariable for corevariable in model.linked_corevariables]
    questiongroups = [questiongroup for questiongroup in
                      QuestionGroup.query.filter_by(questionnaire_id=questionnaire.id)]

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    return render_template("create_study/new_question.html", title="New question", study=study,
                           corevariable=corevariable, questiongroups=questiongroups, corevariable_id=corevariable_id,
                           corevariables=corevariables)


@bp.route('/add_question/<study_code>/<corevariable_id>/<question_id>', methods=['GET', 'POST'])
@login_required
def add_question(study_code, corevariable_id, question_id):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    question = Question.query.filter_by(id=question_id).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    questiongroup = QuestionGroup.query.filter_by(questionnaire_id=questionnaire.id,
                                                  corevariable_id=corevariable_id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    # De bijbehorende kernvariabele verkrijgen voor het bepalen van de afkorting van de correcte variabele.
    corevariable = CoreVariable.query.filter_by(id=corevariable_id).first()
    abbreviation_corevariable = corevariable.abbreviation

    # De code voor de vraag (de kernvariabele plus een cijfer, zoals "PE3")
    new_code = abbreviation_corevariable + str(len([question for question in
                                                    Question.query.filter_by(
                                                        questiongroup_id=questiongroup.id)]) + 1)

    if Question.query.filter_by(question=question.question, questiongroup_id=questiongroup.id).first():
        flash("This question already exists within the core variable.")
        return redirect(url_for('create_study.questionnaire', study_code=study_code))

    # Het aanmaken van een nieuwe vraag in de database.
    new_question = Question(question=question.question,
                            questiongroup_id=questiongroup.id,
                            question_code=new_code)
    db.session.add(new_question)
    db.session.commit()

    return redirect(url_for('create_study.questionnaire', study_code=study_code))


@bp.route('/questionnaire/create_new_question/<study_code>/<corevariable_id>', methods=['GET', 'POST'])
@login_required
def create_new_question(study_code, corevariable_id):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    corevariable = CoreVariable.query.filter_by(id=corevariable_id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    # De Form voor het aanmaken van een nieuwe vraag.
    form = CreateNewQuestionForm()

    # Als de gebruiker aangeeft een nieuwe vraag aan te maken met de gegeven gegevens.
    if form.validate_on_submit():
        questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
        questiongroup = QuestionGroup.query.filter_by(questionnaire_id=questionnaire.id,
                                                      corevariable_id=corevariable_id).first()

        if Question.query.filter_by(question=form.name_question.data, questiongroup_id=questiongroup.id).first():
            flash("This question already exists within the core variable.")
            return redirect(url_for('create_study.questionnaire', study_code=study_code))

        # De bijbehorende kernvariabele verkrijgen voor het bepalen van de afkorting van de correcte variabele.
        corevariable = CoreVariable.query.filter_by(id=corevariable_id).first()
        abbreviation_corevariable = corevariable.abbreviation

        # De code voor de vraag (de kernvariabele plus een cijfer, zoals "PE3")
        new_code = abbreviation_corevariable + str(len([question for question in
                                                        Question.query.filter_by(
                                                            questiongroup_id=questiongroup.id)]) + 1)

        # Het aanmaken van een nieuwe vraag in de database.
        new_question = Question(question=form.name_question.data,
                                questiongroup_id=questiongroup.id,
                                question_code=new_code,
                                user_id=current_user.id,
                                corevariable_id=corevariable.id)
        db.session.add(new_question)
        db.session.commit()

        return redirect(url_for("create_study.questionnaire", study_code=study_code))

    return render_template("create_study/create_new_question.html", title="Create new question", form=form,
                           corevariable=corevariable)


@bp.route('/questionnaire/edit_question/<study_code>/<question_id>', methods=['GET', 'POST'])
@login_required
def edit_question(study_code, question_id):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    question = Question.query.filter_by(id=question_id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    # De Form voor het aanpassen van het onderzoek.
    form = EditQuestionForm(question.question)

    # Als de gebruiker aangeeft de onderzoek te willen aanpassen met de gegeven gegevens.
    if form.validate_on_submit():
        # De gegevens van de studie worden aangepast naar de ingegeven data binnen de Form.
        question.question = form.name_question.data
        db.session.commit()
        flash('Your changes have been saved.')
        return redirect(url_for('create_study.questionnaire', study_code=study.code))
    # Als niks is ingegeven binnen de Form worden geen aanpassingen gemaakt (en dus gebruikgemaakt van de eigen
    # onderzoeksgegevens.
    elif request.method == 'GET':
        form.name_question.data = question.question
    return render_template('create_study/edit_question.html', title='Edit Profile',
                           form=form, study=study)


@bp.route('/remove_question/<study_code>/<question_id>', methods=['GET', 'POST'])
@login_required
def remove_question(study_code, question_id):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    # Het verwijderen van de vraag uit de database.
    Question.query.filter_by(id=question_id).delete()
    db.session.commit()

    return redirect(url_for('create_study.questionnaire', study_code=study_code))


@bp.route('/questionnaire/switch_reversed_score/<study_code>/<question_id>', methods=['GET', 'POST'])
@login_required
def switch_reversed_score(study_code, question_id):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage1(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    # De reversed_score aan- of uitzetten voor de vraag afhankelijk wat de huidige stand is.
    question = Question.query.filter_by(id=question_id).first()
    if question.reversed_score:
        question.reversed_score = False
        db.session.commit()
    else:
        question.reversed_score = True
        db.session.commit()
    return redirect(url_for('create_study.questionnaire', study_code=study_code))


#############################################################################################################
#                                          Start onderzoek
#############################################################################################################

@bp.route('/starting_study/<study_code>', methods=['GET', 'POST'])
@login_required
def starting_study(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    study = Study.query.filter_by(code=study_code).first()
    if current_user not in study.linked_users:
        return redirect(url_for('main.not_authorized'))

    # Checken hoe ver de studie is
    if study.stage_2:
        return redirect(url_for('create_study.study_underway', name_study=study.name, study_code=study_code))
    if study.stage_3:
        return redirect(url_for('create_study.summary_results', study_code=study_code))

    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    questiongroups = [questiongroup for questiongroup in questionnaire.linked_questiongroups]
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()

    # Checken of het onderzoeksmodel goed is ingevuld, anders vereisen dat het model aangepast dient te worden.
    researchmodel_check = check_researchmodel(study, model)
    if researchmodel_check is not None:
        return researchmodel_check

    # Bepalen of alle vragenlijstgroepen tenminste één vraag hebben en er een schaal is gegeven voor de vragenlijst.
    # Zo niet, de Flash geven en terugkeren.
    amount_of_questiongroups = len(questiongroups)
    for questiongroup in questiongroups:
        amount_of_questions = Question.query.filter_by(questiongroup_id=questiongroup.id).count()
        if amount_of_questions < 3 or amount_of_questions > 5:
            flash('The amount of questions for all core variables must be between 3 and 5. Make sure this is the case'
                  'for each core variable.')
            return redirect(url_for('create_study.questionnaire', study_code=study.code))

    if questionnaire.scale is None or 4 > questionnaire.scale or questionnaire.scale > 10:
        flash('A correct scale has not been given yet for the questionnaire. Please select a scale between 4 and 10.')
        return redirect(url_for('create_study.questionnaire', study_code=study.code))

    # Omzetting studie van stage_1 (opstellen van het onderzoek) naar stage_2 (het onderzoek is gaande)
    study.stage_1 = False
    study.stage_2 = True
    db.session.commit()

    return redirect(url_for('create_study.study_underway', name_study=study.name, study_code=study_code))


@bp.route('/study_underway/<name_study>/<study_code>', methods=['GET', 'POST'])
@login_required
def study_underway(name_study, study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage2(study_code)
    if security_check is not None:
        return security_check

    # De link naar de vragenlijst
    study = Study.query.filter_by(code=study_code).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    link = '127.0.0.1:5000/intro_questionnaire/e/{}'.format(study.code)

    return render_template('create_study/study_underway.html', title="Underway: {}".format(name_study), study=study,
                           link=link, questionnaire=questionnaire)


@bp.route('/end_study/<study_code>', methods=['GET', 'POST'])
@login_required
def end_study(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage2(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    # Omzetting studie van stage_2 (het onderzoek is gaande) naar stage_3 (de data-analyse)
    study.stage_2 = False
    study.stage_3 = True
    db.session.commit()

    return redirect(url_for('create_study.summary_results', study_code=study_code))


#############################################################################################################
#                                     Data Analyse en visualisatie
#############################################################################################################

@bp.route('/summary_results/<study_code>', methods=['GET', 'POST'])
@login_required
def summary_results(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage3(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    demographics = [demographic for demographic in questionnaire.linked_demographics]
    questions = [question for question in questionnaire.linked_questions()]
    cases = [case for case in questionnaire.linked_cases()]

    return render_template('create_study/summary_results.html', study_code=study_code, demographics=demographics,
                           questions=questions, cases=cases, study=study)


@bp.route('/data_analysis/<study_code>', methods=['GET', 'POST'])
@login_required
def data_analysis(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    security_check = security_and_studycheck_stage3(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    corevariables = [corevariable for corevariable in model.linked_corevariables]

    # Het opzetten van de dataframe (gebruik van plspm package en pd.dataframe met de vragenlijstresultaten)
    questiongroups = [questiongroup for questiongroup in questionnaire.linked_questiongroups]
    questionlist_and_answerlist = return_questionlist_and_answerlist(questiongroups)
    list_of_questions = questionlist_and_answerlist[0]
    list_of_answers = questionlist_and_answerlist[1]

    df = pd.DataFrame(list_of_answers).transpose()
    df.columns = list_of_questions

    structure = setup_structure_dataframe(corevariables, model.id)

    config = c.Config(structure.path(), scaled=False)
    scheme = Scheme.CENTROID

    for corevariable in corevariables:
        config.add_lv_with_columns_named(corevariable.abbreviation, Mode.A, df, corevariable.abbreviation)

    plspm_calc = Plspm(df, config, scheme)
    plspm_model = plspm_calc.outer_model()

    # Creëert dictionary met alleen loadings van latente variabele
    loadings_dct = pd.DataFrame(plspm_model['loading']).to_dict('dict')['loading']

    # Een matrix van Heterotrait-Monotrait Ratio wordt hier beschikbaar gemaakt (module "htmt_matrix" staat bovenaan
    # verwezen.
    data_htmt = htmt_matrix(df, model)
    amount_of_variables = len(corevariables)

    # Buitenste VIF-waarden worden hier beschikbaar gemaakt in een dictionary onder "data_outer_vif". Module bovenaan
    # geïmporteerd.
    outer_vif_dct = outer_vif_values_dict(df, questionnaire)

    model.edited = False
    db.session.commit()

    return render_template('create_study/data_analysis.html', study_code=study_code, df=df, config=config, scheme=scheme,
                           outer_vif_dct=outer_vif_dct, questiongroups=questiongroups, model=model, corevariables=corevariables,
                           data_htmt=data_htmt, amount_of_variables=amount_of_variables, study=study,
                           loadings_dct=loadings_dct)


@bp.route('/data_analysis/corevariable_analysis/<study_code>/<questiongroup_id>', methods=['GET', 'POST'])
@login_required
def corevariable_analysis(study_code, questiongroup_id):
    security_check = security_and_studycheck_stage3(study_code)
    if security_check is not None:
        return security_check

    study = Study.query.filter_by(code=study_code).first()
    questionnaire = Questionnaire.query.filter_by(study_id=study.id).first()
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    corevariables = [corevariable for corevariable in model.linked_corevariables]
    questiongroups = [questiongroup for questiongroup in questionnaire.linked_questiongroups]
    relevant_questiongroup = QuestionGroup.query.filter_by(id=questiongroup_id).first()

    # De items/vragen (de code specifiek gezegd) die horen bij de kernvariabele
    questions_of_questiongroup = [question for question in relevant_questiongroup.linked_questions()]
    length_questionlist = len(questions_of_questiongroup)

    # Het opzetten van de dataframe (gebruik van plspm package en pd.dataframe met de vragenlijstresultaten)
    questionlist_and_answerlist = return_questionlist_and_answerlist(questiongroups)
    list_of_questions = questionlist_and_answerlist[0]
    list_of_answers = questionlist_and_answerlist[1]

    df = pd.DataFrame(list_of_answers).transpose()
    df.columns = list_of_questions

    # Functie "setup_structure_dataframe" terug te vinden in "new_study/functions".
    structure = setup_structure_dataframe(corevariables, model.id)

    config = c.Config(structure.path(), scaled=False)
    scheme = Scheme.CENTROID

    for corevariable in corevariables:
        config.add_lv_with_columns_named(corevariable.abbreviation, Mode.A, df, corevariable.abbreviation)

    plspm_calc = Plspm(df, config, Scheme.CENTROID)
    model1 = plspm_calc.outer_model()

    # De AVE, Cronbach's Alpha, Composite Reliability voor de fullscreen grafieken (met alle kernvariabelen erin).
    corevariable_js_all = [corevariable for corevariable in model.linked_corevariables]
    corevariable_ave_js_all = [questiongroup.return_ave(model, df, config, scheme) for questiongroup in questiongroups]
    corevariable_ca_js_all = [questiongroup.return_cronbachs_alpha(model, df) for questiongroup in questiongroups]
    corevariable_cr_js_all = [questiongroup.return_composite_reliability(model, df, config, scheme)
                              for questiongroup in questiongroups]

    # De AVE, Cronbach's Alpha, Composite Reliability, ladingen, VIF-waarden en HTMT-ratios voor de kleinere grafieken
    # (voor AVE, CA, CR en HTMT worden de twee/drie dichtstbijzijnde kernvariabelen gebruikt).

    # De indexes van de eerste dichtstbijzijnde kernvariabele, de specifieke kernvariabele en de tweede dichtstbijzijnde
    # kernvariabele respectievelijk.
    indexes_questiongroups = indexes_questiongroups_three(questiongroups, questiongroup_id)

    # Namen van de eerste dichtstbijzijnde kernvariabele, de specifieke kernvariabele en de tweede dichtstbijzijnde
    # kernvariabele respectievelijk.
    corevariable_names_js = [corevariable for corevariable in
                             [corevariables[indexes_questiongroups[0]], corevariables[indexes_questiongroups[1]],
                              corevariables[indexes_questiongroups[2]]]]
    # AVE-lijst
    corevariable_ave_js = [questiongroup.return_ave(model, df, config, scheme) for
                           questiongroup in questiongroups[indexes_questiongroups[0]:indexes_questiongroups[2] + 1]]
    # Cronbach's Alpha lijst
    corevariable_ca_js = [questiongroup.return_cronbachs_alpha(model, df) for
                          questiongroup in questiongroups[indexes_questiongroups[0]:indexes_questiongroups[2] + 1]]
    # Composite Reliability lijst
    corevariable_cr_js = [questiongroup.return_composite_reliability(model, df, config, scheme) for
                          questiongroup in questiongroups[indexes_questiongroups[0]:indexes_questiongroups[2] + 1]]

    length_corevariables = len(corevariable_js_all)

    # VIF-waarden
    dct_of_all_vifs = outer_vif_values_dict(df, questionnaire)
    corevariable_abbreviation = relevant_questiongroup.return_corevariable_abbreviation()
    corevariable_vif_js = [dct_of_all_vifs[key] for key in dct_of_all_vifs if key[:len(corevariable_abbreviation)] ==
                           corevariable_abbreviation]

    # HTMT-waarden
    corevariable = CoreVariable.query.filter_by(id=relevant_questiongroup.corevariable_id).first()
    corevariables_htmt = corevariables
    corevariables_htmt.remove(corevariable)
    length_corevariables_htmt = len(corevariables_htmt)
    corevariable_names_htmt_js = corevariables_htmt[:3]
    corevariable_htmt_js = [round(heterotrait_monotrait(corevariable, lv, correlation_matrix(df), df), 4)
                            for lv in corevariables_htmt[:3]]
    corevariable_htmt_js_all = [round(heterotrait_monotrait(corevariable, lv, correlation_matrix(df), df), 4)
                                for lv in corevariables_htmt]

    # Ladingen van de items
    loadings_dct = pd.DataFrame(model1['loading']).to_dict('dict')['loading']
    loadings_list = [question.return_loading(loadings_dct) for question in questions_of_questiongroup]

    return render_template('create_study/corevariable_analysis.html', study_code=study_code, corevariable=corevariable,
                           corevariables=corevariables, corevariable_names_js=corevariable_names_js,
                           corevariable_ave_js=corevariable_ave_js, corevariable_ca_js=corevariable_ca_js,
                           corevariable_cr_js=corevariable_cr_js, corevariable_js_all=corevariable_js_all,
                           corevariable_ave_js_all=corevariable_ave_js_all, questions_of_questiongroup=questions_of_questiongroup, length_questionlist=length_questionlist,
                           corevariable_ca_js_all=corevariable_ca_js_all, corevariable_vif_js=corevariable_vif_js,
                           corevariable_cr_js_all=corevariable_cr_js_all, length_corevariables=length_corevariables,
                           loadings_list=loadings_list, corevariables_htmt=corevariables_htmt,
                           corevariable_htmt_js=corevariable_htmt_js, corevariable_names_htmt_js=corevariable_names_htmt_js,
                           length_corevariables_htmt=length_corevariables_htmt, corevariable_htmt_js_all=corevariable_htmt_js_all)
