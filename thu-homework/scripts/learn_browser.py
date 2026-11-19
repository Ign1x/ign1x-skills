#!/usr/bin/env python3
"""Ephemeral Learn browser. Run with python -i; this helper never submits work."""

import argparse
import atexit
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

import pyotp

from credentials import ProfileError, load_profile, profile_path


pw = browser = context = page = None
env_path = None
password_attempted = False
totp_attempts = 0
totp_selected = False


def at_host(url, hostname):
    try:
        parsed = urlsplit(url)
        return parsed.scheme == "https" and parsed.hostname == hostname and parsed.port in (None, 443)
    except ValueError:
        return False


def require_identity_host():
    if not at_host(page.url, "id.tsinghua.edu.cn"):
        raise ProfileError("认证页面不是预期的 HTTPS 域名，已停止填写凭证。")


def authenticated():
    return at_host(page.url, "learn.tsinghua.edu.cn") and urlsplit(page.url).path.startswith("/f/wlxt/")


def make_totp(seed):
    if not seed:
        raise ProfileError("需要二次验证：请在本地资料文件填写 totp，或在有界面浏览器完成验证后调用 resume_login()。")
    try:
        otp = pyotp.parse_uri(seed) if seed.startswith("otpauth://") else pyotp.TOTP(seed.replace(" ", ""))
        if not isinstance(otp, pyotp.TOTP) or not 5 <= otp.interval <= 60:
            raise ValueError()
        otp.byte_secret()
    except Exception:
        raise ProfileError("本地 totp 格式无效；应为 Base32 密钥或 TOTP URI（周期 5–60 秒）。") from None
    return otp


def submit_totp():
    global totp_attempts, totp_selected
    if totp_attempts >= 2:
        raise ProfileError("TOTP 已尝试两次；修正本地种子或系统时钟后再重新登录。")
    otp = make_totp(load_profile(env_path).totp)
    selector = page.locator('input[type=radio][value=totp]')
    if selector.is_visible():
        require_identity_host()
        selector.check()
        page.get_by_text("确定", exact=True).click()
        totp_selected = True
    if not totp_selected:
        raise ProfileError("当前验证码类型尚未确认，请在页面选择 TOTP 或由用户完成验证。")
    page.locator("#vericode").wait_for(state="visible")
    while totp_attempts < 2:
        remaining = otp.interval - time.time() % otp.interval
        if remaining < 5 or totp_attempts:
            until = time.time() + remaining + 0.5
            while time.time() < until:
                time.sleep(min(15, max(0, until - time.time())))
        require_identity_host()
        page.locator("#vericode").fill(otp.now())
        totp_attempts += 1
        page.get_by_text("确定", exact=True).click()
        page.wait_for_function(
            "location.hostname === 'learn.tsinghua.edu.cn' || "
            "document.body.innerText.includes('动态验证码验证失败') || "
            "document.body.innerText.includes('二次验证成功')"
        )
        if authenticated() or "动态验证码验证失败" not in page.locator("body").inner_text():
            return
    raise ProfileError("TOTP 已拒绝两次；请检查本地种子和系统时钟，勿连续重试。")


def continue_login():
    global password_attempted
    if authenticated():
        print("已登录网络学堂；脚本未提交任何作业。")
        return True
    user_input = page.locator("#i_user")
    if user_input.is_visible():
        if password_attempted:
            raise ProfileError("主凭证已尝试一次，请检查本地信息或处理页面验证，勿连续尝试密码。")
        profile = load_profile(env_path)
        require_identity_host()
        user_input.fill(profile.number)
        require_identity_host()
        page.locator("#i_pass").fill(profile.password)
        password_attempted = True
        require_identity_host()
        with page.expect_navigation(wait_until="domcontentloaded"):
            page.locator('a[onclick="doLogin(); return false;"]').click()
    if authenticated():
        print("已登录网络学堂；脚本未提交任何作业。")
        return True
    if (page.locator('input[type=radio][value=totp]').is_visible()
            or (totp_selected and page.locator("#vericode").is_visible())):
        submit_totp()
    elif page.locator("#vericode").is_visible():
        raise ProfileError("当前验证码未确认为 TOTP，请用户在页面完成验证后调用 resume_login()。")
    trust = page.locator('input[type=radio][value="否"]')
    if trust.is_visible():
        require_identity_host()
        trust.check()
        with page.expect_navigation(wait_until="domcontentloaded"):
            page.get_by_text("确定", exact=True).click()
    page.wait_for_url("https://learn.tsinghua.edu.cn/f/wlxt/**", timeout=30000)
    if not authenticated():
        raise ProfileError("尚未确认登录成功，请处理当前页面验证。")
    print("已登录网络学堂；脚本未提交任何作业。")
    return True


def resume_login():
    """Resume the same page after local profile edits or manual verification."""
    if page is None:
        print("浏览器尚未启动，请先补齐本地资料并重新运行脚本。")
        return False
    try:
        return continue_login()
    except ProfileError as error:
        print(str(error))
    except Exception:
        # Playwright exceptions can embed token-bearing URLs or field values.
        print("登录未完成。请检查当前页面的可见状态，处理验证后再调用 resume_login()；不要输出认证页原文或重复登录。")
    return False


def close_browser():
    global pw, browser, context, page
    try:
        if browser is not None:
            browser.close()
    finally:
        if pw is not None:
            pw.stop()
        pw = browser = context = page = None


def main():
    global pw, browser, context, page, env_path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    try:
        env_path = profile_path(args.env)
        load_profile(env_path)
    except ProfileError as error:
        print(str(error))
        return
    os.umask(0o077)
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=not args.headed)
        context = browser.new_context(locale="zh-CN", timezone_id="Asia/Shanghai")
        page = context.new_page()
    except Exception:
        print("浏览器启动失败；请按 references/learn-platform.md 安装 Playwright 与匹配的 Chromium。")
        close_browser()
        return
    atexit.register(close_browser)
    try:
        page.goto("https://learn.tsinghua.edu.cn", wait_until="domcontentloaded")
        page.locator("#loginButtonId").click()
        page.locator("#i_user").wait_for(state="visible")
    except Exception:
        print("登录入口未就绪，请检查当前页面是否变更或需要人工验证，再调用 resume_login()。")
        return
    resume_login()


if __name__ == "__main__":
    main()
