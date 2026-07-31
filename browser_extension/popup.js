const elements = {
  url: document.querySelector("#url"),
  filename: document.querySelector("#filename"),
  connections: document.querySelector("#connections"),
  startImmediately: document.querySelector("#startImmediately"),
  interceptDownloads: document.querySelector("#interceptDownloads"),
  showMediaPanel: document.querySelector("#showMediaPanel"),
  useBrowserSession: document.querySelector("#useBrowserSession"),
  send: document.querySelector("#send"),
  scanPage: document.querySelector("#scanPage"),
  mediaSummary: document.querySelector("#mediaSummary"),
  result: document.querySelector("#result"),
  connectionStatus: document.querySelector("#connectionStatus"),
  candidatePanel: document.querySelector("#candidatePanel"),
  candidateList: document.querySelector("#candidateList"),
  downloadSelected: document.querySelector("#downloadSelected")
};
let scannedCandidates = [];

void initialize();

async function initialize() {
  const settings = await chrome.storage.local.get({
    interceptDownloads: false,
    showMediaPanel: true,
    useBrowserSession: false,
    connections: 4
  });
  elements.interceptDownloads.checked = Boolean(settings.interceptDownloads);
  elements.showMediaPanel.checked = Boolean(settings.showMediaPanel);
  elements.useBrowserSession.checked =
    Boolean(settings.useBrowserSession) && await hasCookiePermission();
  elements.connections.value = String(settings.connections || 4);

  const [activeTab] = await chrome.tabs.query({
    active: true,
    currentWindow: true
  });
  if (isHttpUrl(activeTab?.url)) {
    elements.url.value = activeTab.url;
  }

  try {
    const response = await sendRuntimeMessage({ type: "sdm-ping" });
    if (response?.ok) {
      setConnectionStatus(
        `Connected • Native Host ${response.host_version || ""}`,
        true
      );
    } else {
      setConnectionStatus(response?.error || "Native Host unavailable.", false);
    }
  } catch (error) {
    setConnectionStatus(error.message, false);
  }
}

elements.send.addEventListener("click", async () => {
  const url = elements.url.value.trim();
  if (!isHttpUrl(url)) {
    showResult("Enter a valid HTTP or HTTPS file or media-page URL.", false);
    elements.url.focus();
    return;
  }

  elements.send.disabled = true;
  showResult("Sending download to SDM…", null);
  try {
    const response = await sendRuntimeMessage({
      type: "sdm-download",
      payload: {
        url,
        source_url: url,
        filename: elements.filename.value.trim(),
        connections: Number(elements.connections.value),
        start_immediately: elements.startImmediately.checked,
        media_kind: mediaKindForPage(url)
      }
    });
    if (!response?.ok) {
      showResult(response?.error || "SDM rejected the request.", false);
      return;
    }
    const sessionNote = response.session_attached
      ? " • secure browser session attached"
      : "";
    const adapterNote =
      response.adapter_label && response.site_adapter !== "direct"
        ? ` • ${response.adapter_label} adapter`
        : "";
    const ruleNote = response.rule_reason
      ? ` • ${response.rule_reason}`
      : "";
    if (response.duplicate) {
      const duplicateMessage =
        response.duplicate_action === "completed"
          ? "Already completed in SDM"
          : response.duplicate_action === "active"
            ? "Already active in SDM"
            : "Existing SDM download is ready to resume";
      showResult(
        `${duplicateMessage}: ${response.filename}${ruleNote}`,
        true
      );
      return;
    }
    showResult(
      `Sent to Download File Info: ${response.filename}${adapterNote}${sessionNote}${ruleNote}`,
      true
    );
  } catch (error) {
    showResult(error.message, false);
  } finally {
    elements.send.disabled = false;
  }
});


elements.scanPage.addEventListener("click", async () => {
  elements.scanPage.disabled = true;
  elements.mediaSummary.textContent = "Scanning visible page media…";
  try {
    const response = await sendRuntimeMessage({ type: "sdm-scan-active-tab" });
    if (!response?.ok) {
      elements.mediaSummary.textContent = response?.error || "Page scan failed.";
      return;
    }
    scannedCandidates = deduplicateCandidates(response.candidates || []);
    elements.mediaSummary.textContent =
      `Detected media: ${scannedCandidates.length} ` +
      `(${scannedCandidates.filter((item) => item.kind === "video").length} video, ` +
      `${scannedCandidates.filter((item) => item.kind === "audio").length} audio)`;
    renderCandidates();
  } catch (error) {
    elements.mediaSummary.textContent = error.message || "Page scan failed.";
  } finally {
    elements.scanPage.disabled = false;
  }
});

elements.interceptDownloads.addEventListener("change", saveSettings);
elements.showMediaPanel.addEventListener("change", saveSettings);
elements.useBrowserSession.addEventListener(
  "change",
  updateSessionPermission
);
elements.connections.addEventListener("change", saveSettings);

async function saveSettings() {
  await chrome.storage.local.set({
    interceptDownloads: elements.interceptDownloads.checked,
    showMediaPanel: elements.showMediaPanel.checked,
    useBrowserSession: elements.useBrowserSession.checked,
    connections: Number(elements.connections.value)
  });
}

async function updateSessionPermission() {
  if (elements.useBrowserSession.checked) {
    const granted = await requestCookiePermission();
    if (!granted) {
      elements.useBrowserSession.checked = false;
      showResult(
        "Browser-session access was not granted. Private mode remains off.",
        false
      );
    } else {
      showResult(
        "Secure Session Bridge enabled for private file downloads.",
        true
      );
    }
  } else {
    await removeCookiePermission();
    showResult("Secure Session Bridge disabled.", null);
  }
  await saveSettings();
}

function hasCookiePermission() {
  return new Promise((resolve) => {
    chrome.permissions.contains({ permissions: ["cookies"] }, resolve);
  });
}

function requestCookiePermission() {
  return new Promise((resolve) => {
    chrome.permissions.request({ permissions: ["cookies"] }, resolve);
  });
}

function removeCookiePermission() {
  return new Promise((resolve) => {
    chrome.permissions.remove({ permissions: ["cookies"] }, resolve);
  });
}

function sendRuntimeMessage(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

function showResult(message, success) {
  elements.result.textContent = message;
  elements.result.className = success === null ? "" : success ? "success" : "error";
}

function setConnectionStatus(message, success) {
  elements.connectionStatus.textContent = message;
  elements.connectionStatus.className = success ? "success" : "error";
}

function isHttpUrl(value) {
  try {
    const parsed = new URL(String(value || ""));
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch (_error) {
    return false;
  }
}

function mediaKindForPage(value) {
  try {
    const host = new URL(value).hostname.toLowerCase();
    if (host === "soundcloud.com" || host.endsWith(".soundcloud.com")) {
      return "audio";
    }
    const platforms = (
      "youtube.com youtu.be instagram.com facebook.com fb.watch " +
      "tiktok.com vimeo.com x.com twitter.com dailymotion.com"
    ).split(" ");
    return platforms.some(
      (name) => host === name || host.endsWith(`.${name}`)
    )
      ? "video"
      : "direct";
  } catch (_error) {
    return "direct";
  }
}


elements.downloadSelected.addEventListener("click", async () => {
  const selected = Array.from(elements.candidateList.querySelectorAll("input[type=checkbox]:checked"))
    .map((input) => scannedCandidates[Number(input.dataset.index)])
    .filter(Boolean);
  if (!selected.length) {
    showResult("Select at least one media item.", false);
    return;
  }
  elements.downloadSelected.disabled = true;
  showResult(`Sending ${selected.length} media item(s) to SDM…`, null);
  try {
    const response = await sendRuntimeMessage({
      type: "sdm-batch-download",
      payload: {
        connections: Number(elements.connections.value),
        items: selected.map((item) => ({
          ...item,
          source_url: item.url,
          start_immediately: elements.startImmediately.checked,
          connections: Number(elements.connections.value),
          media_kind: item.kind === "stream" ? "video" : item.kind
        }))
      }
    });
    showResult(response?.ok ? `${selected.length} item(s) added to SDM.` : response?.error || "Batch request failed.", Boolean(response?.ok));
  } catch (error) {
    showResult(error.message, false);
  } finally {
    elements.downloadSelected.disabled = false;
  }
});

function deduplicateCandidates(items) {
  const best = new Map();
  for (const raw of items) {
    if (!isHttpUrl(raw?.url)) continue;
    const url = canonicalMediaUrl(raw.url);
    const key = `${url}\n${raw.kind || "other"}\n${raw.quality || ""}\n${raw.codec || ""}`;
    const candidate = { ...raw, url };
    const previous = best.get(key);
    if (!previous || Number(candidate.score || 0) > Number(previous.score || 0)) best.set(key, candidate);
  }
  return Array.from(best.values()).sort((a,b) => Number(b.score||0)-Number(a.score||0)).slice(0,48);
}

function canonicalMediaUrl(value) {
  try {
    const url = new URL(value);
    ["utm_source","utm_medium","utm_campaign","utm_term","utm_content","fbclid","gclid"].forEach((key) => url.searchParams.delete(key));
    url.hash = "";
    return url.href;
  } catch (_error) { return String(value || ""); }
}

function renderCandidates() {
  elements.candidateList.textContent = "";
  elements.candidatePanel.hidden = !scannedCandidates.length;
  scannedCandidates.forEach((item, index) => {
    const row = document.createElement("label");
    row.className = "candidate-item";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = index < 8;
    input.dataset.index = String(index);
    const main = document.createElement("div");
    main.className = "candidate-main";
    const title = document.createElement("div");
    title.className = "candidate-title";
    title.textContent = item.filename || filenameFromUrl(item.url) || "Detected media";
    const meta = document.createElement("div");
    meta.className = "candidate-meta";
    const kind = document.createElement("span");
    kind.className = `kind-pill ${item.kind === "stream" ? "stream-pill" : ""}`;
    kind.textContent = item.kind || "media";
    meta.append(kind, document.createTextNode(` • ${item.source || "page"}${item.total_bytes ? ` • ${formatBytes(item.total_bytes)}` : ""}${item.mime_type ? ` • ${item.mime_type}` : ""}`));
    const url = document.createElement("div");
    url.className = "candidate-url";
    url.textContent = item.url;
    url.title = item.url;
    main.append(title, meta, url);
    row.append(input, main);
    elements.candidateList.append(row);
  });
}

function filenameFromUrl(value) {
  try { return decodeURIComponent(new URL(value).pathname.split("/").pop() || ""); } catch (_error) { return ""; }
}
function formatBytes(value) {
  const bytes = Number(value || 0); if (!bytes) return "";
  const units=["B","KB","MB","GB"]; let i=0,n=bytes; while(n>=1024&&i<units.length-1){n/=1024;i+=1;} return `${n.toFixed(i?1:0)} ${units[i]}`;
}
