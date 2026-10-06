import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'core'))
from metadata_bridge import normalize,people

class PeopleMetadataTests(unittest.TestCase):
    def test_rich_cast_keeps_provider_photo_and_character(self):
        meta=normalize({'cast':[{'person':{'name':'Bob Odenkirk','profile_path':'/bob.jpg'},'character':'Jimmy McGill'}]},'series','tt1')
        self.assertEqual(meta['cast'],['Bob Odenkirk'])
        rows=people(meta,'cast')
        self.assertEqual(rows[0]['name'],'Bob Odenkirk')
        self.assertEqual(rows[0]['job'],'as Jimmy McGill')
        self.assertEqual(rows[0]['poster'],'https://image.tmdb.org/t/p/w342/bob.jpg')

    def test_crew_merges_jobs_and_prefers_available_photo(self):
        meta=normalize({'director':[{'name':'Vince Gilligan','photo':'https://images.example/vince.jpg'}],
                        'writer':['Vince Gilligan']},'series','tt1')
        rows=people(meta,'crew')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['name'],'Vince Gilligan')
        self.assertEqual(rows[0]['job'],'Director / Writer')
        self.assertEqual(rows[0]['poster'],'https://images.example/vince.jpg')

    def test_name_only_cast_remains_supported_for_cinemeta(self):
        meta=normalize({'cast':['Rhea Seehorn']},'series','tt1')
        self.assertEqual(people(meta,'cast'),[{'name':'Rhea Seehorn','job':'Cast','poster':''}])

if __name__=='__main__':unittest.main()
