#!/usr/bin/env python3
"""
Arabic Jazz Podcast — Weekly Upload Pipeline
Upload to Qiniu, generate RSS, push to GitHub Pages.
Reuses Persian jazz logic but with independent state file.
"""

import os, re, json, hashlib, subprocess, urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom

# ─── Config ─────────────────────────────────────────────────
BUCKET = "jazzradio"
DOMAIN = "http://tejnectvq.hd-bkt.clouddn.com"
PAGES_URL = "https://luxuguang-leo.github.io/arabic-jazz-podcast"

VAULT = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/001-项目/波斯爵士播客")
MANIFEST = os.path.join(VAULT, "arabic-episodes.json")
STATE_FILE = os.path.join(VAULT, "arabic-upload_state.json")
REPO = "luxuguang-leo/arabic-jazz-podcast"

SOURCES = {
    "NafasJazz": os.path.expanduser("~/Downloads/NafasJazz"),
    "SaffronJazzLounge": os.path.expanduser("~/Downloads/SaffronJazzLounge"),
    "SantonoNoise": os.path.expanduser("~/Downloads/SantonoNoise"),
    "ArobiyyahJazz": os.path.expanduser("~/Downloads/ArobiyyahJazz"),
}

# ─── Helpers ────────────────────────────────────────────────
def slugify(title):
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_]+', '-', slug)
    return slug[:60].strip('-') + '.m4a'

def load_episodes():
    with open(MANIFEST) as f:
        return json.load(f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"uploaded": [], "skipped": [], "upload_dates": {}, "show_notes": {}, "city_order": [], "batch_plan": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def upload_to_qiniu(ak, sk, key, filepath):
    from qiniu import Auth
    q = Auth(ak, sk)
    token = q.upload_token(BUCKET, key, 7200)
    env = os.environ.copy()
    for k in ['https_proxy','http_proxy','HTTPS_PROXY','HTTP_PROXY','all_proxy','ALL_PROXY']:
        env.pop(k, None)
    r = subprocess.run([
        'curl', '-s', '-m', '300',
        '-F', 'token={}'.format(token),
        '-F', 'key={}'.format(key),
        '-F', 'file=@{}'.format(filepath),
        'http://upload.qiniup.com/'
    ], capture_output=True, text=True, timeout=310, env=env)
    if r.returncode == 0:
        try:
            ret = json.loads(r.stdout)
            return ret.get('key') == key
        except:
            return False
    return False

def format_dur(sec):
    if not sec or sec <= 0:
        return "00:00"
    h, r = divmod(int(sec), 3600)
    m, s = divmod(r, 60)
    if h:
        return "{}:{:02d}:{:02d}".format(h, m, s)
    return "{:d}:{:02d}".format(m, s)

def generate_rss(uploaded_eps, cover_url=None, show_notes=None):
    if show_notes is None:
        show_notes = {}
    if cover_url is None:
        cover_url = DOMAIN + "/arabic-cover.jpg"
    rss = ET.Element("rss", {
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:atom": "http://www.w3.org/2005/Atom",
        "version": "2.0",
    })
    chan = ET.SubElement(rss, "channel")
    ET.SubElement(chan, "title").text = "阿拉伯爵士电台 Arabic Nights Jazz"
    ET.SubElement(chan, "link").text = PAGES_URL
    ET.SubElement(chan, "description").text = "从开罗到巴格达，从卡萨布兰卡到萨那——一次穿越阿拉伯世界的爵士之旅。Arabic jazz from Cairo to Baghdad, Casablanca to Sana'a."
    ET.SubElement(chan, "language").text = "zh"
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    ET.SubElement(chan, "lastBuildDate").text = now
    ET.SubElement(chan, "itunes:author").text = "Leo"
    ET.SubElement(chan, "itunes:summary").text = "阿拉伯爵士电台 — 阿拉伯世界各城市的爵士之声，按城市场景组织。"
    ET.SubElement(chan, "itunes:image", {"href": cover_url})
    ET.SubElement(chan, "itunes:explicit").text = "no"
    owner = ET.SubElement(chan, "itunes:owner")
    ET.SubElement(owner, "itunes:name").text = "Leo"
    cat = ET.SubElement(chan, "itunes:category", {"text": "Music"})
    ET.SubElement(cat, "itunes:category", {"text": "Music Commentary"})
    ET.SubElement(chan, "atom:link", {"href": PAGES_URL + "/feed.xml", "rel": "self", "type": "application/rss+xml"})

    for i, ep in enumerate(uploaded_eps, 1):
        item = ET.SubElement(chan, "item")
        ET.SubElement(item, "title").text = ep["title"]
        dur_str = format_dur(ep.get("duration", 0))
        note = show_notes.get(str(ep.get("state_idx", i-1)), "")
        desc_parts = [ep["title"]]
        if note:
            desc_parts.append(note)
        desc_parts.append("Collection: " + ep.get("source", "Arabic Jazz") + "  |  Duration: " + dur_str)
        desc = "\n\n".join(desc_parts)
        ET.SubElement(item, "description").text = desc
        if note:
            ET.SubElement(item, "itunes:summary").text = note
        guid = hashlib.md5(ep["filename"].encode()).hexdigest()
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = guid
        pub = ep.get("pub_date", now)
        ET.SubElement(item, "pubDate").text = pub
        ET.SubElement(item, "enclosure", {
            "url": DOMAIN + "/" + ep['qiniu_key'],
            "length": str(ep.get("size", 0)),
            "type": "audio/mp4",
        })
        ET.SubElement(item, "itunes:duration").text = dur_str
        ET.SubElement(item, "itunes:episode").text = str(i)
        ET.SubElement(item, "itunes:episodeType").text = "full"

    raw = ET.tostring(rss, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")
    pretty = '<?xml version="1.0" encoding="UTF-8"?>\n' + pretty.split("?>", 1)[-1].strip() + "\n"
    return pretty

def push_to_github(content, token):
    import urllib.request as ur
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    proxy_available = sock.connect_ex(('127.0.0.1', 58591)) == 0
    sock.close()

    if proxy_available:
        proxy_handler = ur.ProxyHandler({"https": "http://127.0.0.1:58591", "http": "http://127.0.0.1:58591"})
    else:
        proxy_handler = ur.ProxyHandler({})
    opener = ur.build_opener(proxy_handler)

    # Get existing SHA
    url = "https://api.github.com/repos/{}/contents/feed.xml".format(REPO)
    req = ur.Request(url, headers={"Authorization": "token " + token, "Accept": "application/vnd.github.v3+json"})
    try:
        data = json.loads(opener.open(req, timeout=15).read())
        sha = data["sha"]
    except:
        sha = None

    payload = json.dumps({
        "message": "Update feed - {}".format(datetime.now().strftime("%Y-%m-%d")),
        "content": __import__('base64').b64encode(content.encode()).decode(),
    })
    if sha:
        payload_obj = json.loads(payload)
        payload_obj["sha"] = sha
        payload = json.dumps(payload_obj)

    req2 = ur.Request(url, data=payload.encode(),
        headers={"Authorization": "token " + token, "Content-Type": "application/json"},
        method="PUT")
    resp = opener.open(req2, timeout=30)
    return resp.getcode() in (200, 201)

def push_cover_to_github(filepath, token):
    import urllib.request as ur
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    proxy_available = sock.connect_ex(('127.0.0.1', 58591)) == 0
    sock.close()

    if proxy_available:
        proxy_handler = ur.ProxyHandler({"https": "http://127.0.0.1:58591", "http": "http://127.0.0.1:58591"})
    else:
        proxy_handler = ur.ProxyHandler({})
    opener = ur.build_opener(proxy_handler)

    url = "https://api.github.com/repos/{}/contents/arabic-cover.jpg".format(REPO)
    req = ur.Request(url, headers={"Authorization": "token " + token, "Accept": "application/vnd.github.v3+json"})
    try:
        data = json.loads(opener.open(req, timeout=15).read())
        sha = data["sha"]
    except:
        sha = None

    with open(filepath, "rb") as f:
        b64 = __import__('base64').b64encode(f.read()).decode()

    payload = json.dumps({"message": "Add cover", "content": b64})
    if sha:
        payload_obj = json.loads(payload)
        payload_obj["sha"] = sha
        payload = json.dumps(payload_obj)

    req2 = ur.Request(url, data=payload.encode(),
        headers={"Authorization": "token " + token, "Content-Type": "application/json"},
        method="PUT")
    resp = opener.open(req2, timeout=60)
    return resp.getcode() in (200, 201)

def push_index_html(content, token):
    import urllib.request as ur
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    proxy_available = sock.connect_ex(('127.0.0.1', 58591)) == 0
    sock.close()

    if proxy_available:
        proxy_handler = ur.ProxyHandler({"https": "http://127.0.0.1:58591", "http": "http://127.0.0.1:58591"})
    else:
        proxy_handler = ur.ProxyHandler({})
    opener = ur.build_opener(proxy_handler)

    url = "https://api.github.com/repos/{}/contents/index.html".format(REPO)
    req = ur.Request(url, headers={"Authorization": "token " + token, "Accept": "application/vnd.github.v3+json"})
    try:
        data = json.loads(opener.open(req, timeout=15).read())
        sha = data["sha"]
    except:
        sha = None

    payload = json.dumps({"message": "Add index", "content": __import__('base64').b64encode(content.encode()).decode()})
    if sha:
        payload_obj = json.loads(payload)
        payload_obj["sha"] = sha
        payload = json.dumps(payload_obj)

    req2 = ur.Request(url, data=payload.encode(),
        headers={"Authorization": "token " + token, "Content-Type": "application/json"},
        method="PUT")
    resp = opener.open(req2, timeout=30)
    return resp.getcode() in (200, 201)

def enable_github_pages(token):
    import urllib.request as ur
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    proxy_available = sock.connect_ex(('127.0.0.1', 58591)) == 0
    sock.close()

    if proxy_available:
        proxy_handler = ur.ProxyHandler({"https": "http://127.0.0.1:58591", "http": "http://127.0.0.1:58591"})
    else:
        proxy_handler = ur.ProxyHandler({})
    opener = ur.build_opener(proxy_handler)

    req = ur.Request("https://api.github.com/repos/{}/pages".format(REPO),
        data=json.dumps({"source": {"branch": "main", "path": "/"}}).encode(),
        headers={"Authorization": "token " + token, "Content-Type": "application/json", "Accept": "application/vnd.github.v3+json"},
        method="POST")
    try:
        resp = opener.open(req, timeout=30)
        return resp.getcode() in (200, 201, 204)
    except ur.HTTPError as e:
        if e.code == 409:
            print("  Pages already enabled (or no repo yet)")
            return False
        raise

# ─── Main ───────────────────────────────────────────────────
def main():
    env_path = os.path.expanduser("~/.hermes/.env")
    ak = sk = None
    github_token = None
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            if line.startswith("QINIU_ACCESS_KEY="): ak = line.strip().split("=", 1)[1]
            elif line.startswith("QINIU_SECRET_KEY="): sk = line.strip().split("=", 1)[1]
            elif line.startswith("GITHUB_TOKEN="): github_token = line.strip().split("=", 1)[1]

    if not ak or not sk:
        print("FAIL: Qiniu credentials not found in .env")
        return
    if not github_token:
        print("WARNING: GITHUB_TOKEN not set, skipping GitHub push")

    episodes = load_episodes()
    state = load_state()
    uploaded_indices = set(state["uploaded"])
    skipped_indices = set(state.get("skipped", []))

    # Batch mode: upload all episodes from batch_plan that haven't been uploaded yet
    batch_plan = state.get("batch_plan", [])
    if not state["uploaded"] and batch_plan:
        print("=== Batch upload mode: {} episodes planned".format(len(batch_plan)))
        for plan_ep in batch_plan:
            idx = plan_ep["ep_index"]
            if idx in uploaded_indices or idx in skipped_indices:
                print("  Skipping [{}] (already uploaded/skipped)".format(idx))
                continue

            ep = episodes[idx]
            source_dir = SOURCES.get(ep["source"])
            if not source_dir:
                print("  SKIP [{}]: unknown source '{}'".format(idx, ep["source"]))
                skipped_indices.add(idx)
                continue

            filepath = os.path.join(source_dir, ep["filename"])
            if not os.path.exists(filepath):
                print("  SKIP [{}]: file not found".format(idx))
                skipped_indices.add(idx)
                continue

            key = slugify(ep["title"])
            size_mb = os.path.getsize(filepath) / 1024 / 1024
            print("  [{}/{}] Uploading: {} ({}MB)".format(idx, len(episodes), ep['title'][:50], int(size_mb)))

            if upload_to_qiniu(ak, sk, key, filepath):
                print("    OK: {}/{}".format(DOMAIN, key))
                state["uploaded"].append(idx)
                if "upload_dates" not in state:
                    state["upload_dates"] = {}
                state["upload_dates"][str(idx)] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
                save_state(state)
            else:
                print("    FAIL: Upload error for [{}], stopping batch".format(idx))
                # Still save what we have so far
                save_state(state)
                return

        save_state(state)
    else:
        # Single episode mode (weekly upload)
        next_ep = None
        next_idx = None
        for idx, ep in enumerate(episodes):
            if idx not in uploaded_indices and idx not in skipped_indices:
                next_ep = ep
                next_idx = idx
                break

        if next_ep is None:
            print("All episodes uploaded!")
            return

        source_dir = SOURCES.get(next_ep["source"])
        filepath = os.path.join(source_dir, next_ep["filename"])
        key = slugify(next_ep["title"])
        size_mb = os.path.getsize(filepath) / 1024 / 1024
        print("[{}/{}] Uploading: {} ({}MB)".format(next_idx+1, len(episodes), next_ep['title'][:60], int(size_mb)))
        if upload_to_qiniu(ak, sk, key, filepath):
            print("  OK: {}/{}".format(DOMAIN, key))
            state["uploaded"].append(next_idx)
            if "upload_dates" not in state:
                state["upload_dates"] = {}
            state["upload_dates"][str(next_idx)] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
            save_state(state)
        else:
            print("  FAIL: Upload error")
            return

    # Rebuild RSS with all uploaded episodes
    upload_dates = state.get("upload_dates", {})
    uploaded_eps = []
    for idx in state["uploaded"]:
        ep = episodes[idx]
        ep_copy = dict(ep)
        ep_copy["qiniu_key"] = slugify(ep["title"])
        ep_copy["state_idx"] = idx
        if str(idx) in upload_dates:
            ep_copy["pub_date"] = upload_dates[str(idx)]
        uploaded_eps.append(ep_copy)

    rss_xml = generate_rss(uploaded_eps, show_notes=state.get("show_notes", {}))
    print("RSS rebuilt: {} episodes, {} bytes".format(len(uploaded_eps), len(rss_xml)))

    # Save local copy
    local_path = "/tmp/arabic-feed.xml"
    with open(local_path, "w") as f:
        f.write(rss_xml)
    print("  Saved locally: {}".format(local_path))

    if not github_token:
        print("  SKIP GitHub push (no token)")
        return

    # Push to GitHub
    if push_to_github(rss_xml, github_token):
        print("OK: Pushed RSS to GitHub Pages: {}/feed.xml".format(PAGES_URL))
    else:
        print("FAIL: GitHub push error")

if __name__ == "__main__":
    main()
