from pathlib import Path
import json
import unittest

from xclawer.normalize import normalize_tweets
from xclawer.scoring import categorize, score_tweet


class NormalizeTest(unittest.TestCase):
    def load_fixture(self):
        return json.loads(Path("tests/fixtures/bird_user_tweets.json").read_text(encoding="utf-8"))

    def test_normalize_fixture(self):
        tweets = normalize_tweets(self.load_fixture())
        self.assertEqual(len(tweets), 3)
        self.assertEqual(tweets[0].author_handle, "karpathy")
        self.assertEqual(tweets[1].author_handle, "researcher_ai")
        self.assertEqual(tweets[1].like_count, 2100)

    def test_scoring_and_category(self):
        tweets = normalize_tweets(self.load_fixture())
        self.assertGreater(score_tweet(tweets[0]), score_tweet(tweets[2]))
        self.assertEqual(categorize(tweets[0]), "模型与论文")


if __name__ == "__main__":
    unittest.main()
