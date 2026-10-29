/* USTC report helper - minimal local GUI */
"use strict";

let state = null;
let departments = [];
let selectedData = null;
let messageTimer = null;

const $ = (id) => document.getElementById(id);
const qsa = (selector) => Array.from(document.querySelectorAll(selector));

function switchPane(name) {
  qsa(".seg-btn").forEach((button) => {
    const active = button.dataset.pane === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
    button.tabIndex = active ? 0 : -1;
  });
  qsa(".config-pane").forEach((pane) => {
    pane.classList.toggle("active", pane.id === `pane-${name}`);
  });
}

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function formatDate(value) {
  return String(value || "").slice(0, 16);
}

function showMessage(text, type = "info", autoHide = true) {
  const box = $("message");
  clearTimeout(messageTimer);
  box.textContent = text;
  box.className = `message ${type}`;
  if (autoHide) {
    messageTimer = setTimeout(() => box.classList.add("hidden"), type === "err" ? 10000 : 6000);
  }
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
    throw new Error(data.error || data.output || `HTTP ${response.status}`);
  }
  return data;
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
    hint.textContent = "已配置";
    hint.className = "secret ok";
  } else {
    input.placeholder = "未配置";
    hint.textContent = "未配置";
    hint.className = "secret bad";
  }
}

function renderService() {
  const service = (state && state.service) || {};
  const pill = $("service-pill");
  const toggle = $("service-toggle");
  const enabled = Boolean(service.supported && service.installed && service.loaded);

  if (!service.supported) {
    pill.textContent = "手动模式";
    pill.className = "service-state off";
    toggle.classList.remove("on");
    toggle.setAttribute("aria-checked", "false");
    toggle.disabled = true;
    toggle.title = "当前平台请手动运行";
    return;
  }

  if (enabled) {
    pill.textContent = "已启用";
    pill.className = "service-state on";
  } else if (service.installed) {
    pill.textContent = "已停止";
    pill.className = "service-state off";
  } else {
    pill.textContent = "未安装";
    pill.className = "service-state off";
  }

  toggle.classList.toggle("on", enabled);
  toggle.setAttribute("aria-checked", enabled ? "true" : "false");
  toggle.disabled = false;
  toggle.title = enabled ? "点击停止自动抢课" : "点击启用自动抢课";
}

function updateStatusLine() {
  if (!state) return;
  const service = state.service || {};
  const parts = [];

  if (!service.supported) {
    parts.push("当前平台请手动运行");
  } else if (service.installed && service.loaded) {
    parts.push("自动抢课已启用");
    if (service.runs != null) parts.push(`已运行 ${service.runs} 次`);
    if (service.last_exit != null) parts.push(`上次退出码 ${service.last_exit}`);
  } else if (service.installed) {
    parts.push("自动抢课已停止");
  } else {
    parts.push("自动抢课未启用");
  }
  parts.push(`每 ${state.schedule_interval_seconds} 秒检测`);

  if (selectedData) {
    parts.push(`已选 ${(selectedData.selected || []).length} 门`);
    parts.push(`可抢 ${selectedData.eligible_count || 0} 门`);
  }
  $("status-line").textContent = parts.join(" · ");
}

function renderState(data) {
  state = data;
  departments = (data.departments || []).map((item) => ({ code: item.code, name: item.name }));

  $("email-sender").value = data.email.sender || "";
  $("email-receiver").value = data.email.receiver || "";
  $("smtp-server").value = data.email.server || "";
  $("smtp-port").value = data.email.port == null ? "" : data.email.port;

  secretHint("smtp-auth", "hint-auth", data.secrets.auth_code);
  secretHint("cookie-GS_DBLOGIN_TOKEN", "hint-GS_DBLOGIN_TOKEN", data.secrets.GS_DBLOGIN_TOKEN);
  secretHint("cookie-GS_SESSIONID", "hint-GS_SESSIONID", data.secrets.GS_SESSIONID);
  secretHint("cookie-_WEU", "hint-_WEU", data.secrets._WEU);
  secretHint("cookie-route", "hint-route", data.secrets.route);

  $("enable-grade-check").checked = Boolean(data.enable_grade_check);
  $("schedule-interval").value = data.schedule_interval_seconds;
  $("config-path").textContent = data.config_path || "—";
  $("config-summary").textContent = `${departments.length} 个院系 · 每 ${data.schedule_interval_seconds} 秒`;

  renderDepartments();
  renderService();
  updateStatusLine();
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
        <button type="button" data-act="up" title="上移" aria-label="上移 ${esc(dept.name)}" ${index === 0 ? "disabled" : ""}>↑</button>
        <button type="button" data-act="down" title="下移" aria-label="下移 ${esc(dept.name)}" ${index === departments.length - 1 ? "disabled" : ""}>↓</button>
        <button type="button" data-act="remove" class="remove" title="移除" aria-label="移除 ${esc(dept.name)}">×</button>
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
    showMessage("至少保留一个院系", "err", false);
    return;
  }
  departments.splice(index, 1);
  renderDepartments();
}

function addDepartment() {
  const code = $("department-select").value;
  if (!code) return;
  const found = ((state && state.known_departments) || []).find((item) => item.code === code);
  if (!found) return;
  departments.push({ code: found.code, name: found.name });
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
    },
    departments: departments.map((item) => ({ code: item.code, name: item.name })),
    enable_grade_check: $("enable-grade-check").checked,
    schedule_interval_seconds: number("schedule-interval", 120),
  };
}

async function saveConfig(showMessage = true) {
  const button = $("save-config");
  setBusy(button, true, "保存中…");
  try {
    const data = await api("/api/config", { method: "POST", body: collectPayload() });
    renderState(data);
    if (showMessage) showMessage("配置已保存", "ok");
    return data;
  } catch (error) {
    const message = error.message || "";
    if (/院系/.test(message)) switchPane("departments");
    else if (/间隔|成绩/.test(message)) switchPane("settings");
    else if (/邮箱|SMTP|授权码|Cookie|密码/.test(message)) switchPane("account");
    throw error;
  } finally {
    setBusy(button, false);
  }
}

function renderSelected(data) {
  selectedData = data;
  const selected = data.selected || [];
  $("selected-summary").textContent = `已选 ${selected.length} 门 · 可抢 ${data.eligible_count || 0} 门`;

  const list = $("selected-list");
  if (!selected.length) {
    list.innerHTML = `<div class="selected-empty">暂无已选报告</div>`;
  } else {
    list.innerHTML = selected.map((row) => `
      <article class="selected-item">
        <div class="selected-title">${esc(row.BGTMZW)}</div>
        <div class="selected-meta">
          <span class="selected-dept">${esc(row.YXDM_DISPLAY)}</span>
          <span>${esc(formatDate(row.BGSJ))}</span>
          <span>截止 ${esc(formatDate(row.JZSJ))}</span>
        </div>
      </article>`).join("");
  }
  if (data.selected_error) {
    showMessage(`已选报告读取失败：${data.selected_error}`, "err", false);
  }
  updateStatusLine();
}

async function refreshSelected(silent = false) {
  const button = $("refresh-selected");
  setBusy(button, true, "刷新中…");
  try {
    const data = await api("/api/preview", { method: "POST", body: {} });
    renderSelected(data);
    if (!silent) showMessage("已刷新", "ok");
  } catch (error) {
    $("selected-summary").textContent = "读取失败";
    $("selected-list").innerHTML = `<div class="selected-empty error">读取失败，请检查平台 Cookie</div>`;
    showMessage(error.message, "err", false);
  } finally {
    setBusy(button, false);
  }
}

async function toggleService() {
  if (!state || !state.service) return;
  const button = $("service-toggle");
  const service = state.service;

  if (service.installed && service.loaded) {
    if (!window.confirm("停止自动抢课？配置和数据会保留。")) return;
    button.disabled = true;
    try {
      const result = await api("/api/service/stop", { method: "POST", body: {} });
      if (result.service) state.service = result.service;
      renderService();
      updateStatusLine();
      showMessage("自动抢课已停止", "ok");
    } catch (error) {
      showMessage(error.message, "err", false);
      renderService();
    }
    return;
  }

  button.disabled = true;
  try {
    await saveConfig(false);
    button.disabled = true;
    const interval = Number($("schedule-interval").value) || 120;
    const result = await api("/api/service/install", {
      method: "POST",
      body: { interval_seconds: interval, keepalive: false },
    });
    if (result.service) state.service = result.service;
    renderService();
    updateStatusLine();
    showMessage("自动抢课已启用", "ok");
  } catch (error) {
    showMessage(error.message, "err", false);
    renderService();
  }
}

function bind() {
  qsa(".seg-btn").forEach((button) => {
    button.addEventListener("click", () => switchPane(button.dataset.pane));
    button.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const buttons = qsa(".seg-btn");
      const index = buttons.indexOf(button);
      const next = buttons[(index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length];
      switchPane(next.dataset.pane);
      next.focus();
    });
  });
  $("save-config").addEventListener("click", () => saveConfig(true).catch((error) => showMessage(error.message, "err", false)));
  $("service-toggle").addEventListener("click", toggleService);
  $("refresh-selected").addEventListener("click", () => refreshSelected(false));
  $("add-department").addEventListener("click", addDepartment);
  $("shutdown-btn").addEventListener("click", async () => {
    if (!window.confirm("关闭 GUI？自动抢课不会受影响。")) return;
    try {
      await api("/api/shutdown", { method: "POST", body: {} });
      showMessage("GUI 已停止，可以关闭页面", "ok", false);
    } catch (error) {
      showMessage(error.message, "err", false);
    }
  });
}

async function init() {
  bind();
  const requestedPane = new URLSearchParams(window.location.search).get("pane");
  switchPane(["account", "departments", "settings"].includes(requestedPane) ? requestedPane : "account");
  try {
    const data = await api("/api/state");
    renderState(data);
  } catch (error) {
    showMessage(error.message, "err", false);
    return;
  }
  await refreshSelected(true);
}

document.addEventListener("DOMContentLoaded", init);
