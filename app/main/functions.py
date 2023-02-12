from flask import render_template, flash, redirect, url_for, request
from app.models import Study, CoreVariable, Relation, ResearchModel
from flask_login import current_user


def security_and_studycheck_full(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    study = Study.query.filter_by(code=study_code).first()
    if current_user not in study.linked_users:
        return redirect(url_for('main.not_authorized'))

    # Checken hoe ver de studie is
    if study.stage_1:
        if study.researchmodel_id is None:
            return redirect(url_for('create_study.choose_model', study_code=study_code))
        else:
            return redirect(url_for('create_study.edit_model', study_code=study_code))
    if study.stage_2:
        return redirect(url_for('create_study.study_underway', name_study=study.name, study_code=study_code))
    if study.stage_3:
        return redirect(url_for('create_study.summary_results', study_code=study_code))


def security_and_studycheck_stage1(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    study = Study.query.filter_by(code=study_code).first()
    if current_user not in study.linked_users:
        return redirect(url_for('main.not_authorized'))

    if study.stage_2:
        return redirect(url_for('create_study.study_underway', name_study=study.name, study_code=study_code))
    if study.stage_3:
        return redirect(url_for('create_study.summary_results', study_code=study_code))


def security_and_studycheck_stage2(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    study = Study.query.filter_by(code=study_code).first()
    if current_user not in study.linked_users:
        return redirect(url_for('main.not_authorized'))

    # Checken hoe ver de studie is
    if study.stage_1:
        if study.researchmodel_id is None:
            return redirect(url_for('create_study.choose_model', study_code=study_code))
        else:
            return redirect(url_for('create_study.edit_model', study_code=study_code))
    if study.stage_3:
        return redirect(url_for('create_study.summary_results', study_code=study_code))


def security_and_studycheck_stage3(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    study = Study.query.filter_by(code=study_code).first()
    if current_user not in study.linked_users:
        return redirect(url_for('main.not_authorized'))

    # Checken hoe ver de studie is
    if study.stage_1:
        if study.researchmodel_id is None:
            return redirect(url_for('create_study.choose_model', study_code=study_code))
        else:
            return redirect(url_for('create_study.edit_model', study_code=study_code))
    if study.stage_2:
        return redirect(url_for('create_study.study_underway', name_study=study.name, study_code=study_code))
