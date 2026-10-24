import unittest
import numpy as np
from capture_color_check import reference_pixels, compare


class CaptureColorTests(unittest.TestCase):
    def test_reference_covers_every_gray_and_primary_level(self):
        pixels=reference_pixels()
        cells=pixels[::16,::16].reshape(-1,3)
        self.assertEqual(pixels.shape,(512,1024,3))
        np.testing.assert_array_equal(cells[:256],np.arange(256)[:,None].repeat(3,axis=1))
        for channel in range(3):
            expected=np.zeros((256,3),np.uint8);expected[:,channel]=np.arange(256)
            np.testing.assert_array_equal(cells[(channel+1)*256:(channel+2)*256],expected)

    def test_comparison_does_not_hide_one_level_error(self):
        expected=np.zeros((2,2,3),np.uint8);actual=expected.copy();actual[0,0,0]=1
        result=compare(expected,actual)
        self.assertFalse(result['exact']);self.assertEqual(result['changed_pixels'],1)
        self.assertEqual(result['maximum_channel_error'],1)


if __name__=='__main__':unittest.main()
