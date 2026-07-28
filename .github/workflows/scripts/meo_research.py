#!/usr/bin/env python3
"""
MEO対策投稿の自動検索・分析スクリプト
毎朝8時に実行され、X（Twitter）から伸びた投稿を収集し、
Claude APIで分析して、Discord通知と日付付きファイル保存を行います。
"""

import os
import json
import tweepy
import requests
from datetime import datetime
from anthropic import Anthropic

# 環境変数から認証情報を取得
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# 検索キーワード
KEYWORDS = [
    "MEO対策",
    "Googleマップ対策",
    "新規集客",
    "店舗集客",
    "飲食店集客",
    "美容クリニック集客",
    "新規集客獲得"
]

def get_twitter_client():
    """X APIクライアントの初期化"""
    client = tweepy.Client(
        bearer_token=TWITTER_BEARER_TOKEN,
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
        wait_on_rate_limit=True
    )
    return client

def search_posts(client, keyword):
    """キーワードで投稿を検索"""
    try:
        # 最初は表示数1万以上で検索
        response = client.search_recent_tweets(
            query=f"{keyword} -is:retweet lang:ja",
            max_results=100,
            tweet_fields=['public_metrics', 'created_at', 'author_id'],
            expansions=['author_id'],
            user_fields=['username']
        )
        
        posts = []
        if response.data:
            users = {user.id: user.username for user in response.includes['users']}
            
            for tweet in response.data:
                impressions = tweet.public_metrics.get('impression_count', 0)
                likes = tweet.public_metrics.get('like_count', 0)
                
                # 表示数1万以上、または50いいね以上のみを対象
                if impressions >= 10000 or likes >= 50:
                    posts.append({
                        'id': tweet.id,
                        'text': tweet.text,
                        'url': f"https://twitter.com/{users.get(tweet.author_id)}/status/{tweet.id}",
                        'author': users.get(tweet.author_id),
                        'likes': likes,
                        'retweets': tweet.public_metrics.get('retweet_count', 0),
                        'impressions': impressions,
                        'created_at': tweet.created_at.isoformat()
                    })
        
        return posts
    except Exception as e:
        print(f"検索エラー ({keyword}): {str(e)}")
        return []

def analyze_post_with_claude(client, post_text):
    """Claude APIを使ってなぜ伸びたかを分析"""
    try:
        message = client.messages.create(
            model="claude-opus-4-1",
            max_tokens=150,
            messages=[
                {
                    "role": "user",
                    "content": f"""以下のX投稿を分析して、「なぜこの投稿が伸びたのか」を
日本語で1~2文で簡潔に答えてください。

投稿内容：
{post_text}

分析（1~2文）："""
                }
            ]
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"分析エラー: {str(e)}")
        return "分析不可"

def send_discord_notification(title, message):
    """Discord Webhookで通知を送信"""
    try:
        payload = {
            "content": f"**{title}**\n{message}"
        }
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=10
        )
        if response.status_code != 204:
            print(f"Discord通知エラー: {response.status_code}")
    except Exception as e:
        print(f"Discord送信エラー: {str(e)}")

def save_results(posts):
    """結果をMarkdownファイルに保存"""
    today = datetime.now().strftime("%Y-%m-%d")
    results_dir = "results"
    
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    
    filepath = os.path.join(results_dir, f"{today}.md")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# MEO対策投稿リサーチ | {today}\n\n")
        f.write(f"**集計時刻**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S JST')}\n\n")
        
        if posts:
            f.write(f"**見つかった投稿数**: {len(posts)}件\n\n")
            f.write("---\n\n")
            
            for i, post in enumerate(posts, 1):
                f.write(f"## {i}. @{post['author']}\n\n")
                f.write(f"**投稿内容**\n")
                f.write(f"> {post['text'][:200]}...\n\n")
                f.write(f"**URL**: {post['url']}\n\n")
                f.write(f"**エンゲージメント**\n")
                f.write(f"- いいね: {post['likes']:,}\n")
                f.write(f"- リツイート: {post['retweets']:,}\n")
                f.write(f"- 表示数: {post['impressions']:,}\n\n")
                f.write(f"**分析**: {post['analysis']}\n\n")
                f.write("---\n\n")
        else:
            f.write("⚠️ 基準を満たす投稿は見つかりませんでした。\n")
    
    return filepath, len(posts)

def main():
    """メイン処理"""
    print(f"MEO対策投稿リサーチを開始します... ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    
    # クライアント初期化
    twitter_client = get_twitter_client()
    claude_client = Anthropic(api_key=CLAUDE_API_KEY)
    
    all_posts = []
    
    # 各キーワードで検索
    for keyword in KEYWORDS:
        print(f"検索中: {keyword}")
        posts = search_posts(twitter_client, keyword)
        
        # 各投稿をClaude APIで分析
        for post in posts:
            post['analysis'] = analyze_post_with_claude(claude_client, post['text'])
        
        all_posts.extend(posts)
    
    # 重複を除去（同じツイートが複数キーワードでヒットしている場合）
    unique_posts = {}
    for post in all_posts:
        if post['id'] not in unique_posts:
            unique_posts[post['id']] = post
    
    all_posts = list(unique_posts.values())
    
    # いいね数で降順ソート
    all_posts.sort(key=lambda x: x['likes'], reverse=True)
    
    # 結果を保存
    filepath, count = save_results(all_posts)
    print(f"結果を保存しました: {filepath} ({count}件)")
    
    # Discord通知
    if count > 0:
        message = f"本日のMEO対策投稿: **{count}件** を収集しました。\n"
        message += f"📁 詳細: {filepath}\n"
        if count > 0:
            top_post = all_posts[0]
            message += f"\n🔝 最も伸びた投稿:\n"
            message += f"@{top_post['author']} | いいね: {top_post['likes']:,}\n"
            message += f"{top_post['url']}"
    else:
        message = "本日は基準を満たす投稿が見つかりませんでした。"
    
    send_discord_notification("📊 MEO対策投稿リサーチ", message)
    print("Discord通知を送信しました。")
    print("完了！")

if __name__ == "__main__":
    main()
