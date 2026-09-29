import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image
from scan_settling_review import review


class ReviewTests(unittest.TestCase):
    def test_missing_probes_cannot_be_called_equivalent(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            self.create(folder)
            result=review(folder)
        self.assertEqual(result['compared'],0)
        self.assertFalse(result['all_material_pixels_identical'])
        self.assertEqual(result['potential_saving_seconds'],0)

    def create(self, folder):
        scene=dict(kind='sampling_ready',board=[0,0,300,300],
                   markers=[[50,90],[150,130],[250,230]],cards=[])
        previous=np.random.default_rng(2).integers(0,256,(300,300,3),dtype=np.uint8)
        current=np.roll(previous,40,axis=1)
        Image.fromarray(previous).save(folder/'max_sampling_board.png')
        Image.fromarray(current).save(folder/'grid_001_board.png')
        row=dict(kind='frame',name='grid_001',scan_timing=dict(
            probe_times=[dict(start_seconds=.08,end_seconds=.12),dict(start_seconds=.18,end_seconds=.22)],
            potential_saving_seconds=.2,baseline_late_seconds=0,fallback_reason=None))
        (folder/'log.json').write_text(json.dumps([scene,row]),encoding='utf8')
        return previous,current

    def test_reload_checks_saved_pixels_not_only_logged_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            previous,current=self.create(folder)
            Image.fromarray(previous).save(folder/'grid_001-settle-early.png')
            Image.fromarray(previous).save(folder/'grid_001-settle-check.png')
            result=review(folder)
            self.assertEqual(result['eligible'],0)
            self.assertEqual(result['potential_saving_seconds'],0)
            for label in ('early','check'):
                Image.fromarray(current).save(folder/f'grid_001-settle-{label}.png')
            result=review(folder)
        self.assertEqual(result['eligible'],1)
        self.assertEqual(result['potential_saving_seconds'],.2)
        self.assertFalse(result['all_material_pixels_identical'])  # incomplete scan


if __name__=='__main__':unittest.main()
