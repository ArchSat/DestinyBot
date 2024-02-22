import os

from bungio import Client
from bungio.models import BungieLanguage
from dotenv import load_dotenv

from utils.logger import create_logger

load_dotenv(override=True)


class CustomClient(Client):
    def __init__(self, *args, **kwargs):
        super().__init__(bungie_client_id=os.getenv("CLIENT_ID_BUNGIE_ADMIN"),
                         bungie_client_secret=os.getenv("CLIENT_SECRET_BUNGIE_ADMIN"),
                         bungie_token=os.getenv("X_API_KEY_ADMIN"),
                         language=BungieLanguage.RUSSIAN,
                         logger=create_logger('bungio'),
                         *args, **kwargs)
