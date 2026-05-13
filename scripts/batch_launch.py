#!/usr/bin/env python3
"""Arabic Jazz Podcast - Batch launch: upload first 12 episodes, init GitHub Pages, generate RSS."""

import os, re, json, hashlib, subprocess, urllib.parse
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from xml.dom import minidom

# ─── Config ─────────────────────────────────────────────────
BUCKET = "jazzradio"
DOMAIN = "http://tejnectvq.hd-bkt.clouddn.com"
PAGES_URL = "https://luxuguang-leo.github.io/arabic-jazz-podcast"
MANIFEST = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/001-项目/波斯爵士播客/arabic-episodes.json")
STATE_FILE = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/001-项目/波斯爵士播客/arabic-upload_state.json")
REPO = "luxuguang-leo/arabic-jazz-podcast"

SOURCES = {
    "NafasJazz":         os.path.expanduser("~/Downloads/NafasJazz"),
    "ArobiyyahJazz":     os.path.expanduser("~/Downloads/ArobiyyahJazz"),
    "SaffronJazzLounge": os.path.expanduser("~/Downloads/SaffronJazzLounge"),
    "SantonoNoise":      os.path.expanduser("~/Downloads/SantonoNoise"),
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
    return {"uploaded": [], "skipped": [], "upload_dates": {}, "show_notes": {}}

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
    h, r = divmod(int(sec), 3600)
    m, s = divmod(r, 60)
    if h:
        return "{}:{:02d}:{:02d}".format(h, m, s)
    return "{:d}:{:02d}".format(m, s)

def generate_rss(uploaded_eps, cover_url=None, show_notes=None):
    if show_notes is None:
        show_notes = {}
    if cover_url is None:
        cover_url = DOMAIN + "/cover.jpg"
    rss = ET.Element("rss", {
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:atom": "http://www.w3.org/2005/Atom",
        "version": "2.0",
    })
    chan = ET.SubElement(rss, "channel")
    ET.SubElement(chan, "title").text = "阿拉伯爵士电台 Arabic Jazz Radio"
    ET.SubElement(chan, "link").text = PAGES_URL
    ET.SubElement(chan, "description").text = "阿拉伯世界的爵士之声 — 从开罗到巴格达，从卡萨布兰卡到萨那。每周一座城市，一段音乐旅程。"
    ET.SubElement(chan, "language").text = "zh"
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    ET.SubElement(chan, "lastBuildDate").text = now
    ET.SubElement(chan, "itunes:author").text = "Leo"
    ET.SubElement(chan, "itunes:summary").text = "阿拉伯世界的爵士之声 — 从开罗到巴格达，从卡萨布兰卡到萨那。每周一座城市，一段音乐旅程。"
    ET.SubElement(chan, "itunes:image", {"href": cover_url})
    ET.SubElement(chan, "itunes:explicit").text = "no"
    owner = ET.SubElement(chan, "itunes:owner")
    ET.SubElement(owner, "itunes:name").text = "Leo"
    cat = ET.SubElement(chan, "itunes:category", {"text": "Music"})
    ET.SubElement(cat, "itunes:category", {"text": "World Music"})
    ET.SubElement(chan, "atom:link", {"href": PAGES_URL + "/feed.xml", "rel": "self", "type": "application/rss+xml"})

    for i, ep in enumerate(uploaded_eps, 1):
        item = ET.SubElement(chan, "item")
        ET.SubElement(item, "title").text = ep["title"]
        dur_str = format_dur(ep["duration"])
        note = show_notes.get(str(ep.get("state_idx", i-1)), "")
        desc_parts = [ep["title"]]
        if note:
            desc_parts.append(note)
        desc_parts.append("Collection: " + ep["source"] + "  |  Duration: " + dur_str)
        desc = "\n\n".join(desc_parts)
        ET.SubElement(item, "description").text = desc
        if note:
            ET.SubElement(item, "itunes:summary").text = note
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = hashlib.md5(ep["filename"].encode()).hexdigest()
        pub = ep.get("pub_date", now)
        ET.SubElement(item, "pubDate").text = pub
        ET.SubElement(item, "enclosure", {
            "url": DOMAIN + "/arabic/" + ep['qiniu_key'],
            "length": str(ep["size"]),
            "type": "audio/mp4",
        })
        ET.SubElement(item, "itunes:duration").text = dur_str
        ET.SubElement(item, "itunes:episode").text = str(i)
        ET.SubElement(item, "itunes:episodeType").text = "full"

    raw = ET.tostring(rss, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")
    pretty = '<?xml version="1.0" encoding="UTF-8"?>\n' + pretty.split("?>", 1)[-1].strip() + "\n"
    return pretty

def push_to_github(content, filename, token, sha=None):
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

    payload = {
        "message": "Launch Arabic Jazz Podcast - {}".format(datetime.now().strftime("%Y-%m-%d")),
        "content": __import__('base64').b64encode(content.encode()).decode(),
    }
    if sha:
        payload["sha"] = sha

    req = ur.Request(
        "https://api.github.com/repos/{}/contents/{}".format(REPO, filename),
        data=json.dumps(payload).encode(),
        headers={"Authorization": "token " + token, "Content-Type": "application/json"},
        method="PUT",
    )
    resp = opener.open(req, timeout=30)
    return resp.getcode() in (200, 201)

def get_file_sha(token, filename):
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
    try:
        req = ur.Request(
            "https://api.github.com/repos/{}/contents/{}".format(REPO, filename),
            headers={"Authorization": "token " + token, "Accept": "application/vnd.github.v3+json"},
        )
        data = json.loads(opener.open(req, timeout=15).read())
        return data["sha"]
    except:
        return None

# ─── Main ───────────────────────────────────────────────────
def main():
    # Load credentials
    env_path = os.path.expanduser("~/.hermes/.env")
    ak = sk = None
    github_token = None
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            if line.startswith("QINIU_ACCESS_KEY="): ak = line.strip().split("=", 1)[1]
            elif line.startswith("QINIU_SECRET_KEY="): sk = line.strip().split("=", 1)[1]
            elif line.startswith("GITHUB_TOKEN="): github_token = line.strip().split("=", 1)[1]

    episodes = load_episodes()
    state = load_state()
    plan = state.get("batch_plan", [])

    # The 12 episodes from batch_plan
    batch_indices = [item["ep_index"] for item in plan]

    print("=== Arabic Jazz Podcast - Batch Launch ===\n")
    print("Plan: {} episodes to upload\n".format(len(batch_indices)))

    # Step 1: Upload to Qiniu
    success_count = 0
    for idx in batch_indices:
        ep = episodes[idx]
        source_dir = SOURCES[ep["source"]]
        filepath = os.path.join(source_dir, ep["filename"])

        if not os.path.isfile(filepath):
            print("  [{}] SKIP - file not found: {}".format(idx, ep["filename"][:50]))
            continue

        # Use arabic/ prefix to namespace from Persian content
        key = "arabic/" + slugify(ep["title"])
        size_mb = os.path.getsize(filepath) / 1024 / 1024

        if idx in state["uploaded"]:
            print("  [{}] Already uploaded: {} ({}MB)".format(idx, ep["title"][:50], int(size_mb)))
            success_count += 1
            continue

        print("  [{}] Uploading: {} ({}MB)".format(idx, ep["title"][:50], int(size_mb)))
        if upload_to_qiniu(ak, sk, key, filepath):
            print("    OK: {}/{}".format(DOMAIN, key))
            state["uploaded"].append(idx)
            if "upload_dates" not in state:
                state["upload_dates"] = {}
            state["upload_dates"][str(idx)] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
            save_state(state)
            success_count += 1
        else:
            print("    FAIL: Upload error for {}".format(ep["title"][:50]))

    print("\nUploaded {}/{} episodes\n".format(success_count, len(batch_indices)))

    # Step 2: Build show_notes from batch_plan
    show_notes = {}
    for item in plan:
        show_notes[str(item["ep_index"])] = item["show_note"]
    state["show_notes"] = show_notes
    save_state(state)

    # Step 3: Build RSS
    upload_dates = state.get("upload_dates", {})
    uploaded_eps = []
    for idx in state["uploaded"]:
        ep = episodes[idx]
        ep_copy = dict(ep)
        ep_copy["qiniu_key"] = "arabic/" + slugify(ep["title"])
        ep_copy["state_idx"] = idx
        if str(idx) in upload_dates:
            ep_copy["pub_date"] = upload_dates[str(idx)]
        uploaded_eps.append(ep_copy)

    rss_xml = generate_rss(uploaded_eps, show_notes=state.get("show_notes", {}))
    print("RSS generated: {} episodes, {} bytes".format(len(uploaded_eps), len(rss_xml)))

    # Step 4: Push RSS + index.html to GitHub
    if github_token:
        # Check if repo exists by trying to get feed.xml SHA
        sha = get_file_sha(github_token, "feed.xml")

        if push_to_github(rss_xml, "feed.xml", github_token, sha):
            print("OK: feed.xml pushed")
        else:
            print("FAIL: feed.xml push error")

        # index.html
        index_html = '''<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0;url=feed.xml">
</head>
<body><a href="feed.xml">阿拉伯爵士电台 Arabic Jazz Radio - RSS Feed</a></body></html>
'''
        idx_sha = get_file_sha(github_token, "index.html")
        if push_to_github(index_html, "index.html", github_token, idx_sha):
            print("OK: index.html pushed")
        else:
            print("FAIL: index.html push error")

        print("\nDeployed: {}/feed.xml".format(PAGES_URL))
    else:
        print("WARNING: GITHUB_TOKEN not set, saving RSS locally")
        with open("/tmp/arabic-feed.xml", "w") as f:
            f.write(rss_xml)
        print("  Saved: /tmp/arabic-feed.xml")

if __name__ == "__main__":
    main()
