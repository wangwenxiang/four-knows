import json
import unittest
from pathlib import Path

from scripts.fetch_ai_v_radar import (
    DEFAULT_AVATAR_CACHE,
    DEFAULT_EXPANSION_WATCHLIST,
    DEFAULT_HOTSPOT_QUERIES,
    Expert,
    append_expansion_experts,
    load_experts,
    load_hotspot_searches,
    parse_args,
)


ROOT = Path(__file__).resolve().parents[1]


class ExpansionWatchlistTest(unittest.TestCase):
    def test_expansion_watchlist_is_capped_and_unique(self):
        payload = json.loads((ROOT / "config" / "ai_x_expansion_watchlist.json").read_text())
        accounts = payload["accounts"]
        handles = [account["handle"].casefold() for account in accounts]
        self.assertEqual(payload["maxAccounts"], 7)
        self.assertFalse(payload["autoExpand"])
        self.assertEqual(len(accounts), 7)
        self.assertEqual(len(handles), len(set(handles)))

    def test_expansion_can_be_appended_without_changing_default_watchlist(self):
        base = [Expert("P0", "AI", "Base", "", "", "base")]
        combined = append_expansion_experts(base, ROOT / "config" / "ai_x_expansion_watchlist.json")
        self.assertEqual(len(base), 1)
        self.assertEqual(len(combined), 8)
        self.assertEqual(combined[-1].handle, "marinkazitnik")

    def test_hotspot_search_has_exactly_five_x_directions(self):
        directions, experts = load_hotspot_searches(ROOT / "config" / "ai_x_hotspot_queries.json")
        self.assertEqual(len(directions), 5)
        self.assertEqual(
            {direction["id"] for direction in directions},
            {"foundation_models", "agents", "robotics", "life_sciences", "machine_consciousness"},
        )
        self.assertTrue(all(direction.get("postMatchAny") for direction in directions))
        self.assertTrue(experts)
        self.assertEqual(len({expert.handle.casefold() for expert in experts}), len(experts))

    def test_production_defaults_include_expansion_and_hotspots(self):
        import sys

        previous_argv = sys.argv
        try:
            sys.argv = ["fetch_ai_v_radar.py"]
            args = parse_args()
        finally:
            sys.argv = previous_argv
        self.assertEqual(args.expansion_watchlist, DEFAULT_EXPANSION_WATCHLIST)
        self.assertEqual(args.hotspot_queries, DEFAULT_HOTSPOT_QUERIES)
        self.assertEqual(args.avatar_cache, DEFAULT_AVATAR_CACHE)

    def test_production_watchlist_has_sixty_two_monitored_accounts(self):
        core = load_experts(ROOT / "ai_key_people_watchlist_visual.html")
        combined = append_expansion_experts(core, DEFAULT_EXPANSION_WATCHLIST)
        self.assertEqual(len(core), 55)
        self.assertEqual(len(combined), 62)
        self.assertEqual(len({expert.handle.casefold() for expert in combined}), 62)

    def test_greg_brockman_has_higher_watchlist_weight_than_jerry_liu(self):
        experts = {expert.handle.casefold(): expert for expert in load_experts(ROOT / "ai_key_people_watchlist_visual.html")}
        self.assertEqual(experts["gdb"].priority, "P0")
        self.assertEqual(experts["jerryjliu0"].priority, "P1")

    def test_xudong_han_is_a_p0_top_five_watchlist_account(self):
        experts = load_experts(ROOT / "ai_key_people_watchlist_visual.html")
        index = {expert.handle.casefold(): position for position, expert in enumerate(experts)}
        self.assertEqual(experts[index["xudong07452910"]].priority, "P0")
        self.assertLess(index["xudong07452910"], 5)


if __name__ == "__main__":
    unittest.main()
