"""User-facing copy. No stack traces, status codes, or secret names."""

from __future__ import annotations


ACK_GENERIC = "已收到，开始处理。"
ACK_MEDIA = "已收到链接。我会先找字幕，没有字幕再转写，完成后把飞书文档发给你。"
ASK_UNKNOWN = "请发一个公开的播客或视频链接（小宇宙、YouTube、B站），或本地音频路径。"
ASK_UNSUPPORTED_SOCIAL = "小D不采集小红书、抖音、公众号和视频号。请发小宇宙、YouTube、B站的公开链接，或本地音频路径。"
ASK_UNSUPPORTED_MINUTES = "小D不处理飞书妙记。请发小宇宙、YouTube、B站的公开链接，或本地音频路径。"
NEED_FFMPEG = "本机还没有音频处理工具，暂时没法下载或转写。请先安装 ffmpeg 后再试。"
NEED_ASR = "没有现成字幕，本机也还没装语音识别组件。可以先装 faster-whisper，或换一条带字幕的视频。"
NEED_FEISHU = "文稿已经整理好，但飞书应用还没接通，所以没法创建文档。请先配置飞书应用后再发一次。"
NEED_LLM = "整理稿会先用规则清洗。要得到更完整的分享式文稿，请再配置大模型密钥。"
STATUS_RUNNING = "还在处理中，好了我会把结果发过来。"
STATUS_IDLE = "当前没有进行中的任务。直接发链接就可以。"
DONE_DOC = "整理完成，文档已创建。请点开确认目录和权限是否正常。"
PERMISSION_MANUAL = "文档已创建，但自动授权没有完成。请你自己打开文档，把访问权限加上。"
TRANSCRIPT_SLOW = "这条音频比较长，本机转写会花一段时间。开始前先告诉你预计耗时。"
WEB_BUSY = "上一条任务还在处理。请等它结束后再提交。"
WEB_EMPTY = "请先粘贴一条公开播客或视频链接。"
WEB_FAILED = "这次没有处理成功。请换一条公开链接再试。"
WEB_INTERRUPTED = "这次处理中断了。请用同一条链接再试一次。"
WEB_STOPPED = "任务已停止。需要同一条链接的话，再提交一次即可。"
WEB_RESUMED = "服务已恢复，继续处理这条任务。"


def user_error(code: str) -> str:
    mapping = {
        "login_required": "这个链接需要登录或会员才能听。请换一条不用登录就能打开的公开链接，或发本地音频文件。",
        "region_blocked": "这个平台在当前地区不提供这段内容。请换一条能直接打开的公开链接，或发本地音频文件。",
        "platform_blocked": "这个平台不允许直接下载，或链接已经失效。请换一条公开播客或视频链接，或发本地音频文件。",
        "no_audio": "这条内容里没有可转写的人声或音频轨。请换一条有人讲话的公开视频或播客。",
        "download_failed": "这个链接没法直接下载。请换一条公开链接，或发本地音频文件。",
        "asr_failed": "语音识别没有成功。可以换一条带字幕的视频，或稍后再试。",
        "qa_failed": "整理稿还不符合交付标准，我已经按规则重写过一轮。请检查后再决定要不要人工改。",
        "feishu_failed": "飞书文档没有创建成功。请稍后重试，或先检查应用是否已发布、权限是否开通。",
        "unknown": "这次没有处理成功。请换一条公开链接再试。",
    }
    return mapping.get(code, mapping["unknown"])


def format_doc_reply(*, url: str, title: str, used_subtitle: bool, permission_granted: bool) -> str:
    source = "平台字幕" if used_subtitle else "语音识别"
    lines = [
        DONE_DOC,
        f"标题：{title}" if title else "",
        f"材料来源：{source}",
        f"文档：{url}" if url else "",
    ]
    if url and not permission_granted:
        lines.append(PERMISSION_MANUAL)
    return "\n".join(line for line in lines if line)


def eta_notice(duration_sec: int, eta_minutes: int) -> str:
    minutes = max(1, duration_sec // 60)
    return f"{TRANSCRIPT_SLOW}音频大约 {minutes} 分钟，预计转写 {eta_minutes} 分钟。"
