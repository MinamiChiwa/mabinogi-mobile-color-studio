"""Pure colour reuse must retain distances, rules and mutable caller ownership."""
import unittest
from unittest.mock import patch
import numpy as np
import vision
from hex_refinement import score_codes
import native_input_response as response


class LosslessColorReuseTests(unittest.TestCase):
    def test_repeated_canonical_distance_does_not_reconvert_colors(self):
        color='#13579B';targets=['#2468AC','#FFFFFF']
        if hasattr(vision,'_color_distance'):vision._color_distance.cache_clear()
        with patch('vision.cv2.cvtColor',wraps=vision.cv2.cvtColor) as convert:
            first=vision.error(color,targets,False)
            calls=convert.call_count
            self.assertGreater(calls,0)
            second=vision.error(' 13579b ',['2468ac','ffffff'],False)
            self.assertEqual(second,first)
            self.assertEqual(convert.call_count,calls,'Repeated colour pairs still perform LAB conversion')

    def test_mutating_target_list_changes_distance_and_invalid_values_still_fail(self):
        targets=['#000000']
        self.assertEqual(vision.error('#000000',targets,False),0.)
        targets[0]='#FFFFFF'
        self.assertGreater(vision.error('#000000',targets,False),99.)
        for bad in ('','GG0000','#1234567'):
            with self.assertRaises(ValueError):vision.error('#000000',[bad],False)
        with self.assertRaises((ValueError,vision.cv2.error)):vision.error('#000000',[],False)

    def test_scalar_scores_match_uncached_cv2_with_alternatives_and_priorities(self):
        rng=np.random.default_rng(329)
        for _ in range(50):
            codes=['#%02X%02X%02X'%tuple(row) for row in rng.integers(0,256,(3,3))]
            targets=['#%02X%02X%02X'%tuple(row) for row in rng.integers(0,256,(4,3))]
            actual=vision.lab([vision.rgb(c) for c in codes])
            target=vision.lab([vision.rgb(c) for c in targets])
            for i,color in enumerate(codes):
                expected=float(np.min(np.linalg.norm(actual[i:i+1]-target,axis=1)))
                self.assertEqual(vision.error(color,targets,False),expected)
                exact=min(max(abs(a-b) for a,b in zip(vision.rgb(color),vision.rgb(t))) for t in targets)
                self.assertEqual(vision.error(color,targets,True),exact)
            rules=[dict(enabled=True,exact=i==0,colors=targets,tolerance=8.,priority=3-i) for i in range(3)]
            score=score_codes(codes,rules)
            self.assertEqual(score['deltas'],[float(np.min(np.linalg.norm(actual[i:i+1]-target,axis=1))) for i in range(3)])
            self.assertFalse(score['accepted'])


class LosslessFloatVectorTests(unittest.TestCase):
    def test_float32_input_does_not_allocate_an_unneeded_float64_vector(self):
        point=np.array([.123,-.456],np.float32);widened=[];asarray=np.asarray
        def observed(value,*args,**kwargs):
            result=asarray(value,*args,**kwargs)
            if value is point and result.dtype==np.float64:widened.append(result)
            return result
        with patch('native_input_response.np.asarray',side_effect=observed):result=response._vector(point)
        np.testing.assert_array_equal(result,point)
        self.assertEqual(widened,[],'Native float32 points are widened only to be narrowed again')
        result[0]=10.
        self.assertEqual(point[0],np.float32(.123),'Returned vectors must own their storage')

    def test_float32_shape_nonfinite_and_large_double_validation_remains_active(self):
        for point in (np.array([np.inf,0],np.float32),np.array([np.nan,0],np.float32),
                      np.array([[0,1]],np.float32),[1e100,0]):
            with self.subTest(point=str(point)):
                with self.assertRaises(ValueError):response._vector(point)
        for point in (np.array([1e-38,-1e-38],np.float32),np.array([3e38,-3e38],np.float32)):
            np.testing.assert_array_equal(response._vector(point),point)

    def test_masked_array_cannot_hide_nonfinite_data_or_change_return_type(self):
        with self.assertRaises(ValueError):
            response._vector(np.ma.array([np.inf,0],mask=[True,False],dtype=np.float32))
        point=np.ma.array([.1,.2],mask=[True,False],dtype=np.float32)
        result=response._vector(point)
        self.assertIs(type(result),np.ndarray)
        np.testing.assert_array_equal(result,np.array([.1,.2],dtype=np.float32))


if __name__=='__main__':unittest.main()
