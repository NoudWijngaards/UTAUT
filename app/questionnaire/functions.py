from app.models import Study
from flask import render_template, flash, redirect, url_for, request


# Het omdraaien van de score in het geval dat "reversed_score" geldt voor de vraag.
def reverse_value(value, scale):
    new_value = scale + 1 - int(value)
    return str(new_value)


def security_check(study_code):
    # Checken of gebruiker tot betrokken onderzoekers hoort
    study = Study.query.filter_by(code=study_code).first()

    if not study.stage_2:
        return redirect(url_for('main.not_authorized'))
