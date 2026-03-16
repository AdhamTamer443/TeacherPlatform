from app import create_app
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run("0.0.0.0", debug=True)
