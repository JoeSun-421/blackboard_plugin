"""Command-Line Interface for CUHK Blackboard Plugin.

Usage:
    python -m cuhk_blackboard.cli auth
    python -m cuhk_blackboard.cli status
    python -m cuhk_blackboard.cli courses
    python -m cuhk_blackboard.cli contents --course <id>
    python -m cuhk_blackboard.cli announcements [--course <id>]
    python -m cuhk_blackboard.cli grades --course <id>
    python -m cuhk_blackboard.cli download --course <id> --content <id> --attachment <id>
    python -m cuhk_blackboard.cli mcp
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Optional

from .auth import AuthManager
from .client import BlackboardClient
from .interactive_login import prompt_user_auth
from .mcp_server import MCPServer


def main(args: Optional[list] = None):
    parser = argparse.ArgumentParser(
        prog="cuhk-blackboard",
        description="CUHK Blackboard Scraper & AI Agent Plugin CLI",
    )
    parser.add_argument("--host", default="https://blackboard.cuhk.edu.hk", help="Blackboard host URL")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: auth
    subparsers.add_parser("auth", help="Interactive authentication wizard")

    # Command: status
    subparsers.add_parser("status", help="Check current authentication and session status")

    # Command: courses
    subparsers.add_parser("courses", help="List all enrolled courses")

    # Command: contents
    p_contents = subparsers.add_parser("contents", help="List course contents/materials")
    p_contents.add_argument("--course", required=True, help="Course ID")
    p_contents.add_argument("--folder", help="Subfolder content ID")
    p_contents.add_argument("--recursive", action="store_true", help="Recursively list subfolders")

    # Command: announcements
    p_ann = subparsers.add_parser("announcements", help="List announcements")
    p_ann.add_argument("--course", help="Optional course ID filter")
    p_ann.add_argument("--limit", type=int, default=10, help="Max announcements to show")

    # Command: grades
    p_grades = subparsers.add_parser("grades", help="View gradebook grades for a course")
    p_grades.add_argument("--course", required=True, help="Course ID")

    # Command: download
    p_dl = subparsers.add_parser("download", help="Download an attachment file")
    p_dl.add_argument("--course", required=True, help="Course ID")
    p_dl.add_argument("--content", required=True, help="Content ID")
    p_dl.add_argument("--attachment", required=True, help="Attachment ID")
    p_dl.add_argument("--dir", default="./downloads", help="Destination folder")

    # Command: mcp
    subparsers.add_parser("mcp", help="Start the Model Context Protocol (MCP) server")

    parsed = parser.parse_args(args)
    client = BlackboardClient(host=parsed.host)

    if parsed.command == "auth":
        prompt_user_auth(client=client, host=parsed.host)

    elif parsed.command == "status":
        if not client.auth_manager.is_configured:
            print("❌ 未配置认证信息。请运行 'python -m cuhk_blackboard.cli auth' 进行配置。")
            return
        print(f"📡 目标服务器: {client.host}")
        print(f"🔑 认证方式: {client.auth_manager.config.method.value}")
        is_valid, result = client.verify_auth()
        if is_valid:
            print(f"✅ 认证有效！登录用户: {result.display_name} ({result.username})")
        else:
            print(f"❌ 认证失效或过期: {result}")

    elif parsed.command == "courses":
        try:
            courses = client.list_courses()
            print(f"\n📚 共获取到 {len(courses)} 门课程:")
            for i, c in enumerate(courses, 1):
                print(f"  {i}. [{c.id}] {c.course_id} - {c.name}")
        except Exception as e:
            print(f"❌ 获取课程失败: {e}")

    elif parsed.command == "contents":
        try:
            items = client.list_course_contents(
                course_id=parsed.course,
                content_id=parsed.folder,
                recursive=parsed.recursive,
            )
            print(f"\n📂 课程内容 ({len(items)} 项):")
            for item in items:
                print(f"  - [{item.content_type.value.upper()}] {item.title} (ID: {item.id})")
                for att in item.attachments:
                    print(f"      📎 附件: {att.file_name} (ID: {att.id})")
        except Exception as e:
            print(f"❌ 获取课件失败: {e}")

    elif parsed.command == "announcements":
        try:
            anns = client.list_announcements(course_id=parsed.course, limit=parsed.limit)
            print(f"\n📢 公告列表 ({len(anns)} 项):")
            for a in anns:
                print(f"  - 标题: {a.title} ({a.created_at or '未知时间'})")
                print(f"    摘要: {a.content_text[:120]}...\n")
        except Exception as e:
            print(f"❌ 获取公告失败: {e}")

    elif parsed.command == "grades":
        try:
            grades = client.get_grades(course_id=parsed.course)
            print(f"\n📊 成绩表 ({len(grades)} 项):")
            for g in grades:
                score_str = f"{g.score}/{g.points_possible}" if g.points_possible else str(g.score)
                print(f"  - {g.column_name}: {score_str} (状态: {g.status})")
        except Exception as e:
            print(f"❌ 获取成绩失败: {e}")

    elif parsed.command == "download":
        try:
            path = client.download_material(
                course_id=parsed.course,
                content_id=parsed.content,
                attachment_id=parsed.attachment,
                target_dir=parsed.dir,
            )
            print(f"✅ 文件下载成功: {path}")
        except Exception as e:
            print(f"❌ 下载失败: {e}")

    elif parsed.command == "mcp":
        server = MCPServer()
        server.run_stdio()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
