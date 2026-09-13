const FIELD_OPTIONS = ["Ngày đăng", "Tiêu đề", "Mô tả", "Comment", "Like", "Từ khoá kênh", "Từ khoá video"];

let appPassword = sessionStorage.getItem("app_password") || "";
let scanState = null;
let resultState = null;

const $ = (id) => document.getElementById(id);

async function api(path, payload) {
  const res = await fetch(`/api/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-App-Password": appPassword },
    body: JSON.stringify(payload || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || `Loi ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function initFieldOptions() {
  const wrap = $("field-options");
  wrap.innerHTML = "";
  FIELD_OPTIONS.forEach((f) => {
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = f;
    cb.checked = true;
    cb.className = "field-cb";
    label.appendChild(cb);
    label.appendChild(document.createTextNode(" " + f));
    wrap.appendChild(label);
  });
}

function getSelectedFields() {
  return Array.from(document.querySelectorAll(".field-cb:checked")).map((el) => el.value);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

// ---------- Login ----------
$("login-btn").addEventListener("click", async () => {
  const pw = $("login-password").value;
  appPassword = pw;
  $("login-error").textContent = "";
  try {
    await api("ping", {});
    sessionStorage.setItem("app_password", pw);
    $("login-screen").hidden = true;
    $("app-screen").hidden = false;
  } catch (e) {
    appPassword = "";
    $("login-error").textContent = e.status === 401 ? "Sai mật khẩu." : e.message;
  }
});

// ---------- Toggle disabled inputs ----------
$("limit-videos").addEventListener("change", (e) => { $("max-videos").disabled = !e.target.checked; });
$("limit-comments").addEventListener("change", (e) => { $("max-comments").disabled = !e.target.checked; });

// ---------- Step 1: scan ----------
$("scan-btn").addEventListener("click", async () => {
  const channelInput = $("channel-input").value.trim();
  const fields = getSelectedFields();
  $("scan-error").textContent = "";

  if (!channelInput) { $("scan-error").textContent = "Vui lòng nhập link/@handle/Channel ID của kênh."; return; }
  if (fields.length === 0) { $("scan-error").textContent = "Vui lòng chọn ít nhất một trường dữ liệu."; return; }

  const btn = $("scan-btn");
  btn.disabled = true;
  btn.textContent = "Đang quét...";

  try {
    const channel = await api("resolve_channel", { channel: channelInput });

    const maxVideos = $("limit-videos").checked ? parseInt($("max-videos").value, 10) : null;
    let videoIds = [];
    let pageToken = null;
    do {
      const page = await api("videos_page", { uploads_playlist: channel.uploads_playlist, page_token: pageToken });
      videoIds = videoIds.concat(page.video_ids);
      pageToken = page.next_page_token;
      if (maxVideos && videoIds.length >= maxVideos) { videoIds = videoIds.slice(0, maxVideos); break; }
    } while (pageToken);

    const videoDetails = {};
    for (let i = 0; i < videoIds.length; i += 50) {
      const batch = videoIds.slice(i, i + 50);
      const resp = await api("videos_details", { video_ids: batch });
      Object.assign(videoDetails, resp.videos);
    }

    const fetchComments = fields.includes("Comment");
    let totalCommentsEst = 0;
    videoIds.forEach((id) => {
      if (videoDetails[id]) totalCommentsEst += parseInt(videoDetails[id].comment_count || 0, 10);
    });

    scanState = {
      channel, videoIds, videoDetails, fields,
      fetchComments,
      includeReplies: $("include-replies").checked,
      maxComments: $("limit-comments").checked ? parseInt($("max-comments").value, 10) : null,
      totalCommentsEst,
    };

    $("scan-channel-title").textContent = `Tìm thấy kênh: ${channel.title} (${channel.id})`;
    $("m-sub").textContent = channel.subscriber_count;
    $("m-total-videos").textContent = channel.video_count || "N/A";
    $("m-scan-videos").textContent = videoIds.length;
    $("m-est-comments").textContent = fetchComments ? totalCommentsEst.toLocaleString("vi-VN") : "Không lấy";

    const warnEl = $("quota-warning");
    if (fetchComments && totalCommentsEst > 20000) {
      const estCalls = Math.round(totalCommentsEst / 100 + videoIds.length);
      warnEl.hidden = false;
      warnEl.textContent = `Ước tính cần khoảng ${estCalls.toLocaleString("vi-VN")} lượt gọi API để lấy hết comment (${totalCommentsEst.toLocaleString("vi-VN")} comment). Quota miễn phí là 10.000 unit/ngày.`;
    } else {
      warnEl.hidden = true;
    }

    $("scan-result").hidden = false;
    $("result").hidden = true;
  } catch (e) {
    $("scan-error").textContent = e.status === 401 ? "Sai mật khẩu — hãy tải lại trang và đăng nhập lại." : e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "1. Tìm kênh & Quét quy mô";
  }
});

// ---------- Step 2: fetch data ----------
$("fetch-btn").addEventListener("click", async () => {
  if (!scanState) return;
  const btn = $("fetch-btn");
  btn.disabled = true;
  const progressWrap = $("progress-wrap");
  const progressFill = $("progress-fill");
  const progressText = $("progress-text");
  progressWrap.hidden = false;

  const { channel, videoIds, videoDetails, fields, fetchComments, includeReplies, maxComments } = scanState;
  const videoRows = [];
  const commentRows = [];

  for (let idx = 0; idx < videoIds.length; idx++) {
    const vid = videoIds[idx];
    const detail = videoDetails[vid];
    if (!detail) continue;

    progressText.textContent = `[${idx + 1}/${videoIds.length}] ${fetchComments ? "Đang lấy comment" : "Đang xử lý"}: ${detail.title.slice(0, 70)}`;

    if (fetchComments) {
      let pageToken = null;
      let count = 0;
      do {
        const page = await api("comments_page", { video_id: vid, page_token: pageToken, include_replies: includeReplies });
        for (const c of page.comments) {
          commentRows.push({ video_id: vid, ...c });
          count++;
          if (maxComments && count >= maxComments) break;
        }
        pageToken = page.next_page_token;
        if (maxComments && count >= maxComments) break;
      } while (pageToken);
    }

    videoRows.push({
      video_id: vid,
      url: detail.url,
      ngay_dang: detail.published_at,
      tieu_de: detail.title,
      mo_ta: detail.description,
      so_like: detail.like_count,
      so_view: detail.view_count,
      so_luong_comment: detail.comment_count,
      tu_khoa_video: (detail.tags || []).join(", "),
    });

    progressFill.style.width = `${Math.round(((idx + 1) / videoIds.length) * 100)}%`;
  }

  progressText.textContent = "Hoàn tất!";

  resultState = { channel, videoRows, commentRows, fields, fetchComments };
  renderResult();

  btn.disabled = false;
});

// ---------- Render result ----------
function fieldColMap() {
  return {
    "Ngày đăng": "ngay_dang", "Tiêu đề": "tieu_de", "Mô tả": "mo_ta",
    "Like": "so_like", "Từ khoá video": "tu_khoa_video",
  };
}

function buildTable(tableEl, rows, cols, colLabels) {
  tableEl.innerHTML = "";
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  cols.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = colLabels[c] || c;
    trh.appendChild(th);
  });
  thead.appendChild(trh);
  tableEl.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.slice(0, 2000).forEach((row) => {
    const tr = document.createElement("tr");
    cols.forEach((c) => {
      const td = document.createElement("td");
      td.textContent = row[c] ?? "";
      if (c === "mo_ta" || c === "tieu_de" || c === "text") td.className = "wrap";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  tableEl.appendChild(tbody);
}

function renderResult() {
  const { channel, videoRows, commentRows, fields, fetchComments } = resultState;

  $("result-title").textContent = `Kết quả: ${channel.title}`;
  $("result-summary").textContent = `Số video: ${videoRows.length} — Số comment: ${commentRows.length.toLocaleString("vi-VN")}`;

  const colMap = fieldColMap();
  const videoCols = ["video_id", "url", ...fields.filter((f) => colMap[f]).map((f) => colMap[f])];
  if (fetchComments) videoCols.push("so_luong_comment");
  const videoColLabels = {
    video_id: "video_id", url: "url", ngay_dang: "Ngày đăng", tieu_de: "Tiêu đề",
    mo_ta: "Mô tả", so_like: "Like", tu_khoa_video: "Từ khoá video", so_luong_comment: "Số lượng comment",
  };
  buildTable($("table-video"), videoRows, videoCols, videoColLabels);

  const channelRow = {
    ten_kenh: channel.title, channel_id: channel.id,
    mo_ta_kenh: channel.description, tu_khoa_kenh: channel.keywords,
    so_subscriber: channel.subscriber_count, tong_so_video: channel.video_count, tong_luot_xem: channel.view_count,
  };
  const channelCols = ["ten_kenh", "channel_id", "so_subscriber", "tong_so_video", "tong_luot_xem"];
  if (fields.includes("Từ khoá kênh")) channelCols.splice(2, 0, "tu_khoa_kenh");
  if (fields.includes("Mô tả")) channelCols.splice(2, 0, "mo_ta_kenh");
  const channelColLabels = {
    ten_kenh: "Tên kênh", channel_id: "Channel ID", mo_ta_kenh: "Mô tả kênh", tu_khoa_kenh: "Từ khoá kênh",
    so_subscriber: "Subscriber", tong_so_video: "Tổng video", tong_luot_xem: "Tổng lượt xem",
  };
  buildTable($("table-kenh"), [channelRow], channelCols, channelColLabels);

  if (commentRows.length) {
    const commentCols = ["video_id", "type", "author", "text", "like_count", "published_at"];
    const commentColLabels = { video_id: "video_id", type: "Loại", author: "Tác giả", text: "Nội dung", like_count: "Like", published_at: "Ngày đăng" };
    buildTable($("table-comment"), commentRows, commentCols, commentColLabels);
  } else {
    $("table-comment").innerHTML = "<tr><td>Không có dữ liệu comment.</td></tr>";
  }

  renderCopyBoxes(resultState, videoRows, channelRow);

  $("result").hidden = false;
}

function renderCopyBoxes(state, videoRows, channelRow) {
  const wrap = $("copy-boxes");
  wrap.innerHTML = "";
  const { fields, commentRows } = state;

  const addBox = (label, values) => {
    const text = values.filter((v) => v !== undefined && v !== null && String(v).trim() !== "").join("\n");
    if (!text) return;
    const box = document.createElement("div");
    box.className = "copy-box";
    const head = document.createElement("div");
    head.className = "copy-box-head";
    const span = document.createElement("span");
    span.textContent = `${label} (${values.length} dòng)`;
    const btn = document.createElement("button");
    btn.textContent = "Copy";
    const ta = document.createElement("textarea");
    ta.readOnly = true;
    ta.value = text.length > 150000 ? text.slice(0, 150000) + "\n... (đã cắt bớt, dùng file Excel để lấy đầy đủ)" : text;
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(ta.value);
        btn.textContent = "Đã copy!";
      } catch {
        ta.select();
        document.execCommand("copy");
        btn.textContent = "Đã copy!";
      }
      setTimeout(() => (btn.textContent = "Copy"), 1500);
    });
    head.appendChild(span);
    head.appendChild(btn);
    box.appendChild(head);
    box.appendChild(ta);
    wrap.appendChild(box);
  };

  if (fields.includes("Tiêu đề")) addBox("Tất cả Tiêu đề", videoRows.map((r) => r.tieu_de));
  if (fields.includes("Mô tả")) addBox("Tất cả Mô tả", videoRows.map((r) => r.mo_ta));
  if (fields.includes("Từ khoá video")) addBox("Tất cả Từ khoá video", videoRows.map((r) => r.tu_khoa_video));
  if (fields.includes("Từ khoá kênh")) addBox("Từ khoá kênh", [channelRow.tu_khoa_kenh]);
  if (commentRows.length) addBox("Tất cả nội dung Comment", commentRows.map((c) => c.text));
}

// ---------- Tabs ----------
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    $(btn.dataset.tab).classList.add("active");
  });
});

// ---------- Excel export ----------
$("download-btn").addEventListener("click", () => {
  if (!resultState) return;
  const { channel, videoRows, commentRows } = resultState;

  const wb = XLSX.utils.book_new();
  const wsKenh = XLSX.utils.json_to_sheet([{
    ten_kenh: channel.title, channel_id: channel.id, mo_ta_kenh: channel.description,
    tu_khoa_kenh: channel.keywords, so_subscriber: channel.subscriber_count,
    tong_so_video: channel.video_count, tong_luot_xem: channel.view_count,
  }]);
  XLSX.utils.book_append_sheet(wb, wsKenh, "Kenh");

  const wsVideo = XLSX.utils.json_to_sheet(videoRows);
  XLSX.utils.book_append_sheet(wb, wsVideo, "Video");

  if (commentRows.length) {
    const wsComment = XLSX.utils.json_to_sheet(commentRows);
    XLSX.utils.book_append_sheet(wb, wsComment, "Comment");
  }

  const safeName = channel.title.slice(0, 30).replace(/[^\wÀ-ỹ ]/g, "").trim().replace(/\s+/g, "_");
  XLSX.writeFile(wb, `doi_thu_${safeName || "ket_qua"}.xlsx`);
});

// ---------- Init ----------
initFieldOptions();
if (appPassword) {
  api("ping", {}).then(() => {
    $("login-screen").hidden = true;
    $("app-screen").hidden = false;
  }).catch(() => {
    sessionStorage.removeItem("app_password");
    appPassword = "";
  });
}
