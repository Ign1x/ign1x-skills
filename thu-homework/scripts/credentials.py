#!/usr/bin/env python3
"""Create/check a local profile without printing its values or running shell code."""

import argparse
from dataclasses import dataclass, field
from io import StringIO
import json
import os
from pathlib import Path
import sys

from dotenv.parser import parse_stream


SKILL_ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("name", "number", "password")
TEMPLATE = "# Fill in locally; do not commit this file.\nname=\nnumber=\npassword=\ntotp=\n"


class ProfileError(Exception):
    """An error message safe to show without exposing profile values."""


@dataclass(frozen=True, repr=False)
class Profile:
    name: str = field(repr=False)
    number: str = field(repr=False)
    password: str = field(repr=False)
    totp: str = field(default="", repr=False)

    def __repr__(self):
        return "Profile(<redacted>)"


def profile_path(path):
    resolved = Path(path).expanduser().resolve()
    if resolved == SKILL_ROOT or SKILL_ROOT in resolved.parents:
        raise ProfileError("个人资料必须放在技能目录之外，避免进入 Git 或 Nix store。")
    return resolved


def read_values(path):
    """Parse dotenv literally: no expansion of shell or environment variables."""
    try:
        content = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeError):
        raise ProfileError("无法读取 UTF-8 资料文件，请检查路径、编码和权限。") from None
    values = {}
    for binding in parse_stream(StringIO(content)):
        if binding.error:
            raise ProfileError(f"资料文件第 {binding.original.line} 行格式有误，请在本地修正。")
        if binding.key is not None:
            if binding.key in values and binding.key in (*REQUIRED, "totp", "topt"):
                raise ProfileError(f"资料文件包含重复的 {binding.key} 字段，请在本地合并。")
            values[binding.key] = binding.value or ""
    return values, content


def init_profile(path):
    path = profile_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.name == ".thu-homework.private":
        # Keep default runtime data ignored even when its workspace is a Git repo.
        ignore = path.parent / ".gitignore"
        try:
            ignore_fd = os.open(ignore, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(ignore_fd, "w", encoding="utf-8") as stream:
                stream.write("*\n")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        values, content = read_values(path)
        fields = [key for key in REQUIRED if key not in values]
        if "totp" not in values and "topt" not in values:
            fields.append("totp")
        if fields:
            suffix = ("\n" if content and not content.endswith("\n") else "")
            suffix += "".join(f"{key}=\n" for key in fields)
            with path.open("ab") as stream:
                stream.write(suffix.encode("utf-8"))
        if os.name == "posix":
            path.chmod(0o600)
    else:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(TEMPLATE)
    return path


def check_profile(path):
    path = profile_path(path)
    if not path.exists():
        return {"path": str(path), "exists": False, "ready": False, "missing": list(REQUIRED)}
    values, _ = read_values(path)
    missing = [key for key in REQUIRED if not values.get(key, "").strip()]
    return {"path": str(path), "exists": True, "ready": not missing, "missing": missing}


def load_profile(path):
    path = profile_path(path)
    values, _ = read_values(path)
    missing = [key for key in REQUIRED if not values.get(key, "").strip()]
    if missing:
        raise ProfileError("请在本地资料文件补齐：" + ", ".join(missing))
    return Profile(
        name=values["name"].strip(),
        number=values["number"].strip(),
        password=values["password"],
        totp=(values.get("totp", "").strip() or values.get("topt", "").strip()),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "check"))
    parser.add_argument("--env", type=Path, default=Path.cwd() / ".thu-homework.private/profile.env")
    args = parser.parse_args()
    try:
        path = init_profile(args.env) if args.command == "init" else profile_path(args.env)
        status = check_profile(path)
    except ProfileError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    except OSError:
        print(json.dumps({"error": "无法创建或更新资料文件，请检查路径和写入权限。"}, ensure_ascii=False))
        return 2
    print(json.dumps(status, ensure_ascii=False))
    return 0 if args.command == "init" or status["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
