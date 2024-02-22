from app.main import create_app

from dotenv import load_dotenv
load_dotenv(override=True)

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
