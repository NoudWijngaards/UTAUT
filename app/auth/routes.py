from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user
from app import db
from app.auth import bp

import os
import smtplib

from werkzeug.urls import url_parse
from app.auth.email import send_password_reset_email, send_registration_mail
from app.auth.forms import LoginForm, RegistrationForm, \
    ResetPasswordRequestForm, ResetPasswordForm
from app.models import User


@bp.route('/login', methods=['GET', 'POST'])
def login():
    # Als de gebruiker al ingelogd is wordt deze verwezen naar het hoofdmenu.
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    # De Form voor het inloggen.
    form = LoginForm()
    # Als de gebruiker aangeeft in te willen loggen.
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        # Als de gebruiker niet bestaart of als het wachtwoord niet klopt.
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('auth.login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            session["name"] = request.form.get("name")
            next_page = url_for('main.index')
        return redirect(next_page)
    return render_template('auth/login.html', title='Sign In', form=form)


@bp.route('/logout')
def logout():
    # De gebruiker wordt uitgelogd.
    logout_user()
    return redirect(url_for('main.index'))


@bp.route('/register', methods=['GET', 'POST'])
def register():
    # Als de gebruiker al ingelogd is wordt deze verwezen naar het hoofdmenu.
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    # De Form voor registratie binnen de app.
    form = RegistrationForm()
    # Als de gebruiker aangeeft de registratiegegevens ingevuld te hebben.
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!')

        # Een email verzenden met de bevestiging.
        username = request.form.get("username")
        email = request.form.get('email')
        send_registration_mail(username, email)
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', title='Register', form=form)


@bp.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    # Als de gebruiker al ingelogd is wordt deze verwezen naar het hoofdmenu.
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    # De Form voor het resetten van het wachtwoord.
    form = ResetPasswordRequestForm()
    # Als de gebruiker aangeeft het wachtwoord te willen resetten.
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)
        flash('Check your email for the instructions to reset your password')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password_request.html',
                           title='Reset Password', form=form)


@bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # Als de gebruiker al ingelogd is wordt deze verwezen naar het hoofdmenu.
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for('main.index'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset.')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', form=form)
