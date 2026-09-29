import unittest
from unittest.mock import patch
import numpy as np
from marker_geometry import refine_marker_center
from vision import recognize,candidate_shift,Scene


def ring_image(width,center,filled=False):
    y,x=np.mgrid[:220,:220];cx,cy=center;radius=width*.112
    distance=np.hypot(x-cx,y-cy)
    outer=np.clip(radius+.5-distance,0,1)
    inner=np.clip(distance-(radius-width*.025)+.5,0,1)
    ring=outer if filled else outer*inner
    stem=np.clip(width*.009+.5-abs(x-cx),0,1)*(y<cy-radius)
    alpha=np.maximum(ring,stem)
    return np.rint(np.array([42,100,120])+(255-np.array([42,100,120]))*alpha[:,:,None]).astype('uint8')


class MarkerGeometryTests(unittest.TestCase):
    def test_fractional_centers_across_sizes_and_white_fills(self):
        for width in (80,113,160):
            for filled in (False,True):
                for center in ((99.3,103.25),(99.7,102.8)):
                    with self.subTest(width=width,filled=filled,center=center):
                        found=refine_marker_center(ring_image(width,center,filled),
                                                   (100,102),width)
                        np.testing.assert_allclose(found,center,atol=.18)

    def test_missing_or_occluded_rim_retains_original_coordinate(self):
        marker=(100,102)
        for image in (np.zeros((220,220,3),np.uint8),np.full((220,220,3),255,np.uint8)):
            self.assertEqual(refine_marker_center(image,marker,113),marker)
        image=ring_image(113,(99.3,103.25));image[100:]=0
        self.assertEqual(refine_marker_center(image,marker,113),marker)
        # At very small sizes this thin antialiased ring has insufficient
        # reliable outer-rim pixels; retaining the coarse point is deliberate.
        self.assertEqual(refine_marker_center(ring_image(50,(99.3,103.25)),marker,50),marker)

    def test_legacy_translation_sampling_accepts_fractional_markers(self):
        image=np.full((210,210,3),100,np.uint8)
        scene=Scene([],[(40.3,100.4),(100.2,100.5),(160.6,100.3)],(10,10,190,190),[],None,None)
        rules=[dict(enabled=True,colors=['#646464'],exact=True,tolerance=0)]*3
        move=candidate_shift(image,scene,rules)
        self.assertIsNotNone(move)

    def test_recognizer_keeps_card_bounds_and_reuses_precise_centers(self):
        image=np.zeros((400,300,3),np.uint8)
        centers=((60.3,160.25),(150.4,170.8),(240.2,180.3))
        cards=[(20,10,80,80),(110,10,80,80),(200,10,80,80)]
        for center in centers:
            y,x=np.mgrid[:400,:300];radius=80*.112
            distance=np.hypot(x-center[0],y-center[1])
            rim=np.clip(radius+.5-distance,0,1)*np.clip(distance-(radius-2)+.5,0,1)
            stem=(abs(x-center[0])<1)&(y<center[1]-radius)
            image=np.maximum(image,np.rint(np.maximum(rim,stem)*255).astype('uint8')[:,:,None])
        with patch('vision.color_cards',return_value=cards),patch('vision.green_buttons',return_value=[]):
            scene=recognize(image,False)
            self.assertEqual(scene.board,(15,110,285,380))
            np.testing.assert_allclose(scene.markers,centers,atol=.18)
            with patch('vision.refine_marker_center',side_effect=AssertionError('Unnecessary refit')):
                self.assertEqual(recognize(image,False,previous=scene).markers,scene.markers)


if __name__=='__main__':unittest.main()
