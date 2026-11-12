from flask import current_app
from pymongo import MongoClient

_client = None


def get_db():
    """Return the MongoDB database (one shared client)."""
    global _client
    if _client is None:
        _client = MongoClient(current_app.config["MONGO_URI"], serverSelectionTimeoutMS=3000)
    return _client[current_app.config["MONGO_DB_NAME"]]
