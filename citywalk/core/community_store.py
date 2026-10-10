# -*- coding: utf-8 -*-
"""社区 UGC：动态帖与找搭子（volume 文件存储）。"""

import json
import logging
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,32}$")
_POST_TYPES = frozenset({"路线", "打卡", "攻略", "夜游", "拍照"})
_BUDDY_FILTERS = frozenset({"全部", "今天", "周末", "摄影", "美食", "轻徒步"})
_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "community"
_MAX_DOC_BYTES = 16 * 1024
_MAX_LIST = 500


def _base_dir() -> Path:
    raw = os.environ.get("CITYWALK_COMMUNITY_DATA_DIR", "").strip()
    if raw:
        return Path(raw)
    shared = os.environ.get("CITYWALK_SHARED_ROUTES_DIR", "").strip()
    if shared:
        return Path(shared).parent / "community"
    return _DEFAULT_DIR


def _subdir(name: str) -> Path:
    p = _base_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_doc(folder: Path, doc: Dict[str, Any]) -> bool:
    rid = doc.get("id")
    if not rid or not _ID_RE.match(rid):
        return False
    fp = folder / f"{rid}.json"
    tmp = folder / f".{rid}.{secrets.token_hex(4)}.tmp"
    try:
        tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(fp)
        return True
    except OSError:
        logging.exception("community write failed")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _read_doc(folder: Path, item_id: str) -> Optional[Dict[str, Any]]:
    if not _ID_RE.match(item_id):
        return None
    fp = folder / f"{item_id}.json"
    if not fp.is_file():
        return None
    try:
        doc = json.loads(fp.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _list_docs(folder: Path, limit: int) -> List[Dict[str, Any]]:
    if not folder.is_dir():
        return []
    items: List[Dict[str, Any]] = []
    for fp in folder.glob("*.json"):
        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and doc.get("id"):
                items.append(doc)
        except (OSError, json.JSONDecodeError):
            continue
    items.sort(key=lambda d: float(d.get("created_at") or 0), reverse=True)
    return items[: max(1, min(limit, _MAX_LIST))]


def _sanitize_text(s: Any, max_len: int) -> str:
    t = str(s or "").strip()
    if len(t) > max_len:
        return t[:max_len]
    return t


def _sanitize_tags(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for t in raw[:8]:
        tag = _sanitize_text(str(t).lstrip("#"), 24)
        if tag and tag not in out:
            out.append(tag)
    return out


def create_post(
    user_id: str,
    author_name: str,
    payload: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    ptype = _sanitize_text(payload.get("type"), 12)
    if ptype not in _POST_TYPES:
        return None, "类型须为：路线 / 打卡 / 攻略 / 夜游 / 拍照"
    title = _sanitize_text(payload.get("title"), 80)
    desc = _sanitize_text(payload.get("desc") or payload.get("body"), 2000)
    if not title or not desc:
        return None, "请填写标题和正文"
    city = _sanitize_text(payload.get("city"), 24)
    image = _sanitize_text(payload.get("image_url") or payload.get("image"), 500)
    if image and not (image.startswith("https://") or image.startswith("http://")):
        image = ""
    now = time.time()
    doc = {
        "id": "p" + uuid.uuid4().hex[:14],
        "created_at": now,
        "author_user_id": user_id,
        "author": _sanitize_text(author_name, 32) or "Walker",
        "type": ptype,
        "city": city or "未标注",
        "title": title,
        "desc": desc,
        "tags": _sanitize_tags(payload.get("tags")),
        "image": image or "",
        "route_id": _sanitize_text(payload.get("route_id"), 64),
        "share_route_id": _sanitize_text(payload.get("share_route_id"), 32),
        "like_count": 0,
        "liked_user_ids": [],
        "reports": [],
    }
    if not _write_doc(_subdir("posts"), doc):
        return None, "发布失败"
    return _public_post(doc, user_id), None


def list_posts(
    *,
    post_type: Optional[str] = None,
    city: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 60,
    viewer_user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    items = _list_docs(_subdir("posts"), limit)
    pt = _sanitize_text(post_type, 12) if post_type and post_type != "全部" else ""
    c = _sanitize_text(city, 24) if city and city != "全部" else ""
    kw = (keyword or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for doc in items:
        if pt and doc.get("type") != pt:
            continue
        if c and doc.get("city") != c:
            continue
        if kw:
            blob = " ".join([
                str(doc.get("title") or ""),
                str(doc.get("desc") or ""),
                str(doc.get("city") or ""),
                " ".join(doc.get("tags") or []),
            ]).lower()
            if kw not in blob:
                continue
        out.append(_public_post(doc, viewer_user_id))
    return out


def _public_post(doc: Dict[str, Any], viewer_user_id: Optional[str] = None) -> Dict[str, Any]:
    liked_ids = doc.get("liked_user_ids") if isinstance(doc.get("liked_user_ids"), list) else []
    author_uid = doc.get("author_user_id") or ""
    return {
        "id": doc.get("id"),
        "created_at": doc.get("created_at"),
        "author": doc.get("author"),
        "type": doc.get("type"),
        "city": doc.get("city"),
        "title": doc.get("title"),
        "desc": doc.get("desc"),
        "tags": doc.get("tags") or [],
        "image": doc.get("image") or "",
        "route_id": doc.get("route_id") or "",
        "share_route_id": doc.get("share_route_id") or "",
        "like_count": int(doc.get("like_count") or 0),
        "liked_by_me": bool(viewer_user_id and viewer_user_id in liked_ids),
        "is_mine": bool(viewer_user_id and viewer_user_id == author_uid),
    }


def get_post(post_id: str, viewer_user_id: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    doc = _read_doc(_subdir("posts"), post_id)
    if not doc:
        return None, "帖子不存在"
    return _public_post(doc, viewer_user_id), None


def toggle_like_post(post_id: str, user_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    folder = _subdir("posts")
    doc = _read_doc(folder, post_id)
    if not doc:
        return None, "帖子不存在"
    liked = doc.get("liked_user_ids") if isinstance(doc.get("liked_user_ids"), list) else []
    if user_id in liked:
        liked = [x for x in liked if x != user_id]
        doc["like_count"] = max(0, int(doc.get("like_count") or 0) - 1)
    else:
        liked.append(user_id)
        doc["like_count"] = int(doc.get("like_count") or 0) + 1
    doc["liked_user_ids"] = liked[-500:]
    if not _write_doc(folder, doc):
        return None, "操作失败"
    return _public_post(doc, user_id), None


def delete_post(post_id: str, user_id: str) -> Optional[str]:
    folder = _subdir("posts")
    doc = _read_doc(folder, post_id)
    if not doc:
        return "帖子不存在"
    if doc.get("author_user_id") != user_id:
        return "只能删除自己的帖子"
    fp = folder / f"{post_id}.json"
    try:
        fp.unlink(missing_ok=True)
        return None
    except OSError:
        return "删除失败"


def report_post(post_id: str, user_id: str, reason: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    folder = _subdir("posts")
    doc = _read_doc(folder, post_id)
    if not doc:
        return None, "帖子不存在"
    text = _sanitize_text(reason, 500) or "未填写原因"
    reports = doc.get("reports") if isinstance(doc.get("reports"), list) else []
    if any(r.get("reporter_id") == user_id for r in reports if isinstance(r, dict)):
        return _public_post(doc, user_id), None
    reports.append({
        "reporter_id": user_id,
        "reason": text,
        "created_at": time.time(),
    })
    doc["reports"] = reports[-30:]
    if not _write_doc(folder, doc):
        return None, "举报失败"
    return _public_post(doc, user_id), None


def create_buddy(
    user_id: str,
    author_name: str,
    payload: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    title = _sanitize_text(payload.get("title"), 80)
    desc = _sanitize_text(payload.get("desc"), 1200)
    if not title or not desc:
        return None, "请填写标题和说明"
    city = _sanitize_text(payload.get("city"), 24)
    if not city:
        return None, "请填写城市"
    walk_at = _sanitize_text(payload.get("date") or payload.get("walk_at"), 64)
    if not walk_at:
        return None, "请填写出发时间"
    try:
        slots_max = int(payload.get("slots_max") or payload.get("people_max") or 4)
    except (TypeError, ValueError):
        slots_max = 4
    slots_max = max(2, min(8, slots_max))
    bf = _sanitize_text(payload.get("filter") or payload.get("buddy_filter"), 12)
    if bf and bf not in _BUDDY_FILTERS:
        bf = "周末"
    if not bf:
        bf = "周末"
    now = time.time()
    doc = {
        "id": "b" + uuid.uuid4().hex[:14],
        "created_at": now,
        "author_user_id": user_id,
        "user": _sanitize_text(author_name, 32) or "Walker",
        "city": city,
        "title": title,
        "desc": desc,
        "date": walk_at,
        "filter": bf,
        "tags": _sanitize_tags(payload.get("tags")),
        "people_max": slots_max,
        "join_user_ids": [user_id],
    }
    if not _write_doc(_subdir("buddies"), doc):
        return None, "发起失败"
    return _public_buddy(doc), None


def list_buddies(
    *,
    buddy_filter: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = 60,
) -> List[Dict[str, Any]]:
    items = _list_docs(_subdir("buddies"), limit)
    bf = _sanitize_text(buddy_filter, 12) if buddy_filter and buddy_filter != "全部" else ""
    c = _sanitize_text(city, 24) if city and city != "全部" else ""
    out: List[Dict[str, Any]] = []
    for doc in items:
        if c and doc.get("city") != c:
            continue
        if bf:
            tags = doc.get("tags") or []
            if doc.get("filter") != bf and bf not in tags:
                continue
        out.append(_public_buddy(doc))
    return out


def join_buddy(buddy_id: str, user_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    folder = _subdir("buddies")
    doc = _read_doc(folder, buddy_id)
    if not doc:
        return None, "活动不存在或已结束"
    joins = doc.get("join_user_ids")
    if not isinstance(joins, list):
        joins = []
    if user_id in joins:
        return _public_buddy(doc), None
    cap = int(doc.get("people_max") or 4)
    if len(joins) >= cap:
        return None, "人数已满"
    joins.append(user_id)
    doc["join_user_ids"] = joins
    if not _write_doc(folder, doc):
        return None, "加入失败"
    return _public_buddy(doc), None


def _public_buddy(doc: Dict[str, Any]) -> Dict[str, Any]:
    joins = doc.get("join_user_ids") if isinstance(doc.get("join_user_ids"), list) else []
    cap = int(doc.get("people_max") or 4)
    filled = len(joins)
    return {
        "id": doc.get("id"),
        "created_at": doc.get("created_at"),
        "user": doc.get("user"),
        "city": doc.get("city"),
        "title": doc.get("title"),
        "desc": doc.get("desc"),
        "date": doc.get("date"),
        "filter": doc.get("filter"),
        "tags": doc.get("tags") or [],
        "people": f"{filled} / {cap} 人",
        "people_filled": filled,
        "people_max": cap,
        "join_user_ids": joins,
    }
