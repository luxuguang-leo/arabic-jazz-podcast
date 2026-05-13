#!/usr/bin/env python3
"""Generate RSS and push to GitHub Pages (no upload needed)."""
import os, re, json, hashlib, base64, subprocess
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from xml.dom import minidom

BUCKET = "jazzradio"
DOMAIN = "http://tejnectvq.hd-bkt.clouddn.com"
PAGES_URL = "https://luxuguang-leo.github.io/arabic-jazz-podcast"
VAULT = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/001-项目/波斯爵士播客")
MANIFEST = os.path.join(VAULT, "arabic-episodes.json")
STATE_FILE = os.path.join(VAULT, "arabic-upload_state.json")
REPO = "luxuguang-leo/arabic-jazz-podcast"

# Load
with open(os.path.expanduser("~/.hermes/.env")) as f:
    for line in f:
        if line.startswith("GITHUB_TOKEN="): token = line.strip().split("=", 1)[1]

with open(MANIFEST) as f:
    episodes = json.load(f)

with open(STATE_FILE) as f:
    state = json.load(f)

def slugify(title):
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_]+', '-', slug)
    return slug[:60].strip('-') + '.m4a'

def format_dur(sec):
    if not sec or sec <= 0:
        return "00:00"
    h, r = divmod(int(sec), 3600)
    m, s = divmod(r, 60)
    if h:
        return "{}:{:02d}:{:02d}".format(h, m, s)
    return "{:d}:{:02d}".format(m, s)

def generate_rss(uploaded_eps, cover_url, show_notes):
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

# Build uploaded episodes list
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

# Generate RSS
rss_xml = generate_rss(uploaded_eps, DOMAIN + "/arabic-cover.jpg", state.get("show_notes", {}))
print("RSS generated: {} episodes, {} bytes".format(len(uploaded_eps), len(rss_xml)))

# Save local
with open("/tmp/arabic-feed.xml", "w") as f:
    f.write(rss_xml)
print("Saved locally: /tmp/arabic-feed.xml")

# Index HTML
index_html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=feed.xml"></head>
<body><a href="feed.xml">Arabic Nights Jazz — Podcast RSS Feed</a></body></html>
"""

# Push to GitHub via Contents API
def gh_put(path, content_b64, msg):
    import urllib.request as ur
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    proxy_on = sock.connect_ex(('127.0.0.1', 58591)) == 0
    sock.close()

    handler = ur.ProxyHandler({"https": "http://127.0.0.1:58591"}) if proxy_on else ur.ProxyHandler({})
    opener = ur.build_opener(handler)

    url = "https://api.github.com/repos/{}/contents/{}".format(REPO, path)

    # Get SHA if exists
    sha = None
    try:
        req = ur.Request(url, headers={"Authorization": "token " + token, "Accept": "application/vnd.github.v3+json"})
        data = json.loads(opener.open(req, timeout=15).read())
        sha = data["sha"]
    except:
        pass

    payload = json.dumps({"message": msg, "content": content_b64})
    if sha:
        payload_obj = json.loads(payload)
        payload_obj["sha"] = sha
        payload = json.dumps(payload_obj)

    req2 = ur.Request(url, data=payload.encode(),
        headers={"Authorization": "token " + token, "Content-Type": "application/json"},
        method="PUT")
    resp = opener.open(req2, timeout=60)
    return resp.getcode() in (200, 201)

# Push feed.xml
if gh_put("feed.xml", base64.b64encode(rss_xml.encode()).decode(), "Initial RSS feed"):
    print("OK: feed.xml pushed")
else:
    print("FAIL: feed.xml push")

# Push index.html
if gh_put("index.html", base64.b64encode(index_html.encode()).decode(), "Add redirect"):
    print("OK: index.html pushed")
else:
    print("FAIL: index.html push")

# Push cover
with open("/tmp/arabic-cover.jpg", "rb") as f:
    cover_b64 = base64.b64encode(f.read()).decode()
if gh_put("arabic-cover.jpg", cover_b64, "Add podcast cover"):
    print("OK: cover pushed")
else:
    print("FAIL: cover push")

# Enable GitHub Pages
try:
    import urllib.request as ur
    sock = __import__('socket').socket(__import__('socket').AF_INET, __import__('socket').SOCK_STREAM)
    sock.settimeout(1)
    proxy_on = sock.connect_ex(('127.0.0.1', 58591)) == 0
    sock.close()
    handler = ur.ProxyHandler({"https": "http://127.0.0.1:58591"}) if proxy_on else ur.ProxyHandler({})
    opener = ur.build_opener(handler)
    req = ur.Request(
        "https://api.github.com/repos/{}/pages".format(REPO),
        data=json.dumps({"source": {"branch": "main", "path": "/"}}).encode(),
        headers={"Authorization": "token " + token, "Content-Type": "application/json",
                 "Accept": "application/vnd.github.v3+json"},
        method="POST")
    resp = opener.open(req, timeout=30)
    print("OK: GitHub Pages enabled")
except ur.HTTPError as e:
    if e.code == 409:
        print("OK: Pages already enabled (or repo too new)")
    else:
        print("Pages error:", e.code)

print("\n=== DONE ===")
print("RSS: {}/feed.xml".format(PAGES_URL))
print("Cover: http://tejnectvq.hd-bkt.clouddn.com/arabic-cover.jpg")
