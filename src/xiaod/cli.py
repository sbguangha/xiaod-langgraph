"""CLI: bot, one-off run, LangSmith hello, local evaluators, web console."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from xiaod.evals.dataset import SAMPLE_CASES
from xiaod.evals.evaluators import evaluate_job
from xiaod.graph import run_text
from xiaod.settings import get_settings
from xiaod.tracing import configure_langsmith, redact_text


def _cmd_bot(_args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from xiaod.bot.feishu_ws import start_bot

    start_bot()
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    configure_langsmith()
    result = run_text(args.text)
    print(result.get("reply_message") or "已完成。")
    if args.json:
        safe = {k: v for k, v in result.items() if k not in {"subtitle", "transcript"}}
        print(redact_text(json.dumps(safe, ensure_ascii=False, indent=2)))
    return 0 if result.get("status") in {"done", "needs_human", "needs_feishu", "idle"} else 1


def _cmd_hello(_args: argparse.Namespace) -> int:
    from langsmith import traceable

    configure_langsmith()
    settings = get_settings()

    @traceable(name="xiaod_hello")
    def ping() -> dict[str, str]:
        return {"ok": "xiaod", "project": settings.langsmith_project}

    ping()
    if settings.has_langsmith:
        print(f"已向 LangSmith 项目 {settings.langsmith_project} 写入一条 hello trace。")
    else:
        print("未配置 LANGSMITH_API_KEY。本地图已编译，打开 smith.langchain.com 填好密钥后再跑 xiaod hello。")
    return 0


def _cmd_eval(_args: argparse.Namespace) -> int:
    rows = []
    for case in SAMPLE_CASES:
        result = evaluate_job(case)
        rows.append(result)
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"{mark} {case['id']}: {result['failed']}")
    failed = [row for row in rows if not row["passed"]]
    return 1 if failed else 0


def _cmd_web(args: argparse.Namespace) -> int:
    import uvicorn

    from xiaod.webapp import create_app, frontend_dir

    settings = get_settings()
    host = args.host or settings.web_host
    port = args.port or settings.web_port
    dist = frontend_dir() / "dist"
    print(f"小D 控制台：http://{host}:{port}")
    if not dist.is_dir():
        print("还没有打包前端。另开窗口执行：cd web && npm install && npm run dev")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xiaod", description="飞书音视频转录整理 Agent")
    sub = parser.add_subparsers(dest="command", required=True)
    bot = sub.add_parser("bot", help="启动飞书 WebSocket 机器人")
    bot.set_defaults(func=_cmd_bot)
    run = sub.add_parser("run", help="本地跑一条消息")
    run.add_argument("text", help="链接或自然语言指令")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=_cmd_run)
    hello = sub.add_parser("hello", help="写一条 LangSmith 连通 trace")
    hello.set_defaults(func=_cmd_hello)
    ev = sub.add_parser("eval", help="跑本地规则评估")
    ev.set_defaults(func=_cmd_eval)
    web = sub.add_parser("web", help="启动 Vue + FastAPI 控制台")
    web.add_argument("--host", default="")
    web.add_argument("--port", type=int, default=0)
    web.set_defaults(func=_cmd_web)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
