"""Screenshot preflight works without a game sender or process-memory backend."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image

class ScreenshotPreflightTests(unittest.TestCase):
    def test_offline_frame_reports_capture_and_never_requires_a_game(self):
        from screenshot_preflight import main
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);image=folder/'ordinary.png'
            Image.fromarray(np.full((120,160,3),127,np.uint8)).save(image)
            with patch('screenshot_preflight.configure_ocr',return_value=True):
                result=main(['--image',str(image),'--output-dir',str(folder/'report')])
            report=json.loads((folder/'report/screenshot-preflight.json').read_text(encoding='utf8'))
            self.assertEqual(result,0)
            self.assertEqual(report['capture_size'],[160,120])
            self.assertFalse(report['board_visible'])
            self.assertEqual(report['input_count'],0)
            self.assertTrue(report['no_game_memory'])
