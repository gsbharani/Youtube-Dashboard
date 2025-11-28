"""
Daily runner script:
- reads channels from channels.txt
- for each channel, fetches video ids in last 7 days using /channel-stats
- calls /track-daily for each video
- run once per day (via Task Scheduler)
"""

import requests
import time
from datetime import datetime, timedelta

API_BASE = "http://127.0.0.1:8000"  # backend must be running locally
CHANNELS_FILE = "channels.txt"

# set range: we fetch videos uploaded in last 7 days to ensure we track recent videos as well
END = datetime.utcnow().date()
START = END - timedelta(days=7)

start_str = START.isoformat()
end_str = END.isoformat()


def read_channels():
    with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
    return lines


def main():
    channels = read_channels()
    print(f"Found {len(channels)} channels")

    for ch in channels:
        print("Processing channel:", ch)
        try:
            res = requests.get(
                f"{API_BASE}/channel-stats?url={requests.utils.requote_uri(ch)}&start={start_str}&end={end_str}"
            )
            data = res.json()
            vids = [v['video_id'] for v in data.get('videos', [])]
            print(f" Found {len(vids)} videos in last 7 days")
            for vid in vids:
                r = requests.get(f"{API_BASE}/track-daily?video_id={vid}")
                print(" tracked:", vid, r.json())
                time.sleep(1)  # polite pause
        except Exception as e:
            print("Error for channel", ch, e)

    print("Done")


if __name__ == '__main__':
    main()
