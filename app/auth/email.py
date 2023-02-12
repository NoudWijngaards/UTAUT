from flask import render_template, current_app
from app.email import send_email
import smtplib
import os
from flask import render_template, redirect, url_for, flash, request, session
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_registration_mail(username, email):
    # Het opzetten van de email om te versturen naar de nieuwe gebruiker.
    msg = MIMEMultipart()
    msg['From'] = os.environ.get('MAIL_USERNAME')
    msg['To'] = email
    msg['Subject'] = 'Welcome to RubyHub'
    message = 'Welcome {} to the RubyHub community. We hope you enjoy our services :)'.format(username)
    msg.attach(MIMEText(message))

    mailserver = smtplib.SMTP(os.environ.get('MAIL_SERVER'), os.environ.get('MAIL_PORT'))
    # Onszelf identificeren aan de Gmail-client.
    mailserver.ehlo()
    # Encryptie gebruiken voor de mail met TLS
    mailserver.starttls()
    # Onszelf heridentificeren als een beveiligde connectie.
    mailserver.ehlo()
    mailserver.login(os.environ.get('MAIL_USERNAME'), os.environ.get('MAIL_PASSWORD'))

    mailserver.sendmail(os.environ.get('MAIL_USERNAME'), email, msg.as_string())
    mailserver.quit()


def send_password_reset_email(user):
    token = user.get_reset_password_token()
    # Het opzetten van de email om te versturen naar de nieuwe gebruiker.
    msg = MIMEMultipart()
    msg['From'] = os.environ.get('MAIL_USERNAME')
    msg['To'] = user.email
    msg['Subject'] = 'Reset Password for RubyHub'
    message = render_template('email/reset_password.txt', user=user, token=token)
    msg.attach(MIMEText(message))

    mailserver = smtplib.SMTP(os.environ.get('MAIL_SERVER'), os.environ.get('MAIL_PORT'))
    # Onszelf identificeren aan de Gmail-client.
    mailserver.ehlo()
    # Encryptie gebruiken voor de mail met TLS
    mailserver.starttls()
    # Onszelf heridentificeren als een beveiligde connectie.
    mailserver.ehlo()
    mailserver.login(os.environ.get('MAIL_USERNAME'), os.environ.get('MAIL_PASSWORD'))

    mailserver.sendmail(os.environ.get('MAIL_USERNAME'), user.email, msg.as_string())
    mailserver.quit()
