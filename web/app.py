import os
import re

from flask import Flask, jsonify, request, send_from_directory
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

CHANNEL_ID_RE = re.compile(r"^UC[a-zA-Z0-9_-]{22}$")


def get_youtube():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("Thieu YOUTUBE_API_KEY tren server.")
    return build("youtube", "v3", developerKey=api_key)


def check_password():
    expected = os.environ.get("APP_PASSWORD")
    if not expected:
        return True
    return request.headers.get("X-App-Password", "") == expected


def parse_channel_input(raw: str) -> str:
    raw = raw.strip()
    if CHANNEL_ID_RE.match(raw):
        return raw
    m = re.search(r"youtube\.com/channel/(UC[a-zA-Z0-9_-]{22})", raw)
    if m:
        return m.group(1)
    m = re.search(r"youtube\.com/@([a-zA-Z0-9_.-]+)", raw)
    if m:
        return "@" + m.group(1)
    m = re.search(r"youtube\.com/(?:c|user)/([a-zA-Z0-9_.-]+)", raw)
    if m:
        return m.group(1)
    if raw.startswith("@"):
        return raw
    return raw


def resolve_channel(youtube, channel_input: str):
    identifier = parse_channel_input(channel_input)
    part = "snippet,contentDetails,brandingSettings,statistics"

    if CHANNEL_ID_RE.match(identifier):
        resp = youtube.channels().list(part=part, id=identifier).execute()
        if resp.get("items"):
            return resp["items"][0]

    if identifier.startswith("@"):
        resp = youtube.channels().list(part=part, forHandle=identifier).execute()
        if resp.get("items"):
            return resp["items"][0]

    resp = youtube.channels().list(part=part, forUsername=identifier).execute()
    if resp.get("items"):
        return resp["items"][0]

    resp = youtube.search().list(part="snippet", q=identifier, type="channel", maxResults=1).execute()
    if resp.get("items"):
        found_id = resp["items"][0]["id"]["channelId"]
        resp2 = youtube.channels().list(part=part, id=found_id).execute()
        if resp2.get("items"):
            return resp2["items"][0]

    return None


@app.errorhandler(Exception)
def handle_error(e):
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, HttpError):
        return jsonify({"error": f"Loi YouTube API: {e}"}), 502
    return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    if filename.startswith("api/"):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(STATIC_DIR, filename)


def require_password():
    if not check_password():
        return jsonify({"error": "Sai mat khau truy cap."}), 401
    return None


@app.route("/api/ping", methods=["POST"])
def ping():
    err = require_password()
    if err:
        return err
    return jsonify({"ok": True})


@app.route("/api/resolve_channel", methods=["POST"])
def api_resolve_channel():
    err = require_password()
    if err:
        return err

    body = request.get_json(force=True, silent=True) or {}
    channel_input = (body.get("channel") or "").strip()
    if not channel_input:
        return jsonify({"error": "Thieu thong tin kenh."}), 400

    youtube = get_youtube()
    channel = resolve_channel(youtube, channel_input)
    if not channel:
        return jsonify({"error": f"Khong tim thay kenh: {channel_input}"}), 404

    stats = channel.get("statistics", {})
    return jsonify({
        "id": channel["id"],
        "title": channel["snippet"]["title"],
        "description": channel["snippet"].get("description", ""),
        "keywords": channel.get("brandingSettings", {}).get("channel", {}).get("keywords", ""),
        "uploads_playlist": channel["contentDetails"]["relatedPlaylists"]["uploads"],
        "subscriber_count": stats.get("subscriberCount", "An"),
        "video_count": stats.get("videoCount", ""),
        "view_count": stats.get("viewCount", ""),
    })


@app.route("/api/videos_page", methods=["POST"])
def api_videos_page():
    err = require_password()
    if err:
        return err

    body = request.get_json(force=True, silent=True) or {}
    playlist_id = body.get("uploads_playlist")
    page_token = body.get("page_token")
    if not playlist_id:
        return jsonify({"error": "Thieu uploads_playlist."}), 400

    youtube = get_youtube()
    resp = youtube.playlistItems().list(
        part="contentDetails", playlistId=playlist_id, maxResults=50, pageToken=page_token,
    ).execute()

    video_ids = [item["contentDetails"]["videoId"] for item in resp.get("items", [])]
    return jsonify({"video_ids": video_ids, "next_page_token": resp.get("nextPageToken")})


@app.route("/api/videos_details", methods=["POST"])
def api_videos_details():
    err = require_password()
    if err:
        return err

    body = request.get_json(force=True, silent=True) or {}
    video_ids = (body.get("video_ids") or [])[:50]
    if not video_ids:
        return jsonify({"error": "Thieu video_ids."}), 400

    youtube = get_youtube()
    resp = youtube.videos().list(part="snippet,statistics", id=",".join(video_ids)).execute()

    videos = {}
    for item in resp.get("items", []):
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        videos[item["id"]] = {
            "url": f"https://www.youtube.com/watch?v={item['id']}",
            "published_at": snippet.get("publishedAt", ""),
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "like_count": stats.get("likeCount", "An"),
            "view_count": stats.get("viewCount", ""),
            "comment_count": stats.get("commentCount", 0),
            "tags": snippet.get("tags", []),
        }
    return jsonify({"videos": videos})


@app.route("/api/comments_page", methods=["POST"])
def api_comments_page():
    err = require_password()
    if err:
        return err

    body = request.get_json(force=True, silent=True) or {}
    video_id = body.get("video_id")
    page_token = body.get("page_token")
    include_replies = bool(body.get("include_replies"))
    if not video_id:
        return jsonify({"error": "Thieu video_id."}), 400

    youtube = get_youtube()
    try:
        resp = youtube.commentThreads().list(
            part="snippet" + (",replies" if include_replies else ""),
            videoId=video_id, maxResults=100, textFormat="plainText", pageToken=page_token,
        ).execute()
    except HttpError as e:
        reason = ""
        try:
            reason = e.error_details[0].get("reason", "")
        except Exception:
            pass
        if reason == "commentsDisabled" or e.resp.status == 403:
            return jsonify({"comments": [], "next_page_token": None, "disabled": True})
        raise

    comments = []
    for item in resp.get("items", []):
        top = item["snippet"]["topLevelComment"]["snippet"]
        comments.append({
            "type": "goc",
            "author": top.get("authorDisplayName", ""),
            "text": top.get("textDisplay", ""),
            "like_count": top.get("likeCount", 0),
            "published_at": top.get("publishedAt", ""),
        })
        if include_replies and item.get("replies"):
            for reply in item["replies"]["comments"]:
                rs = reply["snippet"]
                comments.append({
                    "type": "reply",
                    "author": rs.get("authorDisplayName", ""),
                    "text": rs.get("textDisplay", ""),
                    "like_count": rs.get("likeCount", 0),
                    "published_at": rs.get("publishedAt", ""),
                })

    return jsonify({
        "comments": comments,
        "next_page_token": resp.get("nextPageToken"),
        "disabled": False,
    })


if __name__ == "__main__":
    app.run(debug=True)
