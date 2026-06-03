#!/usr/bin/env python3
"""
微信公众号推送脚本 — 阿拉伯爵士电台
将最新一集播客转为微信图文消息，推送给订阅用户。

用法:
  python3 wechat_push.py preview          # 预览最新一集的内容（不推送）
  python3 wechat_push.py publish [index]  # 推送到公众号（默认推送最新一集）
  python3 wechat_push.py list             # 列出所有已发布的集数

环境变量（在 ~/.hermes/.env 中配置）:
  WX_APPID=wx39931cbd5b262fcc
  WX_APPSECRET=93c462cf037b07d853ee015a525aab01
"""

import os, sys, json, hashlib, time
import requests

APPID = os.environ.get("WX_APPID", "wx39931cbd5b262fcc")
APPSECRET = os.environ.get("WX_APPSECRET", "93c462cf037b07d853ee015a525aab01")
FEED_PATH = os.path.expanduser("~/Projects/arabic-jazz-podcast/feed.xml")
TOKEN_FILE = os.path.expanduser("~/.hermes/wx_token.json")

SEASONS = {
    1: "S1 尼罗河爵士",
    2: "S2 黎凡特",
    3: "S3 两河爵士",
    4: "S4 马格里布",
    5: "S5 番外",
}

def get_access_token():
    """获取或刷新 access_token"""
    # 检查本地缓存的 token 是否有效
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        if data.get("expires_at", 0) > time.time() + 60:
            return data["access_token"]

    url = f"https://api.weixin.qq.com/cgi-bin/token"
    params = {
        "grant_type": "client_credential",
        "appid": APPID,
        "secret": APPSECRET,
    }
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    if "access_token" not in data:
        raise Exception(f"获取 token 失败: {data}")

    token = data["access_token"]
    expires_in = data.get("expires_in", 7200)
    
    # 缓存到本地
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": token, "expires_at": time.time() + expires_in}, f)
    
    return token

def parse_episodes():
    """从 feed.xml 解析所有节目"""
    import xml.etree.ElementTree as ET
    tree = ET.parse(FEED_PATH)
    root = tree.getroot()
    channel = root.find("channel")
    
    episodes = []
    for item in channel.findall("item"):
        title = item.findtext("title", "")
        desc = item.findtext("description", "")
        pub_date = item.findtext("pubDate", "")
        duration = item.findtext("itunes:duration", "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration")
        if not duration:
            duration = item.findtext("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration", "")
        season = item.findtext("{http://www.itunes.com/dtds/podcast-1.0.dtd}season", "")
        episode = item.findtext("{http://www.itunes.com/dtds/podcast-1.0.dtd}episode", "")
        
        episodes.append({
            "title": title,
            "desc": desc,
            "pub_date": pub_date,
            "duration": duration,
            "season": season,
            "episode": episode,
        })
    return episodes

def format_article(ep):
    """将一集播客格式化为微信图文消息"""
    title = ep["title"]
    desc = ep["desc"]
    
    # 提取城市和经典语录
    lines = desc.split("\n")
    city_line = ""
    quote_line = ""
    music_info = ""
    
    for line in lines:
        line = line.strip()
        if line.startswith("📍"):
            city_line = line
        elif line.startswith("「") and line.endswith("」"):
            quote_line = line
        elif line.startswith("Collection:"):
            music_info = line
    
    # 构造推文内容
    body_parts = [city_line]
    
    # 去掉标题行、城市行和引用行，剩下的就是正文
    main_text = []
    for line in lines:
        stripped = line.strip()
        if (stripped.startswith("[") or 
            stripped.startswith("📍") or 
            stripped.startswith("「") or
            stripped.startswith("Collection:") or
            not stripped):
            continue
        main_text.append(stripped)
    
    if main_text:
        body_parts.append("\n".join(main_text))
    if quote_line:
        body_parts.append(f"\n{quote_line}")
    if music_info:
        body_parts.append(f"\n\n🎵 {music_info}")
    
    body = "\n\n".join(body_parts)
    
    # 删除 HTML 实体
    body = body.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    clean_title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    
    return {
        "title": clean_title[:64],
        "body": body,
        "digest": body[:120].replace("\n", " ") + "…" if len(body) > 120 else body,
    }

def upload_image(token, image_url):
    """上传封面图到微信素材库"""
    # 先下载图片
    resp = requests.get(image_url, timeout=15)
    if resp.status_code != 200:
        print(f"  ⚠ 下载封面失败: {image_url}")
        return None
    
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material"
    files = {
        "media": ("cover.jpg", resp.content, "image/jpeg")
    }
    params = {"access_token": token, "type": "image"}
    r = requests.post(url, params=params, files=files, timeout=15)
    data = r.json()
    if "media_id" in data:
        return data["media_id"]
    print(f"  ⚠ 上传封面失败: {data}")
    return None

def create_draft(token, article, thumb_media_id=None):
    """创建草稿"""
    news_item = {
        "title": article["title"],
        "digest": article["digest"],
        "content": article["body"],
        "need_open_comment": 1,
        "only_fans_can_comment": 0,
    }
    if thumb_media_id:
        news_item["thumb_media_id"] = thumb_media_id
    
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add"
    payload = {
        "articles": [news_item]
    }
    params = {"access_token": token}
    r = requests.post(url, params=params, json=payload, timeout=10)
    data = r.json()
    return data

def publish_draft(token, media_id):
    """发布草稿"""
    url = f"https://api.weixin.qq.com/cgi-bin/freepublish/submit"
    payload = {"media_id": media_id}
    params = {"access_token": token}
    r = requests.post(url, params=params, json=payload, timeout=10)
    data = r.json()
    return data

def preview(ep_index=None):
    """预览节目内容"""
    episodes = parse_episodes()
    if ep_index is not None and 0 <= ep_index < len(episodes):
        ep = episodes[ep_index]
    else:
        ep = episodes[-1]  # 最新一集
    
    article = format_article(ep)
    
    print("=" * 50)
    print("📻 阿拉伯爵士电台 · 公众号推文预览")
    print("=" * 50)
    print(f"\n📌 标题: {article['title']}")
    print(f"\n📝 摘要: {article['digest']}")
    print(f"\n📄 正文:\n{article['body']}")
    print("\n" + "=" * 50)
    print(f"\n⚠️  以上内容请确认，确认后在 Obsidian 存档。")
    print(f"   满意后执行: python3 wechat_push.py publish [{ep_index or 'last'}]")
    
    return article

def publish(ep_index=None):
    """推送到公众号"""
    token = get_access_token()
    episodes = parse_episodes()
    
    if ep_index is not None and 0 <= ep_index < len(episodes):
        ep = episodes[ep_index]
    else:
        ep = episodes[-1]
    
    article = format_article(ep)
    
    print(f"📤 推送: {article['title']}")
    
    # 上传封面
    print("  ⬆ 上传封面...")
    thumb_id = upload_image(token, "http://pub-be12e0f10bed438db17fc28b4cad43dd.r2.dev/arabic-cover.jpg")
    if thumb_id:
        print(f"  ✓ 封面上传成功")
    
    # 创建草稿
    print("  📝 创建草稿...")
    draft_resp = create_draft(token, article, thumb_id)
    if "media_id" not in draft_resp:
        print(f"  ✗ 创建草稿失败: {draft_resp}")
        return False
    
    media_id = draft_resp["media_id"]
    print(f"  ✓ 草稿创建成功: {media_id}")
    
    # 发布
    print("  📨 发布中...")
    pub_resp = publish_draft(token, media_id)
    if pub_resp.get("errcode", -1) != 0:
        print(f"  ✗ 发布失败: {pub_resp}")
        return False
    
    print(f"  ✓ 发布成功！")
    print(f"\n🎉 推文已发送给订阅用户")
    return True

def list_episodes():
    """列出所有节目"""
    episodes = parse_episodes()
    print(f"📻 阿拉伯爵士电台 · 共 {len(episodes)} 集\n")
    for i, ep in enumerate(episodes):
        season_tag = ep["season"]
        if season_tag and season_tag in SEASONS:
            season_name = SEASONS[int(season_tag)]
        else:
            season_name = f"S{season_tag}" if season_tag else ""
        
        title_clean = ep["title"].replace("&amp;", "&")
        print(f"  [{i}] {season_name} {title_clean[:50]}")
    
    print(f"\n推送最新一集: python3 wechat_push.py publish")
    print(f"推送指定集:   python3 wechat_push.py publish <编号>")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 wechat_push.py [preview|publish|list] [index]")
        sys.exit(1)
    
    action = sys.argv[1]
    index = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    if action == "preview":
        preview(index)
    elif action == "publish":
        publish(index)
    elif action == "list":
        list_episodes()
    else:
        print(f"未知操作: {action}")
