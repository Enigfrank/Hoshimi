"""读取公开文档并验证模型生成的答复与分类。"""

import html
import json
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

from http_client import JsonAPI

TYPE_LABELS = {"Bug", "Question", "Enhancement", "Documentation"}
AREA_LABELS = {
    "Account-auth", "Battle", "Protocol", "Gm-admin",
    "Data-persistence", "Client-compatibility",
}


def documents(root):
    """读取本次检出中的公开 Markdown，排除导航和网页资源。"""
    paths = [root / "README.md", root / "REPORTING.md"]
    paths.extend(sorted((root / "docs").glob("*.md")))
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8-sig")
        for path in paths if not path.name.startswith("_")
    }


def text_field(value, name, limit):
    """约束展示字段，拒绝模型自带链接、HTML 和回复状态标记。"""
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or re.search(r"https?://|\]\s*\(|<|>", value, re.IGNORECASE)):
        raise ValueError(f"模型字段 {name} 不符合格式要求")
    return value.strip()


def validate(result, docs):
    """校验结构、标签数量和引用原文；模型不直接决定 API 操作。"""
    if not isinstance(result, dict):
        raise TypeError("模型结果不是 JSON 对象")
    expected = {"summary", "steps", "questions", "needs_maintainer",
                "type_label", "area_labels", "label_reason"}
    if set(result) != expected:
        raise ValueError("模型结果字段不完整或包含额外字段")
    result["summary"] = text_field(result["summary"], "summary", 800)
    result["label_reason"] = text_field(result["label_reason"], "label_reason", 500)
    if result["type_label"] is not None and (
            not isinstance(result["type_label"], str) or result["type_label"] not in TYPE_LABELS):
        raise ValueError("模型选择了不允许的问题类型")
    areas = result["area_labels"]
    if (not isinstance(areas, list) or len(areas) > 2
            or any(not isinstance(label, str) or label not in AREA_LABELS for label in areas)
            or len(set(areas)) != len(areas)):
        raise ValueError("模型选择了不允许的模块标签")
    if not isinstance(result["needs_maintainer"], bool):
        raise TypeError("needs_maintainer 必须为布尔值")
    if not isinstance(result["questions"], list) or len(result["questions"]) > 4:
        raise ValueError("补充问题数量不符合要求")
    result["questions"] = [text_field(item, "question", 500) for item in result["questions"]]
    steps = result["steps"]
    if not isinstance(steps, list) or len(steps) > 4:
        raise ValueError("处理建议数量不符合要求")
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"text", "source", "quote"}:
            raise ValueError("处理建议必须带有文档来源和原文")
        step["text"] = text_field(step["text"], "step", 1000)
        source, excerpt = step["source"], step["quote"]
        if (not isinstance(source, str) or source not in docs
                or not isinstance(excerpt, str) or not 12 <= len(excerpt) <= 600
                or excerpt not in docs[source]):
            raise ValueError("处理建议的引用未匹配到公开文档原文")
    if not steps and not result["questions"] and not result["needs_maintainer"]:
        raise ValueError("答复缺少可执行建议、补充问题或维护者接手说明")
    return result


def analyze(issue, comments, docs, env):
    """通过现有 OpenAI 兼容接口生成一次受文档约束的答复。"""
    base = env.get("PR_AGENT_API_BASE", "").rstrip("/")
    model = env.get("PR_AGENT_MODEL", "")
    if not base or not model:
        raise ValueError("请配置 PR_AGENT_API_BASE 和 PR_AGENT_MODEL 仓库变量")
    if not urlsplit(base).path.rstrip("/"):
        base += "/v1"
    prompt = Path(__file__).with_name("prompt.md").read_text(encoding="utf-8")
    context = {
        "issue": {"title": issue["title"], "body": issue.get("body") or ""},
        "comments": [
            {"author": comment["user"]["login"],
             "body": (comment.get("body") or "").split("<!-- hoshimi-issue-bot ", 1)[0].strip()}
            for comment in comments[-30:] if (comment.get("body") or "").strip() != "/issue-bot"
        ],
        "documents": docs,
    }
    api = JsonAPI(base, env.get("OPENAI_KEY", ""))
    response = api.request("/chat/completions", method="POST", data={
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 6000,
    })
    choice = response["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("模型答复未完整生成，未发布任何回复")
    return validate(json.loads(choice["message"]["content"]), docs)


def safe_text(text):
    """转义 HTML 并避免自动回复意外提及 GitHub 用户。"""
    return html.escape(text, quote=False).replace("@", "＠")


def render(result, docs, repo, ref, labels):
    """生成中文答复；文档链接和行号由可信检出内容构造。"""
    lines = ["**Hoshimi Issue 助手**", "", safe_text(result["summary"])]
    for step in result["steps"]:
        source = step["source"]
        start = docs[source].index(step["quote"])
        line = docs[source][:start].count("\n") + 1
        url = f"https://github.com/{repo}/blob/{quote(ref, safe='')}/{quote(source)}#L{line}"
        lines.extend(["", f"- {safe_text(step['text'])}（[文档依据]({url})）"])
    if result["questions"]:
        lines.extend(["", "请补充以下信息："])
        lines.extend(f"- {safe_text(question)}" for question in result["questions"])
    if result["needs_maintainer"]:
        lines.extend(["", "现有公开资料不足以确定原因，需要维护者进一步检查。"])
    names = "、".join(f"`{label}`" for label in sorted(labels)) or "暂不添加标签"
    lines.extend(["", f"分类：{names}。{safe_text(result['label_reason'])}"])
    return "\n".join(lines)
