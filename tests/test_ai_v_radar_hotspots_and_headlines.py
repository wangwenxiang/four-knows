from collections import Counter
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import json
import sys
import unittest

from scripts.fetch_ai_v_radar import (
    Expert,
    build_hotspot_summary,
    cap_selected_posts_per_author,
    has_substantive_primary_top_story_evidence,
    is_redundant_nontechnical_wrapper,
    is_population_adoption_commentary,
    is_retrospective_method_commentary,
    normalize_posts,
    parse_args,
    same_top_story_event,
    select_editorial_top_stories,
    select_diverse_top_stories,
)


NOW = datetime(2026, 7, 22, 3, 0, tzinfo=timezone.utc)
EXPERT = Expert("P0", "机器人", "Robot Lab", "机器人研究", "test", "robotlab")


def raw_post(post_id: str, text: str) -> dict:
    return {
        "id": post_id,
        "text": text,
        "createdAt": (NOW - timedelta(hours=1)).isoformat(),
        "author": {"username": "robotlab", "name": "Robot Lab"},
        "likeCount": 10,
        "retweetCount": 2,
        "replyCount": 1,
    }


class HotspotAttributionTest(unittest.TestCase):
    def test_hotspot_post_is_rechecked_and_tagged_after_duplicate_merge(self):
        raw = raw_post("robot-1", "Our robotics model completed a new humanoid manipulation benchmark.")
        core = {"source": "search", "tweets": [raw]}
        hotspot = {
            "source": "x-hotspot-search",
            "hotspotDirection": "robotics",
            "hotspotDirectionLabel": "机器人领域突破",
            "hotspotPostMatchAny": ["robot", "robotics", "humanoid"],
            "tweets": [raw],
            "ok": True,
            "attempts": 1,
            "elapsedSeconds": 0.1,
        }
        posts, dropped = normalize_posts([core, hotspot], [EXPERT], NOW - timedelta(hours=23), NOW, 10)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["hotspotDirections"], ["robotics"])
        self.assertEqual(posts[0]["hotspotMatches"][0]["matchedTerms"], ["robot", "robotics", "humanoid"])

        summary = build_hotspot_summary(
            [{"id": "robotics", "label": "机器人领域突破", "postMatchAny": hotspot["hotspotPostMatchAny"]}],
            [hotspot],
            posts,
            dropped,
        )
        self.assertEqual(summary["selectedPosts"], 1)
        self.assertEqual(summary["selectedPostsByDirection"], {"robotics": 1})

    def test_hotspot_post_outside_its_direction_is_dropped(self):
        hotspot = {
            "source": "x-hotspot-search",
            "hotspotDirection": "machine_consciousness",
            "hotspotDirectionLabel": "AI 意识研究",
            "hotspotPostMatchAny": ["consciousness"],
            "tweets": [raw_post("robot-2", "Our robotics model completed a humanoid manipulation benchmark.")],
        }
        posts, dropped = normalize_posts([hotspot], [EXPERT], NOW - timedelta(hours=23), NOW, 10)
        self.assertEqual(posts, [])
        self.assertEqual(dropped["hotspotDirectionMismatch:machine_consciousness"], 1)

    def test_lifestyle_team_onsite_is_not_promoted_by_one_agent_keyword(self):
        hotspot = {
            "source": "x-hotspot-search",
            "hotspotDirection": "agents",
            "hotspotDirectionLabel": "Agent 技术突破",
            "hotspotPostMatchAny": ["agent"],
            "tweets": [raw_post(
                "team-onsite",
                "The team flew into SF for a week onsite. Locked in our roadmap for AI agent document infra, then played Topgolf and soccer.",
            )],
        }
        posts, dropped = normalize_posts([hotspot], [EXPERT], NOW - timedelta(hours=23), NOW, 10)
        self.assertEqual(posts, [])
        self.assertEqual(dropped["nonTechnical"], 1)

    def test_cultural_ai_playlist_is_not_promoted_by_a_broad_ai_keyword(self):
        post = raw_post(
            "airport-ai-playlist",
            "Honolulu airport has started playing AI-generated island-themed songs on rotation.",
        )
        posts, dropped = normalize_posts([{"source": "search", "tweets": [post]}], [EXPERT], NOW - timedelta(hours=23), NOW, 10)
        self.assertEqual(posts, [])
        self.assertEqual(dropped["nonTechnical"], 1)

    def test_show_shoot_promo_is_not_lifted_by_quoted_ai_topic_list(self):
        post = raw_post(
            "show-promo",
            "i've been waiting to launch this show for almost a year! "
            "some behind the scenes from the shoot of our latest show!!",
        )
        post["quotedTweet"] = raw_post(
            "episode-description",
            "Our new show discusses agents, decision models, context management, "
            "coding benchmarks and prompt injection.",
        )
        posts, dropped = normalize_posts(
            [{"source": "search", "tweets": [post]}], [EXPERT], NOW - timedelta(hours=23), NOW, 10
        )
        self.assertEqual(posts, [])
        self.assertEqual(dropped["nonTechnical"], 1)

    def test_semantic_editorial_review_is_enabled_by_default(self):
        with patch.object(sys, "argv", ["fetch_ai_v_radar.py"]):
            self.assertTrue(parse_args().editorial_ai)



def headline_post(post_id: str, handle: str, score: int, text: str) -> dict:
    return {
        "id": post_id,
        "text": text,
        "expert": {"handle": handle, "name": handle, "priority": "P0", "domain": "AI", "role": "AI"},
        "author": {"username": handle},
        "topStoryEligible": True,
        "topStoryScore": score,
        "signalScore": score,
        "createdAtIso": NOW.isoformat(),
    }


class HeadlineEventDedupeTest(unittest.TestCase):

    def test_october_27_primary_methods_and_milestone_are_substantive(self):
        expert = Expert("P0", "AI research", "Researcher", "Researcher", "test", "researcher")
        sources = [
            "Pushing the boundaries: training a 100B+ parameter model from scratch in just 3.5 months for under $10 million, while achieving lower cross-entropy than DeepSeek-V4-Pro and GLM 5.3!",
            "You can pick the duck up, carry it 1.5m, put it down, and it relocalizes within 2cm using a 64-pixel depth sensor and leg odometry, all running onboard.",
            "MemoryTax: 花 $25.88 先建一套 Memory，结果还不如 $17.84 直接把完整历史交给模型。More Memory, Worse Agents：错误一旦被总结成 Skill，下次 agent 会更自信地再犯一遍。",
        ]
        for source in sources:
            with self.subTest(source=source[:30]):
                self.assertTrue(has_substantive_primary_top_story_evidence({"text": source}, expert))
        self.assertFalse(has_substantive_primary_top_story_evidence(
            {"text": "This is pretty wild. Watch this", "quotedTweet": {"text": sources[0]}}, expert
        ))

    def test_october_27_weekly_resource_roundup_is_not_a_headline(self):
        self.assertTrue(is_retrospective_method_commentary({"text": (
            "⑥ 学习资源：密歇根 EECS 498-016 让学生造 Coding Agent。"
            "这周的主线其实就一个：模型变强以后，该拆掉什么。"
        )}))
        self.assertFalse(is_retrospective_method_commentary({
            "text": "今天发布了新的 Coding Agent，包含独立的 sandbox 和 Eval。"
        }))

    def test_spatial_perturbation_and_action_free_value_research_are_primary_evidence(self):
        expert = Expert("P0", "AI research", "Researcher", "Researcher", "test", "researcher")
        concert = {
            "text": (
                "CONCERT predicts how the response to a gene knockout depends on where it occurs in a tumor. "
                "Spatial transcriptomics measures gene expression across the tissue. "
                "It outperforms five baselines."
            )
        }
        value_classifier = {
            "text": (
                "Generative value classifiers are a new parametrization of Q-functions "
                "that don't require action conditioning. We think these may combine "
                "with large, pre-trained policies and learn from a richer output signal."
            )
        }
        self.assertTrue(has_substantive_primary_top_story_evidence(concert, expert))
        self.assertTrue(has_substantive_primary_top_story_evidence(value_classifier, expert))
        self.assertFalse(has_substantive_primary_top_story_evidence(
            {"text": "Interesting work!", "quotedTweet": concert}, expert
        ))

    def test_prior_anthropic_method_recap_is_not_a_new_headline_event(self):
        recap = {
            "text": (
                "补充一点：合并 Subagent 最大的风险是在评测时候，分数没掉，"
                "而在某个任务悄悄挂了。合并前后怎么用 Eval 抓这种回退，"
                "我之前拆过 Anthropic 那篇，做 Agent 工程的可以一起收藏。"
            )
        }
        self.assertTrue(is_retrospective_method_commentary(recap))

    def test_inference_router_base_url_compatibility_is_primary_evidence(self):
        expert = Expert("P0", "AI", "Richard Socher", "CEO", "test", "RichardSocher")
        post = {
            "text": "Leading models from @deepseek_ai, @Kimi_Moonshot, @Zai_org, @Alibaba_Qwen, @MiniMax__AI, @AIatMeta, and more, including Kimi K3, GLM 5.3, and Qwen3.8 Flash.\n\nSwitching is one line of code: change your base URL, and your existing OpenAI-compatible code runs on Inference Router."
        }
        self.assertTrue(has_substantive_primary_top_story_evidence(post, expert))
        self.assertFalse(has_substantive_primary_top_story_evidence({
            "text": "Great to see this!", "quotedTweet": post,
        }, expert))

    def test_graphify_computer_primary_describes_concrete_codebase_use(self):
        expert = Expert("P0", "AI search", "Aravind Srinivas", "Perplexity CEO", "test", "AravSrinivas")
        post = {
            "id": "2113029257886847264",
            "text": "/graphify now on Computer. We're giving every user 5,000 credits to try this skill that lets you visualize a codebase.",
            "quotedTweet": {"text": "The Graphify skill is now in Computer's skills marketplace."},
        }
        self.assertTrue(has_substantive_primary_top_story_evidence(post, expert))
        self.assertFalse(has_substantive_primary_top_story_evidence(
            {"text": "Nice launch!", "quotedTweet": post["quotedTweet"]}, expert
        ))

    def test_population_funnel_commentary_cannot_displace_a_technical_event(self):
        expert = {"handle": "karpathy", "name": "Karpathy", "priority": "P0", "domain": "AI", "role": "Researcher", "why": "test"}
        commentary = {
            "id": "2109361546505966046",
            "text": (
                "Dusting off this tweet from April because this gap in shared understanding "
                "of LLM capability is widening. Napkin math somewhere around 6B people "
                "(~75% of the population) have barely come in contact with LLMs. "
                "The funnel is driven by ambition and access; agents can finish coding projects."
            ),
            "expert": expert,
            "author": {"username": "karpathy"},
            "signalScore": 95,
            "editorial": {"dailyGrade": "B", "technicalRelevant": True},
        }
        technical = {
            "id": "agent-stack",
            "text": (
                "Managed deepagents use durable LangGraph workflows, LangSmith Sandboxes "
                "for computer use, a memory and skills hub, schedules, evals, and observability."
            ),
            "expert": {**expert, "handle": "hwchase17", "name": "Harrison Chase"},
            "author": {"username": "hwchase17"},
            "signalScore": 70,
            "editorial": {"dailyGrade": "B", "technicalRelevant": True},
        }
        self.assertTrue(has_substantive_primary_top_story_evidence(commentary, Expert(**expert)))
        self.assertTrue(is_population_adoption_commentary(commentary))
        self.assertFalse(is_population_adoption_commentary(technical))
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": json.dumps({"topStories": [{"id": "2109361546505966046", "category": "AI 技术进步"}, {"id": "agent-stack", "category": "AI 技术应用"}]}),
            "stderr": "",
        })()
        with patch("scripts.fetch_ai_v_radar.subprocess.run", return_value=completed):
            selected = select_editorial_top_stories([commentary, technical], retries=0)
        self.assertEqual([post["id"] for post in selected], ["agent-stack"])
        self.assertEqual(commentary["headlineDecision"]["reason"], "population_adoption_commentary")

    def test_old_bitter_lesson_talk_is_not_a_new_headline_event(self):
        retrospective = {
            "text": (
                "I'm glad this talk I gave 2.5 years ago is still relevant. "
                "The Bitter Lesson has become more popular; my practical interpretation "
                "is to add structure now and remove it when conditions change."
            )
        }
        self.assertTrue(is_retrospective_method_commentary(retrospective))
        self.assertFalse(is_retrospective_method_commentary({
            "text": "We shipped LangSmith Sandboxes for agent computer use today."
        }))

    def test_evaluation_classifier_validation_is_substantive_primary_evidence(self):
        post = {
            "id": "eval-classifier",
            "text": (
                "Q: Can I use Jev for evals?\n\n"
                "A: Jev and an LLM judge are both classifiers that you should "
                "validate against trusted labels."
            ),
            "expert": {"handle": "hamel", "name": "Hamel", "priority": "P0", "domain": "AI", "role": "Researcher", "why": "test"},
            "author": {"username": "hamel"},
            "signalScore": 70,
            "editorial": {"dailyGrade": "B", "technicalRelevant": True},
        }
        self.assertTrue(has_substantive_primary_top_story_evidence(post, Expert(**post["expert"])))
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": json.dumps({"topStories": [{"id": "eval-classifier", "category": "AI 技术应用"}]}),
            "stderr": "",
        })()
        with patch("scripts.fetch_ai_v_radar.subprocess.run", return_value=completed):
            selected = select_editorial_top_stories([post], retries=0)
        self.assertEqual([item["id"] for item in selected], ["eval-classifier"])

    def test_jev_typed_answers_on_every_trace_are_primary_evidence(self):
        expert = Expert("P0", "AI", "Test", "Researcher", "test", "tester")
        post = {
            "id": "2108453917277254058",
            "text": (
                "trajectory labeling is really several questions, not one pass/fail - nice framing here\n\n"
                "that's how Jev as a judge works in LangSmith evals: difficulty and correctness "
                "each get their own typed answer, in one pass, on every trace"
            ),
        }
        self.assertTrue(has_substantive_primary_top_story_evidence(post, expert))
        reaction = {
            "text": "nice framing here",
            "quotedTweet": {"text": post["text"]},
        }
        self.assertFalse(has_substantive_primary_top_story_evidence(reaction, expert))

    def test_sensitive_eval_data_and_subagent_orchestration_are_substantive_primary_evidence(self):
        expert = Expert("P0", "AI", "Test", "Researcher", "test", "tester")
        sensitive_evals = {
            "id": "sensitive-evals",
            "text": (
                "Q: How can I do AI evals when traces contain sensitive data? "
                "A: Four approaches: negotiate access to a defined scope, work "
                "with authorized experts, redaction and synthetic data."
            ),
        }
        subagent_orchestration = {
            "id": "subagent-orchestration",
            "text": (
                "In deepagents you give each subagent its own model, tools, and "
                "permissions - the main loop picks which to spawn and when."
            ),
        }
        self.assertTrue(has_substantive_primary_top_story_evidence(sensitive_evals, expert))
        self.assertTrue(has_substantive_primary_top_story_evidence(subagent_orchestration, expert))

    def test_regression_to_pr_agent_repair_is_substantive_primary_evidence(self):
        expert = Expert("P0", "AI", "Test", "Researcher", "test", "tester")
        post = {
            "id": "regression-repair",
            "text": (
                "When Rollouts catches a regression, it finds the offending PR and "
                "opens an issue. One click starts a cloud agent to fix it."
            ),
        }
        self.assertTrue(has_substantive_primary_top_story_evidence(post, expert))

    def test_local_moe_runtime_and_realtime_game_stack_are_substantive_primary_evidence(self):
        expert = Expert("P0", "AI", "Test", "Researcher", "test", "tester")
        local_runtime = {
            "id": "strata-local-runtime",
            "text": (
                "Strata runs Qwen on consumer NVIDIA and AMD GPUs: it keeps frequent "
                "MoE experts on GPU, moves the rest to CPU memory, and combines this "
                "with speculative decoding."
            ),
        }
        realtime_game_stack = {
            "id": "starcraft-agent-stack",
            "text": (
                "Computer assembled an OpenBW runtime on a VPS, a C++ bridge, and "
                "four gameplay tools per agent. Each agent receives its own "
                "fog-of-war-limited game state."
            ),
        }
        self.assertTrue(has_substantive_primary_top_story_evidence(local_runtime, expert))
        self.assertTrue(has_substantive_primary_top_story_evidence(realtime_game_stack, expert))

    def test_held_out_human_label_check_and_isolated_tool_vm_are_substantive_primary_evidence(self):
        expert = Expert("P0", "AI", "Test", "Researcher", "test", "tester")
        judge_validation = {
            "id": "judge-held-out-validation",
            "text": (
                "Can I use the same model for the main task and evaluation? "
                "Test whether the judge agrees with human labels on a held-out test set."
            ),
        }
        cloud_sandbox = {
            "id": "cloud-tool-vm",
            "text": (
                "模型和 VM 都搬到云端，每个任务有独立 Sandbox。Agent 通过桌面 App "
                "访问本地资源。"
            ),
        }
        self.assertTrue(has_substantive_primary_top_story_evidence(judge_validation, expert))
        self.assertTrue(has_substantive_primary_top_story_evidence(cloud_sandbox, expert))

    def test_chinese_decision_model_and_local_deployment_primary_evidence(self):
        expert = Expert("P0", "AI", "Test", "Researcher", "test", "tester")
        decision_model = {
            "id": "2108774523659264295",
            "text": (
                "微软发布了 Microsoft-Decision-1。这是一个专门做选择题的决策模型，"
                "用 Qwen3.5-9B 后训练而来，能快速给多个选项打分并做出选择。"
                "它在结构化决策任务上，延迟和质量都超过了大语言模型和其他决策模型。"
                "它已经上线 Microsoft Foundry。"
            ),
        }
        local_deployment = {
            "id": "2108772007177551980",
            "text": (
                "欧洲本地平台开始托管 Qwen、GLM 和 Kimi 给欧洲企业用。"
                "Ecosia 换到欧洲平台 Melious 托管的开源权重模型。"
                "换完之后，成本大约砍了一半，质量和性能反而更好。"
                "数据仍然留在欧洲，谁能真的被欧洲企业部署进生产环境更值得看。"
            ),
        }
        reaction = {"id": "quote-only-reaction", "text": "有意思，现在大厂开始集体做这类模型了！"}
        self.assertTrue(has_substantive_primary_top_story_evidence(decision_model, expert))
        self.assertTrue(has_substantive_primary_top_story_evidence(local_deployment, expert))
        self.assertFalse(has_substantive_primary_top_story_evidence(reaction, expert))

    def test_gemini_rollout_and_video_to_robot_simulation_are_primary_evidence(self):
        expert = Expert("P0", "AI", "Test", "Researcher", "test", "tester")
        model_rollout = {
            "id": "2110041008100843835",
            "text": (
                "Gemini 4 Argon is amazing for knowledge work and coding. "
                "Argon's physics understanding & 3D modelling capabilities. "
                "Argon is rolling out today to Google Ultra and Pro subscribers in the GeminiApp and Search."
            ),
        }
        robot_simulation = {
            "id": "2110078384617464201",
            "text": (
                "Gemini 4 Argon taught a robot to play cornhole just by watching a video. "
                "It mapped the physics, coded its own simulation, and taught Apollo humanoid to sink 7 throws in a row."
            ),
        }
        reaction = {"id": "quote-reaction", "text": "Cool robot demo!", "quotedTweet": robot_simulation}
        self.assertTrue(has_substantive_primary_top_story_evidence(model_rollout, expert))
        self.assertTrue(has_substantive_primary_top_story_evidence(robot_simulation, expert))
        self.assertFalse(has_substantive_primary_top_story_evidence(reaction, expert))

    def test_arc_agi_comparison_and_concrete_workflows_are_primary_evidence(self):
        expert = Expert("P0", "AI", "Test", "Researcher", "test", "tester")
        primaries = (
            "Argon has a similar performance profile on ARC-AGI-3 as Astra. Google is back at the frontier.",
            "Gakku is an AI mentoring app for K-12 students. The voice chat coach guides students through 10 min essay writing missions that cover brainstorming, drafting, and revising.",
            "i started with setting up process where I had it analyze all of my internal meeting notes to draft out how to organize everything, and then I had it go through my notes again to start extracting and pulling the key decisions, facts, orgs, processes. I then go through and approve stuff which gets locked in as facts. I’m just doing this with codex/claude code via chat. ongoing, it’s instructed to both use the firmOS as context and to write back in things that belong there",
        )
        for primary in primaries:
            with self.subTest(primary=primary[:35]):
                self.assertTrue(has_substantive_primary_top_story_evidence({"text": primary}, expert))
        reaction = {"text": "Google is back!", "quotedTweet": {"text": primaries[0]}}
        self.assertFalse(has_substantive_primary_top_story_evidence(reaction, expert))

    def test_deepseek_benchmark_delta_and_token_efficiency_are_primary_evidence(self):
        expert = Expert("P0", "AI", "Test", "Researcher", "test", "tester")
        primary = (
            "DeepSeek calling this a minor update while moving Terminal-Bench 4.0 "
            "from 31.2 to 42.3. Reports 77.0 on DeepSWE (vs 74.0 for Opus 5 "
            "and 73.0 for GPT-5.6 Sol). Faster task completion with shorter "
            "outputs, using fewer tokens, with MIT-licensed weights."
        )
        self.assertTrue(has_substantive_primary_top_story_evidence({"text": primary}, expert))
        self.assertFalse(has_substantive_primary_top_story_evidence({
            "text": "These numbers are funny!",
            "quotedTweet": {"text": primary},
        }, expert))

    def test_game_agent_post_training_and_sandbox_integration_are_primary_evidence(self):
        expert = Expert("P0", "AI", "Test", "Researcher", "test", "tester")
        primaries = (
            "Then it built all of it with ElevenLabs, mostly on its own: it wrote the islands and the story, cast 35 voices for 638 lines, generated 16 rigged 3D characters, the music and the sound, and tested everything by playing the game itself. ~15k lines of code.",
            "Asking it to play the game fully was too hard for now, given the state of computer use, but I tried asking it to write the whole script and then do some theory of mind reading of what the player would understand from it.",
            "We now have a platform for SFT & RL. This is why open weight models are great",
            "Perplexity’s open source sandbox platform SPACE will become part of Crusoe’s Managed AI products.",
        )
        for primary in primaries:
            with self.subTest(primary=primary[:35]):
                self.assertTrue(has_substantive_primary_top_story_evidence({"text": primary}, expert))
        self.assertFalse(has_substantive_primary_top_story_evidence({
            "text": "love to see this integration",
            "quotedTweet": {"text": primaries[-1]},
        }, expert))

    def test_laser_aside_quoting_selected_gemini_announcement_is_redundant(self):
        direct = {
            "id": "2110041008100843835",
            "text": "Gemini 4 Argon is rolling out today to Google Ultra and Pro subscribers.",
        }
        aside = {
            "id": "2110052931110318464",
            "text": "I love lasers (really wanted to work on them as a kid)… especially Argon lasers 😀",
            "quotedTweet": direct,
        }
        self.assertTrue(is_redundant_nontechnical_wrapper(aside, {direct["id"], aside["id"]}))
        self.assertFalse(is_redundant_nontechnical_wrapper(aside, {aside["id"]}))

    def test_event_dedupe_ignores_generic_ai_vocabulary(self):
        long_efficiency_thread = {
            "text": (
                "Current AI agents can improve, but benchmark performance still has a large cost and efficiency gap. "
                "People often discuss how models work, which methods are better, and what the next frontier will be."
            )
        }
        data_agent_benchmark = {
            "text": "Our data-agent benchmark spans 12 SQL datasets and exposes failure modes in multi-database queries."
        }
        same_ocr_event = {
            "text": "LlamaParse documents a just-in-time OCR pipeline with LiteParse for fast first-pass parsing."
        }
        ocr_followup = {
            "text": "Just-in-time OCR with LlamaParse and LiteParse reduces unnecessary document parsing work."
        }

        self.assertFalse(same_top_story_event(long_efficiency_thread, data_agent_benchmark))
        self.assertTrue(same_top_story_event(same_ocr_event, ocr_followup))

    def test_document_benchmark_model_mention_does_not_merge_health_research(self):
        document_benchmark = {"text": (
            "We use ParseBench to track the advancement of recent frontier/open-weight models "
            "(most recently, Gemini 4 Argon and Muse Spark/Wonder) for document parsing."
        )}
        health_research = {"text": "10 new papers in health science research, all written with Muse models in under 4 weeks.",
                           "quotedTweet": {"text": "A human-led research scaffold powered by Muse Spark 1.3 and Muse Wonder uses 5M de-identified health records."}}
        self.assertFalse(same_top_story_event(document_benchmark, health_research))

    def test_concrete_tpu_sandbox_and_porting_primaries_qualify(self):
        examples = (
            "TPUs have different bottlenecks from GPUs: few cores, large VMEM so easier to fuse kernels, but vector units have lower throughput.",
            "Our sandbox platform serving daily traffic handles millions of executions with a low error rate while using multiple machines to lower serving costs.",
            "Computer downloaded the binary in its cloud sandbox, decompiled it with headless Ghidra, and ported it to a native Rust app for Linux.",
        )
        for text in examples:
            with self.subTest(text=text[:30]):
                self.assertTrue(has_substantive_primary_top_story_evidence({"text": text}, EXPERT))

    def test_binding_game_control_and_local_model_results_are_primary_evidence(self):
        primaries = (
            "Claude designed scorpion anti-venoms. Out of 211 designs tested, 17 show signs of life by binding. This is promising but a lot of additional testing will be needed to show they actually work in humans.",
            "In addition to human-vs-in-game-AI and human-vs-human it supports two LLMs playing against each other! That works by pausing the game every 5s for them to think about the game state and queue up commands",
            "Perplexity Decider pareto-optimal on Financial ClaimBench of Vals AI",
            "You can now run Perplexity Computer fully local on your Mac with no cloud based inference, without WiFi too.",
        )
        for primary in primaries:
            with self.subTest(primary=primary[:40]):
                self.assertTrue(has_substantive_primary_top_story_evidence({"text": primary}, EXPERT))
        self.assertFalse(has_substantive_primary_top_story_evidence({
            "text": "Tanishq never ceases to impress me. Amazing work",
            "quotedTweet": {"text": primaries[0]},
        }, EXPERT))

    def test_agent_red_team_and_model_effort_control_are_primary_evidence(self):
        primaries = (
            "Last month a large team of agents used over 100 billion tokens to resolve the Navier-Stokes Millennium Prize problem. Now we're using a similar approach for red-teaming to find and fix infra vulnerabilities.",
            "We're letting admins have a lot more control over how people get to tokenmax internally by being able to set a floor and a ceiling on the Effort level (which correlates to capability and cost).",
        )
        for primary in primaries:
            with self.subTest(primary=primary[:40]):
                self.assertTrue(has_substantive_primary_top_story_evidence({"text": primary}, EXPERT))
        self.assertFalse(has_substantive_primary_top_story_evidence({
            "text": "Pretty solid pelican",
            "quotedTweet": {"text": primaries[0]},
        }, EXPERT))

    def test_shared_two_word_model_name_is_not_split_into_two_headlines(self):
        announcement = headline_post(
            "muse-release", "alexandr_wang", 100,
            "We are releasing Muse Glimmer, a 30B agentic model with open weights under Apache 2.0.",
        )
        implementation = headline_post(
            "muse-implementation", "AIatMeta", 98,
            "To run Muse Glimmer locally, quantization shrinks the model and DFlash accelerates token generation.",
        )
        independent = headline_post(
            "cyber", "gdb", 99,
            "OpenAI releases GPT-5.6-Cyber to expand Daybreak for authorized cyber defense work.",
        )
        third_event = headline_post(
            "reasoning", "jeff", 97,
            "Gemini reasoning model reaches a new benchmark with faster inference.",
        )
        selected = select_diverse_top_stories([announcement, implementation, independent, third_event])
        self.assertEqual([post["id"] for post in selected], ["muse-release", "cyber", "reasoning"])

    def test_same_event_from_different_authors_does_not_take_two_headlines(self):
        repeated_event_a = headline_post(
            "a", "gdb", 99,
            "OpenAI cyber-capable models compromised HuggingFace production in a security incident during benchmark evaluation with zero-day vulnerabilities.",
        )
        repeated_event_b = headline_post(
            "b", "thom_wolf", 98,
            "HuggingFace describes the security incident: OpenAI cyber models compromised production during benchmark evaluation through zero-day vulnerabilities.",
        )
        independent_c = headline_post("c", "jeff", 90, "Gemini reasoning model sets a new benchmark with faster inference.")
        independent_d = headline_post("d", "arav", 89, "An agent deployment improved production search workflows.")
        selected = select_diverse_top_stories([repeated_event_a, repeated_event_b, independent_c, independent_d])
        self.assertEqual([post["id"] for post in selected], ["a", "c", "d"])

    def test_final_selection_keeps_no_more_than_three_posts_per_author(self):
        posts = [
            headline_post("a", "same", 99, "A model made a benchmark improvement."),
            headline_post("b", "same", 98, "An agent made a production improvement."),
            headline_post("c", "same", 97, "A reasoning model made an evaluation improvement."),
            headline_post("d", "same", 96, "A robotics model made a benchmark improvement."),
            headline_post("e", "other", 95, "A coding model made a benchmark improvement."),
        ]
        retained, capped = cap_selected_posts_per_author(posts)
        self.assertEqual([post["id"] for post in retained], ["a", "b", "c", "e"])
        self.assertEqual(capped, 1)

    def test_non_core_b_story_can_complete_three_qualified_headlines(self):
        def editorial_post(post_id: str, handle: str, grade: str, text: str) -> dict:
            return {
                "id": post_id,
                "text": text,
                "expert": {"handle": handle, "name": handle, "priority": "P0", "domain": "Independent Lab", "role": "Researcher", "why": "test"},
                "author": {"username": handle},
                "signalScore": 70,
                "editorial": {"dailyGrade": grade, "technicalRelevant": True},
            }

        posts = [
            editorial_post("gdb", "gdb", "A", "OpenAI released a model with benchmark inference performance improvements."),
            editorial_post("qm", "xudong", "A", "YC released an open-source multi-agent workflow system for production use."),
            editorial_post("arc", "fchollet", "B", "Base LLM benchmark results show test-time inference improves reasoning performance."),
        ]
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": json.dumps({"topStories": [
                {"id": "gdb", "category": "AI 技术进步", "rationale": "模型结果"},
                {"id": "qm", "category": "AI 技术应用", "rationale": "Agent系统"},
            ]}),
            "stderr": "",
        })()
        with patch("scripts.fetch_ai_v_radar.subprocess.run", return_value=completed):
            selected = select_editorial_top_stories(posts, retries=0)

        self.assertEqual([post["id"] for post in selected], ["gdb", "qm", "arc"])
        self.assertIn(posts[2]["topStoryCategory"], {"AI 技术进步", "AI 技术前沿", "AI 技术应用"})

    def test_concrete_evidence_displaces_a_generic_roundup_when_three_strong_candidates_exist(self):
        def editorial_post(post_id: str, handle: str, text: str) -> dict:
            return {
                "id": post_id,
                "text": text,
                "expert": {"handle": handle, "name": handle, "priority": "P0", "domain": "AI", "role": "Researcher", "why": "test"},
                "author": {"username": handle},
                "signalScore": 70,
                "editorial": {"dailyGrade": "A", "technicalRelevant": True},
            }

        posts = [
            editorial_post("roundup", "openai", "July for OpenAI Developers"),
            editorial_post("bench", "ion", "AI agent failure taxonomy boosts SWE-bench to 70.7% and TerminalBench to 89.9%."),
            editorial_post("tools", "simon", "LLM CLI adds reasoning traces, Responses API, server-side tools, and smarter logging."),
            editorial_post("safety", "anthropic", "Cybersecurity evaluation removes safeguards and studies reasoning transcripts."),
        ]
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": json.dumps({"topStories": [
                {"id": "roundup", "category": "AI 技术进步", "rationale": "月度更新"},
                {"id": "bench", "category": "AI 技术进步", "rationale": "量化评测"},
                {"id": "tools", "category": "AI 技术应用", "rationale": "工程接口"},
            ]}),
            "stderr": "",
        })()
        with patch("scripts.fetch_ai_v_radar.subprocess.run", return_value=completed):
            selected = select_editorial_top_stories(posts, retries=0)

        self.assertEqual([post["id"] for post in selected], ["bench", "tools", "safety"])

    def test_quote_only_reaction_cannot_be_a_poster_lead(self):
        def editorial_post(post_id: str, handle: str, text: str, quote=None) -> dict:
            post = {
                "id": post_id,
                "text": text,
                "expert": {"handle": handle, "name": handle, "priority": "P0", "domain": "AI", "role": "Researcher", "why": "test"},
                "author": {"username": handle},
                "signalScore": 70,
                "editorial": {"dailyGrade": "A", "technicalRelevant": True},
            }
            if quote:
                post["quotedTweet"] = {"text": quote}
            return post

        posts = [
            editorial_post("reaction", "alex", "gemini who?", "A new model improves agent benchmarks by 20% with faster inference."),
            editorial_post("local", "arav", "We open-sourced a local inference engine for Apple Silicon model serving."),
            editorial_post("cyber", "deepmind", "Our cyber model produced 2.6 times more valid fixes in real codebase testing."),
            editorial_post("agents", "cursor", "Cloud agents now run on autoscaling customer infrastructure with internal-service access."),
        ]
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": json.dumps({"topStories": [
                {"id": "reaction", "category": "AI 技术进步", "rationale": "引用模型结果"},
                {"id": "local", "category": "AI 技术前沿", "rationale": "本地推理"},
                {"id": "cyber", "category": "AI 技术进步", "rationale": "修复效果"},
            ]}),
            "stderr": "",
        })()
        with patch("scripts.fetch_ai_v_radar.subprocess.run", return_value=completed):
            selected = select_editorial_top_stories(posts, retries=0)

        self.assertNotIn("reaction", [post["id"] for post in selected])

    def test_greg_priority_replacement_accepts_full_candidate_profile(self):
        def editorial_post(post_id: str, handle: str, text: str) -> dict:
            return {
                "id": post_id,
                "text": text,
                "expert": {"handle": handle, "name": handle, "priority": "P0", "domain": "AI", "role": "Researcher", "why": "test"},
                "author": {"username": handle},
                "signalScore": 70,
                "editorial": {"dailyGrade": "A", "technicalRelevant": True},
            }

        posts = [
            editorial_post("gdb", "gdb", "OpenAI reports a new model evaluation with measurable inference improvements."),
            editorial_post("jerry", "jerryjliu0", "An agent framework now supports production workflow tracing and tool routing."),
            editorial_post("research", "fchollet", "A reasoning benchmark publishes a new evaluation method and result."),
            editorial_post("robot", "robotlab", "A robotics system improves manipulation accuracy on a controlled benchmark."),
        ]
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": json.dumps({"topStories": [
                {"id": "jerry", "category": "AI 技术应用", "rationale": "生产系统"},
                {"id": "research", "category": "AI 技术前沿", "rationale": "评测方法"},
                {"id": "robot", "category": "AI 技术进步", "rationale": "机器人结果"},
            ]}),
            "stderr": "",
        })()
        with patch("scripts.fetch_ai_v_radar.subprocess.run", return_value=completed):
            selected = select_editorial_top_stories(posts, retries=0)

        self.assertIn("gdb", [post["id"] for post in selected])
        self.assertNotIn("jerry", [post["id"] for post in selected])


if __name__ == "__main__":
    unittest.main()
