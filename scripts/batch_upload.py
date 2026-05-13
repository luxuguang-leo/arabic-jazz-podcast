#!/usr/bin/env python3
"""Batch upload first 12 Arabic Jazz episodes to Qiniu, generate RSS, push to GitHub."""
import os, re, json, hashlib, subprocess, base64
import urllib.request as ur_req
import urllib.error as ur_err
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from xml.dom import minidom

# ─── Config ─────────────────────────────────────────────────
BUCKET = "jazzradio"
DOMAIN = "http://tejnectvq.hd-bkt.clouddn.com"
PAGES_URL = "https://luxuguang-leo.github.io/arabic-jazz-podcast"
ARABIC_MANIFEST = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/001-项目/波斯爵士播客/arabic-episodes.json"
)
ARABIC_STATE = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/001-项目/波斯爵士播客/arabic-upload_state.json"
)
REPO = "luxuguang-leo/arabic-jazz-podcast"

SOURCES = {
    "NafasJazz": os.path.expanduser("~/Downloads/NafasJazz"),
    "SaffronJazzLounge": os.path.expanduser("~/Downloads/SaffronJazzLounge"),
    "SantonoNoise": os.path.expanduser("~/Downloads/SantonoNoise"),
    "ArobiyyahJazz": os.path.expanduser("~/Downloads/ArobiyyahJazz"),
}

# The batch plan from release plan — first 12 episodes
BATCH_PLAN = [
    {"ep_index": 81,  "city": "Cairo",      "qiniu_key": "cairo-after-dark-arabic-jazz.m4a"},
    {"ep_index": 77,  "city": "Alexandria",   "qiniu_key": "a-jazz-evening-in-alexandria.m4a"},
    {"ep_index": 79,  "city": "Beirut",       "qiniu_key": "beirut-jazz-experience.m4a"},
    {"ep_index": 146, "city": "Beirut",       "qiniu_key": "beirut-nights-unspoken.m4a"},
    {"ep_index": 80,  "city": "Beirut",       "qiniu_key": "beirut-unsaid.m4a"},
    {"ep_index": 117, "city": "Beirut",       "qiniu_key": "arabian-oud-lofi-beirut-nights.m4a"},
    {"ep_index": 87,  "city": "Damascus",     "qiniu_key": "damascus-unsaid.m4a"},
    {"ep_index": 72,  "city": "Baghdad",      "qiniu_key": "echoes-of-baghdad.m4a"},
    {"ep_index": 90,  "city": "Casablanca",   "qiniu_key": "hidden-in-casablanca.m4a"},
    {"ep_index": 114, "city": "Tunis",        "qiniu_key": "tunis-knows-jazz.m4a"},
    {"ep_index": 107, "city": "Wahran",       "qiniu_key": "midnight-in-wahran.m4a"},
    {"ep_index": 111, "city": "Sanaa",        "qiniu_key": "remembering-old-sanaa.m4a"},
]

def load_episodes():
    with open(ARABIC_MANIFEST) as f:
        return json.load(f)

def load_state():
    if os.path.exists(ARABIC_STATE):
        with open(ARABIC_STATE) as f:
            return json.load(f)
    return {"uploaded": [], "skipped": [], "upload_dates": {}, "show_notes": {}, "city_order": [
        "Cairo","Alexandria","Beirut","Damascus","Baghdad","Casablanca","Tunis","Wahran","Sanaa"
    ]}

def save_state(state):
    with open(ARABIC_STATE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def upload_to_qiniu(ak, sk, key, filepath):
    """Upload using curl (reliable for large files)."""
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
    ET.SubElement(chan, "description").text = "Arabic jazz from Cairo to Baghdad — city by city, note by note."
    ET.SubElement(chan, "language").text = "zh"
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    ET.SubElement(chan, "lastBuildDate").text = now
    ET.SubElement(chan, "itunes:author").text = "Leo"
    ET.SubElement(chan, "itunes:summary").text = "阿拉伯爵士——从开罗到巴格达，一座城一首爵士曲。"
    ET.SubElement(chan, "itunes:image", {"href": cover_url})
    ET.SubElement(chan, "itunes:explicit").text = "no"
    owner = ET.SubElement(chan, "itunes:owner")
    ET.SubElement(owner, "itunes:name").text = "Leo"
    cat = ET.SubElement(chan, "itunes:category", {"text": "Music"})
    ET.SubElement(cat, "itunes:category", {"text": "Music Commentary"})
    ET.SubElement(chan, "atom:link", {"href": PAGES_URL + "/feed.xml", "rel": "self", "type": "application/rss+xml"})

    for ep in uploaded_eps:
        item = ET.SubElement(chan, "item")
        ET.SubElement(item, "title").text = ep["title"]
        dur_str = format_dur(ep["duration"])
        note = show_notes.get(str(ep.get("state_idx", 0)), "")
        desc_parts = [ep["title"]]
        if note:
            desc_parts.append(note)
        desc_parts.append("城市: " + ep.get("city", "") + "  |  Collection: " + ep["source"] + "  |  Duration: " + dur_str)
        desc = "\n\n".join(desc_parts)
        ET.SubElement(item, "description").text = desc
        if note:
            ET.SubElement(item, "itunes:summary").text = note
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = hashlib.md5(ep["filename"].encode()).hexdigest()
        pub = ep.get("pub_date", now)
        ET.SubElement(item, "pubDate").text = pub
        ET.SubElement(item, "enclosure", {
            "url": DOMAIN + "/" + ep["qiniu_key"],
            "length": str(ep["size"]),
            "type": "audio/mp4",
        })
        ET.SubElement(item, "itunes:duration").text = dur_str
        ET.SubElement(item, "itunes:episodeType").text = "full"

    raw = ET.tostring(rss, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")
    pretty = '<?xml version="1.0" encoding="UTF-8"?>\n' + pretty.split("?>", 1)[-1].strip() + "\n"
    return pretty

def push_to_github(filepath, token):
    """Push a file to GitHub via Contents API."""
    with open(filepath, 'rb') as f:
        content_b64 = base64.b64encode(f.read()).decode()
    remote_name = os.path.basename(filepath)

    # Try direct connection first (works from some Chinese ISPs)
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    proxy_avail = sock.connect_ex(('127.0.0.1', 58591)) == 0
    sock.close()

    if proxy_avail:
        handler = ur_req.ProxyHandler({"https": "http://127.0.0.1:58591", "http": "http://127.0.0.1:58591"})
    else:
        handler = ur_req.ProxyHandler({})
    opener = ur_req.build_opener(handler)

    # Get existing SHA if updating
    sha = None
    get_req = ur_req.Request(
        "https://api.github.com/repos/{}/contents/{}".format(REPO, remote_name),
        headers={"Authorization": "token " + token, "Accept": "application/vnd.github.v3+json"},
    )
    try:
        get_resp = opener.open(get_req, timeout=15)
        existing = json.loads(get_resp.read())
        sha = existing["sha"]
    except:
        pass  # New file, no SHA needed

    payload = {
        "message": "Add {}".format(remote_name),
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha

    data = json.dumps(payload).encode()
    put_req = ur_req.Request(
        "https://api.github.com/repos/{}/contents/{}".format(REPO, remote_name),
        data=data,
        headers={"Authorization": "token " + token, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        resp = opener.open(put_req, timeout=60)
        return resp.getcode() in (200, 201)
    except Exception as e:
        print("  GitHub push error:", e)
        return False

def enable_pages(token):
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    proxy_avail = sock.connect_ex(('127.0.0.1', 58591)) == 0
    sock.close()
    if proxy_avail:
        handler = ur_req.ProxyHandler({"https": "http://127.0.0.1:58591", "http": "http://127.0.0.1:58591"})
    else:
        handler = ur_req.ProxyHandler({})
    opener = ur_req.build_opener(handler)
    data = json.dumps({"source": {"branch": "main", "path": "/"}}).encode()
    req = ur_req.Request(
        "https://api.github.com/repos/{}/pages".format(REPO),
        data=data,
        headers={"Authorization": "token " + token, "Content-Type": "application/json", "Accept": "application/vnd.github.v3+json"},
        method="POST",
    )
    try:
        resp = opener.open(req, timeout=30)
        return resp.getcode() == 201
    except ur_err.HTTPError as e:
        body = e.read().decode()
        print("  Pages enable response:", e.code, body[:200])
        return False

def main():
    # Load credentials
    env_path = os.path.expanduser("~/.hermes/.env")
    ak = sk = github_token = None
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            if line.startswith("QINIU_ACCESS_KEY="): ak = line.strip().split("=", 1)[1]
            elif line.startswith("QINIU_SECRET_KEY="): sk = line.strip().split("=", 1)[1]
            elif line.startswith("GITHUB_TOKEN="): github_token = line.strip().split("=", 1)[1]
    if not ak or not sk:
        print("ERROR: Qiniu credentials not found in .env"); return
    if not github_token:
        print("ERROR: GITHUB_TOKEN not found in .env"); return

    episodes = load_episodes()
    state = load_state()

    # Mark BATCH_PLAN episodes as to-be-uploaded
    total = len(BATCH_PLAN)
    uploaded = 0
    failed = 0

    for batch_ep in BATCH_PLAN:
        idx = batch_ep["ep_index"]
        city = batch_ep["city"]
        qiniu_key = batch_ep["qiniu_key"]

        if idx in state["uploaded"]:
            print("[{}/{}] Already uploaded: [{}] {} — skipping".format(uploaded+1, total, idx, city))
            uploaded += 1
            continue

        ep = episodes[idx]
        src = ep["source"]
        source_dir = SOURCES.get(src)
        if not source_dir:
            print("[{}/{}] SKIP: Unknown source '{}' for [{}]".format(uploaded+1, total, src, idx))
            failed += 1
            continue

        filepath = os.path.join(source_dir, ep["filename"])
        if not os.path.isfile(filepath):
            print("[{}/{}] MISSING: {} — file not found".format(uploaded+1, total, filepath))
            failed += 1
            continue

        size_mb = os.path.getsize(filepath) / 1024 / 1024
        print("[{}/{}] Uploading [{}] {} — {} ({}MB) ...".format(uploaded+1, total, idx, city, ep["title"][:50], int(size_mb)))

        if upload_to_qiniu(ak, sk, qiniu_key, filepath):
            print("  OK: {}/{}".format(DOMAIN, qiniu_key))
            state["uploaded"].append(idx)
            if "upload_dates" not in state:
                state["upload_dates"] = {}
            state["upload_dates"][str(idx)] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
            uploaded += 1
        else:
            print("  FAIL: Upload error for [{}]".format(idx))
            failed += 1

        save_state(state)

    print("\n=== Upload Summary: {} uploaded, {} failed ===".format(uploaded, failed))

    # Build RSS with all uploaded episodes
    upload_dates = state.get("upload_dates", {})
    show_notes = state.get("show_notes", {})
    batch_lookup = {be["ep_index"]: be for be in BATCH_PLAN}

    uploaded_eps = []
    for idx in sorted(state["uploaded"]):
        ep = episodes[idx]
        ep_copy = dict(ep)
        be = batch_lookup.get(idx, {})
        ep_copy["qiniu_key"] = be.get("qiniu_key", "unknown.m4a")
        ep_copy["state_idx"] = idx
        ep_copy["city"] = be.get("city", "")
        if str(idx) in upload_dates:
            ep_copy["pub_date"] = upload_dates[str(idx)]
        uploaded_eps.append(ep_copy)

    rss_xml = generate_rss(uploaded_eps, show_notes=show_notes)
    print("RSS generated: {} episodes, {} bytes".format(len(uploaded_eps), len(rss_xml)))

    # Save locally
    rss_path = "/tmp/arabic_feed.xml"
    index_path = "/tmp/arabic_index.html"
    with open(rss_path, "w") as f:
        f.write(rss_xml)
    with open(index_path, "w") as f:
        f.write('<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;url=feed.xml"></head><body><a href="feed.xml">阿拉伯爵士电台 RSS Feed</a></body></html>\n')
    print("Saved RSS to local: {}".format(rss_path))

    # Push to GitHub
    print("\nPushing to GitHub...")
    for fp in [index_path, rss_path]:
        name = os.path.basename(fp)
        name_github = "feed.xml" if name == "arabic_feed.xml" else "index.html"
        if push_to_github(fp, github_token):
            print("  OK: {}".format(name_github))
        else:
            print("  FAIL: {}".format(name_github))

    # Enable Pages
    print("\nEnabling GitHub Pages...")
    if enable_pages(github_token):
        print("OK: GitHub Pages enabled at {}/".format(PAGES_URL))
    else:
        print("Pages may already be enabled or needs manual setup")

    # Copy to project directory
    os.makedirs(os.path.expanduser("~/Projects/arabic-jazz-podcast/"), exist_ok=True)
    for srcp, dst_name in [(rss_path, "feed.xml"), (index_path, "index.html")]:
        import shutil
        shutil.copy2(srcp, os.path.expanduser("~/Projects/arabic-jazz-podcast/" + dst_name))

    print("\n=== Done! ===")
    print("Feed URL: {}/feed.xml".format(PAGES_URL))

if __name__ == "__main__":
    main()
