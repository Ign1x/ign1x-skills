import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import credentials
import learn_browser


class CredentialsTest(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(prefix="thu-homework-test-")
        self.addCleanup(self.sandbox.cleanup)
        self.env = Path(self.sandbox.name) / "private/profile.env"

    def write(self, text):
        self.env.parent.mkdir(parents=True, exist_ok=True)
        self.env.write_text(text, encoding="utf-8")

    def command(self, operation):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "credentials.py"), operation, "--env", str(self.env)],
            capture_output=True, text=True, check=False,
        )

    def test_first_run_creates_private_template(self):
        result = self.command("init")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["missing"], ["name", "number", "password"])
        self.assertEqual(self.command("check").returncode, 1)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(self.env.parent.stat().st_mode), 0o700)

    def test_check_missing_does_not_create_a_file(self):
        result = self.command("check")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.env.exists())
        self.assertFalse(json.loads(result.stdout)["exists"])

    @unittest.skipUnless(shutil.which("git"), "Git is required for ignore behavior")
    def test_default_private_directory_stays_out_of_workspace_git(self):
        root = Path(self.sandbox.name)
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        profile = root / ".thu-homework.private/profile.env"
        credentials.init_profile(profile)
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--quiet", str(profile)],
            capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0)

    def test_init_preserves_existing_bytes_and_legacy_totp(self):
        self.env.parent.mkdir(parents=True)
        original = b"# existing\r\nnumber=000123\r\npassword='fake # secret'\r\ntopt=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        self.env.write_bytes(original)
        credentials.init_profile(self.env)
        self.assertEqual(self.env.read_bytes(), original + b"\nname=\n")
        once = self.env.read_bytes()
        credentials.init_profile(self.env)
        self.assertEqual(self.env.read_bytes(), once)
        self.assertEqual(credentials.check_profile(self.env)["missing"], ["name"])

    def test_literal_secret_and_leading_zero_number_are_preserved(self):
        sentinel = Path(self.sandbox.name) / "must-not-exist"
        password = f' ${{HOME}} # $(touch {sentinel}) `id` '
        self.write(f"name=测试学生\nnumber=000123\npassword='{password}'\n")
        profile = credentials.load_profile(self.env)
        self.assertEqual(profile.password, password)
        self.assertEqual(profile.number, "000123")
        self.assertFalse(sentinel.exists())
        self.assertNotIn(password, repr(profile))
        result = self.command("check")
        self.assertEqual(result.returncode, 0)
        for value in [password, "测试学生", "000123"]:
            self.assertNotIn(value, result.stdout + result.stderr)

    def test_empty_canonical_totp_falls_back_to_legacy_alias(self):
        self.write("name=测试\nnumber=000123\npassword=fake\ntotp=\ntopt=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ\n")
        self.assertEqual(credentials.load_profile(self.env).totp, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")

    def test_malformed_file_is_not_modified_or_echoed(self):
        original = 'name=测试\nnumber=000123\npassword="sensitive-unterminated\n'
        self.write(original)
        result = self.command("init")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("sensitive-unterminated", result.stdout + result.stderr)
        self.assertEqual(self.env.read_text(), original)

    def test_duplicate_credentials_are_rejected_without_values(self):
        self.write("name=测试\nnumber=000123\npassword=one-secret\npassword=two-secret\n")
        result = self.command("check")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("one-secret", result.stdout + result.stderr)
        self.assertNotIn("two-secret", result.stdout + result.stderr)

    def test_skill_directory_and_symlink_into_it_are_rejected(self):
        fake_skill = Path(self.sandbox.name) / "skill"
        fake_skill.mkdir()
        alias = Path(self.sandbox.name) / "alias"
        alias.symlink_to(fake_skill, target_is_directory=True)
        with patch.object(credentials, "SKILL_ROOT", fake_skill):
            for path in (fake_skill / "profile.env", alias / "profile.env"):
                with self.assertRaises(credentials.ProfileError):
                    credentials.init_profile(path)
                self.assertFalse(path.exists())

    def test_blank_values_remain_missing(self):
        self.write("name=' '\nnumber=\npassword='  '\n")
        self.assertEqual(credentials.check_profile(self.env)["missing"], list(credentials.REQUIRED))


class AuthenticationValidationTest(unittest.TestCase):
    def test_only_official_https_origin_is_accepted(self):
        host = "id.tsinghua.edu.cn"
        self.assertTrue(learn_browser.at_host(f"https://{host}/login", host))
        for url in [
            f"http://{host}/login", f"https://{host}.invalid/login",
            f"https://{host}@example.org/", f"https://{host}:444/", f"https://{host}:invalid/",
        ]:
            self.assertFalse(learn_browser.at_host(url, host))

    def test_totp_seed_and_uri_work_without_exposing_invalid_input(self):
        seed = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        otp = learn_browser.make_totp(seed)
        uri = otp.provisioning_uri(name="offline-test", issuer_name="fixture")
        self.assertEqual(learn_browser.make_totp(uri).at(0), otp.at(0))
        for invalid in ["invalid-sensitive-value", "otpauth://hotp/test?secret=" + seed + "&counter=0"]:
            with self.assertRaises(credentials.ProfileError) as caught:
                learn_browser.make_totp(invalid)
            self.assertNotIn(invalid, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
