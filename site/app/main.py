from uuid import uuid4

from flask_session import Session
from flask import Flask

from .config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    from .routes import index, register
    app.register_blueprint(register.auth)
    app.register_blueprint(register.callback)
    app.register_blueprint(register.check)
    app.register_blueprint(index.main)
    from .error_handlers import handlers
    app.register_blueprint(handlers)
    app.secret_key = str(uuid4())
    sess = Session()
    sess.init_app(app)
    app.debug = True
    return app
