from flask import Blueprint

bp = Blueprint('questionnaire', __name__)

from app.questionnaire import routes
