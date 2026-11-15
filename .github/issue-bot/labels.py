"""用评论中的操作记录和 GitHub 标签事件保留人工分类。"""

import json
import re
from urllib.parse import quote

from analysis import AREA_LABELS, TYPE_LABELS

BOT_LOGIN = "github-actions[bot]"
MARKER = "<!-- hoshimi-issue-bot "
STATE_PATTERN = re.compile(r"\n<!-- hoshimi-issue-bot (\{[^\n]+\}) -->\s*$")


def read_state(comment):
    """只接受 GitHub Actions Bot 发布的本助手状态，忽略用户伪造的标记。"""
    user = comment.get("user") or {}
    if user.get("login") != BOT_LOGIN or user.get("type") != "Bot":
        return None
    match = STATE_PATTERN.search(comment.get("body") or "")
    if match is None:
        return None
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return state if isinstance(state, dict) and state.get("version") == 1 else None


def with_state(body, state):
    """将可恢复的操作记录写在回复末尾，不将 Issue 正文作为状态。"""
    visible = body.split(MARKER, 1)[0].rstrip()
    encoded = json.dumps(state, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"{visible}\n\n{MARKER}{encoded} -->"


def latest_label_events(events):
    """按事件 ID 记录每个标签最近一次添加或删除操作。"""
    latest = {}
    for event in sorted(events, key=lambda item: item["id"]):
        if event.get("event") in {"labeled", "unlabeled"}:
            latest[event["label"]["name"]] = event
    return latest


def owned_labels(state, current, events):
    """仅认领事件 ID 仍匹配的 Bot 标签；人工删除后重加即失去所有权。"""
    if not state:
        return {}
    latest = latest_label_events(events)
    owned = {}
    candidates = set(state.get("owned", {})) | set(state.get("add", []))
    for name in candidates & current:
        event = latest.get(name)
        if (not event or event["event"] != "labeled"
                or (event.get("actor") or {}).get("login") != BOT_LOGIN):
            continue
        recorded = state.get("owned", {}).get(name) == event["id"]
        pending_add = (not state.get("complete") and name in state.get("add", [])
                       and event["id"] > state["baseline"])
        if recorded or pending_add:
            owned[name] = event["id"]
    return owned


def select_labels(suggested, protected):
    """保留人工类型及模块标签，只在剩余名额内采用 Bot 的建议。"""
    selected = set()
    if not protected & TYPE_LABELS:
        selected.update(suggested & TYPE_LABELS)
    remaining = max(0, 2 - len(protected & AREA_LABELS))
    selected.update(sorted((suggested - protected) & AREA_LABELS)[:remaining])
    return selected


def make_plan(result, issue, previous, events, trigger):
    """生成明确的增删计划，只删除本助手仍拥有的标签。"""
    current = {label["name"] for label in issue["labels"]}
    owned = owned_labels(previous, current, events)
    protected = current - set(owned)
    suggested = set(result["area_labels"])
    if result["type_label"]:
        suggested.add(result["type_label"])
    selected = select_labels(suggested, protected)
    state = {
        "version": 1,
        "trigger": trigger,
        "complete": False,
        "baseline": max((event["id"] for event in events), default=0),
        "owned": owned,
        "desired": sorted(selected),
        "add": sorted(selected - current),
        "remove": sorted(set(owned) - selected),
    }
    effective = (current - set(state["remove"])) | set(state["add"])
    return state, effective & (TYPE_LABELS | AREA_LABELS)


def apply_plan(api, path, comment, state):
    """执行或恢复已公布的计划，重复运行不重发回复，也不覆盖新的人工标签。"""
    issue = api.request(path)
    events = api.pages(path + "/events")
    current = {label["name"] for label in issue["labels"]}
    owned = owned_labels(state, current, events)
    latest = latest_label_events(events)
    protected = current - set(owned)
    selected = select_labels(set(state["desired"]), protected)
    for name in sorted(set(owned) - selected):
        api.request(path + "/labels/" + quote(name, safe=""), method="DELETE", allow_missing=True)
        current.discard(name)
    additions = []
    for name in sorted(selected - current):
        last = latest.get(name)
        if (last and last["id"] > state["baseline"]
                and (last.get("actor") or {}).get("login") != BOT_LOGIN):
            continue
        additions.append(name)
    if additions:
        api.request(path + "/labels", method="POST", data={"labels": additions})
    final_issue = api.request(path)
    final_events = api.pages(path + "/events")
    final_names = {label["name"] for label in final_issue["labels"]}
    state["owned"] = owned_labels(state, final_names, final_events)
    state["complete"] = True
    api.request(comment["url"].removeprefix(api.base_url), method="PATCH",
                data={"body": with_state(comment["body"], state)})
