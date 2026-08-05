import unittest

from scripts.render_ai_v_poster import clip_title, editorial_copy_with_metadata, fallback_copy, fit_subtitle, headline_font_size, poster_subtitle, render_story


def sample_post():
    return {
        "id": "1",
        "isTopStory": True,
        "topStoryCategory": "AI 技术进步",
        "expert": {"name": "Test", "handle": "test", "role": "AI Lab"},
        "author": {"username": "test", "profileImageUrl": "https://example.com/avatar.jpg"},
    }


class PosterDensityTest(unittest.TestCase):
    def test_sparse_copy_gets_large_type_class(self):
        rendered = render_story(sample_post(), {"title": "短标题", "summary": "简短但完整的事实说明"}, 1)
        self.assertIn("story--sparse", rendered)

    def test_long_copy_gets_dense_type_class(self):
        rendered = render_story(sample_post(), {"title": "长标题" * 15, "summary": "完整技术事实" * 20}, 1)
        self.assertIn("story--dense", rendered)

    def test_fallback_title_prefers_substantive_primary_sentence_over_thanks(self):
        post = sample_post() | {
            "translationZh": (
                "这是我们首次经历此类事件，我们要感谢 OpenAI 的透明披露与合作。\n\n"
                "用于网络防御的高能力开放权重模型非常重要。"
            ),
            "quotedTweet": {"translationZh": "引用帖提到一次重大安全事件。"},
        }
        copy = fallback_copy(post)
        self.assertIn("网络防御", copy["title"])
        self.assertNotIn("感谢", copy["title"])

    def test_fallback_metadata_records_non_codex_backend(self):
        post = sample_post() | {
            "translationZh": "新模型在生产环境完成了安全基准测试。",
            "quotedTweet": {"translationZh": "引用帖的完整中文翻译。"},
        }
        copies, metadata = editorial_copy_with_metadata([post], use_codex=False)
        self.assertEqual(metadata["copyBackend"], "deterministic-fallback")
        self.assertEqual(metadata["copyAttempts"], 0)
        self.assertTrue(copies[0]["title"])
        self.assertEqual(copies[0]["summary"], "引用｜引用帖的完整中文翻译。")

    def test_title_clipping_uses_a_complete_clause(self):
        title = clip_title("具备网络攻击能力的 OpenAI 模型通过发现并串联多个零日漏洞，攻破了生产环境。", 35)
        self.assertEqual(title, "具备网络攻击能力的 OpenAI 模型通过发现并串联多个零日漏洞")

    def test_fallback_removes_conversational_comparison_wrapper(self):
        post = sample_post() | {
            "translationZh": "我们新的 Gemini 3.6 Flash 模型一个很好的特点是，相比 3.5 Flash，它的 token 效率高得多。"
        }
        self.assertEqual(fallback_copy(post)["title"], "Gemini 3.6 Flash token 效率高于 3.5 Flash")

    def test_subtitle_uses_a_complete_sentence_instead_of_an_ellipsis(self):
        subtitle = fit_subtitle("WebSwarm 在 BrowseComp-Plus 上把准确率从 50.5 提升至 68.0。后续评测还覆盖多跳检索与证据归因。", 40)
        self.assertEqual(subtitle, "WebSwarm 在 BrowseComp-Plus 上把准确率从 50.5 提升至 68.0。")
        self.assertNotIn("…", subtitle)

    def test_short_headline_is_scaled_to_use_more_of_the_card_width(self):
        self.assertGreater(headline_font_size("不可变日志是长期大规模协作的审计底座"), headline_font_size("前 Anthropic 员工称黑客偏爱补贴型实验室 AI 订阅"))

    def test_long_quoted_translation_is_not_shortened_in_copy_generation(self):
        quote = "引用帖完整中文翻译。" * 20
        post = sample_post() | {"quotedTweet": {"translationZh": quote}}
        self.assertEqual(poster_subtitle(post, "备用摘要"), "引用｜" + quote)


if __name__ == "__main__":
    unittest.main()
