const elements = {
  url: document.querySelector("#url"),
  filename: document.querySelector("#filename"),
  connections: document.querySelector("#connections"),
  startImmediately: document.querySelector("#startImmediately"),
  interceptDownloads: document.querySelector("#interceptDownloads"),
  showMediaPanel: document.querySelector("#showMediaPanel"),
  useBrowserSession: document.querySelector("#useBrowserSession"),
  send: document.querySelector("#send"),
  result: document.querySelector("#result"),
  connectionStatus: document.querySelector("#connectionStatus")
};

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
