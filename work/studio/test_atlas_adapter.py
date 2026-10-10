import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from atlas_adapter import rules_targets, build_from_capture


class AdapterTests(unittest.TestCase):
    def test_targets_preserve_three_region_order(self):
        rules=[dict(enabled=True,colors=['#112233']),
               dict(enabled=False,colors=[]),
               dict(enabled=True,colors=['#AABBCC','#000000'])]
        self.assertEqual(rules_targets(rules),['#112233','#000000','#AABBCC'])

    def test_enabled_rule_requires_target(self):
        with self.assertRaises(ValueError):rules_targets([dict(enabled=True,colors=[])]*3)

    def test_formal_builder_uses_validated_1024_map(self):
        with tempfile.TemporaryDirectory() as folder:
            analysis=Path(folder)/'analysis'; analysis.mkdir()
            (analysis/'report.json').write_text(json.dumps({'expanded':{'quality_gate':{'passed':False}}}))
            with patch('atlas_adapter.analyze_capture') as analyze:
                build_from_capture(folder,[])
                self.assertEqual(analyze.call_args.kwargs['atlas_resolution'],1024)


if __name__=='__main__':unittest.main()
