import requests
import datetime
import csv
import re
import time
import os

# --- 配置 ---
# 从环境变量读取API密钥（安全做法）
# 运行前请执行: export YOUTUBE_API_KEY='你的密钥'
API_KEY = 'AIzaSyBWQG98cbU09h-Md9OhE90DmrKB-CwoiyI'

SEARCH_QUERY = 'tech news'
CSV_FILENAME = 'youtube_tech_news_real.csv'
TARGET_VIDEO_COUNT = 1000
DAYS_TO_SEARCH = 30  # 抓取过去30天的数据，确保标签稳定

# --- API端点 ---
SEARCH_URL = 'https://www.googleapis.com/youtube/v3/search'
VIDEOS_URL = 'https://www.googleapis.com/youtube/v3/videos'
CHANNELS_URL = 'https://www.googleapis.com/youtube/v3/channels'


def parse_duration(duration):
    """将ISO 8601格式的时长转换为总秒数"""
    if not duration:
        return 0
    regex = r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
    matches = re.match(regex, duration)
    if not matches:
        return 0
    parts = matches.groups()
    days = int(parts[0]) if parts[0] else 0
    hours = int(parts[1]) if parts[1] else 0
    minutes = int(parts[2]) if parts[2] else 0
    seconds = int(parts[3]) if parts[3] else 0
    return (days * 86400) + (hours * 3600) + (minutes * 60) + seconds


def fetch_with_retry(url, params, max_retries=3):
    """带重试机制的API请求"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                print("已达到最大重试次数，放弃请求。")
                return None


def batch_list(data, batch_size):
    """将列表分割成指定大小的批次"""
    for i in range(0, len(data), batch_size):
        yield data[i:i + batch_size]


# --- 1. 搜索视频 ---
print(f"--- 步骤 1: 搜索视频 (目标: {TARGET_VIDEO_COUNT}条, 过去{DAYS_TO_SEARCH}天) ---")
video_ids = []
next_page_token = None
published_after_date = (
    datetime.datetime.utcnow() - datetime.timedelta(days=DAYS_TO_SEARCH)
).isoformat("T") + "Z"

while len(video_ids) < TARGET_VIDEO_COUNT:
    search_params = {
        'part': 'snippet',
        'q': SEARCH_QUERY,
        'key': API_KEY,
        'maxResults': 50,
        'type': 'video',
        'publishedAfter': published_after_date,
        'pageToken': next_page_token,
        'relevanceLanguage': 'en',  # 优先英语内容
        'videoCategoryId': '28',    # 科技类别
    }

    search_response = fetch_with_retry(SEARCH_URL, search_params)

    if not search_response or 'items' not in search_response:
        print("无法获取数据或已到达结果末尾。")
        break

    for item in search_response['items']:
        video_ids.append(item['id']['videoId'])

    next_page_token = search_response.get('nextPageToken')
    print(f"  已收集 {len(video_ids)} 个视频ID...")

    if not next_page_token:
        print("  已无更多搜索结果。")
        break

    time.sleep(0.5)  # 避免触发频率限制

print(f"搜索完成，共找到 {len(video_ids)} 个视频ID。\n")


# --- 2. 获取视频详情 ---
print("--- 步骤 2: 获取视频详情 ---")
video_data_list = []
video_id_batches = list(batch_list(video_ids, 50))

for i, batch in enumerate(video_id_batches):
    print(f"  处理视频批次 {i + 1}/{len(video_id_batches)}...")
    video_params = {
        'part': 'snippet,statistics,contentDetails,status',
        'id': ','.join(batch),
        'key': API_KEY,
    }
    videos_response = fetch_with_retry(VIDEOS_URL, video_params)
    if not videos_response or 'items' not in videos_response:
        continue

    for item in videos_response['items']:
        snippet = item.get('snippet', {})
        stats = item.get('statistics', {})
        content = item.get('contentDetails', {})
        status = item.get('status', {})

        # 跳过没有统计数据的视频（可能是私密视频）
        if not stats.get('viewCount'):
            continue

        video_data_list.append({
            'video_id': item.get('id'),
            'published_at': snippet.get('publishedAt'),
            'channel_id': snippet.get('channelId'),
            'title': snippet.get('title'),
            'description': snippet.get('description', ''),
            'tags': ','.join(snippet.get('tags', [])),
            'category_id': snippet.get('categoryId'),
            'language': snippet.get('defaultAudioLanguage', ''),
            'view_count': int(stats.get('viewCount', 0)),
            'like_count': int(stats.get('likeCount', 0)),
            'comment_count': int(stats.get('commentCount', 0)),
            'duration_seconds': parse_duration(content.get('duration')),
            'definition': content.get('definition', ''),
            'caption': content.get('caption', 'false'),
        })

    time.sleep(0.5)

print(f"获取了 {len(video_data_list)} 个视频的详情。\n")


# --- 3. 获取频道详情 ---
print("--- 步骤 3: 获取频道详情 ---")
channel_ids = list(set([d['channel_id'] for d in video_data_list if d.get('channel_id')]))
channel_data = {}
channel_id_batches = list(batch_list(channel_ids, 50))

for i, batch in enumerate(channel_id_batches):
    print(f"  处理频道批次 {i + 1}/{len(channel_id_batches)}...")
    channel_params = {
        'part': 'snippet,statistics',
        'id': ','.join(batch),
        'key': API_KEY,
    }
    channels_response = fetch_with_retry(CHANNELS_URL, channel_params)
    if not channels_response or 'items' not in channels_response:
        continue

    for item in channels_response['items']:
        channel_id = item.get('id')
        snippet = item.get('snippet', {})
        stats = item.get('statistics', {})
        channel_data[channel_id] = {
            'channel_name': snippet.get('title'),
            'channel_published_at': snippet.get('publishedAt'),
            'subscriber_count': int(stats.get('subscriberCount', 0)),
            'channel_view_count': int(stats.get('viewCount', 0)),
            'video_count': int(stats.get('videoCount', 0)),
        }

    time.sleep(0.5)

print(f"获取了 {len(channel_data)} 个频道的详情。\n")


# --- 4. 合并并写入CSV ---
print(f"--- 步骤 4: 写入 {CSV_FILENAME} ---")
csv_headers = [
    'video_id', 'title', 'published_at', 'view_count', 'like_count',
    'comment_count', 'duration_seconds', 'tags', 'category_id', 'language',
    'definition', 'caption', 'channel_id', 'channel_name',
    'channel_published_at', 'subscriber_count', 'channel_view_count',
    'video_count', 'description',
]

try:
    with open(CSV_FILENAME, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers, extrasaction='ignore')
        writer.writeheader()
        for v_data in video_data_list:
            ch_data = channel_data.get(v_data.get('channel_id'), {})
            combined_data = {**v_data, **ch_data}
            writer.writerow(combined_data)
    print(f"成功写入 {len(video_data_list)} 条记录。")
except IOError as e:
    print(f"写入CSV时出错: {e}")

print("--- 全部完成! ---")
print(f"\n提示: 请将 {CSV_FILENAME} 放在notebook同目录下再运行模型训练。")
