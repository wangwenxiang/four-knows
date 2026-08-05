import unittest
from unittest.mock import patch

from scripts.fetch_ai_v_radar import CookieManagerBirdSession, bird_command, run_bird


class CookieManagerBirdSessionTest(unittest.TestCase):
    def test_cookie_manager_credentials_stay_out_of_bird_argv(self):
        session = CookieManagerBirdSession("auth-secret", "csrf-secret")
        command = bird_command(session, "search", "from:example", "--json")
        self.assertEqual(command, ["bird", "search", "from:example", "--json"])
        self.assertNotIn("auth-secret", command)
        self.assertNotIn("csrf-secret", command)

    def test_cookie_manager_credentials_are_scoped_to_bird_environment(self):
        session = CookieManagerBirdSession("auth-secret", "csrf-secret")
        with patch("scripts.fetch_ai_v_radar.subprocess.run") as run:
            run_bird(["bird", "search", "from:example"], session, timeout=10)
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["AUTH_TOKEN"], "auth-secret")
        self.assertEqual(environment["CT0"], "csrf-secret")


if __name__ == "__main__":
    unittest.main()
