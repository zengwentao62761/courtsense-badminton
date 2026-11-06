"use strict";

const $ = (id) => document.getElementById(id);
const angleNames = {
  left_elbow: "左肘",
  right_elbow: "右肘",
  left_knee: "左膝",
  right_knee: "右膝",
};
const jointNames = [
  "鼻尖",
  "左眼",
  "右眼",
  "左耳",
  "右耳",
  "左肩",
  "右肩",
  "左肘",
  "右肘",
  "左腕",
  "右腕",
  "左髋",
  "右髋",
  "左膝",
  "右膝",
  "左踝",
  "右踝",
];
const bones = [
  [5, 6],
  [5, 7],
  [7, 9],
  [6, 8],
  [8, 10],
  [5, 11],
  [6, 12],
  [11, 12],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
];
let analysisState = null, analysisBusy = false;
let state = null,
  paused = false,
  loading = false,
  view = "processed",
  selectedPerson = 0;
let frameKey = null,
  loadedObservation = null,
  pendingObservation = null;
let frameRequest = 0,
  frameObjectUrl = null,
  posePaired = false,
  pendingPair = false;
let rotation = -28,
  elevation = 54,
  drag = null;
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const number = (value) => (finite(value) ? value.toLocaleString("zh-CN") : "—");
const clockTime = (value) => {
  if (!finite(value) || value < 0) return "—";
  return `${Math.floor(value / 60)
    .toString()
    .padStart(2, "0")}:${(value % 60).toFixed(1).padStart(4, "0")}`;
};
const setText = (id, value) => {
  $(id).textContent = value == null || value === "" ? "—" : value;
};
const pointsOf = (person) =>
  Array.isArray(person?.keypoints)
    ? person.keypoints
    : Object.values(person?.keypoints || {});
const peopleOf = (observation) =>
  Array.isArray(observation?.people) ? observation.people : [];
const complete = (status) =>
  ["completed", "complete", "finished", "ended", "stopped"].includes(status);

function showNotice(text, type = "") {
  $("notice").textContent = text;
  $("notice").className = `notice ${type}`;
}

async function refresh() {
  if (loading) return;
  loading = true;
  $("refresh").disabled = true;
  try {
    const response = await fetch("/api/state", {
      cache: "no-store",
      signal: AbortSignal.timeout(6000),
    });
    if (!response.ok) throw new Error(`状态接口返回 HTTP ${response.status}`);
    const next = await response.json();
    if (!next || typeof next !== "object" || Array.isArray(next))
      throw new Error("状态接口格式无效");
    state = next;
    renderState();
    await loadAnalysis();
    setText(
      "updated",
      new Date().toLocaleTimeString("zh-CN", { hour12: false }),
    );
  } catch (error) {
    setText("connection", paused ? "已暂停 · 读取失败" : "工作台离线");
    $("status-dot").className = "status-dot error";
    showNotice(
      `无法读取工作台：${error.message}。请检查监测进程与网络。${state ? "当前保留上次读取结果，非实时数据。" : "尚未收到真实观察数据。"}`,
      "error",
    );
  } finally {
    loading = false;
    $("refresh").disabled = false;
  }
}

function renderState() {
  const source = state.source || {},
    progress = state.progress || {},
    summary = state.summary || {};
  const latest = state.latest;
  const errors = Array.isArray(state.errors) ? state.errors : [];
    const failed = ["error", "offline", "failed", "disconnected", "stale"].includes(
    state.status,
  );
  const done = complete(state.status);
  const active = ["running", "processing", "online"].includes(state.status);
  const status = failed
    ? "来源离线 / 处理错误"
    : done
      ? "本次处理已结束"
      : active
        ? "正在观察"
        : "等待来源";
  setText("connection", paused ? `已暂停刷新 · ${status}` : status);
  $("status-dot").className =
    `status-dot ${failed ? "error" : active ? "online" : ""}`;
  setText("source-label", (source.label === "Configured RDK pose service" ? "已配置 RDK 姿态服务" : source.label) || "尚未提供来源");
  setText(
    "source-kind",
    { rdk: "RDK HTTP 姿态服务", video: "本地视频分析" }[source.kind] ||
      source.kind ||
      "默认 RDK 服务",
  );
  setText(
    "platform",
    { desktop_validation: "桌面验证", rdk: "RDK 设备", rdk_x5: "RDK X5", rdk_service_adapter: "RDK 服务适配" }[
      source.platform
    ] ||
      source.platform ||
      "待确认",
  );
  $("source-label").title = source.label || "";
  const errorText = errors
    .map((error) =>
      readableSourceError(typeof error === "string" ? error : error.message || JSON.stringify(error)),
    )
    .join("；");
  if (failed)
    showNotice(
      `来源未就绪。${errorText || "请检查 RDK 服务地址、设备连接或视频处理日志。"}${latest ? " 保留最近处理帧供复核。" : ""}`,
      "error",
    );
  else if (errors.length) showNotice(`观察记录包含错误：${errorText}`, "error");
  else if (done)
    showNotice(
      "本次处理已结束。画面停留在最近处理帧，可下载观察报告复核来源与样本。",
      "complete",
    );
  else if (paused)
    showNotice(
      "已暂停工作台刷新，画面与指标保留在上次读取时刻。后台处理继续运行。",
    );
  else
    showNotice(
      source.kind === "video"
        ? "正在读取真实视频分析结果。源视频时间与处理用时分别记录；抽样检测不覆盖全部视频帧。"
        : "读取已配置的 RDK 姿态服务。仅展示实际返回的观察；连接状态不代表球场标定或精度验收。",
    );
  setText(
    "processed-count",
    number(summary.processed_frames ?? progress.processed_frames),
  );
  setText("people-count", latest ? number(peopleOf(latest).length) : "—");
  setText("video-time", clockTime(progress.video_time_s));
  setText(
    "elapsed",
    finite(summary.elapsed_s) ? `${summary.elapsed_s.toFixed(1)} s` : "—",
  );
  setText("frames-with-people", number(summary.frames_with_people));
  setText("observations", number(summary.person_observations));
  setText("session", state.session_id);
  setText("image-space", latest?.image_space_id);
  const frameId = latest?.frame_id ?? progress.frame_id;
  setText(
    "frame-meta",
    latest
      ? `处理帧 ${frameId ?? "—"}  /  ${latest.width || "—"} × ${latest.height || "—"} px`
      : "等待首个处理帧",
  );
  updateFrame(latest);
  const videoUrl = safeLocalUrl(state.video_url);
  $("original-view").disabled = !videoUrl;
  if (videoUrl && $("original").getAttribute("src") !== videoUrl)
    $("original").src = videoUrl;
  if (!videoUrl) {
    $("original").removeAttribute("src");
    if (view === "original") switchView("processed");
  }
  updatePeople(latest);
  drawDistribution();
  $("download-html").disabled = !done;
  $("download-json").disabled = !done;
  setText(
    "report-message",
    done
      ? "报告可下载；保留原始来源、时间和样本量"
      : failed
        ? "当前会话未正常结束，请先检查错误记录"
        : "报告将在处理完成后开放下载",
  );
}

function readableSourceError(message) {
  if (/deadline exceeded|timed out|timeout/i.test(message)) return "RDK 服务读取超时，请检查服务地址、设备连接与网络。";
  if (/connection refused|actively refused|WinError 10061/i.test(message)) return "无法连接 RDK 服务，请确认姿态服务已经启动。";
  if (/No matched RDK frame/i.test(message)) return "尚未收到图像与观察一致的 RDK 配对帧，请检查上游接口。";
  return message;
}

function safeLocalUrl(value) {
  if (
    typeof value !== "string" ||
    !value.startsWith("/") ||
    value.startsWith("//")
  )
    return null;
  return value;
}

async function updateFrame(latest) {
  const url = safeLocalUrl(state.frame_url);
  if (!latest || !url || !state.source?.kind) {
    frameKey = null;
    loadedObservation = null;
    frameRequest++;
    posePaired = false;
    $("frame-empty").hidden = false;
    $("processed-wrap").hidden = true;
    $("frame-tag").hidden = true;
    return;
  }
  const key = `${state.session_id}:${latest.image_space_id}:${latest.frame_id}`;
  if (key === frameKey) return;
  frameKey = key;
  const request = ++frameRequest;
  try {
    const query = new URLSearchParams({
      frame_id: String(latest.frame_id),
      image_space_id: String(latest.image_space_id),
      service_instance_id:
        latest.service_instance_id == null
          ? ""
          : String(latest.service_instance_id),
      t: String(Date.now()),
    });
    const response = await fetch(
      `${url}${url.includes("?") ? "&" : "?"}${query}`,
      { cache: "no-store", signal: AbortSignal.timeout(6000) },
    );
    if (request !== frameRequest) return;
    if (response.status === 409) {
      waitingForPair();
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const paired =
      response.headers.get("X-Frame-Id") === String(latest.frame_id) &&
      response.headers.get("X-Image-Space-Id") ===
        String(latest.image_space_id) &&
      (!latest.service_instance_id ||
        response.headers.get("X-Service-Instance-Id") ===
          String(latest.service_instance_id));
    if (!paired) {
      waitingForPair();
      return;
    }
    const blob = await response.blob();
    if (request !== frameRequest) return;
    if (frameObjectUrl) URL.revokeObjectURL(frameObjectUrl);
    frameObjectUrl = URL.createObjectURL(blob);
    pendingObservation = latest;
    pendingPair = paired;
    $("frame").src = frameObjectUrl;
  } catch (error) {
    if (request === frameRequest) frameError(error.message);
  }
}

function waitingForPair() {
  frameKey = null;
  if (loadedObservation) {
    $("frame-tag").textContent =
      `保留已配对帧 ${loadedObservation.frame_id} · 等待下一帧配对`;
  } else {
    $("frame-empty").querySelector("h3").textContent = "正在等待配对帧";
    $("frame-empty").querySelector("p").textContent =
      "图像与观察状态尚未一致，下次刷新将重试。未配对画面不显示。";
  }
}

$("frame").addEventListener("load", () => {
  loadedObservation = pendingObservation;
  posePaired = pendingPair;
  $("frame-empty").hidden = true;
  $("processed-wrap").hidden = view !== "processed";
  $("frame-tag").hidden = view !== "processed";
  $("frame-tag").textContent = posePaired
    ? `处理帧 ${loadedObservation.frame_id} · 已核对配对`
    : "图像与状态未配对 · 不叠加关键点";
  drawPose();
});
function frameError(message) {
  frameKey = null;
  loadedObservation = null;
  posePaired = false;
  $("processed-wrap").hidden = true;
  $("frame-empty").hidden = view !== "processed";
  $("frame-tag").hidden = true;
  $("frame-empty").querySelector("h3").textContent = "处理图暂不可用";
  $("frame-empty").querySelector("p").textContent =
    `图像接口读取失败${message ? `（${message}）` : ""}，下次刷新将重试。指标来自状态接口。`;
}
$("frame").addEventListener("error", () => frameError("图像无法解码"));

function switchView(next) {
  view = next;
  for (const name of ["processed", "original"]) {
    $(`${name}-view`).classList.toggle("selected", name === next);
    $(`${name}-view`).setAttribute("aria-pressed", name === next);
  }
  $("original").hidden = next !== "original";
  $("processed-wrap").hidden = next !== "processed" || !loadedObservation;
  $("frame-empty").hidden = next !== "processed" || !!loadedObservation;
  $("frame-tag").hidden = next !== "processed" || !loadedObservation;
  $("show-pose").disabled = next !== "processed";
  setText(
    "video-note",
    next === "original"
      ? "原视频独立播放，与处理图和指标不同步"
      : "处理帧按工作台读取频率更新",
  );
  if (next !== "original") $("original").pause();
  drawPose();
}

function updatePeople(latest) {
  const people = peopleOf(latest);
  selectedPerson = Math.max(0, Math.min(selectedPerson, people.length - 1));
  const selector = $("person");
  selector.replaceChildren();
  if (!people.length) selector.add(new Option("暂无检测", "0"));
  people.forEach((person, index) =>
    selector.add(
      new Option(
        `检测 ${person.detection_index ?? index}${person.track_id == null ? " · 未关联身份" : ` · track ${person.track_id}`}`,
        index,
      ),
    ),
  );
  selector.value = String(selectedPerson);
  selector.disabled = !people.length;
  renderPerson();
}

function renderPerson() {
  const person = peopleOf(state?.latest)[selectedPerson];
  const points = pointsOf(person),
    angles = person?.angles_2d || {};
  $("angles").replaceChildren();
  for (const [key, label] of Object.entries(angleNames)) {
    const raw = angles[key];
    const value =
      typeof raw === "object" && raw !== null
        ? raw.valid
          ? raw.degrees
          : null
        : raw;
    const valid = finite(value) && value >= 0 && value <= 180;
    const block = document.createElement("div");
    const row = document.createElement("div");
    row.className = "angle-label";
    const name = document.createElement("span");
    name.textContent = label;
    const reading = document.createElement("strong");
    reading.textContent = valid ? `${value.toFixed(1)}°` : "—";
    row.append(name, reading);
    const track = document.createElement("div");
    track.className = "angle-track";
    const fill = document.createElement("span");
    fill.style.width = `${valid ? (value / 180) * 100 : 0}%`;
    track.append(fill);
    block.append(row, track);
    $("angles").append(block);
  }
  setText(
    "keypoint-count",
    person
      ? `有效关节点：${points.filter((point) => point.valid).length} / ${points.length} · 无效关节不计算角度`
      : "有效关节点：— · 等待真实人体检测",
  );
  $("keypoints").replaceChildren();
  if (!points.length) {
    const row = $("keypoints").insertRow();
    const cell = row.insertCell();
    cell.colSpan = 4;
    cell.textContent = "当前没有关节点观察";
  }
  points.forEach((point) => {
    const row = $("keypoints").insertRow();
    const values = [
      jointNames[point.index] || point.name,
      finite(point.x) && finite(point.y)
        ? `${point.x.toFixed(1)} / ${point.y.toFixed(1)}`
        : "—",
      finite(point.probability) ? point.probability.toFixed(3) : "—",
      point.valid ? "有效" : point.reason || "无效",
    ];
    values.forEach((value) => {
      row.insertCell().textContent = value;
    });
  });
}

function canvasContext(canvas) {
  const rect = canvas.getBoundingClientRect(),
    ratio = window.devicePixelRatio || 1;
  if (!rect.width || !rect.height) return null;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  return { ctx, width: rect.width, height: rect.height };
}

function drawPose() {
  const surface = canvasContext($("pose-overlay"));
  if (!surface || !loadedObservation || !posePaired || !$("show-pose").checked)
    return;
  const { ctx, width, height } = surface,
    observation = loadedObservation;
  if (!observation.width || !observation.height) return;
  const scale = Math.min(
    width / observation.width,
    height / observation.height,
  );
  const offsetX = (width - observation.width * scale) / 2,
    offsetY = (height - observation.height * scale) / 2;
  const xy = (point) => [offsetX + point.x * scale, offsetY + point.y * scale];
  ctx.lineWidth = 2;
  for (const person of peopleOf(observation)) {
    const points = pointsOf(person),
      byIndex = new Map(points.map((point) => [point.index, point]));
    const visible = (point) =>
      point?.valid && finite(point.x) && finite(point.y);
    ctx.strokeStyle = "#65e9d0";
    for (const [a, b] of bones) {
      const p = byIndex.get(a),
        q = byIndex.get(b);
      if (!visible(p) || !visible(q)) continue;
      ctx.beginPath();
      ctx.moveTo(...xy(p));
      ctx.lineTo(...xy(q));
      ctx.stroke();
    }
    for (const point of points)
      if (visible(point)) {
        ctx.beginPath();
        ctx.arc(...xy(point), 3, 0, Math.PI * 2);
        ctx.fillStyle = "#fff";
        ctx.fill();
        ctx.strokeStyle = "#087e83";
        ctx.stroke();
      }
  }
}

function drawDistribution() {
  const surface = canvasContext($("distribution"));
  if (!surface) return;
  const { ctx, width, height } = surface,
    left = 40,
    top = 12,
    w = width - 62,
    h = height - 42;
  ctx.fillStyle = "#f4f8fa";
  ctx.fillRect(left, top, w, h);
  ctx.font = '10px "Microsoft YaHei",sans-serif';
  ctx.fillStyle = "#7b929f";
  for (let i = 0; i <= 4; i++) {
    const frac = i / 4;
    ctx.strokeStyle = "#dce7eb";
    ctx.beginPath();
    ctx.moveTo(left + w * frac, top);
    ctx.lineTo(left + w * frac, top + h);
    ctx.moveTo(left, top + h * frac);
    ctx.lineTo(left + w, top + h * frac);
    ctx.stroke();
    ctx.textAlign = "center";
    ctx.fillText(frac.toFixed(2), left + w * frac, top + h + 17);
    ctx.textAlign = "right";
    ctx.fillText(frac.toFixed(2), left - 8, top + h * frac + 3);
  }
  const samples = (state?.summary?.ankle_points_image || [])
    .filter(
      (point) =>
        [point.x, point.y, point.width, point.height].every(finite) &&
        point.width > 0 &&
        point.height > 0 &&
        point.x >= 0 &&
        point.y >= 0 &&
        point.x < point.width &&
        point.y < point.height,
    )
    .slice(-1000);
  ctx.fillStyle = "#087e8377";
  for (const point of samples) {
    ctx.beginPath();
    ctx.arc(
      left + (point.x / point.width) * w,
      top + (point.y / point.height) * h,
      2.8,
      0,
      Math.PI * 2,
    );
    ctx.fill();
  }
  if (!samples.length) {
    ctx.fillStyle = "#6d8795";
    ctx.textAlign = "center";
    ctx.font = '12px "Microsoft YaHei",sans-serif';
    ctx.fillText("等待有效足踝采样", left + w / 2, top + h / 2);
  }
  setText(
    "ankle-meta",
    samples.length
      ? `显示 ${samples.length} 个图像点 · 总有效采样 ${number(state.summary.ankle_points_seen ?? samples.length)}`
      : "尚无有效足踝采样",
  );
}

function drawCourt() {
  const surface = canvasContext($("court"));
  if (!surface) return;
  const { ctx, width, height } = surface;
  const yaw = (rotation * Math.PI) / 180,
    tilt = (elevation * Math.PI) / 180;
  const scale = Math.min(width / 18.7, height / 13.8);
  const project = (x, y, z = 0) => {
    const rx = x * Math.cos(yaw) - y * Math.sin(yaw),
      ry = x * Math.sin(yaw) + y * Math.cos(yaw);
    return [
      width / 2 + rx * scale,
      height / 2 + (ry * Math.cos(tilt) - z * Math.sin(tilt)) * scale + 12,
    ];
  };
  const line = (points, color, lineWidth = 1) => {
    ctx.beginPath();
    points.forEach((point, index) => {
      const p = project(...point);
      index ? ctx.lineTo(...p) : ctx.moveTo(...p);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  };
  const corners = [
    [-3.05, -6.7],
    [3.05, -6.7],
    [3.05, 6.7],
    [-3.05, 6.7],
  ];
  ctx.beginPath();
  [
    [-4.4, -8],
    [4.4, -8],
    [4.4, 8],
    [-4.4, 8],
  ].forEach((point, i) => {
    const p = project(...point);
    i ? ctx.lineTo(...p) : ctx.moveTo(...p);
  });
  ctx.closePath();
  ctx.fillStyle = "#e4ece7";
  ctx.fill();
  ctx.beginPath();
  corners.forEach((point, i) => {
    const p = project(...point);
    i ? ctx.lineTo(...p) : ctx.moveTo(...p);
  });
  ctx.closePath();
  ctx.fillStyle = "#237c5c";
  ctx.fill();
  line([...corners, corners[0]], "#eafcfa", 1.6);
  for (const x of [-2.59, 2.59])
    line(
      [
        [x, -6.7],
        [x, 6.7],
      ],
      "#def7ef",
      1,
    );
  for (const y of [-5.94, -1.98, 1.98, 5.94])
    line(
      [
        [-3.05, y],
        [3.05, y],
      ],
      "#def7ef",
      1,
    );
  line(
    [
      [0, -6.7],
      [0, -1.98],
    ],
    "#def7ef",
  );
  line(
    [
      [0, 1.98],
      [0, 6.7],
    ],
    "#def7ef",
  );
  // The net is nominal geometry only; no inferred player or shuttle coordinates.
  for (let z = 0.15; z <= 1.55; z += 0.2)
    line(
      [
        [-3.18, 0, z],
        [3.18, 0, z],
      ],
      "#193d5550",
      0.6,
    );
  for (let x = -3.18; x <= 3.18; x += 0.32)
    line(
      [
        [x, 0, 0.15],
        [x, 0, 1.55],
      ],
      "#193d5550",
      0.5,
    );
  line(
    [
      [-3.18, 0, 1.55],
      [3.18, 0, 1.55],
    ],
    "#fff",
    2,
  );
  for (const x of [-3.18, 3.18])
    line(
      [
        [x, 0],
        [x, 0, 1.55],
      ],
      "#19465b",
      2,
    );
  const analysis = activeAnalysis();
  if (analysis && $("show-trails").checked) {
    const palette = ["#ffbc65", "#c8eafe", "#ffb5ac"];
    (analysis.result.player_tracks || []).forEach((track, index) => {
      let previous = null;
      for (const point of track.points || []) {
        if (!point.contact_confirmed || !point.court_m) { previous = null; continue; }
        const xy = [point.court_m[0] - 3.05, point.court_m[1] - 6.7, 0.04];
        if (previous) line([previous, xy], palette[index % palette.length], 2.5);
        ctx.beginPath(); ctx.arc(...project(...xy), 3, 0, Math.PI * 2);
        ctx.fillStyle = palette[index % palette.length]; ctx.fill();
        previous = xy;
      }
    });
  }
  if (analysis && $("show-world").checked) {
    for (const track of analysis.result.shuttle_tracks || []) {
      let previous = null, previousSource = null;
      for (const point of track.points || []) {
        if (!point.world3d_m) { previous = null; previousSource = null; continue; }
        if (point.world3d_source !== previousSource) previous = null;
        const xyz = [point.world3d_m[0] - 3.05, point.world3d_m[1] - 6.7, point.world3d_m[2]];
        if (previous) line([previous, xyz], "#fbc845", 2);
        ctx.beginPath(); ctx.arc(...project(...xyz), 2.5, 0, Math.PI * 2);
        ctx.fillStyle = "#ffe494"; ctx.fill(); previous = xyz;
        previousSource = point.world3d_source;
      }
    }
  }
  ctx.font = '10px "Microsoft YaHei",sans-serif';
  ctx.fillStyle = "#526f7e";
  ctx.textAlign = "center";
  const label = project(0, 7.7);
  ctx.fillText("6.10 m", ...label);
  const longLabel = project(-4, 0);
  ctx.fillText("13.40 m", ...longLabel);
}

async function downloadReport(format) {
  const button = $(`download-${format}`);
  button.disabled = true;
  setText("report-message", "正在读取报告…");
  try {
    const response = await fetch(`/api/report.${format}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob),
      link = document.createElement("a");
    link.href = url;
    link.download = `courtsense-report.${format}`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    setText("report-message", `${format.toUpperCase()} 报告已准备下载`);
  } catch (error) {
    setText("report-message", `报告读取失败：${error.message}，请重试`);
  } finally {
    button.disabled = !complete(state?.status);
  }
}

$("pause").addEventListener("click", () => {
  paused = !paused;
  $("pause").textContent = paused ? "继续刷新" : "暂停刷新";
  $("pause").setAttribute("aria-pressed", paused);
  if (state) renderState();
  if (!paused) refresh();
});
$("refresh").addEventListener("click", refresh);
$("processed-view").addEventListener("click", () => switchView("processed"));
$("original-view").addEventListener("click", () => switchView("original"));
$("person").addEventListener("change", () => {
  selectedPerson = Number($("person").value);
  renderPerson();
});
$("show-pose").addEventListener("change", drawPose);
$("download-html").addEventListener("click", () => downloadReport("html"));
$("download-json").addEventListener("click", () => downloadReport("json"));
function changeAngle(value) {
  rotation = ((((value + 180) % 360) + 360) % 360) - 180;
  $("court-angle").value = Math.round(rotation);
  drawCourt();
}
$("court-angle").addEventListener("input", () =>
  changeAngle(Number($("court-angle").value)),
);
$("reset-court").addEventListener("click", () => {
  elevation = 54;
  changeAngle(-28);
});
$("court").addEventListener("pointerdown", (event) => {
  drag = { x: event.clientX, y: event.clientY };
  $("court").setPointerCapture(event.pointerId);
});
$("court").addEventListener("pointermove", (event) => {
  if (!drag) return;
  elevation = Math.max(
    25,
    Math.min(80, elevation + (event.clientY - drag.y) * 0.3),
  );
  changeAngle(rotation + (event.clientX - drag.x) * 0.4);
  drag = { x: event.clientX, y: event.clientY };
});
for (const name of ["pointerup", "pointercancel", "lostpointercapture"])
  $("court").addEventListener(name, () => {
    drag = null;
  });
$("court").addEventListener("keydown", (event) => {
  if (
    !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home"].includes(
      event.key,
    )
  )
    return;
  event.preventDefault();
  if (event.key === "Home") {
    elevation = 54;
    changeAngle(-28);
  } else if (event.key === "ArrowLeft" || event.key === "ArrowRight")
    changeAngle(rotation + (event.key === "ArrowLeft" ? -5 : 5));
  else {
    elevation = Math.max(
      25,
      Math.min(80, elevation + (event.key === "ArrowUp" ? 5 : -5)),
    );
    drawCourt();
  }
});
new ResizeObserver(() => {
  drawCourt();
  drawDistribution();
  drawPose();
  drawTrajectory();
}).observe(document.querySelector("main"));
const workspaceCopy = {
  overview: ["训练概览", "从采集画面到球场空间，复核每一次观察。"],
  movement: ["标定与跑位", "以去畸变点对建立球场坐标，只显示已确认接地的采样。"],
  shuttle: ["球迹与击球", "检查图像球迹、扣杀事件与有条件的速度估计。"],
  reports: ["报告与设备", "导出本次观察，检查采集来源与硬件接入状态。"]
};
function selectWorkspace(name) {
  if (!workspaceCopy[name]) name = "overview";
  document.querySelector("main").dataset.workspace = name;
  document.querySelectorAll("button[data-workspace]").forEach((button) => {
    const active = button.dataset.workspace === name;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  document.querySelectorAll("[data-views]").forEach((section) => {
    section.hidden = !section.dataset.views.split(" ").includes(name);
  });
  setText("workspace-label", workspaceCopy[name][0]);
  setText("workspace-title", workspaceCopy[name][0]);
  setText("workspace-description", workspaceCopy[name][1]);
  setText("analysis-title", name === "shuttle" ? "球迹、速度与击球事件" : "分析数据与标定");
  $("analysis-scope").hidden = name === "reports" || !activeAnalysis();
  drawCourt(); drawPose(); drawDistribution(); drawTrajectory();
}
for (const button of document.querySelectorAll("button[data-workspace]")) {
  button.addEventListener("click", () => {
    history.replaceState(null, "", `#${button.dataset.workspace}`);
    selectWorkspace(button.dataset.workspace);
  });
}
window.addEventListener("hashchange", () => selectWorkspace(location.hash.slice(1)));
function activeAnalysis() {
  if (analysisState?.status !== "ready" || !analysisState.result) return null;
  const data = analysisState.data;
  if (data?.mode === "live") {
    const binding = data.binding;
    const latest = state?.latest;
    if (!binding || !latest || binding.session_id !== state.session_id ||
        binding.image_space?.id !== latest.image_space_id ||
        binding.image_space?.width !== latest.width || binding.image_space?.height !== latest.height ||
        binding.image_space?.service_instance_id !== latest.service_instance_id ||
        JSON.stringify(binding.source_identity) !== JSON.stringify(state.source)) return null;
  }
  return analysisState;
}
async function analysisRequest(path = "/api/analysis", data) {
  const response = await fetch(path, {
    method: data === undefined ? "GET" : "POST", cache: "no-store",
    headers: data === undefined ? {} : {"Content-Type": "application/json"},
    body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(8000)
  });
  let body;
  try { body = await response.json(); } catch { throw new Error(`分析服务返回无效内容（HTTP ${response.status}）`); }
  if (!response.ok) {
    const detail = body.error?.message || body.error || body.message || body.detail;
    throw new Error(typeof detail === "string" ? detail : `分析请求失败（HTTP ${response.status}）`);
  }
  return body;
}
async function loadAnalysis() {
  if (analysisBusy) return;
  try {
    analysisState = await analysisRequest(); renderAnalysis();
  } catch (error) {
    analysisState = null; renderAnalysis();
    setText("analysis-message", `分析数据暂不可用：${readableError(error)}。请检查服务并重试。`);
  }
}
function readableError(error) {
  if (error.name === "TimeoutError") return "请求超时";
  if (error instanceof SyntaxError) return "JSON 格式无效，请检查引号、逗号与括号";
  if (error.message === "Failed to fetch") return "无法连接分析服务";
  const translations = [
    ["Live binding mismatch", "当前来源或图像空间不匹配，请刷新后重新标定"],
    ["Offline development requires", "离线数据需要独立来源；当前存在真实帧，请使用匹配的 live 分析输入"],
    ["Calibration requires 4..64", "标定需要 4 到 64 组像素点与球场米制点对"],
    ["Calibration requires undistorted_pixels", "标定输入必须使用去畸变像素坐标"],
    ["Degenerate", "标定点无法构成有效平面映射，请检查是否共线或重合"],
    ["Duplicate calibration", "标定控制点重复，请使用不同点对"],
    ["Control point reprojection", "标定残差超过 0.25 m，请检查像素与球场点的对应关系"],
    ["Pixel outside", "像素点超出声明的图像宽高"],
    ["Invalid coordinate", "坐标维数错误，请使用二维像素或三维空间坐标"],
    ["Expected finite number", "数值无效或超出允许范围，请检查坐标与时间"],
    ["Invalid object fields", "JSON 字段不符合格式，请对照样例检查字段名称和必填项"],
    ["Expected schema_version", "请使用 schema_version: 1，并将 synthetic 设置为 true 或 false"],
    ["strictly", "同一球员或球迹的时间必须严格递增"],
    ["world3d_source", "三维坐标需要同时提供重建来源 world3d_source"],
    ["Expected nonempty text", "名称和来源不能为空，且不得超过 256 个字符"]
  ];
  const matched = translations.find(([text]) => error.message.includes(text));
  return matched ? `${matched[1]}（${error.message}）` : error.message;
}
function renderAnalysis() {
  const active = activeAnalysis(), data = analysisState?.data, result = active?.result;
  const synthetic = data?.synthetic === true;
  const origin = data ? `${data.mode === "offline_development" ? "离线开发" : "当前来源绑定"} / ${data.source_name || "未命名"}${synthetic ? " / 合成数据" : ""}` : "无分析数据";
  const badge = $("analysis-badge"); badge.textContent = origin; badge.classList.toggle("synthetic", synthetic);
  setText("court-data-tag", active ? (synthetic ? "合成数据 · 独立预览" : data.mode === "live" ? "当前来源分析" : "离线分析 · 独立预览") : "标准几何");
  $("court-data-tag").classList.toggle("synthetic", !!active && synthetic);
  $("export-analysis").disabled = !data;
  $("export-analysis-result").disabled = !["ready", "invalidated"].includes(analysisState?.status);
  $("live-analysis-template").disabled = !analysisState?.binding;
  $("analysis-scope").hidden = !active || document.querySelector("main").dataset.workspace === "reports";
  setText("analysis-scope", active ? `以下球场与击球指标来自 ${origin}。${data.mode === "offline_development" ? "独立开发预览；上方采集来源未参与这些分析。" : "手工导入分析，尚未通过真实场地精度验收。"}` : "");
  const calibration = result?.calibration;
  setText("calibration-value", calibration ? "点对已拟合" : "未标定");
  setText("calibration-detail", calibration ? `${calibration.point_count} 组点对 / 拟合残差 ${Number(calibration.reprojection_rmse_m).toFixed(3)} m，非实测精度` : "需要去畸变像素点与米制点对");
  const count = result ? (result.player_tracks || []).reduce((sum, track) => sum + track.points.filter(p => p.contact_confirmed && p.court_m).length, 0) : null;
  setText("trail-value", count === null ? "—" : `${count} 点`);
  setText("smash-value", result?.smash ? `${number(result.smash.confirmed_count)} / ${number(result.smash.candidate_count)}` : "— / —");
  const speeds = result?.speed;
  const lastPixel = speeds?.pixel_segments?.at(-1), lastWorld = speeds?.world3d_segments?.at(-1);
  setText("speed-value", lastWorld ? `≈ ${lastWorld.estimated_km_per_h.toFixed(1)} km/h` : lastPixel ? `${lastPixel.pixel_per_s.toFixed(1)} px/s` : "—");
  setText("speed-detail", lastWorld ? `${lastPixel ? `图像末段 ${lastPixel.pixel_per_s.toFixed(1)} px/s / ` : ""}条件化三维估计来源：${lastWorld.source}` : lastPixel ? "末段图像速度；不能转换为实际球速" : "像素速度与有条件三维估计分开记录");
  setText("court-analysis-note", active ? `${origin}。${calibration ? "米制跑位仅连接接地确认采样。" : "无标定，未绘制米制跑位。"}三维球迹仅使用显式三维坐标，不由地面映射推断。` : analysisState?.status === "invalidated" ? "分析绑定已失效；保留输入供导出。请使用新来源重新标定。" : "尚无有效分析，仅显示标准球场。可在标定与跑位中导入点对。");
  setText("trajectory-note", active ? `${origin} / ${data.image_space.width} × ${data.image_space.height} px。独立坐标画布，不与真实采集画面混合。缺失点处断开。` : "等待有效球迹输入；这是独立分析视图。");
  const list = $("event-list"); list.replaceChildren();
  for (const event of result?.smash?.events || []) {
    const row = document.createElement("div"); row.className = "event-row";
    const left = document.createElement("span"), right = document.createElement("span");
    left.textContent = `扣杀 ${event.status === "confirmed" ? "已确认" : "候选"} / ${event.t_s.toFixed(2)} s`;
    right.textContent = event.source || "来源未注明"; row.append(left, right); list.append(row);
  }
  if (!list.children.length) list.textContent = "尚无击球事件。计数需要事件输入或算法输出。";
  if (!analysisBusy) setText("analysis-message", active ? `已加载 ${origin}。当前为手工导入分析；自动球体检测与扣杀分类尚未接入。` : analysisState?.status === "invalidated" ? "来源发生变化，原分析已失效。请重新导入与当前来源匹配的数据。" : "尚无分析结果。导入 JSON，或主动预览合成样例。 ");
  drawCourt(); drawTrajectory();
}
function drawTrajectory() {
  const surface = canvasContext($("trajectory")); if (!surface) return;
  const {ctx, width, height} = surface;
  ctx.fillStyle = "#f4f6f8"; ctx.fillRect(0, 0, width, height);
  const active = activeAnalysis();
  if (!active || !$("show-shuttle").checked) {
    ctx.fillStyle = "#828d98";ctx.font = '12px "Microsoft YaHei",sans-serif';ctx.textAlign = "center";
    ctx.fillText(active ? "球迹图层已关闭" : "等待羽毛球轨迹数据", width / 2, height / 2); return;
  }
  const space = active.data.image_space;
  const scale = Math.min((width - 32) / space.width, (height - 32) / space.height);
  const ox = (width - space.width * scale) / 2, oy = (height - space.height * scale) / 2;
  ctx.strokeStyle = "#c7d0d8"; ctx.strokeRect(ox, oy, space.width * scale, space.height * scale);
  const palette = ["#e9752c", "#458aa3", "#8d71bb"];
  (active.result.shuttle_tracks || []).forEach((track, index) => {
    let previous = null; ctx.strokeStyle = palette[index % palette.length]; ctx.fillStyle = ctx.strokeStyle; ctx.lineWidth = 2;
    for (const point of track.points || []) {
      if (!point.pixel) {previous = null;continue;}
      const xy = [ox + point.pixel[0] * scale, oy + point.pixel[1] * scale];
      if (previous) {ctx.beginPath();ctx.moveTo(...previous);ctx.lineTo(...xy);ctx.stroke();}
      ctx.beginPath();ctx.arc(...xy, 3, 0, Math.PI * 2);ctx.fill();previous = xy;
      for (const event of active.result.smash?.events || []) {
        if (Math.abs(event.t_s - point.t_s) > .001) continue;
        ctx.save();ctx.setLineDash(event.status === "candidate" ? [3, 3] : []);
        ctx.beginPath();ctx.arc(...xy, 8, 0, Math.PI * 2);ctx.stroke();ctx.restore();
      }
    }
  });
}
async function applyAnalysis(data) {
  if (analysisBusy) return;
  analysisBusy = true; $("import-analysis").disabled = true;
  try {
    analysisState = await analysisRequest("/api/analysis", data);
    if (!analysisState.status) analysisState = await analysisRequest();
    renderAnalysis(); setText("analysis-message", "分析输入已应用。结果按输入来源和适用条件展示。");
  } catch (error) {setText("analysis-message", `未应用输入：${readableError(error)}。原分析保持不变。`);}
  finally {analysisBusy = false; $("import-analysis").disabled = false;}
}
$("import-analysis").addEventListener("click", () => {
  try {const data = JSON.parse($("analysis-input").value); applyAnalysis(data);}
  catch (error) {setText("analysis-message", readableError(error));}
});
$("analysis-file").addEventListener("change", async (event) => {
  const file = event.target.files[0]; if (!file) return;
  if (file.size > 1048576) {setText("analysis-message", "文件超过 1 MiB（1048576 字节），请减少采样后导入。");return;}
  try {const text = await file.text(); JSON.parse(text); $("analysis-input").value = text; setText("analysis-message", "文件已读取。检查来源与点对后点击应用 JSON。");}
  catch(error) {setText("analysis-message", `读取失败：${readableError(error)}`);}
  event.target.value = "";
});
$("export-analysis").addEventListener("click", () => {
  if (!analysisState?.data) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(analysisState.data, null, 2)], {type:"application/json"}));
  const link = document.createElement("a");link.href = url;link.download = "courtsense-analysis-input.json";link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("export-analysis-result").addEventListener("click", () => {
  if (!["ready", "invalidated"].includes(analysisState?.status)) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(analysisState, null, 2)], {type:"application/json"}));
  const link = document.createElement("a");
  link.href = url; link.download = "courtsense-analysis-snapshot.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("reset-analysis").addEventListener("click", async () => {
  if (analysisBusy) return;
  analysisBusy = true;
  try {await analysisRequest("/api/analysis/reset", {}); analysisState = null; renderAnalysis();setText("analysis-message", "分析已清除，采集观察保持独立。");}
  catch(error) {setText("analysis-message", `未清除：${readableError(error)}`);}
  finally {analysisBusy = false;}
});
$("sample-analysis").addEventListener("click", () => {
  const sample = {schema_version:1,mode:"offline_development",source_name:"synthetic-demo",synthetic:true,image_space:{id:"synthetic-space",width:1280,height:720,service_instance_id:"offline"},calibration:{input_space:"undistorted_pixels",points:[{pixel:[200,620],court_m:[0,0]},{pixel:[1080,620],court_m:[6.1,0]},{pixel:[1080,100],court_m:[6.1,13.4]},{pixel:[200,100],court_m:[0,13.4]}]},player_points:[{t_s:0,player_id:"p1",pixel:[450,500],contact_confirmed:true},{t_s:0.5,player_id:"p1",pixel:[600,420],contact_confirmed:true},{t_s:1,player_id:"p1",pixel:[720,490],contact_confirmed:true}],shuttle_points:[{t_s:0,track_id:"s1",pixel:[400,180]},{t_s:0.1,track_id:"s1",pixel:[600,120]},{t_s:0.2,track_id:"s1",pixel:[850,350]}],events:[{event_id:"demo-e1",t_s:0.1,type:"smash",status:"candidate",source:"synthetic manual example"}]};
  $("analysis-input").value = JSON.stringify(sample, null, 2);
  if (analysisState?.binding) {
    setText("analysis-message", "样例已填入编辑器，尚未应用。当前来源已有真实帧，请另开无真实帧的工作台预览离线合成样例；当前分析保持不变。");
    return;
  }
  applyAnalysis(sample);
});
$("live-analysis-template").addEventListener("click", () => {
  const binding = analysisState?.binding;
  if (!binding) return;
  $("analysis-input").value = JSON.stringify({schema_version:1,mode:"live",source_name:"manual-current-source",synthetic:false,binding,image_space:binding.image_space,calibration:null,player_points:[],shuttle_points:[],events:[]}, null, 2);
  setText("analysis-message", "已填入当前来源与图像空间。请添加去畸变标定点对与真实采样，再点击应用 JSON；来源变化后需重新读取模板。");
});
for (const id of ["show-trails", "show-world"]) $(id).addEventListener("change", drawCourt);
$("show-shuttle").addEventListener("change", drawTrajectory);
selectWorkspace(location.hash.slice(1));
renderPerson();
drawCourt();
drawDistribution();
refresh();
setInterval(() => {if (!paused && !document.hidden) refresh();}, 1200);
