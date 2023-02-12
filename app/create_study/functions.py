from app.models import  Study, ResearchModel, Questionnaire, QuestionGroup, CoreVariable, Relation, Question, QuestionAnswer
from app import db
import plspm.config as c
from plspm.plspm import Plspm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tools.tools import add_constant
import math
import pandas as pd
import numpy as np
from flask import render_template, flash, redirect, url_for, request
from flask_login import current_user, login_required


def check_if_used_model(study):
    study = Study.query.filter_by(id=study.id).first()
    if study.used_existing_model:
        flash('You have used a pre-existing model for this study. You cannot change the model.')
        return redirect(url_for('create_study.questionnaire', study_code=study.code))


def check_researchmodel(study, model):
    corevariables = [corevariable for corevariable in model.linked_corevariables]
    if len(corevariables) < 4:
        flash('The research model needs four or more corevariables. Please add more core variables to your model.')
        return redirect(url_for('create_study.edit_model', study_code=study.code))

    for corevariable in corevariables:
        amount_of_relations = len([relation for relation in corevariable.linked_relations_from(model)] +
                                  [relation for relation in corevariable.linked_relations_to(model)])
        if amount_of_relations == 0:
            flash('The research model contains core variables which are not linked to any other core variables yet.'
                  'Make sure at least one relation is created for each core variable.')
            return redirect(url_for('create_study.edit_model', study_code=study.code))


def setup_questiongroups(study):
    model = ResearchModel.query.filter_by(id=study.researchmodel_id).first()
    if Questionnaire.query.filter_by(study_id=study.id).first() is None:
        new_questionnaire = Questionnaire(study_id=study.id)
        db.session.add(new_questionnaire)
        db.session.commit()

        # Vragenlijstgroepen aanmaken per kernvariabele.
        for corevariable in model.linked_corevariables:
            questiongroup = QuestionGroup(questionnaire_id=new_questionnaire.id, corevariable_id=corevariable.id)
            db.session.add(questiongroup)
            db.session.commit()


def setup_structure_dataframe(list_of_corevariables, model_id):
    structure = c.Structure()
    for corevariable in list_of_corevariables:
        influenced_variables = []
        for relation in [relation for relation in Relation.query.filter_by(model_id=model_id)]:
            if relation.influencer_id == corevariable.id:
                influenced = CoreVariable.query.filter_by(id=relation.influenced_id).first()
                influenced_variables.append(influenced.abbreviation)
        if len(influenced_variables) > 0:
            structure.add_path([corevariable.abbreviation], influenced_variables)

    return structure


def return_questionlist_and_answerlist(list_of_questiongroups):
    list_of_questions = []
    list_of_answers = []

    for questiongroup in list_of_questiongroups:
        questions = [question for question in Question.query.filter_by(questiongroup_id=questiongroup.id)]
        for question in questions:
            list_of_questions.append(question.question_code)
            answers_question = []
            for answer in [answer for answer in QuestionAnswer.query.filter_by(question_id=question.id)]:
                answers_question.append(answer.score)
            list_of_answers.append(answers_question)

    return list_of_questions, list_of_answers


def indexes_questiongroups_three(list_of_questiongroups, questiongroup_id):
    length_questiongroups = len(list_of_questiongroups)
    indexes_corevariables = []
    for questiongroup in list_of_questiongroups:
        if questiongroup.id == int(questiongroup_id):
            if list_of_questiongroups.index(questiongroup) == 0:
                indexes_corevariables = [0, 1, 2]
            elif list_of_questiongroups.index(questiongroup) == length_questiongroups - 1:
                indexes_corevariables = [length_questiongroups - 3, length_questiongroups - 2, length_questiongroups - 1]
            else:
                indexes_corevariables = [list_of_questiongroups.index(questiongroup) - 1,
                                         list_of_questiongroups.index(questiongroup),
                                         list_of_questiongroups.index(questiongroup) + 1]

    return indexes_corevariables

# Berekeningen

def variance(items, dataset):
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


def cronbachs_alpha(corevariable, dataset):
    abbreviation = corevariable.abbreviation
    # Alle vragen binnen de kernvariabele.
    questions = [i for i in [question for question in dataset if question[:len(abbreviation)] == abbreviation]]
    total_items = len(questions)
    # De variantie van de "totaal"kolom, oftewel per case de scores opgeteld.
    variance_total_column = variance(questions, dataset)
    # Een lijst met de varianties voor iedere item
    variance_questions = [variance([question], dataset) for question in questions]

    return (total_items / (total_items - 1)) * (
            (variance_total_column - sum(variance_questions)) / variance_total_column)


def composite_reliability(corevariable, dataset, configuration, scheme):
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


def average_variance_extracted(corevariable, dataset, configuration, scheme):
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


def covariance(item1, item2, dataset):
    # De scores van de twee items.
    scores_item1 = []
    scores_item2 = []
    # Deze if-statement komt alleen voor als de correlationmatrix wordt uitgerekend.
    if item1 == item2:
        for item in dataset:
            if item == item1:
                for score in dataset[item]:
                    scores_item1.append(score)
                    scores_item2.append(score)
    else:
        for item in dataset:
            if item == item1:
                for score in dataset[item]:
                    scores_item1.append(score)
            elif item == item2:
                for score in dataset[item]:
                    scores_item2.append(score)

    # De gemiddelden van de items.
    avg_item1 = sum(scores_item1) / len(scores_item1)
    avg_item2 = sum(scores_item2) / len(scores_item2)

    # Een zip met sublijsten voor iedere combinatie van item1 en item2 scores (combination_of_scores).
    combination_of_scores = zip(scores_item1, scores_item2)
    combination_of_differences = [(x - avg_item1, y - avg_item2) for (x, y) in tuple(combination_of_scores)]
    differences_combined = [x * y for (x, y) in combination_of_differences]

    return sum(differences_combined) / len(differences_combined)


def pearson_correlation(lv1, lv2, dataset):
    # De covariantie van de twee variabelen (covar) en de standaarddeviaties van beide variabelen.
    covar = covariance(lv1, lv2, dataset)
    sd_lv1 = math.sqrt(variance([lv1], dataset))
    sd_lv2 = math.sqrt(variance([lv2], dataset))

    return covar / (sd_lv1 * sd_lv2)


def correlation_matrix(dataset):
    # Een dictionary met correlatiescores voor ieder item (data).
    data = {}
    items = [i for i in [item for item in dataset]]
    for item in items:
        data[item] = []
        not_valuable = False
        for lv2 in items:
            if round(pearson_correlation(item, lv2, dataset), 4) == 1:
                not_valuable = True
            if not_valuable:
                data[item].append(np.nan)
            else:
                data[item].append(pearson_correlation(item, lv2, dataset))

    # Het omzetten van de dictionary naar een Pandas Dataframe en deze tabel omdraaien (met transpose).
    df = pd.DataFrame(data, index=[item for item in items])
    df = df.transpose()

    return df


def heterotrait_monotrait(var1, var2, corr_matrix, dataset):
    # Twee lijsten met de items voor iedere variabele.
    length_abbreviation_var1 = len(var1.abbreviation)
    items_var1 = [i for i in [item for item in dataset if item[:length_abbreviation_var1] == var1.abbreviation]]
    length_abbreviation_var2 = len(var2.abbreviation)
    items_var2 = [i for i in [item for item in dataset if item[:length_abbreviation_var2] == var2.abbreviation]]

    # De Monotrait lijsten bevatten de correlaties tussen de eigen items van een kernvariabele (oftewel bijv. de
    # correlatie tussen PE1 en PE2, PE5 en PE3 etc.). De Heterotrait lijst bevat de correlaties tussen de items van de
    # twee kernvariabelen (oftewel bijv. PE1 en EE3, PE4 en EE2 etc.).
    monotrait_var1_list = []
    monotrait_var2_list = []
    heterotrait_list = []

    # Het toevoegen van de correlaties tussen de items binnen de eerste kernvariabele.
    for item_1 in items_var1:
        for item_2 in corr_matrix[item_1].keys():
            if item_2 in items_var1 and not math.isnan(corr_matrix[item_1][item_2]):
                monotrait_var1_list.append(corr_matrix[item_1][item_2])

    # Het toevoegen van de correlaties tussen de items binnen de tweede kernvariabele.
    for item_1 in items_var2:
        for item_2 in corr_matrix[item_1].keys():
            if item_2 in items_var2 and not math.isnan(corr_matrix[item_1][item_2]):
                monotrait_var2_list.append(corr_matrix[item_1][item_2])

    # Het toevoegen van de correlaties tussen de items van de twee kernvariabelen.
    for item_1 in items_var1:
        for item_2 in corr_matrix[item_1].keys():
            if item_2 in items_var2 and not math.isnan(corr_matrix[item_1][item_2]):
                heterotrait_list.append(corr_matrix[item_1][item_2])

            if item_2 in items_var2 and math.isnan(corr_matrix[item_1][item_2]):
                if not math.isnan(corr_matrix[item_2][item_1]):
                    heterotrait_list.append(corr_matrix[item_2][item_1])

    # De gemiddelden van de drie lijsten.
    avg_heterotrait = sum(heterotrait_list) / len(heterotrait_list)
    avg_monotrait_var1 = sum(monotrait_var1_list) / len(monotrait_var1_list)
    avg_monotrait_var2 = sum(monotrait_var2_list) / len(monotrait_var2_list)

    return avg_heterotrait / (math.sqrt(avg_monotrait_var1 * avg_monotrait_var2))


def htmt_matrix(dataset, model):
    corevariables = [corevariable for corevariable in model.linked_corevariables]
    # Een dictionary met de HTMT-ratios van de verschillende kernvariabelen.
    data = {}
    for corevariable in corevariables:
        data[corevariable.abbreviation] = []
        not_valuable = False
        for cv2 in corevariables:
            if round(heterotrait_monotrait(corevariable, cv2, correlation_matrix(dataset), dataset), 4) == 1:
                not_valuable = True
            # Een lege waarde om ervoor te zorgen dat niet de hele tabel, maar slechts de helft gegeven wordt (om ervoor
            # te zorgen dat dezelfde waarden niet twee keer worden gegeven voor betere leesbaarheid, en te voorkomen
            # dat de HTMT-ratio tussen dezelfde kernvariabele gegeven wordt, welke altijd 1 is).
            if not_valuable:
                data[corevariable.abbreviation].append(' ')
            else:
                data[corevariable.abbreviation].append(round(
                    heterotrait_monotrait(corevariable, cv2, correlation_matrix(dataset), dataset),4))

    # Het omzetten van de dictionary naar een Pandas Dataframe.
    df = pd.DataFrame(data, index=[corevariable.abbreviation for corevariable in corevariables])

    return df


def outer_vif_values_dict(dataset, questionnaire):
    # Een lijst met de code van alle vragen binnen de vragenlijst, verdeeld in sublijsten per kernvariabele
    # (abbreviations_by_lv).
    abbreviations_by_lv = []
    questiongroups = [questiongroup for questiongroup in questionnaire.linked_questiongroups]
    for questiongroup in questiongroups:
        questions = [question for question in Question.query.filter_by(questiongroup_id=questiongroup.id)]
        abbreviations_by_lv.append([question.question_code for question in questions])

    # Een Pandas Dataframe met alle VIF-waarden voor ieder item.
    dataframes_vif = []
    for questiongroup in abbreviations_by_lv:
        X = add_constant(dataset[questiongroup])
        # VIF dataframe
        vif_data = pd.DataFrame()
        vif_data["feature"] = X.columns

        # calculating VIF for each feature
        vif_data["VIF"] = [variance_inflation_factor(X.values, i)
                           for i in range(len(X.columns))]

        dataframes_vif.append(vif_data)

    result = pd.concat(dataframes_vif)
    # Het verwijderen van de constantes uit de Pandas Dataserie
    result_outer_vif = result[result.feature != 'const']

    # Een dictionary met de items en de bijbehorende VIF-waarde (data_outer_vif).
    data_outer_vif = {}
    for i in range(len(result_outer_vif)):
        data_outer_vif[result_outer_vif.iloc[i]['feature']] = round(float(result_outer_vif.iloc[i]['VIF']), 4)

    return data_outer_vif


def indexes_corevariables_three(list_of_corevariables, corevariable_id):
    length_corevariables = len(list_of_corevariables)
    indexes_corevariables = []
    for corevariable in list_of_corevariables:
        if corevariable.id == int(corevariable_id):
            if list_of_corevariables.index(corevariable) == 0:
                indexes_corevariables = [0, 1, 2]
            elif list_of_corevariables.index(corevariable) == length_corevariables - 1:
                indexes_corevariables = [length_corevariables - 3, length_corevariables - 2, length_corevariables - 1]
            else:
                indexes_corevariables = [list_of_corevariables.index(corevariable) - 1, list_of_corevariables.index(corevariable),
                                         list_of_corevariables.index(corevariable) + 1]

    return indexes_corevariables
