import io

import pandas as pd
import streamlit as st

import yt_core as core

st.set_page_config(page_title="YouTube Competitor Analyzer", layout="wide")

APP_PASSWORD = core.get_secret("APP_PASSWORD")

if APP_PASSWORD:
    if "authed" not in st.session_state:
        st.session_state.authed = False

    if not st.session_state.authed:
        st.title("Đăng nhập")
        with st.form("login_form"):
            pw = st.text_input("Mật khẩu truy cập", type="password")
            submitted = st.form_submit_button("Vào ứng dụng")
        if submitted:
            if pw == APP_PASSWORD:
                st.session_state.authed = True
                st.rerun()
            else:
                st.error("Sai mật khẩu.")
        st.stop()

if "scan" not in st.session_state:
    st.session_state.scan = None
if "result" not in st.session_state:
    st.session_state.result = None

st.title("Phân tích kênh YouTube đối thủ")
st.caption("Lấy ngày đăng, tiêu đề, mô tả, comment, like, từ khoá kênh, từ khoá video qua YouTube Data API v3.")

api_key = core.get_api_key()
if not api_key:
    st.error(
        "Không tìm thấy YOUTUBE_API_KEY. Hãy tạo file .env (copy từ .env.example) "
        "và dán API key vào, rồi khởi động lại ứng dụng."
    )
    st.stop()

youtube = core.build_youtube_client(api_key)

FIELD_OPTIONS = [
    "Ngày đăng",
    "Tiêu đề",
    "Mô tả",
    "Comment",
    "Like",
    "Từ khoá kênh",
    "Từ khoá video",
]
FIELD_TO_VIDEO_COL = {
    "Ngày đăng": "ngay_dang",
    "Tiêu đề": "tieu_de",
    "Mô tả": "mo_ta",
    "Like": "so_like",
    "Từ khoá video": "tu_khoa_video",
}

with st.form("scan_form"):
    channel_input = st.text_input(
        "Link kênh / @handle / Channel ID của đối thủ",
        placeholder="https://www.youtube.com/@tenkenh hoặc @tenkenh",
    )

    st.markdown("**Chọn trường dữ liệu muốn lấy**")
    selected_fields = st.multiselect(
        "Trường dữ liệu",
        options=FIELD_OPTIONS,
        default=FIELD_OPTIONS,
        label_visibility="collapsed",
        help="Bỏ chọn 'Comment' nếu không cần nội dung comment — sẽ tiết kiệm rất nhiều quota API "
             "vì lấy comment tốn nhiều lượt gọi API nhất.",
    )

    col1, col2 = st.columns(2)
    with col1:
        limit_videos = st.checkbox("Giới hạn số video", value=False)
        max_videos_input = st.number_input(
            "Số video mới nhất muốn lấy", min_value=1, value=50, step=10,
            disabled=not limit_videos,
        )
    with col2:
        include_replies = st.checkbox("Lấy cả reply (trả lời comment)", value=False)
        limit_comments = st.checkbox("Giới hạn số comment / video", value=False)
        max_comments_input = st.number_input(
            "Số comment tối đa mỗi video", min_value=10, value=300, step=50,
            disabled=not limit_comments,
        )
    scan_submitted = st.form_submit_button("1. Tìm kênh & Quét quy mô")

if scan_submitted:
    if not channel_input.strip():
        st.warning("Vui lòng nhập link/@handle/Channel ID của kênh.")
    elif not selected_fields:
        st.warning("Vui lòng chọn ít nhất một trường dữ liệu.")
    else:
        with st.spinner("Đang tìm kênh và quét danh sách video..."):
            try:
                channel = core.resolve_channel_id(youtube, channel_input)
            except core.ChannelNotFoundError as e:
                st.error(str(e))
                st.session_state.scan = None
            else:
                uploads_playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
                max_videos = int(max_videos_input) if limit_videos else None
                video_ids = core.get_all_video_ids(youtube, uploads_playlist, max_videos)
                video_details = core.get_videos_details(youtube, video_ids)

                total_comments_est = sum(
                    int(video_details[v]["statistics"].get("commentCount", 0))
                    for v in video_ids if v in video_details
                )

                st.session_state.scan = {
                    "channel": channel,
                    "video_ids": video_ids,
                    "video_details": video_details,
                    "total_comments_est": total_comments_est,
                    "include_replies": include_replies,
                    "max_comments": int(max_comments_input) if limit_comments else None,
                    "fields": selected_fields,
                }
                st.session_state.result = None

scan = st.session_state.scan
if scan:
    channel = scan["channel"]
    stats = channel.get("statistics", {})
    fetch_comments = "Comment" in scan["fields"]

    st.success(f"Tìm thấy kênh: **{channel['snippet']['title']}** ({channel['id']})")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Subscriber", stats.get("subscriberCount", "Ẩn"))
    c2.metric("Tổng video kênh", stats.get("videoCount", "N/A"))
    c3.metric("Video sẽ lấy", len(scan["video_ids"]))
    c4.metric("Ước tính tổng comment", f"{scan['total_comments_est']:,}" if fetch_comments else "Không lấy")

    if fetch_comments:
        est_calls = scan["total_comments_est"] / 100 + len(scan["video_ids"])
        if scan["total_comments_est"] > 20000:
            st.warning(
                f"Ước tính cần khoảng **{int(est_calls):,} lượt gọi API** để lấy hết comment "
                f"({scan['total_comments_est']:,} comment). Quota miễn phí là 10.000 unit/ngày — "
                "nếu số này lớn, cân nhắc bật giới hạn số comment/video ở bước trên, hoặc bỏ chọn "
                "'Comment' trong danh sách trường dữ liệu."
            )
    else:
        st.info("Bạn đã bỏ chọn 'Comment' — ứng dụng sẽ không gọi API lấy nội dung comment, giúp tiết kiệm quota.")

    if st.button("2. Lấy dữ liệu & Xuất Excel", type="primary"):
        video_ids = scan["video_ids"]
        video_details = scan["video_details"]
        fields = scan["fields"]

        progress = st.progress(0.0)
        status = st.empty()

        video_rows = []
        comment_rows = []

        for idx, vid in enumerate(video_ids, start=1):
            item = video_details.get(vid)
            if not item:
                continue
            title = item["snippet"].get("title", "")[:70]

            if fetch_comments:
                status.text(f"[{idx}/{len(video_ids)}] Đang lấy comment: {title}")
                comments = core.get_comments_for_video(
                    youtube, vid,
                    include_replies=scan["include_replies"],
                    max_comments=scan["max_comments"],
                )
                comment_rows.extend(comments)
            else:
                status.text(f"[{idx}/{len(video_ids)}] Đang xử lý: {title}")

            video_rows.append(core.video_summary_row(vid, item))
            progress.progress(idx / len(video_ids))

        status.text("Đang tạo file Excel...")

        df_channel_full = pd.DataFrame([core.channel_summary_row(channel)])
        df_videos_full = pd.DataFrame(video_rows)
        df_comments = pd.DataFrame(comment_rows) if fetch_comments else pd.DataFrame()

        video_cols = ["video_id", "url"] + [
            FIELD_TO_VIDEO_COL[f] for f in fields if f in FIELD_TO_VIDEO_COL
        ]
        if fetch_comments:
            video_cols.append("so_luong_comment")
        df_videos = df_videos_full[video_cols]

        channel_cols = ["ten_kenh", "channel_id", "so_subscriber", "tong_so_video", "tong_luot_xem"]
        if "Từ khoá kênh" in fields:
            channel_cols.insert(2, "tu_khoa_kenh")
        if "Mô tả" in fields:
            channel_cols.insert(2, "mo_ta_kenh")
        df_channel = df_channel_full[channel_cols]

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_channel.to_excel(writer, sheet_name="Kenh", index=False)
            core.autosize_columns(writer, "Kenh", df_channel)
            df_videos.to_excel(writer, sheet_name="Video", index=False)
            core.autosize_columns(writer, "Video", df_videos)
            if not df_comments.empty:
                df_comments.to_excel(writer, sheet_name="Comment", index=False)
                core.autosize_columns(writer, "Comment", df_comments)
        buffer.seek(0)

        status.text("Hoàn tất!")
        st.session_state.result = {
            "buffer": buffer.getvalue(),
            "df_channel": df_channel,
            "df_videos": df_videos,
            "df_comments": df_comments,
            "channel_title": channel["snippet"]["title"],
            "fields": fields,
        }

result = st.session_state.result
if result:
    st.divider()
    st.subheader(f"Kết quả: {result['channel_title']}")
    st.write(f"Số video: **{len(result['df_videos'])}** — Số comment: **{len(result['df_comments']):,}**")

    file_name = f"doi_thu_{result['channel_title'][:30].strip().replace(' ', '_')}.xlsx"
    st.download_button(
        "Tải file Excel kết quả",
        data=result["buffer"],
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.caption("Mẹo: bấm biểu tượng phóng to (⛶) ở góc trên bên phải mỗi bảng để xem toàn màn hình.")

    long_text_cols = {"mo_ta", "noi_dung", "tieu_de"}
    col_config = {
        c: st.column_config.TextColumn(width="large")
        for c in long_text_cols
        if c in result["df_videos"].columns or c in result["df_comments"].columns
    }

    tab1, tab2, tab3 = st.tabs(["Kênh", "Video", "Comment"])
    with tab1:
        st.dataframe(result["df_channel"], width="stretch", height=140, column_config=col_config)
    with tab2:
        st.dataframe(result["df_videos"], width="stretch", height=600, column_config=col_config)
    with tab3:
        if result["df_comments"].empty:
            st.info("Không có dữ liệu comment (bạn đã bỏ chọn 'Comment' hoặc video tắt bình luận).")
        else:
            st.dataframe(result["df_comments"], width="stretch", height=600, column_config=col_config)

    st.divider()
    st.subheader("Sao chép nhanh")
    st.caption("Bấm biểu tượng copy (📋) ở góc trên bên phải mỗi ô bên dưới để copy toàn bộ nội dung.")

    COPY_MAX_CHARS = 150000

    def copy_box(label, series):
        text = "\n".join(str(v) for v in series.dropna().tolist() if str(v).strip())
        if not text:
            return
        with st.expander(f"{label} ({len(series)} dòng)"):
            if len(text) > COPY_MAX_CHARS:
                st.warning(
                    f"Nội dung quá dài để hiển thị hết ({len(text):,} ký tự) — chỉ hiện "
                    f"{COPY_MAX_CHARS:,} ký tự đầu. Dùng file Excel để lấy đầy đủ."
                )
                text = text[:COPY_MAX_CHARS]
            st.code(text, language=None)

    fields = result["fields"]
    dfv = result["df_videos"]
    if "Tiêu đề" in fields and "tieu_de" in dfv.columns:
        copy_box("Tất cả Tiêu đề", dfv["tieu_de"])
    if "Mô tả" in fields and "mo_ta" in dfv.columns:
        copy_box("Tất cả Mô tả", dfv["mo_ta"])
    if "Từ khoá video" in fields and "tu_khoa_video" in dfv.columns:
        copy_box("Tất cả Từ khoá video", dfv["tu_khoa_video"])
    if "Từ khoá kênh" in fields and "tu_khoa_kenh" in result["df_channel"].columns:
        copy_box("Từ khoá kênh", result["df_channel"]["tu_khoa_kenh"])
    if not result["df_comments"].empty:
        copy_box("Tất cả nội dung Comment", result["df_comments"]["noi_dung"])
