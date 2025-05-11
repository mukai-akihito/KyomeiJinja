import os
import tweepy
from flask import Flask
from flask_socketio import SocketIO
from sudachipy import tokenizer
from sudachipy import dictionary

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
        response = client.search_recent_tweets(query=query, max_results=10)
        if response.data:
            for tweet in response.data:
                text = tweet.text
                tokens = tokenizer_obj.tokenize(text, mode)
                for m in tokens:
                    if m.part_of_speech()[0] in ['名詞', '形容詞']:
                        word = m.surface()
                        socketio.emit("new_word", word)
        socketio.sleep(30)

if __name__ == '__main__':
    socketio.start_background_task(fetch_and_push_words)
    socketio.run(app, host='0.0.0.0', port=5000)
