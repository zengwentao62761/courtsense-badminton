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
  setText("source-label", source.label || "尚未提供来源");
  setText(
    "source-kind",
    { rdk: "RDK HTTP 姿态服务", video: "本地视频分析" }[source.kind] ||
      source.kind ||
      "默认 RDK 服务",
  );
  setText(
    "platform",
    { desktop_validation: "桌面验证", rdk: "RDK 设备", rdk_x5: "RDK X5" }[
      source.platform
    ] ||
      source.platform ||
      "待确认",
  );
  $("source-label").title = source.label || "";
  const errorText = errors
    .map((error) =>
      typeof error === "string"
        ? error
        : error.message || JSON.stringify(error),
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
  ctx.fillStyle = "#dce8ed";
  ctx.fill();
  ctx.beginPath();
  corners.forEach((point, i) => {
    const p = project(...point);
    i ? ctx.lineTo(...p) : ctx.moveTo(...p);
  });
  ctx.closePath();
  ctx.fillStyle = "#168893";
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
}).observe(document.querySelector("main"));
renderPerson();
drawCourt();
drawDistribution();
refresh();
setInterval(() => {
  if (!paused && !document.hidden) refresh();
}, 1200);
