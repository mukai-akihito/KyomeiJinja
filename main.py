#!/usr/bin/env python3
"""
Japanese Twitter Keyword Extractor
--------------------------------
このプログラムはTwitter APIを使用して日本語ツイートをリアルタイムで取得し、
重要なキーワード（名詞と動詞）を抽出してWebSocket経由でクライアントに配信します。
"""

import os
import re
import time
import json
import threading
from datetime import datetime
from collections import Counter
import logging

# 環境変数の読み込み
from dotenv import load_dotenv

# Twitter API
import tweepy

# Webサーバーとソケット通信
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# ログの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('twitter_keyword_extractor')

# 環境変数のロード
load_dotenv()

# .env ファイルからTwitter APIの認証情報を取得
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
if not BEARER_TOKEN:
    logger.warning("BEARER_TOKEN is not set in .env file")

# グローバル変数
keyword_counter = Counter()
recent_tweets = []
MAX_TWEETS = 100  # 保持する最大ツイート数
tweet_count = 0   # 処理されたツイートの総数
connection_attempts = 0  # 接続試行回数

# 日本語処理関連
# 助詞、助動詞などのストップワード
STOP_WORDS = [
    # 代名詞
    'これ', 'それ', 'あれ', 'この', 'その', 'あの', 'ここ', 'そこ', 'あそこ',
    'こちら', 'どこ', 'だれ', 'なに', 'なん', 'なんの', 'いつ', 'どうして',
    
    # 助詞
    'が', 'の', 'を', 'に', 'へ', 'と', 'から', 'より', 'で', 'や', 'は',
    'ので', 'のに', 'ば', 'て', 'って', 'でも', 'し', 'だけ', 'だの',
    'けど', 'けれど', 'けれども', 'だろう', 'でしょう', 'ながら',
    
    # 助動詞
    'です', 'ます', 'でした', 'ました', 'だった', 'ぬ', 'た', 'う', 'よう',
    'ない', 'せる', 'させる', 'れる', 'られる', 'しまう', 'ください',
    'しかし', 'だが', 'ただし', 'ただ', 'なので', 'したがって',
    'らしい', 'みたい', 'そう', 'よう', 'べき', 'はず', 'なければ',
    
    # 動詞の語幹
    'いる', 'ある', 'する', 'なる', 'くる', 'いく', 'できる',
    'てる', 'たい', 'たら', 'なら', 'れる', 'られ', 'せる', 'させ',
    
    # 形容詞の語幹
    'ない', 'いい', 'よい', 'すごい', 'ほしい',
    
    # 副詞
    'もう', 'まだ', 'また', 'さらに', 'なお', 'とても', 'かなり',
    'すごく', 'とっても', 'かなり', 'ちょっと', 'あまり', 'もっと',
    
    # 接続詞
    'その上', 'それから', 'それで', 'それでは', 'したがって', 
    'そのため', 'だから', 'つまり', 'すなわち', 'たとえば',
    'でも', 'しかし', 'だけど', 'ところで', 'さて', 'ならびに',
    'および', 'または', 'あるいは', 'さらに', 'ただし', 'ただ',
    
    # 感動詞・その他
    'じゃ', 'しま', 'せん', 'わな', 'すね', 'かな', 'よね', 'しみ',
    'うん', 'えっ', 'はて', 'あの', 'はい', 'いや', 'おー', 'おお', 'おっ',
    'わ', 'よ', 'ね', 'な', 'のよ', 'のね', 'わよ', 'わね', 'かしら',
    
    # 機能語
    'こと', 'もの', 'ため', 'ところ', 'やつ', 'わけ', 'とき', 'ほう',
    'さ', 'み', 'げ', 'まま', 'ごと', 'がち', 'っぽい', 'がたい',
    
    # SNS特有の語句
    'RT', 'http', 'https', 'co', 'jp', 'com', 'www',
    'ツイート', 'リツイート', 'フォロー', 'リプ', 'いいね'
]

# 名詞の語尾パターン
NOUN_SUFFIXES = [
    '性', '化', '者', '手', '師', '家', '員', '長', '様', '氏',
    '産', '人', '的', '界', '場', '市', '県', '都', '府', '党'
]

# 不自然なパターン
SUSPICIOUS_PATTERNS = [
    r'しみです', r'うんです', r'かなです', r'よねです', r'じゃです', r'えっです',
    r'[ぁ-んー]{1,2}です', r'[ぁ-んー]{1,2}ます'
]

# Flaskアプリとソケット通信の設定
app = Flask(__name__)
app.config['SECRET_KEY'] = 'twitter-keyword-extractor'
socketio = SocketIO(app, cors_allowed_origins="*")

class KeywordExtractor:
    """日本語テキストからキーワードを抽出するクラス"""
    
    @staticmethod
    def clean_text(text):
        """テキストのクリーニング"""
        # URLを削除
        text = re.sub(r'https?://\S+', '', text)
        # ハッシュタグと@メンションを削除
        text = re.sub(r'[#＃@][A-Za-z0-9_ぁ-んァ-ン一-龥]+', '', text)
        # RTの接頭辞を削除
        text = re.sub(r'RT\s+', '', text)
        # 空白文字の正規化
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    @staticmethod
    def tokenize_japanese(text):
        """日本語テキストをトークン化する簡易実装"""
        # 文字タイプ（ひらがな、カタカナ、漢字など）を判定
        def get_char_type(char):
            if re.match(r'[ぁ-ん]', char): return 'hiragana'
            if re.match(r'[ァ-ン]', char): return 'katakana'
            if re.match(r'[一-龥]', char): return 'kanji'
            if re.match(r'[A-Za-z]', char): return 'latin'
            if re.match(r'[0-9０-９]', char): return 'number'
            if re.match(r'\s', char): return 'space'
            return 'other'
        
        tokens = []
        current_token = ''
        current_type = ''
        
        for char in text:
            char_type = get_char_type(char)
            
            # 文字タイプが変わったらトークンを区切る
            if char_type != current_type and current_token:
                if len(current_token) > 0 and current_type != 'space':
                    tokens.append(current_token)
                current_token = ''
            
            if char_type != 'space':
                current_token += char
            
            current_type = char_type
        
        # 最後のトークンを追加
        if current_token and len(current_token) > 0 and current_type != 'space':
            tokens.append(current_token)
        
        return tokens
    
    @staticmethod
    def is_likely_noun(word):
        """単語が名詞である可能性を判定"""
        # ストップワードは除外
        if word in STOP_WORDS:
            return False
        
        # 1文字の場合は漢字のみ許可
        if len(word) == 1:
            return bool(re.match(r'[一-龥]', word))
        
        # 不自然なパターンをチェック
        for pattern in SUSPICIOUS_PATTERNS:
            if re.match(pattern, word):
                return False
        
        # 名詞の語尾パターンをチェック
        for suffix in NOUN_SUFFIXES:
            if word.endswith(suffix):
                return True
        
        # 漢字を含む単語は名詞の可能性が高い
        if re.search(r'[一-龥]', word):
            return True
        
        # カタカナのみの単語は名詞の可能性が高い（外来語、固有名詞）
        if re.match(r'^[ァ-ン]+$', word):
            return True
        
        # カタカナと漢字の混在する単語も名詞の可能性が高い
        if re.search(r'[ァ-ン]', word) and re.search(r'[一-龥]', word):
            return True
        
        # デフォルトでは2文字以上の単語を許可
        return len(word) >= 2
    
    @staticmethod
    def is_likely_verb(word):
        """単語が動詞である可能性を判定"""
        # ストップワードは除外（助動詞も含む）
        if word in STOP_WORDS:
            return False
        
        # 短すぎる単語は除外
        if len(word) < 2:
            return False
        
        # 動詞の語尾パターン
        verb_endings = [
            'する', 'せる', 'させる', 
            'れる', 'られる', 'しまう',
            'なる', 'たい', 'べき', 'ます',
            'ました', 'ません', 'ました',
            'ている', 'ていた', 'ていない'
        ]
        
        # 活用語尾パターン
        conjugation_endings = [
            'う', 'く', 'ぐ', 'す', 'つ', 'ぬ', 'ぶ', 'む', 'る',
            'った', 'いた', 'いだ', 'した', 'った', 'んだ', 'んだ', 'んだ', 'った',
            'って', 'いて', 'いで', 'して', 'って', 'んで', 'んで', 'んで', 'って'
        ]
        
        # 動詞の語尾パターンチェック
        for ending in verb_endings:
            if word.endswith(ending):
                return True
        
        # 活用語尾パターンチェック（漢字+ひらがな）
        if re.search(r'[一-龥][ぁ-ん]+$', word):
            for ending in conjugation_endings:
                if word.endswith(ending):
                    return True
        
        return False
    
    @staticmethod
    def is_likely_adjective(word):
        """単語が形容詞である可能性を判定"""
        # ストップワードは除外
        if word in STOP_WORDS:
            return False
        
        # 短すぎる単語は除外
        if len(word) < 2:
            return False
        
        # 形容詞の語尾パターン
        adj_endings = [
            'い', 'かった', 'くない', 'くて', 'ければ',
            'そう', 'すぎる', 'すぎ', 'げ', 'み',
            '的', 'らしい', 'っぽい', 'みたい'
        ]
        
        # 形容詞の特徴的な単語
        adj_words = [
            'いい', 'よい', 'すごい', 'でかい', 'ちいさい', '小さい', '大きい',
            '赤い', '青い', '白い', '黒い', '美しい', '醜い', '遅い', '速い'
        ]
        
        # 典型的な形容詞か確認
        if word in adj_words:
            return True
        
        # 形容詞の語尾パターンチェック
        for ending in adj_endings:
            if word.endswith(ending):
                # 「的」で終わる単語は名詞である可能性も高いので、追加チェック
                if ending == '的' and KeywordExtractor.is_likely_noun(word):
                    continue
                return True
        
        return False
    
    @staticmethod
    def extract_keywords(text):
        """テキストから名詞、動詞、形容詞を抽出"""
        # テキストのクリーニング
        cleaned_text = KeywordExtractor.clean_text(text)
        if not cleaned_text:
            return []
        
        # トークン化
        tokens = KeywordExtractor.tokenize_japanese(cleaned_text)
        
        # 意味のある単語（名詞、動詞、形容詞）をフィルタリング
        keywords = []
        for token in tokens:
            # ストップワードは無視
            if token in STOP_WORDS:
                continue
            
            # 1文字の非漢字は無視（漢字一文字は許可）
            if len(token) < 2 and not re.match(r'[一-龥]', token):
                continue
            
            # 名詞、動詞、形容詞のいずれかである場合のみ追加
            if (KeywordExtractor.is_likely_noun(token) or 
                KeywordExtractor.is_likely_verb(token) or 
                KeywordExtractor.is_likely_adjective(token)):
                keywords.append(token)
        
        # 重複を排除して返す
        return list(set(keywords))

class TwitterStreamListener(tweepy.StreamingClient):
    """Twitter Stream API リスナー"""
    
    def on_tweet(self, tweet):
        global tweet_count, keyword_counter, recent_tweets
        
        try:
            # ツイートカウントの更新
            tweet_count += 1
            
            # 100ツイートごとにログを出力（ログ負荷軽減のため）
            if tweet_count % 100 == 0:
                logger.info(f"Processed {tweet_count} tweets")
            
            # 日本語ツイートのみを処理
            if tweet.lang != "ja":
                return
            
            # キーワード抽出
            keywords = KeywordExtractor.extract_keywords(tweet.text)
            
            # キーワードの出現頻度を更新
            for keyword in keywords:
                keyword_counter[keyword] += 1
            
            # 上位キーワードを抽出
            top_keywords = [{"text": k, "value": v} for k, v in keyword_counter.most_common(50)]
            
            # ツイートオブジェクトの作成
            tweet_data = {
                "id": tweet.id,
                "text": tweet.text,
                "username": tweet.author.name if hasattr(tweet, 'author') and tweet.author else "Unknown",
                "screenName": tweet.author.screen_name if hasattr(tweet, 'author') and tweet.author else "unknown",
                "keywords": keywords,
                "timestamp": tweet.created_at.isoformat() if hasattr(tweet, 'created_at') and tweet.created_at else datetime.now().isoformat()
            }
            
            # 最近のツイートリストを更新
            recent_tweets.append(tweet_data)
            if len(recent_tweets) > MAX_TWEETS:
                recent_tweets = recent_tweets[-MAX_TWEETS:]
            
            # WebSocketを通じてデータを送信
            socketio.emit('keywords', {"type": "keywords", "data": top_keywords})
            socketio.emit('tweet', {"type": "tweet", "data": tweet_data})
            
            # 処理率やメモリ使用量などの統計情報を定期的に送信
            if tweet_count % 10 == 0:
                system_stats = {
                    "processingRate": f"{tweet_count // (time.time() - start_time)} ツイート/秒",
                    "memoryUsage": f"{os.getpid() // 1024 // 1024} MB",
                    "uptime": str(int(time.time() - start_time)) + "秒",
                    "analyzedTweets": str(tweet_count)
                }
                socketio.emit('stats', {"type": "stats", "data": system_stats})
        
        except Exception as e:
            logger.error(f"Error processing tweet: {e}")
    
    def on_error(self, status):
        logger.error(f"Twitter API error: {status}")
    
    def on_connection_error(self):
        logger.error("Twitter stream connection error")
        socketio.emit('error', {"type": "error", "data": {"message": "Twitter API connection error"}})
    
    def on_disconnect(self):
        logger.info("Disconnected from Twitter API")
        socketio.emit('connection', {"type": "connection", "data": {"status": "disconnected", "message": "Disconnected from Twitter API"}})

def start_twitter_stream():
    """Twitter Stream の起動と自動再接続処理"""
    global connection_attempts
    
    while True:
        try:
            connection_attempts += 1
            logger.info(f"Twitter stream connection attempt {connection_attempts}")
            
            # Twitterストリームの初期化
            stream = TwitterStreamListener(bearer_token=BEARER_TOKEN)
            
            # 既存のルールを削除
            rules = stream.get_rules()
            if rules.data:
                rule_ids = [rule.id for rule in rules.data]
                stream.delete_rules(rule_ids)
            
            # 日本語ツイートのルールを追加
            stream.add_rules(tweepy.StreamRule("lang:ja"))
            
            # ストリームフィルターを設定して接続
            # パラメータを追加することでより詳細な情報を取得できる
            # ユーザー情報やツイートの言語などが必要な場合は適宜追加
            stream.filter(
                tweet_fields=['lang', 'created_at'],
                user_fields=['name', 'username'],
                expansions=['author_id'],
                threaded=True
            )
            
            # 接続成功のメッセージ
            logger.info("Connected to Twitter API")
            socketio.emit('connection', {"type": "connection", "data": {"status": "connected", "message": "Connected to Twitter API"}})
            
            # 接続成功したら無限ループを抜ける
            break
        
        except Exception as e:
            # エラーが発生した場合は再接続を試みる
            logger.error(f"Stream error: {e}")
            socketio.emit('error', {"type": "error", "data": {"message": f"Twitter stream error: {str(e)}"}})
            
            # エクスポネンシャルバックオフ（最大2分）
            sleep_time = min(120, 2 ** (connection_attempts - 1))
            logger.info(f"Retrying in {sleep_time} seconds...")
            time.sleep(sleep_time)

# Flask ルート
@app.route('/')
def index():
    return jsonify({"status": "OK", "message": "Twitter Keyword Extractor API is running"})

@app.route('/api/keywords')
def get_keywords():
    top_keywords = [{"text": k, "value": v} for k, v in keyword_counter.most_common(50)]
    return jsonify(top_keywords)

@app.route('/api/tweets')
def get_tweets():
    return jsonify(recent_tweets)

@app.route('/api/stats')
def get_stats():
    return jsonify({
        "processingRate": f"{tweet_count // max(1, int(time.time() - start_time))} ツイート/秒",
        "memoryUsage": f"{os.getpid() // 1024 // 1024} MB",
        "uptime": str(int(time.time() - start_time)) + "秒",
        "analyzedTweets": str(tweet_count)
    })

# Socket.IO イベント
@socketio.on('connect')
def on_socket_connect():
    """クライアント接続時のハンドラ"""
    logger.info("Client connected to WebSocket")
    # 現在のキーワードリストを送信
    top_keywords = [{"text": k, "value": v} for k, v in keyword_counter.most_common(50)]
    emit('keywords', {"type": "keywords", "data": top_keywords})
    # 接続状態を送信
    emit('connection', {"type": "connection", "data": {"status": "connected", "message": "WebSocket server connected"}})

@socketio.on('reset')
def on_reset():
    """システムリセット要求のハンドラ"""
    global keyword_counter, recent_tweets, tweet_count, start_time
    keyword_counter = Counter()
    recent_tweets = []
    tweet_count = 0
    start_time = time.time()
    emit('keywords', {"type": "keywords", "data": []})
    
    # システム統計情報をリセット
    system_stats = {
        "processingRate": "0 ツイート/秒",
        "memoryUsage": "0 MB",
        "uptime": "0秒",
        "analyzedTweets": "0"
    }
    emit('stats', {"type": "stats", "data": system_stats})

@socketio.on('filters')
def on_filters(data):
    """フィルター設定のハンドラ"""
    logger.info(f"Filter update: {data}")
    # ここでTwitterストリームのフィルター設定を更新
    # 実装は現在のTwitter API v2の仕様に基づいて行う必要がある

if __name__ == "__main__":
    # 測定開始時間
    start_time = time.time()
    
    # Twitterストリームを別スレッドで開始
    if BEARER_TOKEN:
        threading.Thread(target=start_twitter_stream, daemon=True).start()
    else:
        logger.warning("Twitter stream not started: BEARER_TOKEN is missing")
    
    # ソケットサーバーを起動
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5001))
    logger.info(f"Starting SocketIO server on {host}:{port}")
    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
