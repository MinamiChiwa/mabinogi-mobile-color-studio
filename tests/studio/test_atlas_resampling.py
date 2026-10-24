import unittest
import cv2
import numpy as np
from periodic_atlas import PeriodicAtlas


class ResamplingTests(unittest.TestCase):
    def test_cropped_projection_matches_full_period_reference(self):
        rng=np.random.default_rng(917)
        image=rng.integers(0,256,(43,51,3),dtype=np.uint8)
        masks=rng.random((3,43,51))>.1
        for basis in ([[65,0],[0,61]],[[22,-9],[8,26]],[[-35,7],[5,38]]):
            with self.subTest(basis=basis):
                a=PeriodicAtlas(basis,origin=(3.4,-8.2),resolution=32)
                count=np.zeros_like(a.count);total=np.zeros_like(a.total);squared=np.zeros_like(a.squared)
                for translation in ((0,0),(59.1,-70.4)):
                    a.add_resampled(image,masks,translation)
                    corners=(np.array([[0,0],[50,0],[0,42],[50,42]])-a.origin-translation)@np.linalg.inv(a.basis).T
                    lo=np.floor(corners.min(0)).astype(int);hi=np.floor(corners.max(0)).astype(int)
                    yy,xx=np.mgrid[:32,:32];phase=np.stack(((xx+.5)/32,(yy+.5)/32),axis=-1)
                    for ty in range(lo[1],hi[1]+1):
                        for tx in range(lo[0],hi[0]+1):
                            points=(phase+[tx,ty])@a.basis.T+a.origin+translation
                            px,py=points[...,0].astype(np.float32),points[...,1].astype(np.float32)
                            ix=np.floor(px).astype(int);iy=np.floor(py).astype(int)
                            inside=(ix>=0)&(iy>=0)&(ix<50)&(iy<42)
                            ix=np.clip(ix,0,49);iy=np.clip(iy,0,41)
                            values=cv2.remap(image.astype(np.float32),px,py,cv2.INTER_LINEAR)
                            for i,mask in enumerate(masks):
                                good=inside&mask[iy,ix]&mask[iy+1,ix]&mask[iy,ix+1]&mask[iy+1,ix+1]
                                count[i,good]+=1;total[i,good]+=values[good]
                                squared[i,good]+=values[good].astype(float)**2
                np.testing.assert_array_equal(a.count,count)
                np.testing.assert_array_equal(a.total,total)
                np.testing.assert_array_equal(a.squared,squared)
                colors,valid,rmse=a.maps()
                for i in range(3):
                    for expected,actual in zip((colors[i],valid[i],rmse[i]),a.maps(region=i)):
                        np.testing.assert_array_equal(actual,expected)


if __name__=='__main__':unittest.main()
