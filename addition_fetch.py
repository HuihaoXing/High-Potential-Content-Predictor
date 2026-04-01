import requests
import datetime
import csv
import re
import time
import os
import sys

# --- 配置 ---
API_KEY = 'AIzaSyCuAhftEIqtTujBo71oJ5RG6C1KqmMRhwY'

CSV_FILENAME = 'youtube_tech_news_real.csv'  # 追加到同一个文件
TARGET_NEW_VIDEOS = 1200   # 目标新增数量（已有225，凑到1000+）
DAYS_TO_SEARCH = 30

# 多关键词 + 多排序，扩大覆盖面
KEYWORDS = [
    # 科技大佬 / 思想
    'Sam Altman interview 2026',
    'Demis Hassabis DeepMind interview',
    'Andrew Ng AI agent talk',
    'Yann LeCun AGI debate',
    'Elon Musk'

    # Agent
    'OpenClaw',

    # AI Coding
    'AI coding agent',

    # 医疗 / 生物
    'AlphaFold drug discovery',
    'Neuralink human trial',
    'OpenEvidence medical AI',

    # 商业趋势
    'AI startup trends 2026',
    'AI vs SaaS future',
]

ORDER_MODES = ['date', 'relevance']  # 两种排序各搜一轮

# --- API端点 ---
SEARCH_URL   = 'https://www.googleapis.com/youtube/v3/search'
VIDEOS_URL   = 'https://www.googleapis.com/youtube/v3/videos'
CHANNELS_URL = 'https://www.googleapis.com/youtube/v3/channels'


def parse_duration(duration):
    if not duration:
        return 0
    regex = r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
    matches = re.match(regex, duration)
    if not matches:
        return 0
    parts = matches.groups()
    days    = int(parts[0]) if parts[0] else 0
    hours   = int(parts[1]) if parts[1] else 0
    minutes = int(parts[2]) if parts[2] else 0
    seconds = int(parts[3]) if parts[3] else 0
    return (days * 86400) + (hours * 3600) + (minutes * 60) + seconds


def fetch_with_retry(url, params, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params)
            # 配额耗尽时直接退出，不要浪费重试
            if response.status_code == 403:
                data = response.json()
                reason = data.get('error', {}).get('errors', [{}])[0].get('reason', '')
                if reason == 'quotaExceeded':
                    print('\n API配额已耗尽，请明天再运行。已保存的数据不会丢失。')
                    sys.exit(0)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"  请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None


def batch_list(data, batch_size):
    for i in range(0, len(data), batch_size):
        yield data[i:i + batch_size]


# --- 0. 加载已有video_id，避免重复抓取 ---
existing_ids = set()
file_exists = os.path.exists(CSV_FILENAME)
if file_exists:
    with open(CSV_FILENAME, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing_ids.add(row['video_id'])
    print(f'已有数据: {len(existing_ids)} 条，将跳过这些video_id')
else:
    print(f'未找到 {CSV_FILENAME}，将新建文件')

print(f'目标新增: {TARGET_NEW_VIDEOS} 条\n')


# --- 1. 搜索新video_id ---
print('--- 步骤 1: 搜索新视频 ---')
new_video_ids = []
published_after = (
    datetime.datetime.utcnow() - datetime.timedelta(days=DAYS_TO_SEARCH)
).isoformat("T") + "Z"

for keyword in KEYWORDS:
    for order in ORDER_MODES:
        if len(new_video_ids) >= TARGET_NEW_VIDEOS * 1.5:
            break

        print(f'  搜索: "{keyword}" | 排序: {order}')
        next_page_token = None
        keyword_count = 0

        while True:
            search_params = {
                'part': 'snippet',
                'q': keyword,
                'key': API_KEY,
                'maxResults': 50,
                'type': 'video',
                'publishedAfter': published_after,
                'order': order,
                'relevanceLanguage': 'en',
                'videoCategoryId': '28',
                'pageToken': next_page_token,
            }
            search_response = fetch_with_retry(SEARCH_URL, search_params)

            if not search_response or 'items' not in search_response:
                break

            for item in search_response['items']:
                vid = item['id']['videoId']
                if vid not in existing_ids and vid not in new_video_ids:
                    new_video_ids.append(vid)
                    keyword_count += 1

            next_page_token = search_response.get('nextPageToken')
            if not next_page_token:
                break

            time.sleep(0.3)

        print(f'    新增 {keyword_count} 个ID（累计: {len(new_video_ids)}）')

new_video_ids = new_video_ids[:TARGET_NEW_VIDEOS]
print(f'\n共找到 {len(new_video_ids)} 个新视频ID\n')

if not new_video_ids:
    print('没有新视频，退出。')
    sys.exit(0)


# --- 2. 获取视频详情（只处理新ID）---
print('--- 步骤 2: 获取视频详情 ---')
video_data_list = []
for i, batch in enumerate(batch_list(new_video_ids, 50)):
    print(f'  处理批次 {i + 1}/{(len(new_video_ids) - 1) // 50 + 1}...')
    video_params = {
        'part': 'snippet,statistics,contentDetails,status',
        'id': ','.join(batch),
        'key': API_KEY,
    }
    resp = fetch_with_retry(VIDEOS_URL, video_params)
    if not resp or 'items' not in resp:
        continue

    for item in resp['items']:
        snippet = item.get('snippet', {})
        stats   = item.get('statistics', {})
        content = item.get('contentDetails', {})

        if not stats.get('viewCount'):
            continue

        video_data_list.append({
            'video_id':         item.get('id'),
            'published_at':     snippet.get('publishedAt'),
            'channel_id':       snippet.get('channelId'),
            'title':            snippet.get('title'),
            'description':      snippet.get('description', ''),
            'tags':             ','.join(snippet.get('tags', [])),
            'category_id':      snippet.get('categoryId'),
            'language':         snippet.get('defaultAudioLanguage', ''),
            'view_count':       int(stats.get('viewCount', 0)),
            'like_count':       int(stats.get('likeCount', 0)),
            'comment_count':    int(stats.get('commentCount', 0)),
            'duration_seconds': parse_duration(content.get('duration')),
            'definition':       content.get('definition', ''),
            'caption':          content.get('caption', 'false'),
        })

    time.sleep(0.3)

print(f'获取了 {len(video_data_list)} 条视频详情\n')


# --- 3. 获取频道详情（只处理新频道）---
print('--- 步骤 3: 获取频道详情 ---')

existing_channel_ids = set()
if file_exists:
    with open(CSV_FILENAME, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('channel_id'):
                existing_channel_ids.add(row['channel_id'])

new_channel_ids = list(set(
    d['channel_id'] for d in video_data_list
    if d.get('channel_id') and d['channel_id'] not in existing_channel_ids
))
print(f'  需要获取 {len(new_channel_ids)} 个新频道信息')

channel_data = {}
for i, batch in enumerate(batch_list(new_channel_ids, 50)):
    channel_params = {
        'part': 'snippet,statistics',
        'id': ','.join(batch),
        'key': API_KEY,
    }
    resp = fetch_with_retry(CHANNELS_URL, channel_params)
    if not resp or 'items' not in resp:
        continue

    for item in resp['items']:
        cid     = item.get('id')
        snippet = item.get('snippet', {})
        stats   = item.get('statistics', {})
        channel_data[cid] = {
            'channel_name':         snippet.get('title'),
            'channel_published_at': snippet.get('publishedAt'),
            'subscriber_count':     int(stats.get('subscriberCount', 0)),
            'channel_view_count':   int(stats.get('viewCount', 0)),
            'video_count':          int(stats.get('videoCount', 0)),
        }

    time.sleep(0.3)

print(f'获取了 {len(channel_data)} 个新频道的详情\n')


# --- 4. 追加写入CSV ---
print(f'--- 步骤 4: 追加写入 {CSV_FILENAME} ---')
csv_headers = [
    'video_id', 'title', 'published_at', 'view_count', 'like_count',
    'comment_count', 'duration_seconds', 'tags', 'category_id', 'language',
    'definition', 'caption', 'channel_id', 'channel_name',
    'channel_published_at', 'subscriber_count', 'channel_view_count',
    'video_count', 'description',
]

write_mode   = 'a' if file_exists else 'w'
write_header = not file_exists

try:
    with open(CSV_FILENAME, write_mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers, extrasaction='ignore')
        if write_header:
            writer.writeheader()
        for v_data in video_data_list:
            ch_data = channel_data.get(v_data.get('channel_id'), {})
            writer.writerow({**v_data, **ch_data})

    print(f'新增 {len(video_data_list)} 条，文件总计约 {len(existing_ids) + len(video_data_list)} 条')
except IOError as e:
    print(f'写入出错: {e}')

print('--- 完成 ---')