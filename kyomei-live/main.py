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
        socketio.sleep(120)  # 2分間隔に変更