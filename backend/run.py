"""Development entry point: python run.py"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # use_reloader=False: dev_restart.py handles restarts so no orphan process
    # keeps the SQLite DB locked on Windows.
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
