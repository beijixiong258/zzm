"""Regression for observed r5 crop truncation/budget starvation. Not OCR scores."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/material_stage13'))
import ocr_verification as ov


def tilted_line(y,x=.1):
    polygon=[[x,y+.02],[.8,y],[.8,y+.015],[x,y+.035]]
    return {'text':'Retained source line','confidence':.99,'polygon':polygon,'bbox':[x,y,.8,y+.035]}


class RecoveryGeometryTests(unittest.TestCase):
    def test_parallel_skewed_prose_is_not_a_two_column_layout(self):
        lines=[tilted_line(.08+i*.02)for i in range(3)]
        self.assertTrue(ov.linear_layout(lines))

    def test_source_crop_cannot_slice_a_known_neighbour_line(self):
        lines=[tilted_line(.08),tilted_line(.10,.25),tilted_line(.12)]
        tiles=ov.recovery_tiles({'status':'complete','lines':lines},8)
        self.assertTrue(tiles)
        covered=[]
        for t in tiles:
            covered+=t['cpu_line_indices'];a=t['bbox']
            for index,line in enumerate(lines):
                b=line['bbox'];intersects=min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])
                if intersects:
                    self.assertIn(index,t['cpu_line_indices'])
                    self.assertTrue(a[0]<=b[0] and a[1]<=b[1] and a[2]>=b[2] and a[3]>=b[3])
        self.assertEqual(sorted(covered),list(range(len(lines))))

    def test_side_by_side_labels_remain_nonlinear(self):
        lines=[{'text':'TEST','confidence':.99,'bbox':[.1,.1,.3,.2],'polygon':[]},
               {'text':'Students','confidence':.99,'bbox':[.5,.1,.8,.2],'polygon':[]}]
        self.assertFalse(ov.linear_layout(lines))

    def test_right_neighbour_margin_uses_group_right_not_group_left(self):
        lines=[{'text':'Long left line','confidence':.99,'bbox':[.1,.1,.5,.2],'polygon':[]},
               {'text':'Right line','confidence':.99,'bbox':[.6,.1,.9,.2],'polygon':[]}]
        bounds=ov.source_crop_bounds([lines[0]],lines)
        self.assertGreaterEqual(bounds[2],.5)
        self.assertLess(bounds[2],.6)

    def test_ten_pages_get_budget_without_raising_document_limit(self):
        used=0;grants=[]
        for page in range(1,11):
            grant=ov.recovery_allowance(64,used,page,10);grants.append(grant);used+=grant
        self.assertEqual(used,64);self.assertTrue(all(0<n<=8 for n in grants))
        self.assertGreater(grants[8],0);self.assertGreater(grants[9],0)

    def test_low_budget_is_spread_and_unused_allowance_carries(self):
        used=0;grants=[]
        for page in range(1,101):
            grant=ov.recovery_allowance(64,used,page,100);grants.append(grant);used+=grant
        self.assertEqual(used,64);self.assertGreater(grants[-1],0)
        self.assertEqual(ov.recovery_allowance(64,0,10,10),8)
        self.assertEqual(ov.recovery_allowance(0,0,10,10),0)
        self.assertEqual(ov.recovery_allowance(64,64,10,10),0)

if __name__=='__main__':unittest.main()
