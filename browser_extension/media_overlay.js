(() => {
  const MEDIA_SELECTOR = "video, audio";
  const AUDIO_EXTENSIONS = [
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".oga",
    ".opus",
    ".wav",
    ".flac",
    ".weba"
  ];
  const VIDEO_EXTENSIONS = [
    ".mp4",
    ".m4v",
    ".webm",
    ".mov",
    ".mkv",
    ".avi",
    ".ts"
  ];
  const MANIFEST_EXTENSIONS = [".m3u8", ".mpd"];
  const MAX_SMART_CANDIDATES = 24;
  const DEFAULT_SETTINGS = { showMediaPanel: true, connections: 4 };
  const observedMedia = new WeakSet();
  const dismissedMedia = new WeakSet();
  const mediaCandidates = new Map();
  let enabled = true;
  let activeMedia = null;
  let activeKind = "video";
  let pageFallback = false;
  let pageMediaUrl = "";
  let pageDismissed = false;
  let hideTimer = 0;
  let statusTimer = 0;
  let audioDetectionTimer = 0;
  let networkDetectionBusy = false;
  let lastDownloadHint = "";

  const overlay = document.createElement("div");
  overlay.id = "sdm-media-overlay";
  overlay.setAttribute("role", "group");
  overlay.setAttribute("aria-label", "Smart Download Manager media panel");
  overlay.innerHTML = `
    <button class="sdm-media-download" type="button" title="Download now with SDM">
      <span class="sdm-media-logo">SDM</span>
      <span class="sdm-media-label">Download this video</span>
    </button>
    <button class="sdm-media-later" type="button" title="Add to SDM queue">Queue</button>
    <span class="sdm-media-count" title="Detected media candidates">0</span>
    <button class="sdm-media-help" type="button" title="Supported media">?</button>
    <button class="sdm-media-close" type="button" title="Hide for this media">×</button>
  `;

  const downloadButton = overlay.querySelector(".sdm-media-download");
  const label = overlay.querySelector(".sdm-media-label");
  const laterButton = overlay.querySelector(".sdm-media-later");
  const countBadge = overlay.querySelector(".sdm-media-count");
  const helpButton = overlay.querySelector(".sdm-media-help");
  const closeButton = overlay.querySelector(".sdm-media-close");

  void initialize();

  async function initialize() {
    const settings = await chrome.storage.local.get(DEFAULT_SETTINGS);
    enabled = Boolean(settings.showMediaPanel);
    if (!document.documentElement.contains(overlay)) {
      document.documentElement.appendChild(overlay);
    }
    scan(document);
    observePage();
    observeDownloadLinks();
    observeAudioResources();
    collectDeclaredMedia();
    collectStructuredMedia();
    await collectNetworkCandidates();
    window.setTimeout(showPageFallback, 900);
    window.setTimeout(refreshAudioDetection, 700);
    window.setInterval(refreshAudioDetection, 1800);
    window.setInterval(refreshNetworkDetection, 1400);
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "sdm-scan-page") {
      return false;
    }
    collectDeclaredMedia();
    collectStructuredMedia();
    collectPerformanceCandidates();
    void collectNetworkCandidates().then(() => {
      const candidates = rankedMediaCandidates("");
      updateCandidateCount(candidates.length);
      sendResponse({
        ok: true,
        count: candidates.length,
        audio: candidates.filter((item) => item.kind === "audio").length,
        video: candidates.filter((item) => item.kind === "video").length,
        candidates: candidates.map((item) => ({
          ...item,
          page_url: location.href,
          page_title: document.title
        }))
      });
    });
    return true;
  });

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "local" || !changes.showMediaPanel) {
      return;
    }
    enabled = Boolean(changes.showMediaPanel.newValue);
    if (!enabled) {
      hideOverlay();
    } else {
      scan(document);
    }
  });

  function observePage() {
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) {
            continue;
          }
          if (node.matches?.(MEDIA_SELECTOR)) {
            attachMedia(node);
          }
          scan(node);
          scheduleAudioDetection();
        }
      }
    });
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true
    });
  }

  function scan(root) {
    if (!root?.querySelectorAll) {
      return;
    }
    root.querySelectorAll(MEDIA_SELECTOR).forEach(attachMedia);
  }

  function attachMedia(media) {
    if (observedMedia.has(media)) {
      return;
    }
    observedMedia.add(media);
    media.addEventListener("mouseenter", () => showForMedia(media), true);
    media.addEventListener("pointerdown", () => showForMedia(media), true);
    media.addEventListener("loadedmetadata", () => {
      if (activeMedia === media) {
        positionOverlay();
      }
      if (media.tagName === "AUDIO") {
        showDetectedAudio(media);
      }
    });
    media.addEventListener(
      "play",
      () => {
        if (media.tagName === "AUDIO") {
          showDetectedAudio(media);
        }
      },
      true
    );
    media.addEventListener("mouseleave", scheduleHide, true);
    if (media.tagName === "AUDIO") {
      window.setTimeout(() => showDetectedAudio(media), 250);
    }
  }

  function showForMedia(media) {
    if (!enabled || dismissedMedia.has(media) || !isVisibleMedia(media)) {
      return;
    }
    clearTimeout(hideTimer);
    activeMedia = media;
    const kind = media.tagName === "AUDIO" ? "audio" : "video";
    activeKind = kind;
    pageFallback = false;
    pageMediaUrl = "";
    setLabel(`Download this ${kind}`, "");
    overlay.style.display = "flex";
    positionOverlay();
  }

  function isVisibleMedia(media) {
    const rect = media.getBoundingClientRect();
    if (media.tagName === "AUDIO") {
      return rect.width >= 160 && rect.height >= 28;
    }
    return rect.width >= 160 && rect.height >= 80;
  }

  function positionOverlay() {
    if (overlay.style.display === "none") {
      return;
    }
    if (!activeMedia) {
      const panelRect = overlay.getBoundingClientRect();
      overlay.style.left = "16px";
      overlay.style.top = `${
        Math.max(8, window.innerHeight - panelRect.height - 18)
      }px`;
      return;
    }
    const mediaRect = activeMedia.getBoundingClientRect();
    const panelRect = overlay.getBoundingClientRect();
    const left = Math.max(
      8,
      Math.min(
        mediaRect.left + 10,
        window.innerWidth - panelRect.width - 8
      )
    );
    const top = Math.max(
      8,
      Math.min(
        mediaRect.top + 10,
        window.innerHeight - panelRect.height - 8
      )
    );
    overlay.style.left = `${Math.round(left)}px`;
    overlay.style.top = `${Math.round(top)}px`;
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = window.setTimeout(hideOverlay, 700);
  }

  function hideOverlay() {
    overlay.style.display = "none";
    activeMedia = null;
    pageFallback = false;
    pageMediaUrl = "";
    window.setTimeout(showPageFallback, 1200);
  }

  function setLabel(message, state) {
    label.textContent = message;
    overlay.dataset.state = state;
  }

  function showTemporaryMessage(message, state) {
    clearTimeout(statusTimer);
    setLabel(message, state);
    statusTimer = window.setTimeout(() => {
      if (activeMedia || pageFallback) {
        setLabel(`Download this ${activeKind}`, "");
      }
    }, 2800);
  }

  downloadButton.addEventListener("click", (event) => {
    void submitCapture(event, true);
  });

  laterButton.addEventListener("click", (event) => {
    void submitCapture(event, false);
  });

  async function submitCapture(event, startImmediately) {
    event.preventDefault();
    event.stopPropagation();
    if (!activeMedia && !pageFallback) {
      return;
    }
    collectMediaElementCandidates(activeMedia);
    collectDeclaredMedia();
    collectStructuredMedia();
    collectPerformanceCandidates();
    await collectNetworkCandidates();
    const captureCandidates = rankedMediaCandidates(activeKind);
    updateCandidateCount(captureCandidates.length);
    const smartDirect = captureCandidates.find(
      (candidate) => candidate.direct
    );
    const resolvedUrl =
      resolveMediaUrl(activeMedia) ||
      pageMediaUrl ||
      smartDirect?.url ||
      "";
    const mediaUrl = isDownloadableMediaUrl(resolvedUrl) ? resolvedUrl : "";
    const targetUrl = mediaUrl || canonicalPlatformUrl(location.href);
    const mediaKind = mediaUrl ? "direct" : activeKind;
    const selectedCandidate =
      captureCandidates.find((candidate) => candidate.url === mediaUrl) ||
      smartDirect ||
      null;

    downloadButton.disabled = true;
    laterButton.disabled = true;
    setLabel(
      startImmediately
        ? (mediaUrl ? "Sending to SDM…" : "Analyzing with SDM…")
        : "Adding to queue…",
      "working"
    );
    try {
      const settings = await chrome.storage.local.get(DEFAULT_SETTINGS);
      const response = await sendRuntimeMessage({
        type: "sdm-download-media",
        payload: {
          url: targetUrl,
          filename: mediaUrl
            ? selectedCandidate?.filename || guessFilename(mediaUrl)
            : suggestedPageFilename(activeKind),
          total_bytes: Number(selectedCandidate?.total_bytes) || 0,
          mime_type: String(selectedCandidate?.mime_type || ""),
          connections: Number(settings.connections) || 4,
          start_immediately: startImmediately,
          media_kind: mediaKind,
          page_url: location.href,
          capture_candidates: captureCandidates,
          capture_context: mediaCaptureContext()
        }
      });
      if (!response?.ok) {
        showTemporaryMessage(
          response?.error || "SDM rejected this media",
          "error"
        );
        return;
      }
      showTemporaryMessage(
        startImmediately ? "Added to SDM ✓" : "Added to queue ✓",
        "success"
      );
    } catch (error) {
      showTemporaryMessage(error.message || "Could not contact SDM", "error");
    } finally {
      downloadButton.disabled = false;
      laterButton.disabled = false;
    }
  }

  function isDownloadableMediaUrl(value) {
    if (!value) return false;
    try {
      const url = new URL(value, location.href);
      const host = url.hostname.toLowerCase();
      if (host.endsWith("youtube.com") || host === "youtu.be") return false;
      const path = url.pathname.toLowerCase();
      return [...AUDIO_EXTENSIONS, ...VIDEO_EXTENSIONS, ...MANIFEST_EXTENSIONS]
        .some((extension) => path.endsWith(extension)) ||
        url.protocol === "blob:" ||
        /(?:mime|type)=(?:audio|video)/i.test(url.search);
    } catch (_) {
      return false;
    }
  }

  function canonicalPlatformUrl(value) {
    try {
      const url = new URL(value);
      if (url.hostname.endsWith("youtube.com")) {
        const embed = url.pathname.match(/^\/embed\/([^/?#]+)/);
        if (embed) return `https://www.youtube.com/watch?v=${embed[1]}`;
        const shorts = url.pathname.match(/^\/shorts\/([^/?#]+)/);
        if (shorts) return `https://www.youtube.com/watch?v=${shorts[1]}`;
      }
      return url.href;
    } catch (_) {
      return value;
    }
  }

  helpButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    showTemporaryMessage(
      "SDM supports public media pages and direct files; DRM is unsupported",
      "info"
    );
  });

  closeButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (activeMedia) {
      dismissedMedia.add(activeMedia);
    } else {
      pageDismissed = true;
    }
    hideOverlay();
  });

  overlay.addEventListener("mouseenter", () => clearTimeout(hideTimer));
  overlay.addEventListener("mouseleave", scheduleHide);
  window.addEventListener("scroll", positionOverlay, true);
  window.addEventListener("resize", positionOverlay);

  function resolveMediaUrl(media) {
    if (!media) {
      return "";
    }
    const candidates = collectMediaElementCandidates(media).map(
      (candidate) => candidate.url
    );
    return candidates.find(isDirectMediaUrl) || "";
  }

  function collectMediaElementCandidates(media) {
    if (!media) {
      return [];
    }
    const kind = media.tagName === "AUDIO" ? "audio" : "video";
    const values = [
      media.currentSrc,
      media.src,
      ...Array.from(media.querySelectorAll("source")).map(
        (source) => source.src
      )
    ];
    return values
      .map((url, index) =>
        registerMediaCandidate({
          url,
          kind,
          source: "dom",
          score: index === 0 ? 980 : 940,
          direct: isDirectMediaUrl(url),
          mime_type: media.currentType || ""
        })
      )
      .filter(Boolean);
  }

  function guessFilename(url) {
    try {
      const path = new URL(url).pathname;
      return decodeURIComponent(path.split("/").pop() || "");
    } catch (_error) {
      return "";
    }
  }

  function isHttpUrl(value) {
    try {
      const parsed = new URL(String(value || ""));
      return parsed.protocol === "http:" || parsed.protocol === "https:";
    } catch (_error) {
      return false;
    }
  }

  function isDirectMediaUrl(value) {
    if (!isHttpUrl(value)) {
      return false;
    }
    try {
      const pathname = new URL(value).pathname.toLowerCase();
      return !pathname.endsWith(".m3u8") && !pathname.endsWith(".mpd");
    } catch (_error) {
      return false;
    }
  }

  function showPageFallback() {
    if (
      window.top !== window.self ||
      !enabled ||
      pageDismissed ||
      activeMedia ||
      overlay.style.display === "flex"
    ) {
      return;
    }
    const kind = mediaKindForPage();
    if (!kind) {
      return;
    }
    activeKind = kind;
    pageFallback = true;
    pageMediaUrl = "";
    setLabel(`Download this ${kind}`, "");
    overlay.style.display = "flex";
    positionOverlay();
  }

  function mediaKindForPage() {
    const host = location.hostname.toLowerCase();
    if (host === "soundcloud.com" || host.endsWith(".soundcloud.com")) {
      return "audio";
    }
    const audioHosts = (
      "bandcamp.com mixcloud.com audiomack.com hearthis.at last.fm"
    ).split(" ");
    if (
      audioHosts.some(
        (name) => host === name || host.endsWith(`.${name}`)
      )
    ) {
      return "audio";
    }
    const videoHosts = (
      "youtube.com youtu.be instagram.com facebook.com fb.watch " +
      "tiktok.com vimeo.com x.com twitter.com dailymotion.com"
    ).split(" ");
    return videoHosts.some(
      (name) => host === name || host.endsWith(`.${name}`)
    )
      ? "video"
      : "";
  }

  function suggestedPageFilename(kind) {
    const clean = String(document.title || `Browser ${kind}`)
      .replace(/[<>:"/\\|?*\u0000-\u001f]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 140) || `Browser ${kind}`;
    return `${clean}${kind === "audio" ? ".m4a" : ".mp4"}`;
  }

  function showDetectedAudio(media) {
    if (!enabled || pageDismissed || dismissedMedia.has(media)) {
      return;
    }
    const directUrl = resolveMediaUrl(media);
    const hasAudioState =
      directUrl ||
      media.readyState > 0 ||
      Number.isFinite(media.duration) ||
      !media.paused;
    if (!hasAudioState || activeKind === "video" && activeMedia) {
      return;
    }
    if (isVisibleMedia(media)) {
      showForMedia(media);
      return;
    }
    showAudioFallback(directUrl);
  }

  function refreshAudioDetection() {
    if (!enabled || pageDismissed || activeMedia) {
      return;
    }
    const audio = Array.from(document.querySelectorAll("audio")).find(
      (element) =>
        resolveMediaUrl(element) ||
        element.readyState > 0 ||
        Number.isFinite(element.duration) ||
        !element.paused
    );
    if (audio) {
      showDetectedAudio(audio);
      return;
    }

    collectDeclaredMedia();
    collectStructuredMedia();
    collectPerformanceCandidates();
    const declaredUrl = declaredAudioUrl();
    if (declaredUrl) {
      showAudioFallback(declaredUrl);
      return;
    }
    const networkUrl = recentAudioResource();
    if (networkUrl) {
      showAudioFallback(networkUrl);
      return;
    }
    const pageKind = mediaKindForPage();
    if (
      pageKind === "audio" ||
      (pageKind !== "video" &&
        !document.querySelector("video") &&
        hasMediaSessionAudio())
    ) {
      showAudioFallback("");
    }
  }

  async function refreshNetworkDetection() {
    if (
      networkDetectionBusy ||
      !enabled ||
      pageDismissed ||
      window.top !== window.self
    ) {
      return;
    }
    networkDetectionBusy = true;
    try {
      await collectNetworkCandidates();
      if (activeMedia || overlay.dataset.state === "working") {
        return;
      }
      const candidate =
        rankedMediaCandidates("audio").find((item) => item.direct) ||
        rankedMediaCandidates("video").find((item) => item.direct);
      if (candidate) {
        showMediaFallback(candidate.kind, candidate.url);
      }
    } finally {
      networkDetectionBusy = false;
    }
  }

  async function collectNetworkCandidates() {
    if (window.top !== window.self) {
      return [];
    }
    try {
      const response = await sendRuntimeMessage({
        type: "sdm-get-network-media-candidates"
      });
      const candidates = Array.isArray(response?.candidates)
        ? response.candidates
        : [];
      return candidates.map(registerMediaCandidate).filter(Boolean);
    } catch (_error) {
      return [];
    }
  }

  function scheduleAudioDetection() {
    clearTimeout(audioDetectionTimer);
    audioDetectionTimer = window.setTimeout(refreshAudioDetection, 180);
  }

  function showAudioFallback(url) {
    showMediaFallback("audio", url);
  }

  function showMediaFallback(kind, url) {
    if (
      !enabled ||
      pageDismissed ||
      activeMedia ||
      overlay.dataset.state === "working"
    ) {
      return;
    }
    if (window.top !== window.self && !isDirectMediaUrl(url)) {
      return;
    }
    activeKind = kind === "video" ? "video" : "audio";
    pageFallback = true;
    pageMediaUrl = isDirectMediaUrl(url) ? url : "";
    setLabel(`Download this ${activeKind}`, "");
    overlay.style.display = "flex";
    positionOverlay();
  }


  function updateCandidateCount(count = mediaCandidates.size) {
    const safeCount = Math.max(0, Math.min(99, Number(count) || 0));
    countBadge.textContent = safeCount > 9 ? "9+" : String(safeCount);
    countBadge.style.display = safeCount ? "inline-flex" : "none";
    if (window.top === window.self) {
      chrome.runtime.sendMessage({
        type: "sdm-media-count",
        count: safeCount
      }, () => void chrome.runtime.lastError);
    }
  }

  function declaredAudioUrl() {
    const selectors = [
      'meta[property="og:audio"]',
      'meta[property="og:audio:url"]',
      'meta[property="og:audio:secure_url"]',
      'meta[name="twitter:player:stream"]',
      'link[type^="audio/"]'
    ];
    for (const element of document.querySelectorAll(selectors.join(","))) {
      const value = element.content || element.href || "";
      if (isHttpUrl(value)) {
        registerMediaCandidate({
          url: value,
          kind: "audio",
          source: "metadata",
          score: 900,
          direct: isDirectMediaUrl(value),
          mime_type: element.type || "audio/*"
        });
        return value;
      }
    }
    return "";
  }

  function recentAudioResource() {
    collectPerformanceCandidates();
    return (
      rankedMediaCandidates("audio").find(
        (candidate) => candidate.direct
      )?.url || ""
    );
  }

  function observeAudioResources() {
    if (!("PerformanceObserver" in window)) {
      return;
    }
    try {
      const observer = new PerformanceObserver((list) => {
        const detected = list
          .getEntries()
          .map(registerPerformanceEntry)
          .some(Boolean);
        if (detected) {
          scheduleAudioDetection();
        }
      });
      observer.observe({ type: "resource", buffered: true });
    } catch (_error) {
      // Resource observation is optional and must never affect the page.
    }
  }

  function hasMediaSessionAudio() {
    try {
      return Boolean(navigator.mediaSession?.metadata);
    } catch (_error) {
      return false;
    }
  }

  function isAudioFileUrl(value) {
    if (!isHttpUrl(value)) {
      return false;
    }
    try {
      const pathname = new URL(value).pathname.toLowerCase();
      return AUDIO_EXTENSIONS.some((extension) =>
        pathname.endsWith(extension)
      );
    } catch (_error) {
      return false;
    }
  }

  function collectDeclaredMedia() {
    const declarations = [
      ['meta[property="og:audio"]', "audio"],
      ['meta[property="og:audio:url"]', "audio"],
      ['meta[property="og:audio:secure_url"]', "audio"],
      ['meta[property="og:video"]', "video"],
      ['meta[property="og:video:url"]', "video"],
      ['meta[property="og:video:secure_url"]', "video"],
      ['meta[name="twitter:player:stream"]', activeKind],
      ['link[type^="audio/"]', "audio"],
      ['link[type^="video/"]', "video"]
    ];
    for (const [selector, kind] of declarations) {
      for (const element of document.querySelectorAll(selector)) {
        const url = element.content || element.href || "";
        registerMediaCandidate({
          url,
          kind,
          source: "metadata",
          score: 900,
          direct: isDirectMediaUrl(url),
          mime_type: element.type || ""
        });
      }
    }
  }

  function collectStructuredMedia() {
    for (const script of document.querySelectorAll(
      'script[type="application/ld+json"]'
    )) {
      try {
        walkStructuredMedia(JSON.parse(script.textContent || ""), "");
      } catch (_error) {
        // Broken third-party JSON-LD must not affect the page.
      }
    }
  }

  function walkStructuredMedia(value, parentKey) {
    if (typeof value === "string") {
      if (
        ["contenturl", "embedurl", "audiourl", "videourl"].includes(
          parentKey
        )
      ) {
        const kind = parentKey.includes("audio")
          ? "audio"
          : parentKey.includes("video")
            ? "video"
            : activeKind;
        registerMediaCandidate({
          url: value,
          kind,
          source: "jsonld",
          score: parentKey === "contenturl" ? 930 : 820,
          direct: isDirectMediaUrl(value),
          mime_type: ""
        });
      }
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => walkStructuredMedia(item, parentKey));
      return;
    }
    if (!value || typeof value !== "object") {
      return;
    }
    for (const [key, item] of Object.entries(value)) {
      walkStructuredMedia(item, key.toLowerCase());
    }
  }

  function collectPerformanceCandidates() {
    try {
      performance
        .getEntriesByType("resource")
        .slice(-180)
        .forEach(registerPerformanceEntry);
    } catch (_error) {
      // Resource Timing is optional.
    }
  }

  function registerPerformanceEntry(entry) {
    const url = String(entry?.name || "");
    if (!isLikelyMediaResource(url, entry?.initiatorType)) {
      return null;
    }
    const kind = inferMediaKind(url, entry?.initiatorType);
    const direct =
      isDirectMediaUrl(url) &&
      (
        isKnownMediaFileUrl(url) ||
        ["audio", "video"].includes(
          String(entry?.initiatorType || "").toLowerCase()
        )
      );
    return registerMediaCandidate({
      url,
      kind,
      source: "performance",
      score: direct ? 880 : 620,
      direct,
      mime_type: kind === "audio" ? "audio/*" : "video/*"
    });
  }

  function registerMediaCandidate(candidate) {
    const url = String(candidate?.url || "");
    if (!isHttpUrl(url) || url.length > 8192 || isRejectedResource(url)) {
      return null;
    }
    const normalized = {
      url,
      kind: candidate.kind === "video" ? "video" : "audio",
      source: String(candidate.source || "performance"),
      score: Math.max(0, Math.min(1000, Number(candidate.score) || 0)),
      direct: Boolean(candidate.direct) && !isManifestUrl(url),
      mime_type: String(candidate.mime_type || "").slice(0, 255),
      filename: String(candidate.filename || "").slice(0, 260),
      total_bytes: Math.max(0, Number(candidate.total_bytes) || 0),
      captured_at: Math.max(0, Number(candidate.captured_at) || 0)
    };
    const previous = mediaCandidates.get(url);
    if (!previous || normalized.score >= previous.score) {
      mediaCandidates.set(url, normalized);
    }
    while (mediaCandidates.size > 96) {
      mediaCandidates.delete(mediaCandidates.keys().next().value);
    }
    updateCandidateCount(mediaCandidates.size);
    return mediaCandidates.get(url);
  }

  function rankedMediaCandidates(kind) {
    return Array.from(mediaCandidates.values())
      .filter((candidate) => !kind || candidate.kind === kind)
      .sort(
        (left, right) =>
          right.score - left.score ||
          right.captured_at - left.captured_at
      )
      .slice(0, MAX_SMART_CANDIDATES);
  }

  function mediaCaptureContext() {
    let metadata = null;
    try {
      metadata = navigator.mediaSession?.metadata || null;
    } catch (_error) {
      metadata = null;
    }
    return {
      page_url: location.href,
      page_title: document.title,
      media_title: String(metadata?.title || ""),
      artist: String(metadata?.artist || ""),
      album: String(metadata?.album || "")
    };
  }

  function inferMediaKind(url, initiatorType) {
    if (
      String(initiatorType || "").toLowerCase() === "audio" ||
      isAudioFileUrl(url)
    ) {
      return "audio";
    }
    return "video";
  }

  function isKnownMediaFileUrl(value) {
    if (!isHttpUrl(value)) {
      return false;
    }
    const pathname = new URL(value).pathname.toLowerCase();
    return [...AUDIO_EXTENSIONS, ...VIDEO_EXTENSIONS].some((extension) =>
      pathname.endsWith(extension)
    );
  }

  function isManifestUrl(value) {
    if (!isHttpUrl(value)) {
      return false;
    }
    const pathname = new URL(value).pathname.toLowerCase();
    return MANIFEST_EXTENSIONS.some((extension) =>
      pathname.endsWith(extension)
    );
  }

  function isLikelyMediaResource(value, initiatorType) {
    if (!isHttpUrl(value) || isRejectedResource(value)) {
      return false;
    }
    const type = String(initiatorType || "").toLowerCase();
    if (["audio", "video"].includes(type)) {
      return true;
    }
    if (isKnownMediaFileUrl(value) || isManifestUrl(value)) {
      return true;
    }
    const lower = value.toLowerCase();
    return /(?:stream|playback|audio|podcast|media|listen)/.test(lower);
  }

  function isRejectedResource(value) {
    try {
      const pathname = new URL(value).pathname.toLowerCase();
      return /\.(?:js|css|json|html?|xml|woff2?|ttf|otf|png|jpe?g|gif|webp|svg|ico)(?:$|\?)/.test(
        pathname
      );
    } catch (_error) {
      return true;
    }
  }

  function observeDownloadLinks() {
    document.addEventListener("pointerdown", captureDownloadHint, true);
    document.addEventListener("click", captureDownloadHint, true);
  }

  function captureDownloadHint(event) {
    const anchor = findEventAnchor(event);
    if (!anchor || !isHttpUrl(anchor.href)) {
      return;
    }
    const filename = filenameHintFromAnchor(anchor);
    if (!filename) {
      return;
    }
    const signature = `${anchor.href}\n${filename}`;
    if (signature === lastDownloadHint) {
      return;
    }
    lastDownloadHint = signature;
    window.setTimeout(() => {
      if (lastDownloadHint === signature) {
        lastDownloadHint = "";
      }
    }, 1200);
    chrome.runtime.sendMessage(
      {
        type: "sdm-download-hint",
        payload: {
          url: anchor.href,
          filename,
          page_url: location.href
        }
      },
      () => void chrome.runtime.lastError
    );
  }

  function findEventAnchor(event) {
    const path = event.composedPath?.() || [];
    const fromPath = path.find(
      (node) => node instanceof HTMLAnchorElement && node.href
    );
    if (fromPath) {
      return fromPath;
    }
    return event.target instanceof Element
      ? event.target.closest("a[href]")
      : null;
  }

  function filenameHintFromAnchor(anchor) {
    const values = [
      anchor.getAttribute("download"),
      anchor.dataset.filename,
      anchor.dataset.fileName,
      anchor.getAttribute("aria-label"),
      anchor.getAttribute("title"),
      anchor.textContent
    ];
    let parent = anchor.parentElement;
    for (let depth = 0; depth < 3 && parent; depth += 1) {
      values.push(parent.getAttribute("aria-label"), parent.textContent);
      parent = parent.parentElement;
    }
    for (const value of values) {
      const filename = normalizeFilenameHint(value);
      if (filename) {
        return filename;
      }
    }
    return "";
  }

  function normalizeFilenameHint(value) {
    const clean = String(value || "")
      .replace(/\s+/g, " ")
      .trim();
    if (!clean || clean.length > 260) {
      return "";
    }
    const direct = clean.replace(/^download\s+/i, "").trim();
    const match = direct.match(
      /([^<>:"/\\|?*\u0000-\u001f]{1,190}\.[a-z0-9]{1,12})(?=\s|$)/i
    );
    return (match?.[1] || "").trim();
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
})();
