import os
import re

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

CHANNEL_ID_RE = re.compile(r"^UC[a-zA-Z0-9_-]{22}$")


class ChannelNotFoundError(Exception):
    pass


def get_secret(name: str):
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(name)
    except Exception:
        return None


def get_api_key():
    return get_secret("YOUTUBE_API_KEY")


def build_youtube_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key)


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


def resolve_channel_id(youtube, channel_input: str) -> dict:
    identifier = parse_channel_input(channel_input)

    if CHANNEL_ID_RE.match(identifier):
        resp = youtube.channels().list(
            part="snippet,contentDetails,brandingSettings,statistics",
            id=identifier,
        ).execute()
        if resp.get("items"):
            return resp["items"][0]

    if identifier.startswith("@"):
        resp = youtube.channels().list(
            part="snippet,contentDetails,brandingSettings,statistics",
            forHandle=identifier,
        ).execute()
        if resp.get("items"):
            return resp["items"][0]

    resp = youtube.channels().list(
        part="snippet,contentDetails,brandingSettings,statistics",
        forUsername=identifier,
    ).execute()
    if resp.get("items"):
        return resp["items"][0]

    resp = youtube.search().list(
        part="snippet", q=identifier, type="channel", maxResults=1
    ).execute()
    if resp.get("items"):
        found_id = resp["items"][0]["id"]["channelId"]
        resp2 = youtube.channels().list(
            part="snippet,contentDetails,brandingSettings,statistics",
            id=found_id,
        ).execute()
        if resp2.get("items"):
            return resp2["items"][0]

    raise ChannelNotFoundError(f"Khong tim thay kenh voi thong tin: {channel_input}")


def get_all_video_ids(youtube, uploads_playlist_id: str, max_videos=None):
    video_ids = []
    page_token = None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for item in resp.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
            if max_videos and len(video_ids) >= max_videos:
                return video_ids
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def get_videos_details(youtube, video_ids):
    details = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(batch),
        ).execute()
        for item in resp.get("items", []):
            details[item["id"]] = item
    return details


def get_comments_for_video(youtube, video_id, include_replies=False, max_comments=None):
    comments = []
    page_token = None
    while True:
        try:
            resp = youtube.commentThreads().list(
                part="snippet" + (",replies" if include_replies else ""),
                videoId=video_id,
                maxResults=100,
                textFormat="plainText",
                pageToken=page_token,
            ).execute()
        except HttpError as e:
            reason = ""
            try:
                reason = e.error_details[0].get("reason", "")
            except Exception:
                pass
            if reason == "commentsDisabled" or e.resp.status == 403:
                return comments
            raise

        for item in resp.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "video_id": video_id,
                "loai": "Comment goc",
                "tac_gia": top.get("authorDisplayName", ""),
                "noi_dung": top.get("textDisplay", ""),
                "so_like": top.get("likeCount", 0),
                "ngay_dang": top.get("publishedAt", ""),
            })

            if include_replies and item.get("replies"):
                for reply in item["replies"]["comments"]:
                    rs = reply["snippet"]
                    comments.append({
                        "video_id": video_id,
                        "loai": "Tra loi",
                        "tac_gia": rs.get("authorDisplayName", ""),
                        "noi_dung": rs.get("textDisplay", ""),
                        "so_like": rs.get("likeCount", 0),
                        "ngay_dang": rs.get("publishedAt", ""),
                    })

            if max_comments and len(comments) >= max_comments:
                return comments[:max_comments]

        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return comments


def autosize_columns(writer, sheet_name, df):
    ws = writer.sheets[sheet_name]
    for idx, col in enumerate(df.columns, start=1):
        max_len = max(
            [len(str(col))] + [len(str(v)) for v in df[col].astype(str).tolist()]
        )
        ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = min(max_len + 2, 80)


def channel_summary_row(channel: dict) -> dict:
    stats = channel.get("statistics", {})
    return {
        "ten_kenh": channel["snippet"]["title"],
        "channel_id": channel["id"],
        "mo_ta_kenh": channel["snippet"].get("description", ""),
        "tu_khoa_kenh": channel.get("brandingSettings", {}).get("channel", {}).get("keywords", ""),
        "so_subscriber": stats.get("subscriberCount", "An"),
        "tong_so_video": stats.get("videoCount", ""),
        "tong_luot_xem": stats.get("viewCount", ""),
    }


def video_summary_row(video_id: str, item: dict) -> dict:
    snippet = item["snippet"]
    vstats = item.get("statistics", {})
    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "ngay_dang": snippet.get("publishedAt", ""),
        "tieu_de": snippet.get("title", ""),
        "mo_ta": snippet.get("description", ""),
        "so_like": vstats.get("likeCount", "An"),
        "so_view": vstats.get("viewCount", ""),
        "so_luong_comment": vstats.get("commentCount", 0),
        "tu_khoa_video": ", ".join(snippet.get("tags", [])),
    }
