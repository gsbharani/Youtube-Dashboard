from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import requests, json
from datetime import date, timedelta
from upstash_redis import Redis
from typing import Dict, Any

API_KEY = "AIzaSyCi1tZBBhnB-s_WYkwd-YHylClvdJXrOgY"

redis = Redis(
    url="https://resolved-marmot-14333.upstash.io",
    token="ATf9AAIncDJlZTgyMTdlZDRmYTA0NjU2OGY5YzNhNTdhMzRhNmM3MXAyMTQzMzM"
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_channel_id(input_str: str) -> str | None:
    if input_str.startswith("UC") and len(input_str) > 20:
        return input_str
    if "channel/" in input_str:
        return input_str.split("channel/")[1].split("?")[0].split("/")[0]
    if input_str.startswith("@"):
        handle = input_str[1:]
    elif "@" in input_str:
        handle = input_str.split("@", 1)[1].split("/")[0].split("?")[0]
    else:
        handle = input_str

    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={handle}&key={API_KEY}"
    resp = requests.get(url).json()
    try:
        return resp["items"][0]["snippet"]["channelId"]
    except:
        return None

def yt(url: str) -> Dict[Any, Any]:
    return requests.get(url).json()

# ———————— MAIN: All videos in date range (your original feature) ————————
@app.get("/channel-stats")
def channel_stats(url: str, start: str, end: str):
    channel_id = get_channel_id(url)
    if not channel_id:
        return {"error": "Channel not found"}

    chan = yt(f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id={channel_id}&key={API_KEY}")
    try:
        uploads_playlist = chan["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except:
        return {"error": "No uploads playlist"}

    videos = []
    next_page = ""
    while True:
        pl = yt(
            f"https://www.googleapis.com/youtube/v3/playlistItems?"
            f"part=snippet&maxResults=50&playlistId={uploads_playlist}&pageToken={next_page}&key={API_KEY}"
        )
        for item in pl.get("items", []):
            pub = item["snippet"]["publishedAt"][:10]
            if start <= pub <= end:
                videos.append(item["snippet"]["resourceId"]["videoId"])
        next_page = pl.get("nextPageToken", "")
        if not next_page:
            break

    stats = []
    for i in range(0, len(videos), 50):
        batch = ",".join(videos[i:i+50])
        data = yt(f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={batch}&key={API_KEY}")
        for v in data.get("items", []):
            stats.append({
                "video_id": v["id"],
                "title": v["snippet"]["title"],
                "published": v["snippet"]["publishedAt"][:10],
                "views": int(v["statistics"].get("viewCount", 0)),
                "likes": int(v["statistics"].get("likeCount", 0)),
                "comments": int(v["statistics"].get("commentCount", 0)),
            })
    return {"videos": stats}

# ———————— NEW: Last 7 videos + daily history ————————
@app.get("/channel-recent-history")
def channel_recent_history(url: str):
    channel_id = get_channel_id(url)
    if not channel_id:
        return {"error": "Channel not found"}

    chan = yt(f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id={channel_id}&key={API_KEY}")
    try:
        uploads_playlist = chan["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except:
        return {"error": "No uploads playlist"}

    # Get last 7 videos (most recent first)
    pl = yt(
        f"https://www.googleapis.com/youtube/v3/playlistItems?"
        f"part=snippet&maxResults=7&playlistId={uploads_playlist}&key={API_KEY}"
    )

    video_ids = []
    video_meta = {}

    for item in pl.get("items", []):
        vid = item["snippet"]["resourceId"]["videoId"]
        published = item["snippet"]["publishedAt"][:10]
        video_ids.append(vid)
        video_meta[vid] = {
            "title": item["snippet"]["title"],
            "published": published,
        }

    # Save today’s snapshot (this builds the history over time)
    if video_ids:
        batch = ",".join(video_ids)
        today = date.today().isoformat()
        data = yt(f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={batch}&key={API_KEY}")
        for v in data.get("items", []):
            vid = v["id"]
            stats = {
                "views": int(v["statistics"].get("viewCount", 0)),
                "likes": int(v["statistics"].get("likeCount", 0)),
                "comments": int(v["statistics"].get("commentCount", 0)),
            }
            redis.hset(f"yt_hist:{vid}", today, json.dumps(stats))

    # Build response with daily history
    histories = []
    for vid in video_ids:
        raw = redis.hgetall(f"yt_hist:{vid}")  # dict[str, str]
        history = {k: json.loads(v) for k, v in raw.items()}

        pub_date = date.fromisoformat(video_meta[vid]["published"])
        days = []
        for i in range(8):  # day 0 → day 7
            d = pub_date + timedelta(days=i)
            if d > date.today():
                break
            ds = d.isoformat()
            days.append({
                "date": ds,
                "stats": history.get(ds)  # None if no snapshot yet
            })

        histories.append({
            "video_id": vid,
            "title": video_meta[vid]["title"],
            "published": video_meta[vid]["published"],
            "days": days
        })

    return {"histories": histories}

# Optional: serve the HTML directly so you don’t have to open file manually
@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", encoding="utf-8") as f:
        return f.read()








