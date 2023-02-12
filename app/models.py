from hashlib import md5
import uuid
from datetime import datetime
from hashlib import md5
from time import time
import jwt
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import StringField, SelectField, RadioField, SelectMultipleField
from wtforms.validators import DataRequired
from app import db, login
import numpy as np

import plspm.config as c
from plspm.plspm import Plspm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tools.tools import add_constant
import math
import pandas as pd


study_user = db.Table('study_user',
                      db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
                      db.Column('study_id', db.Integer, db.ForeignKey('study.id'))
                      )


researchmodel_corevariable = db.Table('researchmodel_corevariable',
                                      db.Column('researchmodel_id', db.Integer, db.ForeignKey('research_model.id')),
                                      db.Column('corevariable_id', db.Integer, db.ForeignKey('core_variable.id'))
                                      )


questionnaire_demographic = db.Table('questionnaire_demographic',
                                     db.Column('questionnaire_id', db.Integer, db.ForeignKey('questionnaire.id')),
                                     db.Column('demographic_id', db.Integer, db.ForeignKey('demographic.id'))
                                     )


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True)
    email = db.Column(db.String(90), unique=True)
    password_hash = db.Column(db.String(128))
    about_me = db.Column(db.String(250))

    linked_studies = db.relationship('Study', secondary=study_user, backref=db.backref('researchers'), lazy='dynamic')

    def __repr__(self):
        return '<User {}>'.format(self.username)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def link(self, study):
        if not self.is_linked(study):
            self.linked_studies.append(study)

    def unlink(self, study):
        if self.is_linked(study):
            self.linked_studies.remove(study)

    def is_linked(self, study):
        return self.linked_studies.filter(
            study_user.c.study_id == study.id).count() > 0

    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            current_app.config['SECRET_KEY'], algorithm='HS256')

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_password']
        except:
            return
        return User.query.get(id)

@login.user_loader
def load_user(id):
    return User.query.get(int(id))


class Study(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    description = db.Column(db.String(5000))
    technology = db.Column(db.String(100))
    code = db.Column(db.String(60), unique=True)
    stage_1 = db.Column(db.Boolean, default=True)
    stage_2 = db.Column(db.Boolean, default=False)
    stage_3 = db.Column(db.Boolean, default=False)
    stage_completed = db.Column(db.Boolean, default=False)
    used_existing_model = db.Column(db.Boolean, default=False)

    researchmodel_id = db.Column(db.Integer, db.ForeignKey('research_model.id'))
    linked_users = db.relationship('User', secondary=study_user, backref=db.backref('researchers'), lazy='dynamic')

    def __repr__(self):
        return '<Study {}>'.format(self.name_study)

    def change_model(self, new_model_id):
        self.model_id = new_model_id

    def create_code(self):
        self.code = str(uuid.uuid4())

    def total_completed_cases_questionnaire(self):
        questionnaire = Questionnaire.query.filter_by(study_id=self.id).first()
        return questionnaire.total_completed_cases()


class ResearchModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    edited = db.Column(db.Boolean, default=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    linked_corevariables = db.relationship('CoreVariable', secondary=researchmodel_corevariable,
                                           backref=db.backref('corevariables'), lazy='dynamic')

    def linked_relations(self):
        relations = []
        for relation in Relation.query.filter_by(model_id=self.id):
            influencer = CoreVariable.query.filter_by(id=relation.influencer_id).first()
            influenced = CoreVariable.query.filter_by(id=relation.influenced_id).first()
            relations.append('{} to {}'.format(influencer.name, influenced.name))
        return relations


class CoreVariable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    abbreviation = db.Column(db.String(4))
    description = db.Column(db.String(800))

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def __repr__(self):
        return '<Core variable {}>'.format(self.name)

    def return_creator(self):
        user = User.query.filter_by(id=self.user_id).first()
        return user

    def link(self, model):
        if not self.is_linked(model):
            model.linked_corevariables.append(self)

    def unlink(self, model):
        if self.is_linked(model):
            model.linked_corevariables.remove(self)

    def is_linked(self, model):
        return model.linked_corevariables.filter(
            researchmodel_corevariable.c.corevariable_id == self.id).count() > 0

    def linked_questions(self):
        questions = [question for question in Question.query.filter_by(corevariable_id=self.id)]
        return questions

    def linked_relations_from(self, model):
        relations_from = [relation for relation in Relation.query.filter_by(model_id=model.id, influencer_id=self.id)]
        return relations_from

    def linked_relations_to(self, model):
        relations_to = [relation for relation in Relation.query.filter_by(model_id=model.id, influenced_id=self.id)]
        return relations_to


class Relation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    model_id = db.Column(db.Integer, db.ForeignKey('research_model.id'))
    influencer_id = db.Column(db.Integer, db.ForeignKey('core_variable.id'))
    influenced_id = db.Column(db.Integer, db.ForeignKey('core_variable.id'))

    def return_relation(self):
        return '{} ----> {}'.format(
            CoreVariable.query.get(self.influencer_id).name,
            CoreVariable.query.get(self.influenced_id).name)


class Questionnaire(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True)
    scale = db.Column(db.Integer)

    study_id = db.Column(db.Integer, db.ForeignKey('study.id'))
    linked_demographics = db.relationship('Demographic', secondary=questionnaire_demographic,
                                           backref=db.backref('demographics'), lazy='dynamic')
    linked_questiongroups = db.relationship('QuestionGroup', backref='questionnaire_questiongroup',
                                            lazy='dynamic')

    def __repr__(self):
        return '<Questionnaire {}>'.format(self.code)

    def total_completed_cases(self):
        total = Case.query.filter_by(questionnaire_id=self.id, completed=True).count()
        return str(total)

    def linked_cases(self):
        cases = [case for case in Case.query.filter_by(questionnaire_id=self.id, completed=True)]
        return cases

    def linked_questions(self):
        questions = []
        for questiongroup in self.linked_questiongroups:
            for question in questiongroup.linked_questions():
                questions.append(question)
        return questions


class QuestionGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    questionnaire_id = db.Column(db.Integer, db.ForeignKey('questionnaire.id'))
    corevariable_id = db.Column(db.Integer, db.ForeignKey('core_variable.id'))

    def __repr__(self):
        return '<Question group {}>'.format(self.return_corevariable_name)

    def return_corevariable(self):
        corevariable = CoreVariable.query.filter_by(id=self.corevariable_id).first()
        return corevariable

    def return_corevariable_name(self):
        corevariable_name = CoreVariable.query.filter_by(id=self.corevariable_id).first().name
        return corevariable_name

    def return_corevariable_abbreviation(self):
        corevariable_abbreviation = CoreVariable.query.filter_by(id=self.corevariable_id).first().abbreviation
        return corevariable_abbreviation

    def linked_questions(self):
        questions = [question for question in Question.query.filter_by(questiongroup_id=self.id)]
        return questions

    def return_amount_of_questions(self):
        questions = self.linked_questions()
        return len(questions)

    # Berekeningen

    def generate_ave(self, dataset, configuration, scheme):
        corevariable = CoreVariable.query.filter_by(id=self.corevariable_id).first()

        abbreviation = corevariable.abbreviation
        plspm_calc = Plspm(dataset, configuration, scheme)
        model = plspm_calc.outer_model()

        # Dictionary met alleen loadings van latente variabele (loadings_dct)
        loadings_dct = pd.DataFrame(model['loading']).to_dict('dict')['loading']
        not_questions = [question for question in loadings_dct if question[:len(abbreviation)] == abbreviation]
        loadings_dct = {key: loadings_dct[key] for key in loadings_dct if key in not_questions}

        # Lijst met ladingen (loadings), lijst met gekwadrateerde ladingen (loadings_squared) en de populatie (oftewel
        # hoeveel ladingen/items er zijn.
        loadings = [loadings_dct[i] for i in loadings_dct]
        loadings_squared = [score * score for score in loadings]
        population = len(loadings)

        return sum(loadings_squared) / population

    def return_ave(self, model, dataset, configuration, scheme):
        if not model.edited:
            ave = AverageVarianceExtracted.query.filter_by(questiongroup_id=self.id).first()
            if not ave:
                ave = AverageVarianceExtracted(value=self.generate_ave(dataset, configuration, scheme),
                                               questiongroup_id=self.id)
                db.session.add(ave)
                db.session.commit()
            return round(ave.value, 4)
        else:
            ave = AverageVarianceExtracted(value=self.generate_ave(dataset, configuration, scheme),
                                           questiongroup_id=self.id)
            db.session.add(ave)
            db.session.commit()

            return round(ave.value, 4)

    def variance(self, items, dataset):
        # Als er één item is gegeven binnen de lijst (de variantie van één item wordt berekend).
        if len(items) == 1:
            # De item wordt gereturned met "item"
            item = items[0]
            scores = [score for score in dataset[item]]
            average = sum(scores) / len(scores)
            # Een lijst met de gekwadrateerde verschillen tussen de scores en de gemiddelde van de scores
            differences_squared = [(score - average) * (score - average) for score in scores]

            return sum(differences_squared) / (len(scores))

        # Als er meerdere items gegeven zijn.
        else:
            scores_per_case = {}
            scores = len([score for score in dataset[items[0]]])
            for question in items:
                for row in range(scores):
                    if row in scores_per_case:
                        scores_per_case[row].append(dataset[question][row])
                    else:
                        scores_per_case[row] = []
                        scores_per_case[row].append(dataset[question][row])

            list_of_totals = [sum(scores_per_case[case]) for case in scores_per_case]

            average = sum(list_of_totals) / len(list_of_totals)
            differences_squared = [(score - average) * (score - average) for score in list_of_totals]

            return sum(differences_squared) / (len(list_of_totals))

    def generate_cronbachs_alpha(self, dataset):
        corevariable = CoreVariable.query.filter_by(id=self.corevariable_id).first()

        abbreviation = corevariable.abbreviation
        # Alle vragen binnen de kernvariabele.
        questions = [i for i in [question for question in dataset if question[:len(abbreviation)] == abbreviation]]
        total_items = len(questions)
        # De variantie van de "totaal"kolom, oftewel per case de scores opgeteld.
        variance_total_column = self.variance(questions, dataset)
        # Een lijst met de varianties voor iedere item
        variance_questions = [self.variance([question], dataset) for question in questions]

        return (total_items / (total_items - 1)) * (
                (variance_total_column - sum(variance_questions)) / variance_total_column)

    def return_cronbachs_alpha(self, model, dataset):
        if not model.edited:
            ca = CronbachsAlpha.query.filter_by(questiongroup_id=self.id).first()
            if not ca:
                ca = CronbachsAlpha(value=self.generate_cronbachs_alpha(dataset), questiongroup_id=self.id)
                db.session.add(ca)
                db.session.commit()
            return round(ca.value, 4)
        else:
            ca = CronbachsAlpha(value=self.generate_cronbachs_alpha(dataset), questiongroup_id=self.id)
            db.session.add(ca)
            db.session.commit()

            return round(ca.value, 4)

    def generate_composite_reliability(self, dataset, configuration, scheme):
        corevariable = CoreVariable.query.filter_by(id=self.corevariable_id).first()

        abbreviation = corevariable.abbreviation
        plspm_calc = Plspm(dataset, configuration, scheme)
        model = plspm_calc.outer_model()

        # Dictionary met alleen loadings van kernvariabele (loadings_dct)
        loadings_dct = pd.DataFrame(model['loading']).to_dict('dict')['loading']
        questions = [question for question in loadings_dct if question[:len(abbreviation)] == abbreviation]
        loadings_dct = {key: loadings_dct[key] for key in loadings_dct if key in questions}

        # Lijst met de ladingen (loadings), lijst met de gekwadrateerde ladingen (loadings_squared) en lijst met de
        # errors (errors).
        loadings = [loadings_dct[i] for i in loadings_dct]
        loadings_squared = [score * score for score in loadings]
        errors = [1 - score for score in loadings_squared]

        return (sum(loadings) * sum(loadings)) / ((sum(loadings) * sum(loadings)) + sum(errors))

    def return_composite_reliability(self, model, dataset, configuration, scheme):
        if not model.edited:
            cr = CompositeReliability.query.filter_by(questiongroup_id=self.id).first()
            if not cr:
                cr = CompositeReliability(value=self.generate_composite_reliability(dataset, configuration, scheme),
                                          questiongroup_id=self.id)
                db.session.add(cr)
                db.session.commit()
            return round(cr.value, 4)
        else:
            cr = CompositeReliability(value=self.generate_composite_reliability(dataset, configuration, scheme),
                                      questiongroup_id=self.id)
            db.session.add(cr)
            db.session.commit()

            return round(cr.value, 4)


class QuestionType(db.Model):
    name = db.Column(db.String(64), primary_key=True)

    def __repr__(self):
        return '<Question type {}>'.format(self.name)


class Demographic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    description = db.Column(db.String(300))
    optional = db.Column(db.Boolean, default=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    questiontype = db.Column(db.String(64), db.ForeignKey('question_type.name'))
    linked_questionnaires = db.relationship('Questionnaire', secondary=questionnaire_demographic,
                                          backref=db.backref('questionnaires'), lazy='dynamic')

    def __repr__(self):
        return '<Demographic {}>'.format(self.name)

    def return_creator(self):
        user = User.query.filter_by(id=self.user_id).first()
        return user

    def return_list_of_options(self):
        options = [option.name for option in DemographicOption.query.filter_by(demographic_id=self.id)]
        return options

    def return_field(self):
        if self.questiontype == "open":
            if self.optional:
                return StringField(self.name)
            required_name = self.name + '*'
            return StringField(required_name, validators=[DataRequired()])
        elif self.questiontype == "multiplechoice":
            if self.optional:
                choices = self.return_list_of_options()
                return SelectMultipleField(u'{}'.format(self.name), choices=choices)
            required_name = self.name + '*'
            return SelectMultipleField(u'{}'.format(required_name), choices=self.return_list_of_options())
        elif self.questiontype == "radio":
            if self.optional:
                choices = self.return_list_of_options()
                return RadioField(u'{}'.format(self.name), choices=choices)
            required_name = self.name + '*'
            return RadioField(u'{}'.format(required_name), choices=self.return_list_of_options())

    def return_amount_of_options(self):
        return len(self.return_list_of_options())

    def link(self, questionnaire):
        if not self.is_linked(questionnaire):
            questionnaire.linked_demographics.append(self)

    def unlink(self, questionnaire):
        if self.is_linked(questionnaire):
            questionnaire.linked_demographics.remove(self)

    def is_linked(self, questionnaire):
        return questionnaire.linked_demographics.filter(
            questionnaire_demographic.c.demographic_id == self.id).count() > 0


class DemographicOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(250))

    demographic_id = db.Column(db.Integer, db.ForeignKey('demographic.id'))

    def __repr__(self):
        return '<Option {}>'.format(self.name)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(120))
    reversed_score = db.Column(db.Boolean, default=False)
    question_code = db.Column(db.String(10))

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    questiongroup_id = db.Column(db.Integer, db.ForeignKey('question_group.id'))
    corevariable_id = db.Column(db.Integer, db.ForeignKey('core_variable.id'))

    def __repr__(self):
        return '<Question {}>'.format(self.question)

    def return_creator(self):
        user = User.query.filter_by(id=self.user_id).first()
        return user

    def return_original_corevariable(self):
        questiongroup = QuestionGroup.query.filter_by(id=self.questiongroup_id).first()
        return questiongroup.return_corevariable()

    def return_average_question_answers(self):
        answers = [answer.score for answer in QuestionAnswer.query.filter_by(question_id=self.id)]
        return round(np.average(answers), 2)

    def return_standarddeviation_question_answers(self):
        answers = [answer.score for answer in QuestionAnswer.query.filter_by(question_id=self.id)]
        return round(np.std(answers), 2)

    def return_loading(self, loadings_dct):
        loading = loadings_dct[self.question_code]
        return round(loading, 4)

    def return_vif(self, outer_vif_dct):
        vif = outer_vif_dct[self.question_code]
        return round(vif, 4)


class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session = db.Column(db.String(100), unique=True)
    start_time = db.Column(db.DateTime, default=datetime.utcnow())
    completed = db.Column(db.Boolean, default=False)

    questionnaire_id = db.Column(db.Integer, db.ForeignKey('questionnaire.id'))

    def linked_demographic_answers(self):
        answers = [answer for answer in DemographicAnswer.query.filter_by(case_id=self.id)]
        return answers

    def linked_question_answers(self):
        answers = [answer for answer in QuestionAnswer.query.filter_by(case_id=self.id)]
        return answers


class QuestionAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    score = db.Column(db.SmallInteger)

    question_id = db.Column(db.Integer, db.ForeignKey('question.id'))
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'))


class DemographicAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    answer = db.Column(db.String(200))

    case_id = db.Column(db.Integer, db.ForeignKey('case.id'))
    demographic_id = db.Column(db.Integer, db.ForeignKey('demographic.id'))


# Berekeningen

class AverageVarianceExtracted(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Float)

    questiongroup_id = db.Column(db.Integer, db.ForeignKey('question_group.id'))


class CronbachsAlpha(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Float)

    questiongroup_id = db.Column(db.Integer, db.ForeignKey('question_group.id'))


class CompositeReliability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Float)

    questiongroup_id = db.Column(db.Integer, db.ForeignKey('question_group.id'))
