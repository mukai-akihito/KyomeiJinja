import os
import tweepy
import MeCab
from flask import Flask
from flask_socketio import SocketIO

# Twitter API Token
BEARER_TOKEN = os.getenv('BEARER_TOKEN')

# Tweepy Client
client = tweepy.Client(bearer_token=BEARER_TOKEN)

# Flask + SocketIO setup
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# MeCab setup
tagger = MeCab.Tagger("-Ochasen")

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
                for line in tagger.parse(text).splitlines():
                    if "\t" in line and ("名詞" in line or "形容詞" in line):
                        word = line.split("\t")[0]
                        socketio.emit("new_word", word)
        socketio.sleep(30)

if __name__ == '__main__':
    socketio.start_background_task(fetch_and_push_words)
    socketio.run(app, host='0.0.0.0', port=5000)
