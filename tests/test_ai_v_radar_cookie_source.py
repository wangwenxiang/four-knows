import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.fetch_ai_v_radar import (
    BirdCookieSession, bird_command, dsh_bird_session, parse_args,
    prepare_bird_session, run_bird,
)


class BirdCookieSessionTest(unittest.TestCase):
    def test_credentials_stay_out_of_bird_argv_and_repr(self):
        session = BirdCookieSession("auth-secret", "csrf-secret", "dsh")
        command = bird_command(session, "search", "from:example", "--json")
        self.assertEqual(command, ["bird", "search", "from:example", "--json"])
        self.assertNotIn("auth-secret", command)
        self.assertNotIn("csrf-secret", command)
        self.assertNotIn("auth-secret", repr(session))

    def test_credentials_are_scoped_to_bird_environment(self):
        session = BirdCookieSession("auth-secret", "csrf-secret", "dsh")
        with patch("scripts.fetch_ai_v_radar.subprocess.run") as run:
            run_bird(["bird", "search", "from:example"], session, timeout=10)
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["AUTH_TOKEN"], "auth-secret")
        self.assertEqual(environment["CT0"], "csrf-secret")

    def test_dsh_success_extracts_only_required_fields(self):
        result = SimpleNamespace(returncode=0, stdout="Cookie: guest_id=guest; auth_token=auth-secret; ct0=csrf-secret", stderr="")
        with patch("scripts.fetch_ai_v_radar.DSH_COOKIE_CLI", Path(__file__)), patch(
            "scripts.fetch_ai_v_radar.subprocess.run", return_value=result
        ) as run:
            session = dsh_bird_session()
        self.assertEqual((session.auth_token, session.ct0, session.source), ("auth-secret", "csrf-secret", "dsh"))
        command = run.call_args.args[0]
        self.assertEqual(command[2:], ["get", "x.com", "--format", "header"])
        self.assertNotIn("auth-secret", command)

    def test_dsh_denial_and_missing_field_fail_without_exposing_values(self):
        cases = [
            SimpleNamespace(returncode=1, stdout="", stderr="secret-value"),
            SimpleNamespace(returncode=0, stdout="auth_token=secret-value", stderr=""),
        ]
        for result in cases:
            with self.subTest(exit=result.returncode), patch("scripts.fetch_ai_v_radar.DSH_COOKIE_CLI", Path(__file__)), patch(
                "scripts.fetch_ai_v_radar.subprocess.run", return_value=result,
            ):
                with self.assertRaises(RuntimeError) as error:
                    dsh_bird_session()
                self.assertNotIn("secret-value", str(error.exception))

    def test_dsh_is_the_production_default(self):
        with patch("sys.argv", ["fetch_ai_v_radar.py"]):
            self.assertEqual(parse_args().cookie_source, "dsh")

    def test_legacy_cookie_manager_source_is_rejected(self):
        with patch("scripts.fetch_ai_v_radar.dsh_bird_session") as dsh:
            with self.assertRaisesRegex(ValueError, "only supports the DSH"):
                prepare_bird_session("cookie-manager")
        dsh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
