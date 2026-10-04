import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
XML=ROOT/'resources/skins/Main/1080i/script-stremio-settings.xml'

class SettingsFocusColumnsTests(unittest.TestCase):
 def setUp(self):self.root=ET.parse(XML).getroot()
 def focused(self,cid):
  control=self.root.find(".//control[@type='list'][@id='%s']"%cid)
  self.assertIsNotNone(control);layout=control.find('focusedlayout');self.assertIsNotNone(layout);return layout
 def test_left_selected_item_is_dim_until_left_column_has_real_focus(self):
  layout=self.focused(100)
  bright=[c for c in layout.findall("control[@type='image']") if c.findtext('visible')=='Control.HasFocus(100)']
  self.assertGreaterEqual(len(bright),2)
  base=[c for c in layout.findall("control[@type='image']") if c.find('visible') is None]
  self.assertTrue(any((c.find('texture').get('colordiffuse') or '').startswith('A0') for c in base))
  labels=[c for c in layout.findall("control[@type='label']") if c.findtext('visible')=='Control.HasFocus(100)']
  self.assertTrue(any(c.findtext('textcolor')=='FFFFFFFF' for c in labels))
 def test_right_selected_item_is_dim_until_right_column_has_real_focus(self):
  layout=self.focused(200)
  bright=[c for c in layout.findall("control[@type='image']") if c.findtext('visible')=='Control.HasFocus(200)']
  self.assertTrue(bright)
  base=[c for c in layout.findall("control[@type='image']") if c.find('visible') is None]
  self.assertTrue(any((c.find('texture').get('colordiffuse') or '').startswith('A0') for c in base))
  labels=[c for c in layout.findall("control[@type='label']") if c.findtext('visible')=='Control.HasFocus(200)']
  self.assertTrue(any(c.findtext('textcolor')=='FFC4ACFF' for c in labels))
 def test_navigation_still_moves_between_columns(self):
  left=self.root.find(".//control[@type='list'][@id='100']")
  right=self.root.find(".//control[@type='list'][@id='200']")
  self.assertEqual(left.findtext('onright'),'200');self.assertEqual(right.findtext('onleft'),'100')

if __name__=='__main__':unittest.main()
