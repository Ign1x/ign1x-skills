"""Exercise authentication in Chromium; intercept every request with offline HTML."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import learn_browser as helper

SEED = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
LOGIN = '''<form id="login" method="post" action="/auth">
<input id="i_user" name="number"><input id="i_pass" name="password" type="password">
</form><script>function doLogin(){document.querySelector('#login').submit();}</script>
<a href="#" onclick="doLogin(); return false;">登录</a>'''
SELECT_TOTP = '''<input type="radio" value="totp" name="kind">
<button onclick="location.href='/otp'">确定</button>'''
OTP = '''<form method="post" action="/verify"><input id="vericode" name="code">
<button>确定</button></form>'''
TRUST = '''二次验证成功<form method="post" action="/trust">
<input type="radio" name="trust" value="是"><input type="radio" name="trust" value="否">
<button>确定</button></form>'''
DESTINATION = "https://learn.tsinghua.edu.cn/f/wlxt/index/course/student/"


class Clock:
    def __init__(self):
        self.now = 1_000_000_010

    def time(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


class BrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception:
            cls.pw.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="thu-homework-browser-test-")
        self.addCleanup(self.tmp.cleanup)
        self.env = Path(self.tmp.name) / "profile.env"
        self.env.write_text(f"name=测试学生\nnumber=000123\npassword=offline-fake\ntotp={SEED}\n")
        self.context = self.browser.new_context(service_workers="block")
        self.addCleanup(self.context.close)
        self.context.route("**/*", self.respond)
        self.page = self.context.new_page()
        helper.page = self.page
        helper.env_path = self.env
        helper.password_attempted = False
        helper.totp_selected = False
        helper.totp_attempts = 0
        self.mode = "plain"
        self.reject_count = 0
        self.primary = []
        self.codes = []
        self.trust = []
        self.unexpected = []
        self.output = StringIO()
        self.addCleanup(patch.stopall)
        patch.object(helper, "time", Clock()).start()

    def respond(self, route):
        request = route.request
        parsed = urlsplit(request.url)
        data = parse_qs(request.post_data or "")
        if parsed.hostname in ("id.tsinghua.edu.cn", "id.tsinghua.edu.cn.invalid"):
            if parsed.path == "/login":
                html = LOGIN
            elif parsed.path == "/auth":
                self.primary.append(data)
                if self.mode == "plain":
                    route.fulfill(status=302, headers={"location": DESTINATION}, body="")
                    return
                html = SELECT_TOTP if self.mode == "totp" else '<input id="vericode">短信验证码'
            elif parsed.path == "/otp":
                html = OTP
            elif parsed.path == "/verify":
                self.codes.append(data.get("code", [""])[0])
                html = OTP + "动态验证码验证失败" if len(self.codes) <= self.reject_count else TRUST
            elif parsed.path == "/trust":
                self.trust.append(data)
                route.fulfill(status=302, headers={"location": DESTINATION}, body="")
                return
            else:
                self.unexpected.append(parsed.path)
                route.abort()
                return
            route.fulfill(content_type="text/html; charset=utf-8", body=html)
        elif parsed.hostname == "learn.tsinghua.edu.cn":
            # The real page may request favicons, static assets, or redirects
            # after authentication; keep the fixture offline and harmless.
            route.fulfill(content_type="text/html; charset=utf-8", body="课程列表")
        else:
            self.unexpected.append(parsed.hostname)
            route.abort()

    def run_login(self):
        self.page.goto("https://id.tsinghua.edu.cn/login")
        with redirect_stdout(self.output):
            return helper.resume_login()

    def tearDown(self):
        self.assertEqual(self.unexpected, [])
        for value in ("offline-fake", "000123", SEED):
            self.assertNotIn(value, self.output.getvalue())

    def test_primary_login_and_no_duplicate_password_submission(self):
        self.assertTrue(self.run_login())
        with redirect_stdout(self.output):
            self.assertTrue(helper.resume_login())
        self.assertEqual(self.primary, [{"number": ["000123"], "password": ["offline-fake"]}])
        self.assertEqual(self.codes, [])

    def test_totp_retry_then_success_declines_long_term_trust(self):
        self.mode = "totp"
        self.reject_count = 1
        self.assertTrue(self.run_login(), self.output.getvalue())
        self.assertEqual(len(self.primary), 1)
        self.assertEqual(len(self.codes), 2)
        self.assertTrue(all(len(code) == 6 and code.isdigit() for code in self.codes))
        self.assertEqual(self.trust, [{"trust": ["否"]}])
        self.assertTrue(helper.authenticated())

    def test_missing_totp_can_resume_same_browser_after_local_edit(self):
        self.mode = "totp"
        self.env.write_text("name=测试学生\nnumber=000123\npassword=offline-fake\n")
        self.assertFalse(self.run_login())
        self.assertEqual(self.codes, [])
        with self.env.open("a") as stream:
            stream.write(f"totp={SEED}\n")
        with redirect_stdout(self.output):
            self.assertTrue(helper.resume_login())
        self.assertEqual(len(self.primary), 1)
        self.assertEqual(len(self.codes), 1)

    def test_two_totp_failures_prevent_further_attempts(self):
        self.mode = "totp"
        self.reject_count = 99
        self.assertFalse(self.run_login())
        with redirect_stdout(self.output):
            self.assertFalse(helper.resume_login())
        self.assertEqual(len(self.codes), 2)
        self.assertEqual(self.trust, [])

    def test_wrong_origin_never_receives_identity_fields(self):
        self.page.goto("https://id.tsinghua.edu.cn.invalid/login")
        with redirect_stdout(self.output):
            self.assertFalse(helper.resume_login())
        self.assertEqual(self.page.locator("#i_user").input_value(), "")
        self.assertEqual(self.page.locator("#i_pass").input_value(), "")
        self.assertEqual(self.primary, [])

    def test_non_totp_challenge_requires_user(self):
        self.mode = "sms"
        self.assertFalse(self.run_login())
        self.assertEqual(self.page.locator("#vericode").input_value(), "")
        self.assertEqual(self.codes, [])


if __name__ == "__main__":
    unittest.main()
