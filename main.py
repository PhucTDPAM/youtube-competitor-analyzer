import argparse
import os
import sys
import time

import pandas as pd

import yt_core as core

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(
        description="Lay du lieu video + comment cua kenh YouTube doi thu"
    )
    parser.add_argument(
        "channel",
        help="URL kenh, @handle, hoac Channel ID cua kenh doi thu (vd: @MrBeast hoac https://www.youtube.com/@MrBeast)",
    )
    parser.add_argument(
        "--max-videos", type=int, default=0,
        help="So video moi nhat toi da can lay (mac dinh 0 = lay toan bo kenh)",
    )
    parser.add_argument(
        "--include-replies", action="store_true",
        help="Lay ca cac cau tra loi (reply) cua comment, khong chi comment goc",
    )
    parser.add_argument(
        "--max-comments-per-video", type=int, default=0,
        help="So comment toi da lay cho moi video (mac dinh 0 = lay toan bo, "
             "video co hang tram nghin comment se ton rat nhieu quota API)",
    )
    parser.add_argument(
        "--out", default="ket_qua_doi_thu.xlsx",
        help="Ten file Excel xuat ra (mac dinh: ket_qua_doi_thu.xlsx)",
    )
    args = parser.parse_args()

    api_key = core.get_api_key()
    if not api_key:
        print("Loi: Khong tim thay YOUTUBE_API_KEY.")
        print("Hay tao file .env (copy tu .env.example) va dien API key vao.")
        sys.exit(1)
    youtube = core.build_youtube_client(api_key)

    print(f"Dang tim kenh: {args.channel} ...")
    try:
        channel = core.resolve_channel_id(youtube, args.channel)
    except core.ChannelNotFoundError as e:
        print(str(e))
        sys.exit(1)

    channel_title = channel["snippet"]["title"]
    uploads_playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"Tim thay kenh: {channel_title} ({channel['id']})")

    max_videos = None if args.max_videos == 0 else args.max_videos
    print("Dang lay danh sach video (toan bo kenh neu khong gioi han)...")
    video_ids = core.get_all_video_ids(youtube, uploads_playlist, max_videos)
    print(f"Tim thay {len(video_ids)} video. Dang lay chi tiet...")

    video_details = core.get_videos_details(youtube, video_ids)

    video_rows = []
    comment_rows = []
    max_c = None if args.max_comments_per_video == 0 else args.max_comments_per_video

    for idx, vid in enumerate(video_ids, start=1):
        item = video_details.get(vid)
        if not item:
            continue
        title = item["snippet"].get("title", "")[:60]
        print(f"[{idx}/{len(video_ids)}] Dang lay comment cho video: {title}")

        comments = core.get_comments_for_video(
            youtube, vid, include_replies=args.include_replies, max_comments=max_c
        )
        comment_rows.extend(comments)
        video_rows.append(core.video_summary_row(vid, item))

        time.sleep(0.05)

    df_channel = pd.DataFrame([core.channel_summary_row(channel)])
    df_videos = pd.DataFrame(video_rows)
    df_comments = pd.DataFrame(comment_rows)

    print(f"Dang ghi ra file {args.out} ...")
    with pd.ExcelWriter(args.out, engine="openpyxl") as writer:
        df_channel.to_excel(writer, sheet_name="Kenh", index=False)
        core.autosize_columns(writer, "Kenh", df_channel)

        df_videos.to_excel(writer, sheet_name="Video", index=False)
        core.autosize_columns(writer, "Video", df_videos)

        if not df_comments.empty:
            df_comments.to_excel(writer, sheet_name="Comment", index=False)
            core.autosize_columns(writer, "Comment", df_comments)

    print("Hoan tat!")
    print(f" - So video: {len(df_videos)}")
    print(f" - So comment lay duoc: {len(df_comments)}")
    print(f" - File ket qua: {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
