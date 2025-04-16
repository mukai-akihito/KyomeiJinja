import os
import time
import requests
from flask import Flask
from flask_socketio import SocketIO
from threading import Thread

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*')

BEARER_TOKEN = os.getenv("BEARER_TOKEN")
if not BEARER_TOKEN:
    raise ValueError("BEARER_TOKEN is not set")

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
QUERY = "lang:ja"
MAX_RESULTS = 5

def get_recent_tweets():
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    params = {
        "query": QUERY,
        "max_results": MAX_RESULTS
    }
    try:
        response = requests.get(SEARCH_URL, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            print("API error:", response.status_code)
    except Exception as e:
        print("Request failed:", str(e))
    return None

def tweet_loop():
    while True:
        data = get_recent_tweets()
        if data and "data" in data:
            for tweet in data["data"]:
                text = tweet["text"]
                socketio.emit("new-word", {"word": text})
        time.sleep(60)

@app.route('/')
def index():
    return "KYOMEI JINJA - Minimal Server is running."

if __name__ == "__main__":
    Thread(target=tweet_loop, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=5000)
