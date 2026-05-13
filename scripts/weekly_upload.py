#!/usr/bin/env python3
"""Arabic Jazz Podcast - Weekly: upload 1 episode, update RSS on GitHub."""

import os, re, json, hashlib, subprocess
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
    # Copy to temp to avoid special chars in filepath
    tmp_path = "/tmp/arabic_upload_temp.m4a"
    import shutil
    shutil.copy2(filepath, tmp_path)
    try:
        r = subprocess.run([
            'curl', '-s', '-m', '300',
            '-F', 'token={}'.format(token),
            '-F', 'key={}'.format(key),
            '-F', 'file=@{}'.format(tmp_path),
            'http://upload.qiniup.com/'
        ], capture_output=True, text=True, timeout=310, env=env)
        if r.returncode == 0:
            try:
                ret = json.loads(r.stdout)
                return ret.get('key') == key
            except:
                return False
        return False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

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
        cover_url = DOMAIN + "/arabic/cover.jpg"
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
        ET.SubElement(item, "description").text = "\n\n".join(desc_parts)
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

def push_to_github(content, filename, token):
    """Push file to GitHub via API (direct connection works from China)."""
    import urllib.request as ur
    import base64

    # Get SHA for existing file
    get_req = ur.Request(
        "https://api.github.com/repos/{}/contents/{}".format(REPO, filename),
        headers={"Authorization": "token " + token, "Accept": "application/vnd.github.v3+json"}
    )
    sha = None
    try:
        data = json.loads(ur.urlopen(get_req, timeout=15).read())
        sha = data.get("sha")
    except:
        pass

    payload = {
        "message": "Update - {}".format(datetime.now().strftime("%Y-%m-%d")),
        "content": base64.b64encode(content.encode()).decode(),
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha

    put_req = ur.Request(
        "https://api.github.com/repos/{}/contents/{}".format(REPO, filename),
        data=json.dumps(payload).encode(),
        headers={"Authorization": "token " + token, "Content-Type": "application/json"},
        method="PUT",
    )
    resp = ur.urlopen(put_req, timeout=30)
    return resp.getcode() in (200, 201)

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

    episodes = load_episodes()
    state = load_state()
    uploaded_indices = set(state["uploaded"])
    skipped_indices = set(state.get("skipped", []))

    # Find next unuploaded (not in batch_plan - the rest of the 168)
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

    # Upload EXACTLY ONE
    source_dir = SOURCES[next_ep["source"]]
    filepath = os.path.join(source_dir, next_ep["filename"])
    key = "arabic/" + slugify(next_ep["title"])
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

    # Rebuild RSS
    upload_dates = state.get("upload_dates", {})
    uploaded_eps = []
    for idx in sorted(state["uploaded"]):
        ep = episodes[idx]
        ep_copy = dict(ep)
        ep_copy["qiniu_key"] = slugify(ep["title"])  # no arabic/ prefix - added in generate_rss
        ep_copy["state_idx"] = idx
        if str(idx) in upload_dates:
            ep_copy["pub_date"] = upload_dates[str(idx)]
        uploaded_eps.append(ep_copy)

    rss_xml = generate_rss(uploaded_eps, show_notes=state.get("show_notes", {}))
    print("RSS rebuilt: {} episodes, {} bytes".format(len(uploaded_eps), len(rss_xml)))

    # Push to GitHub
    if github_token:
        if push_to_github(rss_xml, "feed.xml", github_token):
            print("OK: Pushed to GitHub Pages: {}/feed.xml".format(PAGES_URL))
        else:
            print("FAIL: GitHub push error")
    else:
        print("WARNING: GITHUB_TOKEN not set")

if __name__ == "__main__":
    main()
