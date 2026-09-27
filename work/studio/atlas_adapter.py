"""Offline half of the atlas adapter used by the formal Runner.

It consumes a completed capture directory and publishes nothing unless the
analysis report's quality gate passed.  Live capture remains an injected
Windows callback, so importing this module never sends input.
"""
import json
from pathlib import Path
from analyze_live_atlas import run as analyze_capture


def rules_targets(rules):
    targets=[]
    for rule in rules:
        if not rule.get('enabled'):
            targets.append('#000000')
        else:
            colors=rule.get('colors') or []
            if not colors:raise ValueError('Enabled atlas rule has no target')
            targets.append(colors[0])
    if len(targets)!=3:raise ValueError('Atlas analysis expects three rules')
    return targets


def build_from_capture(capture_dir, rules):
    artifact=capture_dir if isinstance(capture_dir,dict) else {'folder':capture_dir}
    source=Path(artifact['folder'])
    game=artifact.get('game')
    analyze_capture(source, target_rules=rules,check=game.check if game is not None else None,
                    atlas_resolution=1024,progress=artifact.get('progress'))
    report_path=source/'analysis'/'report.json'
    if not report_path.is_file():raise RuntimeError('Atlas analysis did not produce report.json')
    report=json.loads(report_path.read_text(encoding='utf-8'))
    gate=report.get('expanded',{}).get('quality_gate',{})
    if not gate.get('passed',False):
        return dict(quality_gate=gate,candidates=[],board=report.get('expanded',{}).get('scene',{}).get('board'))
    review=source/'analysis'/'expanded'/'review.json'
    data=json.loads(review.read_text(encoding='utf-8')) if review.is_file() else {}
    return dict(quality_gate=gate,candidates=data.get('candidates',[]),report=report,
                search_space=data.get('search_space'),search_diagnostics=data.get('search_diagnostics',{}),
                board=report.get('scene',{}).get('board'),
                selection_deadline=artifact.get('deadline'))
