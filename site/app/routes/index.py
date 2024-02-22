from flask import Blueprint, render_template, redirect, url_for, session

main = Blueprint('index_page', __name__, url_prefix='/')


@main.route('', methods=('GET', 'POST'))
@main.route('/', methods=('GET', 'POST'))
@main.route('/index', methods=('GET', 'POST'))
@main.route('/main', methods=('GET', 'POST'))
def register():
    session.clear()
    session.modified = True
    return render_template('index.html')


@main.route('/discord', methods=('GET', 'POST'))
def discord_route():
    return redirect('https://discord.gg/D5fe4rC')
