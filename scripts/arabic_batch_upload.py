#!/usr/bin/env python3
"""Upload files with special characters by copying to clean temp names first."""
import os, re, json, shutil, subprocess
from qiniu import Auth
from datetime import datetime, timezone

BUCKET = "jazzradio"
DOMAIN = "http://tejnectvq.hd-bkt.clouddn.com"
VAULT = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/001-项目/波斯爵士播客")
MANIFEST = os.path.join(VAULT, "arabic-episodes.json")
STATE_FILE = os.path.join(VAULT, "arabic-upload_state.json")

SOURCES = {
    "NafasJazz": os.path.expanduser("~/Downloads/NafasJazz"),
    "SaffronJazzLounge": os.path.expanduser("~/Downloads/SaffronJazzLounge"),
    "SantonoNoise": os.path.expanduser("~/Downloads/SantonoNoise"),
    "ArobiyyahJazz": os.path.expanduser("~/Downloads/ArobiyyahJazz"),
}

with open(os.path.expanduser("~/.hermes/.env")) as f:
    for line in f:
        if line.startswith("QINIU_ACCESS_KEY="): ak = line.strip().split("=", 1)[1]
        elif line.startswith("QINIU_SECRET_KEY="): sk = line.strip().split("=", 1)[1]

with open(MANIFEST) as f:
    episodes = json.load(f)

with open(STATE_FILE) as f:
    state = json.load(f)

uploaded = set(state["uploaded"])
skipped = set(state.get("skipped", []))
batch_plan = state.get("batch_plan", [])

q = Auth(ak, sk)

def slugify(title):
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_]+', '-', slug)
    return slug[:60].strip('-') + '.m4a'

for plan_ep in batch_plan:
    idx = plan_ep["ep_index"]
    if idx in uploaded or idx in skipped:
        print("  Skipping [{}] (already uploaded)".format(idx))
        continue

    ep = episodes[idx]
    source_dir = SOURCES.get(ep["source"])
    orig_path = os.path.join(source_dir, ep["filename"])

    if not os.path.exists(orig_path):
        print("  SKIP [{}]: file not found".format(idx))
        continue

    # Copy to clean temp name (avoids special chars in curl -F file=@...)
    tmp_path = "/tmp/_upload_{}.m4a".format(idx)
    shutil.copy2(orig_path, tmp_path)

    key = slugify(ep["title"])
    size_mb = os.path.getsize(tmp_path) / 1024 / 1024
    print("  [{}] Uploading: {} ({}MB)".format(idx, ep['title'][:50], int(size_mb)))

    token = q.upload_token(BUCKET, key, 7200)
    env = os.environ.copy()
    for k in ['https_proxy','http_proxy','HTTPS_PROXY','HTTP_PROXY','all_proxy','ALL_PROXY']:
        env.pop(k, None)

    r = subprocess.run([
        'curl', '-s', '-m', '300',
        '-F', 'token={}'.format(token),
        '-F', 'key={}'.format(key),
        '-F', 'file=@{}'.format(tmp_path),
        'http://upload.qiniup.com/'
    ], capture_output=True, text=True, timeout=310, env=env)

    os.unlink(tmp_path)

    if r.returncode == 0:
        try:
            ret = json.loads(r.stdout)
            if ret.get('key') == key:
                print("    OK: {}/{}".format(DOMAIN, key))
                state["uploaded"].append(idx)
                if "upload_dates" not in state:
                    state["upload_dates"] = {}
                state["upload_dates"][str(idx)] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
                with open(STATE_FILE, "w") as f:
                    json.dump(state, f, indent=2, ensure_ascii=False)
                continue
        except:
            pass
    print("    FAIL: curl exit={} stdout='{}' stderr='{}'".format(r.returncode, r.stdout[:100], r.stderr[:100]))
    break

print("\nFinal state: {} uploaded".format(len(state["uploaded"])))
print("Uploaded indices:", sorted(state["uploaded"]))
