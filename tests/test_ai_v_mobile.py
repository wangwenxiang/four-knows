import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from scripts import fetch_ai_v_radar as radar
from scripts.render_ai_v_mobile import render_mobile


class MobileRadarTests(unittest.TestCase):
    def test_semantic_chinese_growth_is_not_rejected_by_old_keyword_gate(self):
        post = {'text': '新站要先做低竞争长尾词，站点权重不足时难排核心词。', 'editorial': {'technicalRelevant': True, 'channel': 'growth', 'evidence': '新站长尾词与权重策略'}}
        with patch.object(radar, 'MOBILE_REPORT', True), patch.object(radar, 'is_radar_post', return_value=False):
            self.assertTrue(radar.passes_editorial_gate(post))
            post['text'] = '我们正在招聘，欢迎加入团队。'
            self.assertFalse(radar.passes_editorial_gate(post))

    def test_exact_reposts_collapse_but_distinct_commentary_survives(self):
        posts = [{'id': str(i), 'expert': {'handle': 'gkxspace'}, 'text': text, 'quotedTweet': {'id': 'quoted'}} for i,text in enumerate(['https://t.co/same','https://t.co/same','补充具体制作流程'])]
        kept, dropped = radar.deduplicate_mobile_reposts(posts)
        self.assertEqual([p['id'] for p in kept], ['0','2'])
        self.assertEqual(dropped[0]['retainedId'], '0')

    def test_chinese_growth_and_enterprise_without_english_keywords(self):
        for text in ('小网站通过少而精的页面获得搜索引擎流量，附转化数据。', '把订单审批、客户回访接成自动化业务流程，记录验收失败的案例。', '分享剪纸动画的制作过程与提示词。'):
            self.assertTrue(radar.is_radar_post({'text': text}))
        self.assertFalse(radar.is_radar_post({'text': '今天吃了一碗面，天气很好。'}))

    def test_full_mode_preserves_more_than_three_posts_by_author(self):
        posts = [{'id': str(i), 'expert': {'handle': 'someone'}} for i in range(8)]
        self.assertEqual(radar.cap_selected_posts_per_author(posts, 0), (posts, 0))

    def test_cursor_is_drained_instead_of_silently_truncated(self):
        result = type('Completed', (), {'returncode': 0, 'stdout': json.dumps({'tweets': [{'id':'2'}], 'nextCursor':None})})()
        with patch.object(radar, 'MOBILE_REPORT', True), patch.object(radar, 'run_bird', return_value=result) as run:
            out = radar.finish_search_pagination({'tweets':[{'id':'1'}], 'nextCursor':'next'}, ['bird','search','query','--json'], 'test')
        self.assertEqual([p['id'] for p in out['tweets']], ['1','2'])
        self.assertEqual(run.call_args.args[0][-2:], ['--cursor','next'])

    def test_render_has_real_data_no_generated_titles_or_sample_labels(self):
        now = datetime(2026,10,27,tzinfo=timezone.utc)
        post = {'id':'1','text':'Full original <script> stays inert','author':{'username':'test','name':'Test'},'expert':{'handle':'test'},'editorial':{'channel':'growth'}}
        page = render_mobile([{}]*122, [post], now, now-timedelta(hours=23))
        self.assertNotIn('条排版样本', page)
        self.assertNotIn('<details', page)
        self.assertNotIn('${esc(r.title)}', page)
        self.assertIn('Full original \\u003cscript>', page)
        self.assertIn('122</strong>人监控', page)
        self.assertIn('font-size:13px;line-height:1.6', page)

    def test_saturated_group_is_split_even_if_cursor_is_absent(self):
        now = datetime(2026,10,27,tzinfo=timezone.utc)
        people = [radar.Expert('P1','AI','One','research','test','one'), radar.Expert('P1','AI','Two','research','test','two')]
        seed = {'ok':True,'tweets':[{'id':str(i)} for i in range(40)]}
        child = [{'ok':True,'tweets':[{'id':'new-one'}]}, {'ok':True,'tweets':[{'id':'new-two'}]}]
        with patch.object(radar, 'fetch_search_batch', side_effect=child) as fetch:
            result = radar.fetch_search_full(people, now-timedelta(hours=23), now, 'test', 5, 0, seed)
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['tweets']),42)
        self.assertEqual(fetch.call_count,2)

    def test_failed_split_prevents_false_complete_status(self):
        now = datetime(2026,10,27,tzinfo=timezone.utc)
        people = [radar.Expert('P1','AI','One','research','test','one')]
        seed = {'ok':True,'tweets':[{'id':str(i)} for i in range(40)]}
        with patch.object(radar, 'fetch_search_batch', return_value={'ok':False,'tweets':[],'error':'rate limited'}):
            result = radar.fetch_search_full(people, now-timedelta(hours=23), now, 'test', 5, 0, seed)
        self.assertFalse(result['ok'])

    def test_same_window_recovery_reuses_only_complete_account_scan(self):
        people = [radar.Expert('P1','AI','One','research','test','one'), radar.Expert('P1','AI','Two','research','test','two')]
        first = {'source':'search', 'ok':True, 'experts':[{'handle':'one'}], 'tweets':[{'id':'1'}]}
        second = {'source':'timeline', 'ok':True, 'experts':[{'handle':'two'}], 'tweets':[{'id':'2'}]}
        hotspot = {'source':'x-hotspot-search', 'ok':False, 'experts':[]}
        self.assertEqual(radar.complete_snapshot_account_results({'results':[first, second, hotspot]}, people), [first, second])
        self.assertIsNone(radar.complete_snapshot_account_results({'results':[first, first, hotspot]}, people))
        self.assertIsNone(radar.complete_snapshot_account_results({'results':[first, dict(second, ok=False)]}, people))


if __name__ == '__main__':
    unittest.main()
