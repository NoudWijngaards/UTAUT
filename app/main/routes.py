from flask import render_template, flash, redirect, url_for, request
from flask_login import current_user, login_required
from app import db
from app.main import bp

from app.main.forms import EditProfileForm, EmptyForm
from app.models import User


@bp.route('/', methods=['GET', 'POST'])
@bp.route('/not_authorized', methods=['GET', 'POST'])
@login_required
def not_authorized():
    return render_template("not_authorized.html", title='Not Authorized')


@bp.route('/', methods=['GET', 'POST'])
@bp.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    return render_template("main/index.html", title='Home Page')


@bp.route('/user/<username>')
@login_required
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    form = EmptyForm()
    return render_template('main/user.html', user=user, form=form)


@bp.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    # De Form voor het aanpassen van het profiel.
    form = EditProfileForm()

    # Als de gebruiker aangeeft aanpassingen te willen maken aan het profiel.
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        # Een Flash/bericht binnen de applicatie welke aangeeft dat de aanpassingen zijn gemaakt.
        flash('Your changes have been saved.')
        return redirect(url_for('main.edit_profile'))
    # Bij het ophalen van de huidige gegevens voorafgaand aan het kunnen maken van aanpassingen.
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    return render_template('main/edit_profile.html', title='Edit Profile',
                           form=form)