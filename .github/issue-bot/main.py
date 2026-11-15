"""新 Issue 自动答复一次；维护者可用 /issue-bot 重新分析。"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from analysis import analyze, documents, render
from http_client import JsonAPI
from labels import apply_plan, make_plan, read_state, with_state


def can_trigger(api, repo, login):
    """以 GitHub 当前仓库权限核验人工触发者，不把组织成员身份当作写权限。"""
    if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9-]+", login):
        return False
    permissions = api.request(
        f"/repos/{repo}/collaborators/{login}/permission", allow_missing=True,
    )
    return bool(permissions and permissions.get("permission") in {"admin", "maintain", "write"})


def event_trigger(api, repo, env, preview_number):
    """筛选 Issue 事件和独立命令；预览永远不会发布评论或修改标签。"""
    if preview_number is not None:
        if preview_number <= 0:
            raise ValueError("Issue 编号必须为正整数")
        return preview_number, "preview", True
    event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    name = env.get("GITHUB_EVENT_NAME")
    sender = event.get("sender") or {}
    if sender.get("type") == "Bot":
        return None
    if name == "workflow_dispatch":
        if not can_trigger(api, repo, sender.get("login")):
            return None
        number = str(event.get("inputs", {}).get("issue_number", ""))
        if not number.isascii() or not number.isdecimal() or int(number) <= 0:
            raise ValueError("Issue 编号必须为正整数")
        return int(number), "preview", True
    issue = event.get("issue") or {}
    if not issue or "pull_request" in issue:
        return None
    if name == "issues" and event.get("action") == "opened":
        return issue["number"], "opened", False
    if name == "issue_comment" and event.get("action") == "created":
        comment = event.get("comment") or {}
        if (comment.get("body") or "").strip() != "/issue-bot":
            return None
        if can_trigger(api, repo, sender.get("login")):
            return issue["number"], f"comment:{comment['id']}", False
    return None


def run(api, repo, env, preview_number=None, output=None):
    """读取资料、去重、分析并执行受限写入；未验证完整结果前不发布回复。"""
    trigger = event_trigger(api, repo, env, preview_number)
    if trigger is None:
        print("已忽略：事件或调用权限不符合条件。")
        return
    number, key, preview = trigger
    path = f"/repos/{repo}/issues/{number}"
    issue = api.request(path)
    if "pull_request" in issue or (not preview and (issue["state"] != "open" or issue.get("locked"))):
        print("已忽略：目标不是可回复的开放 Issue。")
        return
    comments = api.pages(path + "/comments")
    records = [(comment, read_state(comment)) for comment in comments]
    records = [(comment, state) for comment, state in records if state]
    latest = records[-1][1] if records else None
    if not preview:
        matches = [(comment, state) for comment, state in records if state["trigger"] == key]
        if matches:
            comment, state = matches[-1]
            if not state["complete"] and state is latest:
                apply_plan(api, path, comment, state)
            print("本次事件已有回复，未重复调用模型或发布评论。")
            return
        if key == "opened" and records:
            print("此 Issue 已有助手回复，未重复自动回复。")
            return
    root = Path(__file__).resolve().parents[2]
    docs = documents(root)
    available = {label["name"] for label in api.pages(f"/repos/{repo}/labels")}
    result = analyze(issue, comments, docs, env)
    # 模型请求期间可能有人工分类；重新读取标签后再制定计划。
    issue = api.request(path)
    events = api.pages(path + "/events")
    state, effective = make_plan(result, issue, latest, events, key)
    if set(state["add"]) - available:
        raise ValueError("仓库缺少建议使用的标签，请先补齐现有分类标签")
    ref = env.get("ISSUE_BOT_DOCS_REF") or "main"
    body = render(result, docs, repo, ref, effective)
    suggested = set(result["area_labels"])
    if result["type_label"]:
        suggested.add(result["type_label"])
    if suggested - effective:
        body += "\n\n已保留人工分类，跳过与其冲突的建议标签。"
    if preview:
        draft = {"issue": number, "reply": body, "add_labels": state["add"],
                 "remove_labels": state["remove"], "preview": True}
        if output:
            Path(output).write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(draft, ensure_ascii=False, indent=2))
        if env.get("GITHUB_STEP_SUMMARY"):
            with Path(env["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
                summary.write(f"预览 Issue #{number}，未发布评论或修改标签。\n\n{body}\n")
        return
    # 再次核对开放状态，避免分析期间关闭或锁定的 Issue 被自动回复。
    current = api.request(path)
    if current["state"] != "open" or current.get("locked"):
        print("分析完成时 Issue 已关闭或锁定，未发布回复。")
        return
    comment = api.request(path + "/comments", method="POST", data={"body": with_state(body, state)})
    apply_plan(api, path, comment, state)
    print(f"已回复 Issue #{number} 并完成分类。")


def main():
    """处理 Actions 与本机预览入口，错误仅输出必要原因。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", type=int, metavar="ISSUE", help="只读预览指定 Issue")
    parser.add_argument("--output", help="将预览草稿保存到指定 JSON 文件")
    args = parser.parse_args()
    if args.output and args.preview is None:
        parser.error("--output 仅可与 --preview 一起使用")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("GITHUB_REPOSITORY 必须为 owner/repo")
    api = JsonAPI("https://api.github.com", os.environ.get("GITHUB_TOKEN", ""), github=True)
    run(api, repo, os.environ, args.preview, args.output)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        print(f"Issue 助手停止：{error}", file=sys.stderr)
        sys.exit(1)
    except (AttributeError, IndexError, KeyError, OSError, TypeError) as error:
        print(f"Issue 助手停止：{type(error).__name__}，请检查配置和 API 响应格式。", file=sys.stderr)
        sys.exit(1)
