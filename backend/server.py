from app.api.main import create_app
from app.core.config import settings
app = create_app()
if __name__ == "__main__":
    app.run(host=settings.host, port=settings.port, debug=settings.debug)
