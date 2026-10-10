# -*- coding: utf-8 -*-
"""Flask：社区动态与找搭子 UGC。"""
import logging

from flask import Blueprint, jsonify, request

from citywalk.core.community_store import (
    create_buddy,
    create_post,
    delete_post,
    join_buddy,
    list_buddies,
    list_posts,
    report_post,
    toggle_like_post,
)
from citywalk.core.user_auth import user_id_from_authorization_header
from citywalk.core.user_store import get_user_profile

bp = Blueprint("cw_community", __name__)


def _uid():
    return user_id_from_authorization_header(request.headers.get("Authorization"))


def _author_name(uid: str) -> str:
    prof = get_user_profile(uid) or {}
    return (prof.get("display_name") or prof.get("email") or "Walker").split("@")[0][:32]


@bp.route("/community/posts", methods=["GET", "POST", "OPTIONS"])
def community_posts():
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    if request.method == "GET":
        try:
            args = request.args
            posts = list_posts(
                post_type=args.get("type"),
                city=args.get("city"),
                keyword=args.get("q"),
                limit=int(args.get("limit") or 60),
                viewer_user_id=_uid(),
            )
            return jsonify({"success": True, "posts": posts}), 200
        except Exception:
            logging.exception("list_posts")
            return jsonify({"success": False, "message": "加载动态失败"}), 500

    uid = _uid()
    if not uid:
        return jsonify({"success": False, "message": "请先登录再发布"}), 401
    try:
        body = request.get_json(silent=True) or {}
        post, err = create_post(uid, _author_name(uid), body)
        if err:
            return jsonify({"success": False, "message": err}), 400
        return jsonify({"success": True, "post": post}), 201
    except Exception:
        logging.exception("create_post")
        return jsonify({"success": False, "message": "发布失败"}), 500


@bp.route("/community/posts/<post_id>/like", methods=["POST", "OPTIONS"])
def community_post_like(post_id: str):
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    uid = _uid()
    if not uid:
        return jsonify({"success": False, "message": "请先登录"}), 401
    try:
        post, err = toggle_like_post(post_id, uid)
        if err:
            return jsonify({"success": False, "message": err}), 404
        return jsonify({"success": True, "post": post}), 200
    except Exception:
        logging.exception("community_post_like")
        return jsonify({"success": False, "message": "操作失败"}), 500


@bp.route("/community/posts/<post_id>", methods=["DELETE", "OPTIONS"])
def community_post_delete(post_id: str):
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    uid = _uid()
    if not uid:
        return jsonify({"success": False, "message": "请先登录"}), 401
    err = delete_post(post_id, uid)
    if err:
        status = 403 if "只能" in err else 404
        return jsonify({"success": False, "message": err}), status
    return jsonify({"success": True}), 200


@bp.route("/community/posts/<post_id>/report", methods=["POST", "OPTIONS"])
def community_post_report(post_id: str):
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    uid = _uid()
    if not uid:
        return jsonify({"success": False, "message": "请先登录"}), 401
    try:
        body = request.get_json(silent=True) or {}
        post, err = report_post(post_id, uid, body.get("reason") or "")
        if err:
            return jsonify({"success": False, "message": err}), 404
        return jsonify({"success": True, "post": post, "message": "已收到举报，我们会尽快处理"}), 200
    except Exception:
        logging.exception("community_post_report")
        return jsonify({"success": False, "message": "举报失败"}), 500


@bp.route("/community/buddies", methods=["GET", "POST", "OPTIONS"])
def community_buddies():
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    if request.method == "GET":
        try:
            args = request.args
            items = list_buddies(
                buddy_filter=args.get("filter"),
                city=args.get("city"),
                limit=int(args.get("limit") or 60),
            )
            return jsonify({"success": True, "buddies": items}), 200
        except Exception:
            logging.exception("list_buddies")
            return jsonify({"success": False, "message": "加载找搭子失败"}), 500

    uid = _uid()
    if not uid:
        return jsonify({"success": False, "message": "请先登录再发起"}), 401
    try:
        body = request.get_json(silent=True) or {}
        item, err = create_buddy(uid, _author_name(uid), body)
        if err:
            return jsonify({"success": False, "message": err}), 400
        return jsonify({"success": True, "buddy": item}), 201
    except Exception:
        logging.exception("create_buddy")
        return jsonify({"success": False, "message": "发起失败"}), 500


@bp.route("/community/buddies/<buddy_id>/join", methods=["POST", "OPTIONS"])
def community_buddy_join(buddy_id: str):
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    uid = _uid()
    if not uid:
        return jsonify({"success": False, "message": "请先登录再加入"}), 401
    try:
        item, err = join_buddy(buddy_id, uid)
        if err:
            status = 404 if "不存在" in err else 400
            return jsonify({"success": False, "message": err}), status
        return jsonify({"success": True, "buddy": item}), 200
    except Exception:
        logging.exception("join_buddy")
        return jsonify({"success": False, "message": "加入失败"}), 500
