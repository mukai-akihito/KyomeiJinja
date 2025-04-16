import os
import time
import requests
from flask import Flask
from flask_socketio import SocketIO, emit
from janome.tokenizer import Tokenizer
from threading import Thread
from collections import deque

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*')

# Twitter API 認証用トークン
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
if not BEARER_TOKEN:
    raise ValueError("BEARER_TOKEN is not set")

# Twitter REST API (Recent Search)
SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
QUERY = "lang:ja"
MAX_RESULTS = 5  # メモリ軽量化のため、取得数を抑える

# キーワード抽出用
tokenizer = Tokenizer()

# 取得済みツイートID（上限1000件まで保存）
processed_tweet_ids = deque(maxlen=1000)

def get_recent_tweets():
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    params = {
        "query": QUERY,
        "max_results": MAX_RESULTS
    }
    response = requests.get(SEARCH_URL, headers=headers, params=params)
    if response.status_code != 200:
        print("Twitter API error:", response.status_code, response.text)
        return None
    return response.json()

def extract_keywords(text):
    tokens = tokenizer.tokenize(text)
    return [
        token.surface for token in tokens
        if token.part_of_speech.split(',')[0] in ['名詞', '動詞']
        and len(token.surface) > 1
    ]

def tweet_search_loop():
    while True:
        data = get_recent_tweets()
        if data and "data" in data:
            for tweet in data["data"]:
                tweet_id = tweet["id"]
                if tweet_id in processed_tweet_ids:
                    continue
                processed_tweet_ids.append(tweet_id)
                text = tweet["text"]
                keywords = extract_keywords(text)
                for word in keywords:
                    socketio.emit('new-word', {'word': word})
        else:
            print("No new tweets or API error.")
        time.sleep(60)  # 1分ごとに実行

@app.route('/')
def index():
    return "KYOMEI JINJA REST API Server is running."

if __name__ == '__main__':
    Thread(target=tweet_search_loop, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000)
