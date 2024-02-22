from flask import Blueprint, render_template, redirect, url_for, session
from werkzeug.exceptions import HTTPException

handlers = Blueprint('errors', __name__)


@handlers.app_errorhandler(HTTPException)
def exception_handler(e):
    print(e.description)
    return f"{e}", 404
