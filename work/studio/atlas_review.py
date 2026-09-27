"""Build/review an atlas from annotated native PNGs; never controls the game.

Run: python work/studio/atlas_review.py manifest.json output_directory
Each frame supplies three mask PNGs and an image-measured absolute translation.
All frames must have the same angle/scale; masks use white for valid pixels.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from periodic_atlas import PeriodicAtlas, translation_candidates


def review(manifest, output):
    manifest = Path(manifest); output = Path(output)
    data = json.loads(manifest.read_text(encoding='utf-8'))
    atlas = PeriodicAtlas(data['basis'], data['origin'], data.get('resolution', 256))
    for frame in data['frames']:
        image = np.array(Image.open(manifest.parent / frame['image']).convert('RGB'))
        masks = np.array([np.array(Image.open(manifest.parent / p).convert('L')) > 127 for p in frame['masks']])
        atlas.add_resampled(image, masks, frame['measured_translation'])
    colors, valid, rmse = atlas.maps()
    output.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        rgba = np.dstack((colors[i], valid[i].astype(np.uint8)*255))
        Image.fromarray(rgba).save(output / f'region-{i+1}.png')
    np.savez_compressed(output / 'atlas.npz', basis=atlas.basis, origin=atlas.origin,
                        colors=colors, valid=valid, count=atlas.count, rmse=rmse)
    result = dict(schema=1, source=str(manifest.resolve()), metric='Delta E 76',
                  verified=False, coverage=atlas.report(), candidates=[])
    if 'rules' in data:
        result['candidates'] = translation_candidates(atlas, data['markers'], data['rules'],
                                                      data['current_translation'])
    (output / 'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest'); parser.add_argument('output')
    args = parser.parse_args()
    print(json.dumps(review(args.manifest, args.output), ensure_ascii=False, indent=2))
