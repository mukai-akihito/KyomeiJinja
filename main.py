import os
import time
import requests
import json
from flask import Flask
from flask_socketio import SocketIO, emit
from janome.tokenizer import Tokenizer
from threading import Thread

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*')

# 環境変数から Twitter API の Bearer Token を取得
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
if BEARER_TOKEN is None:
    raise ValueError("BEARER_TOKEN is not set")

# Twitter Recent Search API の URL とクエリパラメータ（例：日本語のみ取得）
SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
QUERY = "lang:ja"  # 日本語ツイート限定、他にキーワードなど追加可能
MAX_RESULTS = 10  # 1リクエストで取得する件数（最大100件）

# 形態素解析用
tokenizer = Tokenizer()

# 既に取得済みのツイートIDを記録して、重複送信を防止するためのセット
processed_tweet_ids = set()

def get_recent_tweets():
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    params = {
        "query": QUERY,
        "max_results": MAX_RESULTS
    }
    response = requests.get(SEARCH_URL, headers=headers, params=params)
    if response.status_code != 200:
        print("Error fetching tweets: ", response.status_code, response.text)
        return None
    return response.json()

def extract_keywords(text):
    tokens = tokenizer.tokenize(text)
    # 名詞と動詞のみ抽出し、適当なフィルタをかける（例として、長さ2以上のもの）
    words = [token.surface for token in tokens if token.part_of_speech.split(',')[0] in ['名詞', '動詞'] and len(token.surface) > 1]
    return words

def tweet_search_loop():
    while True:
        data = get_recent_tweets()
        if data and "data" in data:
            for tweet in data["data"]:
                tweet_id = tweet["id"]
                if tweet_id in processed_tweet_ids:
                    continue
                processed_tweet_ids.add(tweet_id)
                text = tweet["text"]
                keywords = extract_keywords(text)
                # 各キーワードをWebSocket経由で送信（件数カウントは省略例）
                for word in keywords:
                    # ここでは単にキーワードを送る例です
                    socketio.emit('new-word', {'word': word})
                    print(f"Emitted: {word}")
        else:
            print("No data received from Twitter API.")
        # 次のAPI呼び出しまで1分待つ（間隔は調整可能）
        time.sleep(60)

@app.route('/')
def index():
    return "KYOMEI REST API Server is running."

if __name__ == '__main__':
    # 別スレッドで定期的なツイート取得ループを開始
    tweet_thread = Thread(target=tweet_search_loop)
    tweet_thread.daemon = True
    tweet_thread.start()

    # Flaskサーバーを起動
    socketio.run(app, host='0.0.0.0', port=5000)
