import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import refine_ai_v_mobile as quality


def post(pid,text='具体步骤与对照结果'):
    return {'id':pid,'text':text,'expert':{'handle':'tester'},'editorial':{'channel':'tools'}}


def review(pid,qualified=True,score=85):
    return {'id':pid,'qualified':qualified,'score':score,'event':'独立事件 '+pid,'evidence':'具体步骤','reason':'包含可复用步骤与对照'}


class FinalQualityTests(unittest.TestCase):
    def test_omitted_or_duplicate_review_blocks(self):
        with self.assertRaises(ValueError):
            quality.validate_reviews([post('1'),post('2')],[review('1'),review('1')])

    def test_low_score_cannot_qualify(self):
        with self.assertRaises(ValueError):
            quality.validate_reviews([post('1')],[review('1',True,40)])

    def test_selection_cannot_smuggle_new_id_or_exceed_cap(self):
        for rows in ([{'id':'3','reason':'x'}],[{'id':'1','reason':'x'},{'id':'2','reason':'y'}]):
            with self.assertRaises(ValueError):
                quality.validate_selection(rows,{'1','2'},1)

    def test_all_posts_reviewed_before_global_selection_and_originals_preserved(self):
        posts=[post('1'),post('2'),post('3','只有感叹')]
        original=copy.deepcopy(posts)
        rows=[review('1'),review('2'),review('3',False,20)]
        response={'selected':[{'id':'2','reason':'最佳完整版本'}],'omitted':[{'id':'1','reason':'同事件且信息更少'}]}
        with tempfile.TemporaryDirectory() as folder, patch.object(quality,'review_batch',return_value=rows) as batch, patch.object(quality,'model_json',return_value=response):
            retained,audit=quality.quality_review(posts,Path(folder)/'audit.json',1)
            self.assertEqual(len(batch.call_args.args[0]),3)
            self.assertEqual([p['id'] for p in retained],['2'])
            self.assertEqual(len(audit['decisions']),3)
            self.assertEqual(audit['dropped'],2)
            self.assertEqual(posts,original)

    def test_source_edit_invalidates_audit_fingerprint(self):
        self.assertNotEqual(quality.fingerprint([post('1','旧文')]),quality.fingerprint([post('1','新文')]))


if __name__=='__main__':
    unittest.main()
