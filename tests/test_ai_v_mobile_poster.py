import copy
import unittest
from scripts.select_ai_v_mobile_poster import validate_selection, selection_fingerprint

class MobilePosterTests(unittest.TestCase):
    def setUp(self):
        self.data={'posts':[{'id':str(i),'text':'Method '+str(i),'expert':{'handle':'author'+str(i)},'editorial':{'channel':'agent'}} for i in range(5)],'finalQuality':{'decisions':[{'id':str(i),'selected':True,'score':85} for i in range(5)]}}
        self.selection={'stories':[{'id':str(i),'event':'event'+str(i),'category':'engineering','reason':'concrete source evidence','title':'Grounded title','summary':'Concrete method and limitations'} for i in (3,1,4)]}
    def test_poster_does_not_have_to_follow_detail_order(self):
        self.assertEqual([r['id'] for r in validate_selection(self.data,self.selection)],['3','1','4'])
    def test_duplicate_authors_block(self):
        self.data['posts'][3]['expert']['handle']='author1'
        with self.assertRaises(ValueError):validate_selection(self.data,self.selection)
    def test_duplicate_events_block(self):
        self.selection['stories'][1]['event']=self.selection['stories'][0]['event']
        with self.assertRaises(ValueError):validate_selection(self.data,self.selection)
    def test_unselected_source_blocks(self):
        self.data['finalQuality']['decisions'][3]['selected']=False
        with self.assertRaises(ValueError):validate_selection(self.data,self.selection)
    def test_source_change_invalidates_fingerprint(self):
        old=selection_fingerprint(self.data['posts']);self.data['posts'][0]['text']='Changed'
        self.assertNotEqual(old,selection_fingerprint(self.data['posts']))
    def test_long_quote_cannot_fill_poster(self):
        self.selection['stories'][0]['summary']='x'*111
        with self.assertRaises(ValueError):validate_selection(self.data,self.selection)

if __name__=='__main__':unittest.main()
