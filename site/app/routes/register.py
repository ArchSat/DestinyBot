import json
import os
import time
import urllib
from uuid import uuid4

import pika
import requests as requests
from flask import Blueprint, current_app, redirect, url_for, session, request, abort


from logger import create_logger
from dotenv import load_dotenv
load_dotenv(override=True)


logger = create_logger(__name__)


def base_headers():
    return {'X-API-KEY': current_app.config['X_API_KEY']}


def base_admin_headers():
    return {'X-API-KEY': current_app.config['X_API_KEY_ADMIN']}


def make_authorization_url_bungie_admin(state):
    params = {"client_id": current_app.config['CLIENT_ID_BUNGIE_ADMIN'],
              "response_type": "code",
              "state": state,
              "redirect_uri": current_app.config['REDIRECT_URI_BUNGIE_ADMIN'],
              "duration": "temporary"}
    url_bungie = "https://www.bungie.net/en/OAuth/Authorize?" + urllib.parse.urlencode(params)
    return url_bungie


def make_authorization_url_bungie(state):
    params = {"client_id": current_app.config['CLIENT_ID_BUNGIE'],
              "response_type": "code",
              "state": state,
              "redirect_uri": current_app.config['REDIRECT_URI_BUNGIE'],
              "duration": "temporary"}
    url_bungie = "https://www.bungie.net/en/OAuth/Authorize?" + urllib.parse.urlencode(params)
    return url_bungie


def make_authorization_url_discord(state):
    params = {"state": state,
              "client_id": current_app.config['CLIENT_ID_DISCORD'],
              "response_type": "code",
              "redirect_uri": current_app.config['REDIRECT_URI_DISCORD'],
              "scope": "identify"}
    url_discord = "https://discord.com/api/oauth2/authorize?" + urllib.parse.urlencode(params)
    return url_discord


auth = Blueprint('auth', __name__, url_prefix='/auth')


@auth.route('/', methods=('GET', 'POST'))
def auth_base_route():
    return redirect(url_for('auth.discord'))


@auth.route('/bungie/')
def bungie():
    session['bungie_state'] = str(uuid4())
    session.modified = True
    url_bungie = make_authorization_url_bungie(session['bungie_state'])
    res = redirect(url_bungie)
    return res


@auth.route('/bungie/admin/')
def bungie_admin():
    session['bungie_state'] = str(uuid4())
    session.modified = True
    url_bungie = make_authorization_url_bungie_admin(session['bungie_state'])
    res = redirect(url_bungie)
    return res


@auth.route('/discord/')
def discord():
    session['discord_state'] = str(uuid4())
    session.modified = True
    url_discord = make_authorization_url_discord(session['discord_state'])
    res = redirect(url_discord)
    return res


callback = Blueprint('callback', __name__, url_prefix='/callback')


def is_valid_bungie_state(state):
    if state == session.get('bungie_state', None):
        return True
    else:
        return False


def is_valid_discord_state(state):
    if state == session.get('discord_state', None):
        return True
    else:
        return False


def get_discord_data(code):
    post_data = {
        "client_id": current_app.config["CLIENT_ID_DISCORD"],
        "client_secret": current_app.config["CLIENT_SECRET_DISCORD"],
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": current_app.config["REDIRECT_URI_DISCORD"],
        "scope": "identify"
    }
    response = requests.post("https://discord.com/api/oauth2/token",
                             data=post_data)
    token_json = response.json()
    if response.status_code == 200:
        header = {
            'Authorization': f"{token_json['token_type']} {token_json['access_token']}"
        }
        discord_answ = requests.get('https://discord.com/api/users/@me', headers=header)
        discord_json = discord_answ.json()
        return discord_answ.status_code, discord_json
    else:
        return response.status_code, token_json


@callback.route('/discord')
def discord_callback():
    error = request.args.get('error', '')
    if error:
        session.clear()
        session.modified = True
        abort(502, error)
    code = request.args.get('code')
    state = request.args.get('state')

    if not is_valid_discord_state(state):
        session.clear()
        session.modified = True
        abort(503)
    response_status, discord_data = get_discord_data(code)
    if response_status == 200:
        session['discord'] = discord_data['id']
        session.modified = True
    else:
        discord_error_code = discord_data['code']
        session.clear()
        session.modified = True
        abort(response_status, discord_error_code)
    if 'bungie' in session:
        res = redirect(url_for('check.check_view'))
    else:
        res = redirect(url_for('auth.bungie'))
    return res


def bungie_get_tokens(code):
    client_auth = requests.auth.HTTPBasicAuth(current_app.config['CLIENT_ID_BUNGIE'],
                                              current_app.config['CLIENT_SECRET_BUNGIE'])
    post_data = {"grant_type": "authorization_code",
                 "code": code,
                 "redirect_uri": current_app.config['REDIRECT_URI_BUNGIE']}
    headers = base_headers()
    response = requests.post("https://www.bungie.net/Platform/App/OAuth/token/",
                             auth=client_auth,
                             headers=headers,
                             data=post_data)
    token_json = response.json()
    return response.status_code, token_json


@callback.route('/bungie')
def bungie_callback():
    error = request.args.get('error', '')
    if error:
        session.clear()
        session.modified = True
        abort(502, error)
    code = request.args.get('code')
    state = request.args.get('state')

    if not is_valid_bungie_state(state):
        session.clear()
        session.modified = True
        abort(503)
    response_status, bungie_data = bungie_get_tokens(code)
    if response_status == 200:
        session['bungie'] = bungie_data
        session['admin'] = False
        session.modified = True
    else:
        session.clear()
        session.modified = True
        abort(response_status)
    if 'discord' in session:
        res = redirect(url_for('check.check_view'))
    else:
        res = redirect(url_for('auth.discord'))
    return res


def bungie_get_admin_tokens(code):
    client_auth = requests.auth.HTTPBasicAuth(current_app.config['CLIENT_ID_BUNGIE_ADMIN'],
                                              current_app.config['CLIENT_SECRET_BUNGIE_ADMIN'])
    post_data = {"grant_type": "authorization_code",
                 "code": code,
                 "redirect_uri": current_app.config['REDIRECT_URI_BUNGIE_ADMIN']}
    headers = base_admin_headers()
    response = requests.post("https://www.bungie.net/Platform/App/OAuth/token/",
                             auth=client_auth,
                             headers=headers,
                             data=post_data)
    token_json = response.json()
    return response.status_code, token_json


@callback.route('/bungie/admin')
def bungie_admin_callback():
    error = request.args.get('error', '')
    if error:
        session.clear()
        session.modified = True
        abort(502, error)
    code = request.args.get('code')
    state = request.args.get('state')
    if not is_valid_bungie_state(state):
        session.clear()
        session.modified = True
        abort(503)
    response_status, bungie_data = bungie_get_admin_tokens(code)
    if response_status == 200:
        session['bungie'] = bungie_data
        session['admin'] = True
        session.modified = True
    else:
        session.clear()
        session.modified = True
        abort(response_status)
    if 'discord' in session:
        res = redirect(url_for('check.check_view'))
    else:
        res = redirect(url_for('auth.discord'))
    return res


check = Blueprint('check', __name__, url_prefix='/check')


def create_message():
    logger.debug('start')
    admin = session.get('admin', None)
    bungie_info = session.get('bungie', None)
    discord_id = session.get('discord', None)
    logger.debug(admin, bungie_info, discord_id)
    if admin is None or bungie_info is None or discord_id is None:
        session.clear()
        return False
    message_data = {
        'admin': admin,
        'bungie': bungie_info,
        'discord': discord_id,
    }
    logger.debug(message_data)

    connection = pika.BlockingConnection(
        pika.URLParameters(os.getenv('RABBIT_SITE_URL')))
    channel = connection.channel()
    channel.queue_declare(queue='registration', durable=True)
    channel = connection.channel()
    channel.basic_publish(exchange='', routing_key='registration', body=json.dumps(message_data))
    logger.debug('message published')
    connection.close()
    session.clear()
    session.modified = True
    return True


@check.route('/success/')
def success():
    return redirect('https://discord.gg/D5fe4rC')


@check.route('/')
def check_view():
    user_created = create_message()
    if user_created:
        return redirect('success')
    else:
        session.clear()
        session.modified = True
        abort(502)
