"""Run:  python check_db.py      (from the medsecure_ai folder, venv active)
Tells you WHY MongoDB is not reachable. Never prints your password."""
import os, re, sys
from dotenv import load_dotenv, find_dotenv

path = find_dotenv(usecwd=True)
print(".env file found:", path if path else "NO  <-- the app falls back to local MongoDB (localhost:27017)")
load_dotenv(path)
uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
safe = re.sub(r"//([^:/@]+):[^@]*@", r"//\1:<password hidden>@", uri)
print("MONGO_URI in use:", safe)
print("Database name   :", os.getenv("MONGO_DB_NAME", "medsecure_ai"))
if "localhost" in uri or "127.0.0.1" in uri:
    print("-> This is LOCAL MongoDB. It must be installed and running (Windows service 'MongoDB').")
elif uri.startswith("mongodb+srv"):
    print("-> This is MongoDB ATLAS (cloud). Needs internet, correct password, and your IP allowed in Atlas.")
if re.search(r"//[^:/@]+:[^@]*[@#/?][^@]*@", uri):
    print("-> WARNING: password seems to contain @ # / or ? . Use letters/numbers only, or URL-encode it.")
try:
    from pymongo import MongoClient
    c = MongoClient(uri, serverSelectionTimeoutMS=10000)
    c.admin.command("ping")
    print("\nRESULT: CONNECTED OK. Restart the app (python app.py).")
except Exception as e:
    msg = re.sub(r"//([^:/@]+):[^@]*@", r"//\1:<hidden>@", str(e))
    print("\nRESULT: FAILED ->", type(e).__name__)
    print(msg[:500])
    low = msg.lower()
    if "authentication failed" in low or "bad auth" in low:
        print("\nFIX: wrong username/password in MONGO_URI (did you change it in Atlas but not in .env?).")
    elif "timed out" in low or "serverselectiontimeout" in low or "no replica set members" in low:
        print("\nFIX (Atlas): Atlas > Network Access > Add IP Address > 'Add Current IP Address' (or 0.0.0.0/0 for a college demo).")
        print("FIX (local): start the MongoDB service (Services > MongoDB Server > Start).")
    elif "dns" in low or "resolution" in low:
        print("\nFIX: no internet / DNS problem, or the cluster address in MONGO_URI is wrong.")
    sys.exit(1)