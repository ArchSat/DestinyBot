import os
from dotenv import load_dotenv
load_dotenv(override=True)


basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    CLIENT_ID_BUNGIE = os.environ['CLIENT_ID_BUNGIE']
    CLIENT_SECRET_BUNGIE = os.environ['CLIENT_SECRET_BUNGIE']
    CLIENT_ID_BUNGIE_ADMIN = os.environ['CLIENT_ID_BUNGIE_ADMIN']
    CLIENT_SECRET_BUNGIE_ADMIN = os.environ['CLIENT_SECRET_BUNGIE_ADMIN']
    REDIRECT_URI_BUNGIE = f"{os.environ['REDIRECT_URI']}callback/bungie"
    REDIRECT_URI_BUNGIE_ADMIN = REDIRECT_URI_BUNGIE + '/admin'
    CLIENT_ID_DISCORD = os.environ['CLIENT_ID_DISCORD']
    CLIENT_SECRET_DISCORD = os.environ['CLIENT_SECRET_DISCORD']
    REDIRECT_URI_DISCORD = f"{os.environ['REDIRECT_URI']}callback/discord"
    X_API_KEY = os.environ['X_API_KEY']
    X_API_KEY_ADMIN = os.environ['X_API_KEY_ADMIN']
    DATABASE_URL = os.environ['DATABASE_URL']
    SESSION_TYPE = 'filesystem'
