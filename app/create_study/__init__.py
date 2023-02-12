from flask import Blueprint

bp = Blueprint('create_study', __name__)

from app.create_study import routes
