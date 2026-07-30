from __future__ import annotations

import fnmatch
import json
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

from sdm.categories import DOWNLOAD_CATEGORIES, normalize_category
from sdm.site_adapters import (
    ADAPTER_CHATGPT,
    ADAPTER_DIRECT,
    ADAPTER_GOOGLE_DRIVE,
    build_adapter_plan,
)


RULES_SETTING_KEY = "smart_rules_v1"
ALLOWED_CONNECTIONS = frozenset({1, 2, 4, 8, 16})
START_MODES = frozenset({"inherit", "now", "later"})


@dataclass(frozen=True, slots=True)
class SmartRule:
    id: str
    name: str
    enabled: bool = True
    domain: str = ""
    adapter: str = ""
    media_kind: str = ""
    extension: str = ""
    mime_prefix: str = ""
    filename_glob: str = ""
    url_contains: str = ""
    category: str = ""
    minimum_bytes: int = 0
    maximum_bytes: int = 0
    target_folder: str = ""
    target_category: str = ""
    filename_prefix: str = ""
    filename_suffix: str = ""
    subfolder: str = ""
    connections: int = 0
    start_mode: str = "inherit"


@dataclass(frozen=True, slots=True)
class RuleContext:
    url: str
    filename: str
    source_url: str = ""
    page_url: str = ""
    adapter: str = ""
    media_kind: str = "direct"
    mime_type: str = ""
    category: str = "Other"
    total_bytes: int = 0


@dataclass(frozen=True, slots=True)
class RuleDecision:
    matched: bool
    rule_id: str = ""
    rule_name: str = ""
    reason: str = "No smart rule matched; using the selected settings."
    folder: str = ""
    category: str = ""
    filename: str = ""
    connections: int = 0
    start_immediately: bool | None = None


def default_rules() -> list[SmartRule]:
    return [
        SmartRule(
            id="builtin-chatgpt",
            name="ChatGPT private files",
            adapter=ADAPTER_CHATGPT,
            connections=2,
        ),
        SmartRule(
            id="builtin-google-drive",
            name="Google Drive files",
            adapter=ADAPTER_GOOGLE_DRIVE,
            connections=2,
        ),
        SmartRule(
            id="builtin-audio",
            name="Browser audio",
            media_kind="audio",
            target_category="Music",
            connections=4,
        ),
        SmartRule(
            id="builtin-video",
            name="Browser video",
            media_kind="video",
            target_category="Videos",
            connections=4,
        ),
    ]


def load_rules(repository) -> list[SmartRule]:
    raw = repository.get_setting(RULES_SETTING_KEY, "").strip()
    return deserialize_rules(raw)


def deserialize_rules(raw: str) -> list[SmartRule]:
    raw = str(raw or "").strip()
    if not raw:
        return default_rules()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return default_rules()
    if not isinstance(payload, list):
        return default_rules()
    if not payload:
        return []
    rules: list[SmartRule] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            rules.append(normalize_rule(SmartRule(**item)))
        except (TypeError, ValueError):
            continue
    return rules or default_rules()


def save_rules(repository, rules: Iterable[SmartRule]) -> None:
    payload = [asdict(normalize_rule(rule)) for rule in rules]
    repository.set_setting(
        RULES_SETTING_KEY,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )


def new_rule(name: str = "New rule") -> SmartRule:
    return SmartRule(id=str(uuid.uuid4()), name=name)


def normalize_rule(rule: SmartRule) -> SmartRule:
    category = _known_category(rule.category)
    target_category = _known_category(rule.target_category)
    connections = (
        int(rule.connections)
        if int(rule.connections or 0) in ALLOWED_CONNECTIONS
        else 0
    )
    start_mode = (
        rule.start_mode
        if str(rule.start_mode).casefold() in START_MODES
        else "inherit"
    )
    extension = str(rule.extension or "").strip().casefold().lstrip(".")
    media_kind = str(rule.media_kind or "").strip().casefold()
    if media_kind not in {"", "direct", "audio", "video"}:
        media_kind = ""
    return replace(
        rule,
        id=str(rule.id or uuid.uuid4()),
        name=str(rule.name or "Unnamed rule").strip()[:100],
        enabled=bool(rule.enabled),
        domain=str(rule.domain or "").strip().casefold()[:253],
        adapter=str(rule.adapter or "").strip().casefold()[:64],
        media_kind=media_kind,
        extension=extension[:32],
        mime_prefix=str(rule.mime_prefix or "").strip().casefold()[:100],
        filename_glob=str(rule.filename_glob or "").strip()[:255],
        url_contains=str(rule.url_contains or "").strip().casefold()[:500],
        category=category,
        minimum_bytes=max(0, int(rule.minimum_bytes or 0)),
        maximum_bytes=max(0, int(rule.maximum_bytes or 0)),
        target_folder=str(rule.target_folder or "").strip()[:4096],
        target_category=target_category,
        filename_prefix=_safe_name_fragment(rule.filename_prefix),
        filename_suffix=_safe_name_fragment(rule.filename_suffix),
        subfolder=_safe_subfolder(rule.subfolder),
        connections=connections,
        start_mode=start_mode.casefold(),
    )


def evaluate_rules(
    rules: Iterable[SmartRule],
    context: RuleContext,
) -> RuleDecision:
    normalized_context = normalize_context(context)
    for raw_rule in rules:
        rule = normalize_rule(raw_rule)
        if not rule.enabled or not rule_matches(rule, normalized_context):
            continue
        start_immediately: bool | None = None
        if rule.start_mode == "now":
            start_immediately = True
        elif rule.start_mode == "later":
            start_immediately = False
        actions: list[str] = []
        if rule.target_folder:
            actions.append(f"folder {rule.target_folder}")
        if rule.target_category:
            actions.append(f"category {rule.target_category}")
        if rule.filename_prefix or rule.filename_suffix:
            actions.append("rename file")
        if rule.subfolder:
            actions.append(f"subfolder {rule.subfolder}")
        if rule.connections:
            actions.append(f"{rule.connections} connections")
        if start_immediately is not None:
            actions.append(
                "start now" if start_immediately else "download later"
            )
        action_text = ", ".join(actions) if actions else "keep current settings"
        return RuleDecision(
            matched=True,
            rule_id=rule.id,
            rule_name=rule.name,
            reason=f'Matched rule "{rule.name}" → {action_text}.',
            folder=str(Path(rule.target_folder) / rule.subfolder) if rule.target_folder and rule.subfolder else (rule.target_folder or rule.subfolder),
            category=rule.target_category,
            filename=_apply_filename_actions(normalized_context.filename, rule),
            connections=rule.connections,
            start_immediately=start_immediately,
        )
    return RuleDecision(matched=False)


def normalize_context(context: RuleContext) -> RuleContext:
    plan = build_adapter_plan(
        context.url,
        source_url=context.source_url,
        page_url=context.page_url,
    )
    adapter = context.adapter or plan.adapter
    category = normalize_category(context.category, context.filename)
    return replace(
        context,
        adapter=adapter,
        media_kind=str(context.media_kind or "direct").casefold(),
        mime_type=str(context.mime_type or "").casefold(),
        category=category,
        total_bytes=max(0, int(context.total_bytes or 0)),
    )


def rule_matches(rule: SmartRule, context: RuleContext) -> bool:
    hosts = _context_hosts(context)
    if rule.domain and not any(
        fnmatch.fnmatch(host, rule.domain)
        or fnmatch.fnmatch(host, rule.domain.removeprefix("*."))
        for host in hosts
    ):
        return False
    if rule.adapter and rule.adapter != context.adapter:
        return False
    if rule.media_kind and rule.media_kind != context.media_kind:
        return False
    if rule.extension:
        extension = Path(context.filename).suffix.casefold().lstrip(".")
        if extension != rule.extension:
            return False
    if rule.mime_prefix and not context.mime_type.startswith(rule.mime_prefix):
        return False
    if rule.filename_glob and not fnmatch.fnmatch(context.filename.casefold(), rule.filename_glob.casefold()):
        return False
    if rule.url_contains:
        haystack = " ".join((context.url, context.source_url, context.page_url)).casefold()
        if rule.url_contains not in haystack:
            return False
    if rule.category and rule.category != context.category:
        return False
    if rule.minimum_bytes and context.total_bytes < rule.minimum_bytes:
        return False
    if (
        rule.maximum_bytes
        and context.total_bytes
        and context.total_bytes > rule.maximum_bytes
    ):
        return False
    return True


def describe_rule(rule: SmartRule) -> tuple[str, str]:
    matches: list[str] = []
    actions: list[str] = []
    if rule.domain:
        matches.append(f"domain {rule.domain}")
    if rule.adapter:
        matches.append(f"adapter {rule.adapter}")
    if rule.media_kind:
        matches.append(rule.media_kind)
    if rule.extension:
        matches.append(f".{rule.extension}")
    if rule.mime_prefix:
        matches.append(rule.mime_prefix)
    if rule.filename_glob:
        matches.append(f"name {rule.filename_glob}")
    if rule.url_contains:
        matches.append(f"URL contains {rule.url_contains}")
    if rule.category:
        matches.append(rule.category)
    if rule.minimum_bytes:
        matches.append(f"≥ {rule.minimum_bytes} B")
    if rule.maximum_bytes:
        matches.append(f"≤ {rule.maximum_bytes} B")
    if rule.target_folder:
        actions.append(rule.target_folder)
    if rule.target_category:
        actions.append(rule.target_category)
    if rule.filename_prefix or rule.filename_suffix:
        actions.append(f"rename {rule.filename_prefix}…{rule.filename_suffix}")
    if rule.subfolder:
        actions.append(f"subfolder {rule.subfolder}")
    if rule.connections:
        actions.append(f"{rule.connections} connections")
    if rule.start_mode != "inherit":
        actions.append("start now" if rule.start_mode == "now" else "later")
    return (
        ", ".join(matches) or "Every download",
        ", ".join(actions) or "Keep selected settings",
    )



def _safe_name_fragment(value: str) -> str:
    text = str(value or "").strip()[:120]
    return "".join(ch for ch in text if ch not in '<>:"/\\|?*')


def _safe_subfolder(value: str) -> str:
    parts = []
    for part in Path(str(value or "").strip()).parts:
        cleaned = _safe_name_fragment(part)
        if cleaned and cleaned not in {".", ".."}:
            parts.append(cleaned)
    return str(Path(*parts)) if parts else ""


def _apply_filename_actions(filename: str, rule: SmartRule) -> str:
    path = Path(filename)
    stem = path.stem or "download"
    suffix = "".join(path.suffixes)
    result = f"{rule.filename_prefix}{stem}{rule.filename_suffix}{suffix}"
    return result[:255]

def _context_hosts(context: RuleContext) -> set[str]:
    hosts: set[str] = set()
    for value in (context.url, context.source_url, context.page_url):
        try:
            host = (urlsplit(value).hostname or "").casefold()
        except ValueError:
            host = ""
        if host:
            hosts.add(host)
    return hosts


def _known_category(value: str) -> str:
    candidate = str(value or "").strip()
    for known in DOWNLOAD_CATEGORIES:
        if candidate.casefold() == known.casefold():
            return known
    return ""


__all__ = [
    "ADAPTER_DIRECT",
    "RuleContext",
    "RuleDecision",
    "SmartRule",
    "default_rules",
    "deserialize_rules",
    "describe_rule",
    "evaluate_rules",
    "load_rules",
    "new_rule",
    "normalize_rule",
    "rule_matches",
    "save_rules",
]
