import uuid
from datetime import datetime

from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_required
from wtforms import RadioField

from app import db
from app.current_studies import bp
from app.models import User, Study


@bp.route('/my_studies', methods=['GET', 'POST'])
@login_required
def my_studies():
    # Een lijst met alle bestaande studies waarbinnen de gebruiker betrokken is.
    studies = [study for study in Study.query.all() if current_user in study.linked_users]
    amount_of_studies = len(studies)

    return render_template("current_studies/my_studies.html", title='My studies', studies=studies,
                           amount_of_studies=amount_of_studies)