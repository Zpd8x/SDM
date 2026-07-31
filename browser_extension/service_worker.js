const HOST_NAME = "com.zpd8x.sdm";
const MENU_LINK = "sdm-download-link";
const MENU_MEDIA = "sdm-download-media";
const MENU_PAGE = "sdm-download-page";
const MENU_AUDIO = "sdm-download-audio";
const MENU_ANALYZE = "sdm-analyze-media";
const MENU_LATER = "sdm-download-later";
let nativePort = null;
let nativeRequestId = 0;
const nativePending = new Map();
const DOWNLOAD_METADATA_WAIT_MS = 2200;
const DOWNLOAD_METADATA_POLL_MS = 125;
const DOWNLOAD_HINT_TTL_MS = 30000;
const DOWNLOAD_TRACE_TTL_MS = 2 * 60 * 1000;
const NETWORK_CANDIDATE_TTL_MS = 5 * 60 * 1000;
const MAX_NETWORK_CANDIDATES_PER_TAB = 48;
const recentDownloadHints = [];
const requestTraceById = new Map();
const redirectSourceByUrl = new Map();
const recentDownloadTraces = [];
const networkMediaByTab = new Map();

chrome.webRequest.onBeforeRequest.addListener(
  recordRequestStart,
  { urls: ["http://*/*", "https://*/*"] }
);
chrome.webRequest.onBeforeRedirect.addListener(
  recordRequestRedirect,
  { urls: ["http://*/*", "https://*/*"] },
  ["responseHeaders"]
);
chrome.webRequest.onHeadersReceived.addListener(
  recordNetworkMediaResponse,
  { urls: ["http://*/*", "https://*/*"] },
  ["responseHeaders"]
);
chrome.webRequest.onCompleted.addListener(
  finishRequestTrace,
  { urls: ["http://*/*", "https://*/*"] }
);
chrome.webRequest.onErrorOccurred.addListener(
  finishRequestTrace,
  { urls: ["http://*/*", "https://*/*"] }
);

chrome.tabs.onRemoved.addListener((tabId) => {
  networkMediaByTab.delete(tabId);
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_LINK,
      title: "Download link with SDM",
      contexts: ["link"]
    });
    chrome.contextMenus.create({
      id: MENU_MEDIA,
      title: "Download media with SDM",
      contexts: ["audio", "video", "image"]
    });
    chrome.contextMenus.create({
      id: MENU_PAGE,
      title: "Download with SDM",
      contexts: ["page", "frame"]
    });
    chrome.contextMenus.create({
      id: MENU_AUDIO,
      title: "Download audio with SDM",
      contexts: ["link", "audio", "video", "page"]
    });
    chrome.contextMenus.create({
      id: MENU_ANALYZE,
      title: "Analyze media with SDM",
      contexts: ["link", "audio", "video", "page"]
    });
    chrome.contextMenus.create({
      id: MENU_LATER,
      title: "Add to SDM queue",
      contexts: ["link", "audio", "video", "page"]
    });
  });
  chrome.storage.local.get(
    {
      interceptDownloads: false,
      showMediaPanel: true,
      useBrowserSession: false,
      connections: 4
    },
    (settings) => chrome.storage.local.set(settings)
  );
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const isLink = info.menuItemId === MENU_LINK;
  const isMedia = info.menuItemId === MENU_MEDIA;
  const audioOnly = info.menuItemId === MENU_AUDIO;
  const analyzeOnly = info.menuItemId === MENU_ANALYZE;
  const downloadLater = info.menuItemId === MENU_LATER;
  const directUrl = isLink ? info.linkUrl : isMedia ? info.srcUrl : "";
  const linkedMediaKind = mediaKindForPage(directUrl);
  const useDirectUrl =
    isDirectDownloadUrl(directUrl) &&
    !(isLink && linkedMediaKind !== "auto");
  const url = useDirectUrl
    ? directUrl
    : isLink && isHttpUrl(directUrl)
      ? directUrl
      : info.frameUrl || info.pageUrl || tab?.url;
  if (!isHttpUrl(url)) {
    return;
  }
  const mediaKind = useDirectUrl ? "direct" : mediaKindForPage(url);
  chrome.storage.local.get({ connections: 4 }, (settings) => {
    sendDownload({
      url,
      source_url: directUrl || url,
      filename: useDirectUrl
        ? ""
        : suggestedMediaFilename(tab?.title || "Browser media", mediaKind),
      connections: Number(settings.connections) || 4,
      start_immediately: !downloadLater,
      media_kind: audioOnly ? "audio" : mediaKind,
      inspect_only: analyzeOnly,
      page_url: info.pageUrl || tab?.url || ""
    })
      .then(showResultBadge)
      .catch((error) => showResultBadge({ ok: false, error: error.message }));
  });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "sdm-media-count") {
    const count = Math.max(0, Math.min(99, Number(message.count) || 0));
    if (sender.tab?.id != null) {
      chrome.action.setBadgeText({
        tabId: sender.tab.id,
        text: count ? (count > 9 ? "9+" : String(count)) : ""
      });
      chrome.action.setBadgeBackgroundColor({
        tabId: sender.tab.id,
        color: "#2f80ed"
      });
    }
    sendResponse({ ok: true });
    return false;
  }
  if (message?.type === "sdm-scan-active-tab") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tabId = tabs[0]?.id;
      if (tabId == null) {
        sendResponse({ ok: false, error: "No active browser tab." });
        return;
      }
      chrome.tabs.sendMessage(tabId, { type: "sdm-scan-page" }, (response) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        sendResponse(response || { ok: true, count: 0, audio: 0, video: 0 });
      });
    });
    return true;
  }
  if (message?.type === "sdm-get-network-media-candidates") {
    sendResponse({
      ok: true,
      candidates: networkCandidatesForTab(sender.tab?.id)
    });
    return false;
  }
  if (message?.type === "sdm-download-hint") {
    rememberDownloadHint(message.payload || {});
    sendResponse({ ok: true });
    return false;
  }
  if (message?.type === "sdm-ping") {
    sendNative({ action: "ping" })
      .then(sendResponse)
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "sdm-batch-download") {
    sendBatchDownload(message.payload || {})
      .then(showResultBadge)
      .then(sendResponse)
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (
    message?.type === "sdm-download" ||
    message?.type === "sdm-download-media"
  ) {
    sendDownload(message.payload || {})
      .then(showResultBadge)
      .then(sendResponse)
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  return false;
});

chrome.downloads.onCreated.addListener((downloadItem) => {
  void interceptBrowserDownload(downloadItem);
});

async function interceptBrowserDownload(downloadItem) {
  const settings = await chrome.storage.local.get({
    interceptDownloads: false,
    connections: 4
  });
  if (!settings.interceptDownloads || !isHttpUrl(downloadItem.url)) {
    return;
  }

  const detailedItem = await waitForDownloadMetadata(downloadItem);
  const downloadHint = takeDownloadHint(
    downloadItem.url,
    downloadItem.finalUrl,
    detailedItem.url,
    detailedItem.finalUrl
  );
  const requestTrace = takeDownloadTrace(detailedItem, downloadHint);
  const requestUrl =
    requestTrace?.source_url ||
    downloadHint?.url ||
    detailedItem.url;
  let response;
  try {
    response = await sendDownload({
      url:
        requestTrace?.final_url ||
        detailedItem.finalUrl ||
        detailedItem.url,
      request_url: requestUrl,
      source_url: requestUrl,
      final_url:
        requestTrace?.final_url ||
        detailedItem.finalUrl ||
        "",
      filename: chooseInterceptedFilename(
        detailedItem.filename,
        downloadHint?.filename || requestTrace?.filename || ""
      ),
      total_bytes: normalizeTotalBytes(detailedItem.totalBytes),
      mime_type: String(detailedItem.mime || ""),
      connections: Number(settings.connections) || 4,
      start_immediately: true,
      media_kind: "direct",
      page_url: String(
        downloadHint?.page_url ||
        detailedItem.referrer ||
        requestTrace?.referrer ||
        ""
      )
    });
  } catch (error) {
    showResultBadge({ ok: false, error: error.message });
    return;
  }
  if (!response?.ok) {
    showResultBadge(response);
    return;
  }

  chrome.downloads.cancel(downloadItem.id, () => {
    void chrome.runtime.lastError;
    chrome.downloads.removeFile(downloadItem.id, () => {
      void chrome.runtime.lastError;
      chrome.downloads.erase({ id: downloadItem.id }, () => {
        void chrome.runtime.lastError;
      });
    });
  });
  showResultBadge(response);
}

function rememberDownloadHint(payload) {
  const url = String(payload.url || "");
  const filename = basename(payload.filename);
  if (!isHttpUrl(url)) {
    return;
  }
  const key = downloadHintKey(url);
  const expiresAt = Date.now() + DOWNLOAD_HINT_TTL_MS;
  const existing = recentDownloadHints.find((hint) => hint.key === key);
  if (existing) {
    existing.filename = filename;
    existing.url = url;
    existing.page_url = String(payload.page_url || "");
    existing.expiresAt = expiresAt;
  } else {
    recentDownloadHints.push({
      key,
      url,
      filename,
      page_url: String(payload.page_url || ""),
      expiresAt
    });
  }
  pruneDownloadHints();
}

function takeDownloadHint(...urls) {
  pruneDownloadHints();
  const keys = new Set(urls.filter(isHttpUrl).map(downloadHintKey));
  const index = recentDownloadHints.findIndex((hint) => keys.has(hint.key));
  if (index < 0) {
    return null;
  }
  return recentDownloadHints.splice(index, 1)[0];
}

function pruneDownloadHints() {
  const now = Date.now();
  for (let index = recentDownloadHints.length - 1; index >= 0; index -= 1) {
    if (recentDownloadHints[index].expiresAt <= now) {
      recentDownloadHints.splice(index, 1);
    }
  }
  while (recentDownloadHints.length > 32) {
    recentDownloadHints.shift();
  }
}

function downloadHintKey(value) {
  try {
    const parsed = new URL(value);
    const fileId = parsed.searchParams.get("id");
    if (fileId?.startsWith("file_")) {
      return `${parsed.origin}${parsed.pathname}?id=${fileId}`;
    }
    parsed.hash = "";
    return parsed.href;
  } catch (_error) {
    return String(value || "");
  }
}

function chooseInterceptedFilename(browserPath, hintedFilename) {
  const browserFilename = basename(browserPath);
  return isGenericFilename(browserFilename) && !isGenericFilename(hintedFilename)
    ? basename(hintedFilename)
    : browserFilename;
}

async function waitForDownloadMetadata(initialItem) {
  const deadline = Date.now() + DOWNLOAD_METADATA_WAIT_MS;
  let best = initialItem;
  while (Date.now() < deadline) {
    const current = await findDownload(initialItem.id);
    if (current) {
      best = chooseRicherDownload(best, current);
    }
    if (hasUsefulDownloadMetadata(best)) {
      break;
    }
    await delay(DOWNLOAD_METADATA_POLL_MS);
  }
  return best;
}

function findDownload(id) {
  return new Promise((resolve) => {
    chrome.downloads.search({ id }, (items) => {
      if (chrome.runtime.lastError) {
        resolve(null);
        return;
      }
      resolve(items?.[0] || null);
    });
  });
}

function chooseRicherDownload(previous, current) {
  const previousName = basename(previous?.filename);
  const currentName = basename(current?.filename);
  return {
    ...previous,
    ...current,
    filename:
      isGenericFilename(currentName) && !isGenericFilename(previousName)
        ? previous.filename
        : current.filename || previous.filename,
    totalBytes:
      normalizeTotalBytes(current?.totalBytes) ||
      normalizeTotalBytes(previous?.totalBytes),
    mime: current?.mime || previous?.mime || "",
    finalUrl: current?.finalUrl || previous?.finalUrl || ""
  };
}

function hasUsefulDownloadMetadata(item) {
  return (
    !isGenericFilename(basename(item?.filename)) &&
    normalizeTotalBytes(item?.totalBytes) > 0
  );
}

function isGenericFilename(value) {
  const filename = basename(value);
  const dot = filename.lastIndexOf(".");
  const stem = (dot > 0 ? filename.slice(0, dot) : filename).toLowerCase();
  return ["", "content", "download", "file", "open", "uc", "view"].includes(
    stem
  );
}

function normalizeTotalBytes(value) {
  const total = Number(value);
  return Number.isSafeInteger(total) && total > 0 ? total : 0;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function recordNetworkMediaResponse(details) {
  const headers = responseHeaderMap(details.responseHeaders);
  recordDownloadResponse(details, headers);
  if (!Number.isInteger(details.tabId) || details.tabId < 0) {
    return;
  }
  if (details.type === "main_frame") {
    networkMediaByTab.delete(details.tabId);
  }
  const mimeType = String(headers.get("content-type") || "")
    .split(";", 1)[0]
    .trim()
    .toLowerCase();
  const url = String(details.url || "");
  const manifest = isStreamingManifest(url, mimeType);
  const knownFile = knownMediaKindFromUrl(url);
  const mimeKind = mimeType.startsWith("audio/")
    ? "audio"
    : mimeType.startsWith("video/")
      ? "video"
      : "";
  const octetMedia =
    mimeType === "application/octet-stream" && Boolean(knownFile);
  if (!manifest && !mimeKind && !octetMedia) {
    return;
  }

  const kind =
    mimeKind ||
    knownFile ||
    (String(details.type || "").toLowerCase() === "media"
      ? "audio"
      : "video");
  const contentDisposition = headers.get("content-disposition") || "";
  const filename =
    filenameFromContentDisposition(contentDisposition) ||
    filenameFromMediaUrl(url);
  const totalBytes = totalBytesFromHeaders(headers);
  const fragmented = isFragmentedMediaResource(url, mimeType);
  rememberNetworkCandidate(details.tabId, {
    url,
    kind,
    source: "webrequest",
    score: mimeKind ? (fragmented ? 680 : 995) : octetMedia ? 900 : 720,
    direct: !manifest && !fragmented,
    mime_type: mimeType,
    filename,
    total_bytes: totalBytes,
    captured_at: Date.now()
  });
}

function recordRequestStart(details) {
  if (!details?.requestId || !isHttpUrl(details.url)) {
    return;
  }
  pruneDownloadTraces();
  const redirect = redirectSourceByUrl.get(downloadHintKey(details.url));
  requestTraceById.set(details.requestId, {
    source_url: redirect?.source_url || String(details.url),
    final_url: String(details.url),
    tab_id: Number.isInteger(details.tabId) ? details.tabId : -1,
    referrer: String(details.initiator || details.documentUrl || ""),
    updated_at: Date.now()
  });
}

function recordRequestRedirect(details) {
  if (!details?.requestId || !isHttpUrl(details.redirectUrl)) {
    return;
  }
  const trace = requestTraceById.get(details.requestId) || {
    source_url: String(details.url || details.redirectUrl),
    tab_id: Number.isInteger(details.tabId) ? details.tabId : -1,
    referrer: String(details.initiator || details.documentUrl || "")
  };
  trace.final_url = String(details.redirectUrl);
  trace.updated_at = Date.now();
  requestTraceById.set(details.requestId, trace);
  redirectSourceByUrl.set(downloadHintKey(details.redirectUrl), {
    source_url: trace.source_url,
    expires_at: Date.now() + DOWNLOAD_TRACE_TTL_MS
  });
}

function finishRequestTrace(details) {
  if (details?.requestId) {
    requestTraceById.delete(details.requestId);
  }
}

function recordDownloadResponse(details, headers) {
  const disposition = String(headers.get("content-disposition") || "");
  const filename = filenameFromContentDisposition(disposition);
  if (!filename && !/\battachment\b/i.test(disposition)) {
    return;
  }
  const trace = requestTraceById.get(details.requestId);
  const item = {
    source_url: String(trace?.source_url || details.url || ""),
    final_url: String(details.url || trace?.final_url || ""),
    filename,
    total_bytes: totalBytesFromHeaders(headers),
    referrer: String(trace?.referrer || details.initiator || ""),
    captured_at: Date.now()
  };
  recentDownloadTraces.push(item);
  pruneDownloadTraces();
}

function takeDownloadTrace(downloadItem, downloadHint) {
  pruneDownloadTraces();
  const urls = [
    downloadItem?.url,
    downloadItem?.finalUrl,
    downloadHint?.url
  ].filter(isHttpUrl);
  const keys = new Set(urls.map(downloadHintKey));
  const filename = basename(
    downloadItem?.filename || downloadHint?.filename || ""
  ).toLowerCase();
  const totalBytes = normalizeTotalBytes(downloadItem?.totalBytes);
  let bestIndex = -1;
  let bestScore = 0;
  recentDownloadTraces.forEach((trace, index) => {
    let score = 0;
    if (
      keys.has(downloadHintKey(trace.source_url)) ||
      keys.has(downloadHintKey(trace.final_url))
    ) {
      score += 1000;
    }
    if (filename && basename(trace.filename).toLowerCase() === filename) {
      score += 300;
    }
    if (totalBytes && trace.total_bytes === totalBytes) {
      score += 120;
    }
    score += Math.max(
      0,
      60 - Math.floor((Date.now() - trace.captured_at) / 1000)
    );
    if (score > bestScore) {
      bestScore = score;
      bestIndex = index;
    }
  });
  if (bestIndex < 0 || bestScore < 200) {
    return null;
  }
  return recentDownloadTraces.splice(bestIndex, 1)[0];
}

function pruneDownloadTraces() {
  const cutoff = Date.now() - DOWNLOAD_TRACE_TTL_MS;
  for (let index = recentDownloadTraces.length - 1; index >= 0; index -= 1) {
    if (recentDownloadTraces[index].captured_at <= cutoff) {
      recentDownloadTraces.splice(index, 1);
    }
  }
  for (const [key, value] of redirectSourceByUrl.entries()) {
    if (value.expires_at <= Date.now()) {
      redirectSourceByUrl.delete(key);
    }
  }
  while (recentDownloadTraces.length > 64) {
    recentDownloadTraces.shift();
  }
}

function rememberNetworkCandidate(tabId, candidate) {
  pruneNetworkCandidates(tabId);
  let candidates = networkMediaByTab.get(tabId);
  if (!candidates) {
    candidates = new Map();
    networkMediaByTab.set(tabId, candidates);
  }
  const previous = candidates.get(candidate.url);
  if (!previous || candidate.score >= previous.score) {
    candidates.set(candidate.url, candidate);
  }
  while (candidates.size > MAX_NETWORK_CANDIDATES_PER_TAB) {
    candidates.delete(candidates.keys().next().value);
  }
}

function networkCandidatesForTab(tabId) {
  if (!Number.isInteger(tabId) || tabId < 0) {
    return [];
  }
  pruneNetworkCandidates(tabId);
  return Array.from(networkMediaByTab.get(tabId)?.values() || [])
    .sort(
      (left, right) =>
        right.score - left.score || right.captured_at - left.captured_at
    )
    .slice(0, 24);
}

function pruneNetworkCandidates(tabId) {
  const candidates = networkMediaByTab.get(tabId);
  if (!candidates) {
    return;
  }
  const cutoff = Date.now() - NETWORK_CANDIDATE_TTL_MS;
  for (const [url, candidate] of candidates) {
    if (candidate.captured_at < cutoff) {
      candidates.delete(url);
    }
  }
  if (!candidates.size) {
    networkMediaByTab.delete(tabId);
  }
}

function responseHeaderMap(responseHeaders) {
  const allowed = new Set([
    "content-type",
    "content-length",
    "content-range",
    "content-disposition"
  ]);
  const headers = new Map();
  for (const header of responseHeaders || []) {
    const name = String(header?.name || "").trim().toLowerCase();
    if (allowed.has(name)) {
      headers.set(name, String(header?.value || ""));
    }
  }
  return headers;
}

function isStreamingManifest(url, mimeType) {
  const manifests = new Set([
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
    "application/dash+xml"
  ]);
  if (manifests.has(mimeType)) {
    return true;
  }
  try {
    const path = new URL(url).pathname.toLowerCase();
    return path.endsWith(".m3u8") || path.endsWith(".mpd");
  } catch (_error) {
    return false;
  }
}

function knownMediaKindFromUrl(url) {
  try {
    const path = new URL(url).pathname.toLowerCase();
    if (
      /\.(?:mp3|m4a|aac|ogg|oga|opus|wav|flac|weba)$/.test(path)
    ) {
      return "audio";
    }
    if (/\.(?:mp4|m4v|webm|mov|mkv|avi|ts)$/.test(path)) {
      return "video";
    }
  } catch (_error) {
    return "";
  }
  return "";
}

function isFragmentedMediaResource(url, mimeType) {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname.toLowerCase();
    if (
      /\.(?:m4s|cmfa|cmfv)$/.test(path) ||
      /(?:^|[/_.-])(?:segment|fragment|frag|chunk)[-_/.\d]/.test(path)
    ) {
      return true;
    }
    if (
      parsed.searchParams.has("range") &&
      !["audio/mpeg", "video/mp4", "audio/mp4"].includes(mimeType)
    ) {
      return true;
    }
  } catch (_error) {
    return false;
  }
  return false;
}

function filenameFromContentDisposition(value) {
  const encoded = String(value || "").match(
    /filename\*\s*=\s*UTF-8''([^;]+)/i
  );
  const plain = String(value || "").match(
    /filename\s*=\s*(?:"([^"]+)"|([^;]+))/i
  );
  const raw = encoded?.[1] || plain?.[1] || plain?.[2] || "";
  try {
    return basename(decodeURIComponent(raw.trim()));
  } catch (_error) {
    return basename(raw.trim());
  }
}

function filenameFromMediaUrl(value) {
  try {
    const filename = basename(decodeURIComponent(new URL(value).pathname));
    return /\.(?:mp3|m4a|aac|ogg|oga|opus|wav|flac|weba|mp4|m4v|webm|mov|mkv|avi)$/i.test(
      filename
    )
      ? filename
      : "";
  } catch (_error) {
    return "";
  }
}

function totalBytesFromHeaders(headers) {
  const contentRange = String(headers.get("content-range") || "");
  const rangeTotal = Number(contentRange.match(/\/(\d+)\s*$/)?.[1] || 0);
  if (Number.isSafeInteger(rangeTotal) && rangeTotal > 0) {
    return rangeTotal;
  }
  return normalizeTotalBytes(headers.get("content-length"));
}

async function sendDownload(payload) {
  const candidates = Array.isArray(payload.capture_candidates)
    ? payload.capture_candidates.slice(0, 24).map((candidate) => ({
        url: String(candidate?.url || "").slice(0, 8192),
        kind: String(candidate?.kind || "").slice(0, 16),
        source: String(candidate?.source || "").slice(0, 32),
        score: Number(candidate?.score) || 0,
        direct: Boolean(candidate?.direct),
        mime_type: String(candidate?.mime_type || "").slice(0, 255),
        filename: basename(candidate?.filename).slice(0, 260),
        total_bytes: normalizeTotalBytes(candidate?.total_bytes)
      }))
    : [];
  const message = {
    action: "download",
    url: String(payload.url || ""),
    filename: String(payload.filename || ""),
    total_bytes: normalizeTotalBytes(payload.total_bytes),
    mime_type: String(payload.mime_type || ""),
    connections: Number(payload.connections) || 4,
    start_immediately: payload.start_immediately !== false,
    media_kind: String(payload.media_kind || "direct"),
    page_url: String(payload.page_url || "").slice(0, 8192),
    request_url: String(
      payload.request_url || payload.source_url || payload.url || ""
    ).slice(0, 8192),
    source_url: String(
      payload.source_url || payload.original_url || payload.url || ""
    ).slice(0, 8192),
    final_url: String(payload.final_url || "").slice(0, 8192),
    capture_candidates: candidates,
    capture_context:
      payload.capture_context && typeof payload.capture_context === "object"
        ? {
            page_title: String(
              payload.capture_context.page_title || ""
            ).slice(0, 300),
            media_title: String(
              payload.capture_context.media_title || ""
            ).slice(0, 300),
            artist: String(payload.capture_context.artist || "").slice(0, 200),
            album: String(payload.capture_context.album || "").slice(0, 200)
          }
        : {}
  };
  const sessionAuth = await buildSessionAuth(payload);
  if (sessionAuth) {
    message.session_auth = sessionAuth;
  }
  return sendNative(message);
}

async function sendBatchDownload(payload) {
  const items = Array.isArray(payload.items) ? payload.items.slice(0, 48) : [];
  const prepared = [];
  for (const item of items) {
    if (!isHttpUrl(item?.url)) continue;
    const sessionAuth = await buildSessionAuth(item);
    const candidate = {
      url: String(item.url).slice(0, 8192),
      source_url: String(item.source_url || item.url).slice(0, 8192),
      page_url: String(item.page_url || "").slice(0, 8192),
      filename: basename(item.filename).slice(0, 260),
      mime_type: String(item.mime_type || "").slice(0, 255),
      total_bytes: normalizeTotalBytes(item.total_bytes),
      connections: Number(item.connections || payload.connections) || 4,
      start_immediately: item.start_immediately !== false,
      media_kind: String(item.media_kind || item.kind || "auto"),
      requires_ffmpeg: Boolean(item.requires_ffmpeg),
      quality: String(item.quality || "").slice(0, 80),
      codec: String(item.codec || "").slice(0, 80)
    };
    if (sessionAuth) candidate.session_auth = sessionAuth;
    prepared.push(candidate);
  }
  if (!prepared.length) throw new Error("No valid media candidates were selected.");
  return sendNative({ action: "batch_download", items: prepared });
}

async function buildSessionAuth(payload) {
  if (String(payload.media_kind || "direct") !== "direct") {
    return null;
  }
  const settings = await chrome.storage.local.get({
    useBrowserSession: false
  });
  if (!settings.useBrowserSession || !(await hasCookiePermission())) {
    return null;
  }

  const sourceUrls = collectSessionUrls(payload);
  const cookies = [];
  const seen = new Set();
  for (const url of sourceUrls) {
    const matching = await cookiesForUrl(url);
    for (const cookie of matching) {
      const key = [
        cookie.name,
        cookie.domain,
        cookie.path,
        cookie.storeId
      ].join("\n");
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      cookies.push({
        name: String(cookie.name || "").slice(0, 256),
        value: String(cookie.value || "").slice(0, 4096),
        domain: String(cookie.domain || "").slice(0, 253),
        path: String(cookie.path || "/").slice(0, 1024),
        secure: Boolean(cookie.secure),
        host_only: Boolean(cookie.hostOnly),
        expiration_date:
          Number.isFinite(cookie.expirationDate) && cookie.expirationDate > 0
            ? cookie.expirationDate
            : null
      });
      if (cookies.length >= 128) {
        break;
      }
    }
    if (cookies.length >= 128) {
      break;
    }
  }
  if (!cookies.length) {
    return null;
  }
  return {
    enabled: true,
    source_urls: sourceUrls,
    user_agent: String(navigator.userAgent || "").slice(0, 512),
    cookies
  };
}

function collectSessionUrls(payload) {
  const values = [
    payload.url,
    payload.request_url,
    payload.source_url,
    payload.final_url,
    payload.page_url,
    ...(Array.isArray(payload.capture_candidates)
      ? payload.capture_candidates
          .filter((candidate) => candidate?.direct)
          .map((candidate) => candidate.url)
      : [])
  ];
  return Array.from(new Set(values.filter(isHttpUrl))).slice(0, 8);
}

function hasCookiePermission() {
  return new Promise((resolve) => {
    chrome.permissions.contains({ permissions: ["cookies"] }, resolve);
  });
}

function cookiesForUrl(url) {
  return new Promise((resolve) => {
    chrome.cookies.getAll({ url }, (cookies) => {
      if (chrome.runtime.lastError) {
        resolve([]);
        return;
      }
      resolve(Array.isArray(cookies) ? cookies : []);
    });
  });
}

function ensureNativePort() {
  if (nativePort) {
    return nativePort;
  }
  nativePort = chrome.runtime.connectNative(HOST_NAME);
  nativePort.onMessage.addListener((response) => {
    const requestId = Number(response?.request_id || 0);
    const pending = nativePending.get(requestId);
    if (!pending) {
      return;
    }
    nativePending.delete(requestId);
    pending.resolve(response);
  });
  nativePort.onDisconnect.addListener(() => {
    const error = new Error(chrome.runtime.lastError?.message || "SDM Native Host disconnected.");
    for (const pending of nativePending.values()) {
      pending.reject(error);
    }
    nativePending.clear();
    nativePort = null;
  });
  return nativePort;
}

function sendNative(message) {
  return new Promise((resolve, reject) => {
    const requestId = ++nativeRequestId;
    nativePending.set(requestId, { resolve, reject });
    try {
      ensureNativePort().postMessage({ ...message, request_id: requestId });
    } catch (error) {
      nativePending.delete(requestId);
      nativePort = null;
      reject(error);
    }
  });
}

function showResultBadge(response) {
  const ok = Boolean(response?.ok);
  const duplicate = ok && Boolean(response?.duplicate);
  chrome.action.setBadgeBackgroundColor({
    color: duplicate ? "#d58b2e" : ok ? "#2ca66f" : "#d34f5f"
  });
  chrome.action.setBadgeText({ text: duplicate ? "1" : ok ? "✓" : "!" });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 2500);
  return response;
}

function basename(path) {
  return String(path || "").split(/[\\/]/).pop() || "";
}

function isHttpUrl(value) {
  try {
    const parsed = new URL(String(value || ""));
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch (_error) {
    return false;
  }
}

function mediaKindForPage(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (host === "soundcloud.com" || host.endsWith(".soundcloud.com")) {
      return "audio";
    }
    const audioPlatforms = (
      "bandcamp.com mixcloud.com audiomack.com hearthis.at last.fm"
    ).split(" ");
    if (
      audioPlatforms.some(
        (name) => host === name || host.endsWith(`.${name}`)
      )
    ) {
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
      : "auto";
  } catch (_error) {
    return "auto";
  }
}

function isDirectDownloadUrl(value) {
  if (!isHttpUrl(value)) {
    return false;
  }
  const pathname = new URL(value).pathname.toLowerCase();
  return !pathname.endsWith(".m3u8") && !pathname.endsWith(".mpd");
}

function suggestedMediaFilename(title, mediaKind) {
  const clean = String(title || "Browser media")
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 140) || "Browser media";
  return `${clean}${mediaKind === "audio" ? ".m4a" : ".mp4"}`;
}
