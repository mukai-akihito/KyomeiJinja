import eventlet
eventlet.monkey_patch()

import os
import tweepy
from flask import Flask
from flask_socketio import SocketIO
from sudachipy import tokenizer
from sudachipy import dictionary

# Twitter API設定
BEARER_TOKEN = os.getenv('BEARER_TOKEN')
client = tweepy.Client(bearer_token=BEARER_TOKEN)

# Flask + Socket.IO設定
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# SudachiPy形態素解析設定
tokenizer_obj = dictionary.Dictionary().create()
mode = tokenizer.Tokenizer.SplitMode.C

@app.route('/')
def index():
    return 'KYOMEI JINJA Server is running'

def fetch_and_push_words():
    query = "祈り OR 共鳴 OR 平和 lang:ja -is:retweet"
    while True:
        try:
            response = client.search_recent_tweets(query=query, max_results=10)
            if response.data:
                print(f"🌀 ツイート取得: {len(response.data)} 件")
                for tweet in response.data:
                    text = tweet.text
                    tokens = tokenizer_obj.tokenize(text, mode)
                    for m in tokens:
                        if m.part_of_speech()[0] in ['名詞', '形容詞']:
                            word = m.surface()
                            print(f"🔁 送信: {word}")
                            socketio.emit("new_word", word)
        except Exception as e:
            print(f"❌ エラー: {e}")
        socketio.sleep(120)  # 2分間隔

# 非同期で実行
@socketio.on('connect')
def handle_connect():
    print("✅ クライアント接続")
    socketio.start_background_task(fetch_and_push_words)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
