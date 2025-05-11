import os
import tweepy
from flask import Flask
from flask_socketio import SocketIO
from sudachipy import tokenizer
from sudachipy import dictionary
import eventlet

# 必須：eventlet の monkey patch を最初に適用！
eventlet.monkey_patch()

# Twitter API Token
BEARER_TOKEN = os.getenv('BEARER_TOKEN')
client = tweepy.Client(bearer_token=BEARER_TOKEN)

# Flask + SocketIO setup
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# SudachiPy setup
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
                for tweet in response.data:
                    text = tweet.text
                    tokens = tokenizer_obj.tokenize(text, mode)
                    for m in tokens:
                        if m.part_of_speech()[0] in ['名詞', '形容詞']:
                            word = m.surface()
                            socketio.emit("new_word", word)
        except Exception as e:
            print(f"Error fetching tweets: {e}")
        socketio.sleep(120)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)