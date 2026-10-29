/* USTC report helper - local GUI */
"use strict";

let state = null;
let departments = [];
let previewData = null;
let toastTimer = null;
let logTimer = null;

const $ = (id) => document.getElementById(id);
const qs = (selector) => document.querySelector(selector);
const qsa = (selector) => Array.from(document.querySelectorAll(selector));

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function toast(message, type = "info", duration = 4200) {
  const box = $("toast");
  box.textContent = message;
  box.className = "toast show " + (type === "ok" ? "ok" : type === "err" ? "err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    box.className = "toast";
  }, duration);
}

async function api(path, options = {}) {
  const init = { credentials: "same-origin", ...options };
  if (init.body && typeof init.body !== "string") {
    init.body = JSON.stringify(init.body);
    init.headers = { "Content-Type": "application/json", ...(init.headers || {}) };
  }
  const response = await fetch(path, init);
  let data;
  try {
    data = await response.json();
  } catch (error) {
    throw new Error(`HTTP ${response.status}`);
  }
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function showDialog(title, html) {
  $("dialog-title").textContent = title;
  $("dialog-body").innerHTML = html;
  $("dialog").classList.remove("hidden");
}

function hideDialog() {
  $("dialog").classList.add("hidden");
}

function switchTab(name) {
  qsa(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  qsa(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `panel-${name}`));
  if (name === "service") refreshLogs(true);
}

function setBusy(button, busy, text) {
  if (!button) return;
  button.disabled = busy;
  if (busy) {
    button.dataset.original = button.textContent;
    button.textContent = text || "处理中…";
  } else if (button.dataset.original) {
    button.textContent = button.dataset.original;
    delete button.dataset.original;
  }
}

function secretHint(inputId, hintId, status) {
  const input = $(inputId);
  const hint = $(hintId);
  if (!input) return;
  input.value = "";
  if (status && status.set) {
    input.placeholder = `已保存（长度 ${status.length}），留空不修改`;
    if (hint) {
      hint.textContent = "已配置";
      hint.className = "secret ok";
    }
  } else {
    input.placeholder = "未配置";
    if (hint) {
      hint.textContent = "未配置";
      hint.className = "secret bad";
    }
  }
}

function renderState(data) {
  state = data;
  departments = (data.departments || []).map((item) => ({ code: item.code, name: item.name }));

  $("platform-badge").textContent = data.platform || "—";
  const service = data.service || {};
  let pillText = "未安装";
  let pillClass = "pill muted";
  if (!service.supported) {
    pillText = "手动模式";
  } else if (service.installed && service.loaded) {
    pillText = service.running ? "运行中" : "已启用";
    pillClass = "pill ok";
  } else if (service.installed) {
    pillText = "已停止";
    pillClass = "pill bad";
  }
  const pill = $("service-pill");
  pill.textContent = pillText;
  pill.className = pillClass;

  $("card-service").textContent = pillText;
  $("card-service-detail").textContent = service.installed
    ? `已运行 ${service.runs == null ? "—" : service.runs} 次 · 间隔 ${service.interval || data.schedule_interval_seconds}s`
    : "尚未安装定时任务";
  $("card-exit").textContent = service.last_exit == null ? "—" : String(service.last_exit);
  $("card-runs").textContent = service.runs == null ? "运行次数未知" : `累计 ${service.runs} 次`;
  if (previewData) {
    $("card-selected").textContent = String((previewData.selected || []).length);
    $("card-eligible").textContent = String(previewData.eligible_count == null ? "—" : previewData.eligible_count);
  }

  const minutes = Math.round((Number(data.schedule_interval_seconds) || 120) / 6) / 10;
  $("overview-hint").textContent =
    `${departments.length} 个院系 · 每 ${minutes} 分钟检测 · 每轮最多成功选 ${data.max_grabs_per_cycle} 门 · ` +
    `成绩查询${data.enable_grade_check ? "开启" : "关闭"} · 冲突窗口 ${data.conflict_window_minutes} 分钟`;

  $("email-sender").value = data.email.sender || "";
  $("email-receiver").value = data.email.receiver || "";
  $("smtp-server").value = data.email.server || "";
  $("smtp-port").value = data.email.port == null ? "" : data.email.port;

  secretHint("smtp-auth", "hint-auth", data.secrets.auth_code);
  secretHint("cookie-GS_DBLOGIN_TOKEN", "hint-GS_DBLOGIN_TOKEN", data.secrets.GS_DBLOGIN_TOKEN);
  secretHint("cookie-GS_SESSIONID", "hint-GS_SESSIONID", data.secrets.GS_SESSIONID);
  secretHint("cookie-_WEU", "hint-_WEU", data.secrets._WEU);
  secretHint("cookie-route", "hint-route", data.secrets.route);

  $("cookie-EMAP_LANG").value = data.optional_cookies.EMAP_LANG || "";
  $("cookie-THEME").value = data.optional_cookies.THEME || "";

  $("enable-grade-check").checked = Boolean(data.enable_grade_check);
  $("max-grabs").value = data.max_grabs_per_cycle;
  $("conflict-window").value = data.conflict_window_minutes;
  $("schedule-interval").value = data.schedule_interval_seconds;
  $("page-size").value = data.page_size;
  $("enable-keepalive").checked = Boolean(data.enable_keepalive);
  $("particular-bgbm").value = data.particular_bgbm || "";
  $("exclude-list").value = (data.exclude || []).join("\n");

  $("config-path").textContent = data.config_path || "—";
  $("save-hint").textContent = "配置已加载";

  renderDepartments();
  renderServiceDetail(data);
}

function renderDepartments() {
  const list = $("departments-list");
  list.innerHTML = "";
  departments.forEach((dept, index) => {
    const row = document.createElement("div");
    row.className = "dept-row";
    row.innerHTML = `
      <span class="dept-index">${index + 1}</span>
      <span class="dept-name">${esc(dept.name)} <code>${esc(dept.code)}</code></span>
      <span class="dept-actions">
        <button type="button" data-act="up" title="上移" ${index === 0 ? "disabled" : ""}>↑</button>
        <button type="button" data-act="down" title="下移" ${index === departments.length - 1 ? "disabled" : ""}>↓</button>
        <button type="button" data-act="remove" class="remove" title="移除">×</button>
      </span>`;
    row.querySelector('[data-act="up"]').onclick = () => moveDepartment(index, -1);
    row.querySelector('[data-act="down"]').onclick = () => moveDepartment(index, 1);
    row.querySelector('[data-act="remove"]').onclick = () => removeDepartment(index);
    list.appendChild(row);
  });
  updateDepartmentSelect();
}

function updateDepartmentSelect() {
  const select = $("department-select");
  const used = new Set(departments.map((item) => item.code));
  const known = (state && state.known_departments) || [];
  const available = known.filter((item) => !used.has(item.code));
  select.innerHTML = "";
  if (!available.length) {
    const option = document.createElement("option");
    option.textContent = "全部已知院系已添加";
    option.value = "";
    select.appendChild(option);
    select.disabled = true;
    $("add-department").disabled = true;
    return;
  }
  select.disabled = false;
  $("add-department").disabled = false;
  available.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.code;
    option.textContent = `${item.name}（${item.code}）`;
    select.appendChild(option);
  });
}

function moveDepartment(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= departments.length) return;
  const [item] = departments.splice(index, 1);
  departments.splice(target, 0, item);
  renderDepartments();
}

function removeDepartment(index) {
  if (departments.length <= 1) {
    toast("至少保留一个院系", "err");
    return;
  }
  departments.splice(index, 1);
  renderDepartments();
}

function addDepartment() {
  const select = $("department-select");
  const code = select.value;
  if (!code) return;
  const known = (state && state.known_departments) || [];
  const found = known.find((item) => item.code === code);
  if (!found) return;
  departments.push({ code: found.code, name: found.name });
  renderDepartments();
}

function addCustomDepartment() {
  const code = $("custom-code").value.trim();
  const name = $("custom-name").value.trim();
  if (!code || !name) {
    toast("请填写院系代码和名称", "err");
    return;
  }
  if (departments.some((item) => item.code === code)) {
    toast("该院系代码已存在", "err");
    return;
  }
  departments.push({ code, name });
  $("custom-code").value = "";
  $("custom-name").value = "";
  renderDepartments();
}

function collectPayload() {
  const number = (id, fallback) => {
    const value = Number($(id).value);
    return Number.isFinite(value) ? value : fallback;
  };
  return {
    email: {
      sender: $("email-sender").value.trim(),
      receiver: $("email-receiver").value.trim(),
      server: $("smtp-server").value.trim(),
      port: number("smtp-port", 465),
      auth_code: $("smtp-auth").value.trim(),
    },
    cookies: {
      GS_DBLOGIN_TOKEN: $("cookie-GS_DBLOGIN_TOKEN").value.trim(),
      GS_SESSIONID: $("cookie-GS_SESSIONID").value.trim(),
      _WEU: $("cookie-_WEU").value.trim(),
      route: $("cookie-route").value.trim(),
      EMAP_LANG: $("cookie-EMAP_LANG").value.trim(),
      THEME: $("cookie-THEME").value.trim(),
    },
    departments: departments.map((item) => ({ code: item.code, name: item.name })),
    particular_bgbm: $("particular-bgbm").value.trim(),
    enable_grade_check: $("enable-grade-check").checked,
    enable_keepalive: $("enable-keepalive").checked,
    max_grabs_per_cycle: number("max-grabs", 1),
    conflict_window_minutes: number("conflict-window", 120),
    schedule_interval_seconds: number("schedule-interval", 120),
    page_size: number("page-size", 999),
    exclude: $("exclude-list").value.split("\n").map((line) => line.trim()).filter(Boolean),
  };
}

async function saveConfig(showMessage = true) {
  const button = $("save-config");
  setBusy(button, true, "保存中…");
  try {
    const data = await api("/api/config", { method: "POST", body: collectPayload() });
    renderState(data);
    $("save-hint").textContent = "刚刚已保存";
    if (showMessage) toast("配置已保存", "ok");
    return data;
  } finally {
    setBusy(button, false);
  }
}

async function refreshState(showMessage = false) {
  try {
    const data = await api("/api/state");
    renderState(data);
    if (showMessage) toast("状态已刷新", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

function renderServiceDetail(data) {
  const service = data.service || {};
  const info = [
    ["平台", data.platform],
    ["配置目录", data.home],
    ["服务", service.supported === false ? "当前平台仅支持手动运行" : service.installed ? (service.loaded ? "已加载" : "已安装但未加载") : "未安装"],
    ["上次退出码", service.last_exit == null ? "—" : String(service.last_exit)],
    ["运行次数", service.runs == null ? "—" : String(service.runs)],
    ["检测间隔", `${data.schedule_interval_seconds} 秒`],
    ["任务标识", service.label || "—"],
  ];
  if (service.last_run) info.push(["上次运行", service.last_run]);
  if (service.next_run) info.push(["下次运行", service.next_run]);
  $("service-detail").innerHTML = info
    .map(([key, value]) => `<dt>${esc(key)}</dt><dd>${esc(value)}</dd>`)
    .join("");
}

async function refreshLogs(silent = false) {
  try {
    const data = await api("/api/logs?lines=300");
    const output = $("log-output");
    output.textContent = data.text || "（暂无日志）";
    output.scrollTop = output.scrollHeight;
  } catch (error) {
    if (!silent) toast(error.message, "err");
  }
}

async function testPlatform() {
  const button = $("btn-test-platform");
  setBusy(button, true, "测试中…");
  try {
    const result = await api("/api/test/platform", { method: "POST", body: {} });
    const departments = (result.departments || [])
      .slice(0, 12)
      .map((item) => `<li>${esc(item.name)}（${esc(item.code)}）：${item.count} 条</li>`)
      .join("");
    showDialog(
      "平台连接正常",
      `<p>返回 ${result.rows} 条记录，totalSize=${esc(result.total_size)}。</p>
       <p class="hint">院系分布（前 12）：</p><ul>${departments || "<li>无</li>"}</ul>`
    );
  } catch (error) {
    toast(error.message, "err");
  } finally {
    setBusy(button, false);
  }
}

async function testSmtp() {
  const button = $("btn-test-smtp");
  setBusy(button, true, "测试中…");
  try {
    const result = await api("/api/test/smtp", { method: "POST", body: {} });
    showDialog("SMTP 测试", `<p>${esc(result.message)}</p>`);
  } catch (error) {
    toast(error.message, "err");
  } finally {
    setBusy(button, false);
  }
}

async function testEmail() {
  if (!window.confirm("发送一封测试邮件到收件邮箱？")) return;
  const button = $("btn-test-email");
  setBusy(button, true, "发送中…");
  try {
    const result = await api("/api/test/email", { method: "POST", body: {} });
    showDialog("测试邮件", `<p>${esc(result.message)}</p>`);
  } catch (error) {
    toast(error.message, "err");
  } finally {
    setBusy(button, false);
  }
}

function renderPreview(data) {
  previewData = data;
  const eligible = data.eligible || [];
  const selected = data.selected || [];
  $("card-selected").textContent = String(selected.length);
  $("card-eligible").textContent = String(data.eligible_count || 0);

  const summary = [
    `平台返回 ${data.rows} 条`,
    `通过筛选 ${data.eligible_count} 条`,
    `冲突窗口 ${data.conflict_window_minutes} 分钟`,
  ];
  if (data.eligible_count > eligible.length) summary.push(`仅展示前 ${eligible.length} 条`);
  if (data.selected_error) summary.push("已选报告读取失败：" + data.selected_error);
  $("preview-summary").textContent = summary.join(" · ");

  const body = $("eligible-body");
  if (!eligible.length) {
    body.innerHTML = `<tr><td colspan="7" class="empty">当前没有符合条件的报告</td></tr>`;
  } else {
    body.innerHTML = eligible.map((row) => {
      const index = departments.findIndex((item) => item.code === row.YXDM);
      const priority = index >= 0 ? index + 1 : "—";
      const remaining = Number(row.KXRS) - Number(row.YXRS || 0);
      const conflict = row.conflicts_selected;
      const status = conflict
        ? '<span class="badge bad">与已选冲突</span>'
        : '<span class="badge ok">可抢</span>';
      return `<tr>
        <td>${esc(priority)}</td>
        <td>${esc(row.YXDM_DISPLAY)}</td>
        <td><strong>${esc(row.BGTMZW)}</strong><div class="hint">${esc(row.BGBM)}</div></td>
        <td>${esc(row.BGSJ)}</td>
        <td>${esc(row.JZSJ)}</td>
        <td>${Number.isFinite(remaining) ? remaining : "—"}</td>
        <td>${status}</td>
      </tr>`;
    }).join("");
  }

  $("selected-summary").textContent = `${selected.length} 门`;
  const selectedBody = $("selected-body");
  if (!selected.length) {
    selectedBody.innerHTML = `<tr><td colspan="5" class="empty">暂无已选报告</td></tr>`;
  } else {
    selectedBody.innerHTML = selected.map((row) => `<tr>
      <td>${esc(row.YXDM_DISPLAY)}</td>
      <td>${esc(row.BGTMZW)}</td>
      <td>${esc(row.BGSJ)}</td>
      <td>${esc(row.JZSJ)}</td>
      <td>${esc(row.DD)}</td>
    </tr>`).join("");
  }
}

async function refreshPreview() {
  const button = $("preview-refresh");
  const overviewButton = $("btn-preview");
  setBusy(button, true, "查询中…");
  setBusy(overviewButton, true, "查询中…");
  try {
    const data = await api("/api/preview", { method: "POST", body: {} });
    renderPreview(data);
    switchTab("preview");
    toast(`查询完成：${data.eligible_count} 门可抢`, data.eligible_count ? "ok" : "info");
  } catch (error) {
    toast(error.message, "err");
  } finally {
    setBusy(button, false);
    setBusy(overviewButton, false);
  }
}

async function serviceAction(path, confirmText) {
  if (confirmText && !window.confirm(confirmText)) return;
  const output = $("service-output");
  output.classList.remove("hidden");
  output.textContent = "执行中，请稍候…";
  try {
    const result = await api(`/api/service/${path}`, { method: "POST", body: {} });
    output.textContent = result.output || result.message || "完成";
    if (result.service) {
      state.service = result.service;
      renderServiceDetail(state);
      renderState(state);
    }
    toast("操作完成", "ok");
    refreshLogs(true);
  } catch (error) {
    output.textContent = error.message;
    toast(error.message, "err");
  }
}

async function installService() {
  const button = $("btn-install-service");
  setBusy(button, true, "安装中…");
  try {
    await saveConfig(false);
    const result = await api("/api/service/install", { method: "POST", body: {} });
    $("service-output").classList.remove("hidden");
    $("service-output").textContent = result.output || "安装完成";
    if (result.service) {
      state.service = result.service;
      renderServiceDetail(state);
      renderState(state);
    }
    toast("定时任务已安装 / 更新", "ok");
    refreshLogs(true);
  } catch (error) {
    toast(error.message, "err");
    $("service-output").classList.remove("hidden");
    $("service-output").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
}

function bind() {
  qsa(".tab").forEach((tab) => tab.addEventListener("click", () => switchTab(tab.dataset.tab)));
  $("refresh-btn").addEventListener("click", () => refreshState(true));
  $("save-config").addEventListener("click", () => saveConfig(true).catch((error) => toast(error.message, "err")));
  $("save-install").addEventListener("click", async () => {
    if (!window.confirm("保存配置并安装 / 更新定时任务？")) return;
    await installService();
  });
  $("add-department").addEventListener("click", addDepartment);
  $("add-custom").addEventListener("click", addCustomDepartment);
  $("btn-test-platform").addEventListener("click", testPlatform);
  $("btn-test-smtp").addEventListener("click", testSmtp);
  $("btn-test-email").addEventListener("click", testEmail);
  $("btn-preview").addEventListener("click", refreshPreview);
  $("preview-refresh").addEventListener("click", refreshPreview);
  $("btn-install-service").addEventListener("click", () => {
    if (window.confirm("安装 / 更新定时任务？会保存当前配置并同步代码。")) installService();
  });
  $("btn-run-now").addEventListener("click", () => serviceAction("start"));
  $("btn-service-install").addEventListener("click", () => {
    if (window.confirm("安装 / 更新定时任务？会保存当前配置并同步代码。")) installService();
  });
  $("btn-service-start").addEventListener("click", () => serviceAction("start"));
  $("btn-service-stop").addEventListener("click", () => serviceAction("stop", "停止定时任务？任务会从 launchd / 任务计划中卸载，之后可以重新启动。"));
  $("btn-service-uninstall").addEventListener("click", () => serviceAction("uninstall", "卸载定时任务？配置与数据会保留。"));
  $("log-refresh").addEventListener("click", () => refreshLogs(false));
  $("dialog-close").addEventListener("click", hideDialog);
  $("dialog").addEventListener("click", (event) => {
    if (event.target === $("dialog")) hideDialog();
  });
  $("shutdown-btn").addEventListener("click", async () => {
    if (!window.confirm("关闭 GUI 服务？定时任务不会受影响。")) return;
    try {
      await api("/api/shutdown", { method: "POST", body: {} });
      toast("GUI 已停止，可以关闭页面", "ok", 6000);
      clearInterval(logTimer);
    } catch (error) {
      toast(error.message, "err");
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideDialog();
  });
}

async function init() {
  bind();
  try {
    const data = await api("/api/state");
    renderState(data);
    await refreshLogs(true);
  } catch (error) {
    toast(error.message, "err");
    showDialog("无法连接 GUI", `<p>${esc(error.message)}</p><p>请回到终端确认 GUI 仍在运行。</p>`);
    return;
  }
  const initialTab = new URLSearchParams(window.location.search).get("tab");
  if (initialTab) switchTab(initialTab);
  logTimer = setInterval(() => {
    const active = qs("#panel-service").classList.contains("active");
    if (active && $("log-auto").checked) refreshLogs(true);
  }, 10000);
}

document.addEventListener("DOMContentLoaded", init);
