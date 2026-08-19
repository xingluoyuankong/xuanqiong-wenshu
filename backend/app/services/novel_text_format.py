# -*- coding: utf-8 -*-
"""导出/导入共享的纯文本小说格式契约。

导出与导入必须引用同一份契约，否则两侧各写一份正则会再次分叉：
历史实现里导出用换行包裹标题并加分隔线，而导入只认「第N章」开头，
导致导出的全文重新导入后被当成单一「序章」，章节、摘要、账本、版本全部错位。
"""
from __future__ import annotations

import base64
import json
import re
from typing import List, Tuple

# 导出文件头的机读标记。导入侧凭此确定性剥离头部，而不是猜测“像文件头的文本”。
EXPORT_HEADER_MARKER = "# XUANQIONG-EXPORT v1"
EXPORT_HEADER_END_MARKER = "# XUANQIONG-EXPORT-BODY"
EXPORT_METADATA_PREFIX = "# XUANQIONG-METADATA "

# 章节标题正则：导出保证每章标题以「第N章」开头，导入据此还原章节边界。
CHAPTER_TITLE_PATTERN = r"(^\s*第[0-9零一二三四五六七八九十百千]+[章卷回节].*|^\s*Chapter\s+[0-9]+.*)"
_CHAPTER_PREFIX_RE = re.compile(r"^\s*第[0-9零一二三四五六七八九十百千]+[章卷回节]")


def has_chapter_prefix(title: str) -> bool:
    """标题是否已带「第N章/卷/回/节」前缀，避免导出时重复添加章号。"""
    return bool(_CHAPTER_PREFIX_RE.match(title or ""))


def build_chapter_title(chapter_number: int, outline_title: str | None) -> str:
    """构造可被导入侧还原的章节标题。"""
    bare = (outline_title or "").strip()
    if bare and has_chapter_prefix(bare):
        return bare
    return f"第{chapter_number}章 {bare}".strip()


def encode_export_metadata(metadata: dict) -> str:
    raw = json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return EXPORT_METADATA_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii")


def parse_export_metadata(content: str) -> dict | None:
    for line in (content or "").splitlines():
        if line.startswith(EXPORT_METADATA_PREFIX):
            try:
                raw = base64.urlsafe_b64decode(line[len(EXPORT_METADATA_PREFIX):].encode("ascii"))
                value = json.loads(raw.decode("utf-8"))
                return value if isinstance(value, dict) else None
            except (ValueError, UnicodeError, json.JSONDecodeError):
                return None
    return None


def strip_export_header(content: str) -> str:
    """剥离本系统导出的文件头；非本系统文件原样返回，保持旧稿导入兼容。"""
    if EXPORT_HEADER_MARKER not in content:
        return content
    _, _, remainder = content.partition(EXPORT_HEADER_END_MARKER)
    return remainder.lstrip("\n") if remainder else content


def split_into_chapters(content: str) -> List[Tuple[str, str]]:
    """按章节标题切分正文，返回 (标题, 正文) 列表。

    先剥离导出头，再切章。剥离后如果仍有前置内容（真实旧稿的序章/前言），
    仍然保留为「序章」，不能因为对齐导出格式而丢掉旧稿正文。
    """
    body = strip_export_header(content or "")
    parts = re.split(CHAPTER_TITLE_PATTERN, body, flags=re.MULTILINE)

    chapters: List[Tuple[str, str]] = []
    if parts and parts[0].strip():
        chapters.append(("序章", parts[0].strip()))

    for index in range(1, len(parts), 2):
        title = parts[index].strip()
        chapter_body = parts[index + 1].strip() if index + 1 < len(parts) else ""
        if chapter_body:
            chapters.append((title, chapter_body))

    return chapters
