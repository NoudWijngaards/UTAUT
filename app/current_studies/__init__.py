from flask import Blueprint

bp = Blueprint('current_studies', __name__)

from app.current_studies import routes