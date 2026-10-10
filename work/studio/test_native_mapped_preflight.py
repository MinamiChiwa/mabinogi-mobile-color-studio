"""A wide physical client is supported when its native extent agrees."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from native_live import service


class NativeMappedPreflightTests(unittest.TestCase):
    def test_verified_scaled_window_reaches_backend_without_sender(self):
        backend=MagicMock();context=dict(extent_one_to_one=False,coordinate_mapping_verified=True,
            window=dict(hwnd=1,pid=2,client_size_physical=[1920,1440],dpi=144),
            unity_screen=dict(size=[1280,960],hwnd=1),
            pixel_mapping=dict(source='win32_target_awareness_pixel_lattice',coordinate_validation=dict(verified=True)))
        backend.observe_window_context.return_value=context
        with tempfile.TemporaryDirectory() as tmp,patch.object(service,'CurrentBuildBackend',return_value=backend), \
            patch.object(service,'configure_ocr'),patch.object(service,'prepare_timer_assets',return_value={}), \
            patch.object(service,'prepare_hex_assets',return_value={}),patch.object(service,'read_input_backend',return_value={}) as read, \
            patch.object(service,'ProjectClosedLoopIO') as sender:
            result=service.preflight(2,Path(tmp),hwnd=1)
        self.assertEqual(result['stop_reason'],'preflight_complete',result.get('error'))
        read.assert_called_once();sender.assert_not_called()
    def test_common_client_sizes_and_dpi_metadata_reach_input_read_without_sender(self):
        for size,dpi in (([800,600],96),([1280,960],144),([1920,1080],144),
                         ([2560,1440],168),([3840,2160],192),([900,1600],120)):
            with self.subTest(size=size,dpi=dpi),tempfile.TemporaryDirectory() as tmp:
                backend=MagicMock()
                backend.observe_window_context.return_value=dict(extent_one_to_one=True,
                    window=dict(client_size_physical=size,dpi=dpi,physical_coordinates=True),unity_screen=dict(size=size))
                with patch.object(service,'CurrentBuildBackend',return_value=backend), \
                    patch.object(service,'configure_ocr'),patch.object(service,'prepare_timer_assets',return_value={}), \
                    patch.object(service,'prepare_hex_assets',return_value={}),patch.object(service,'read_input_backend',return_value={}) as read, \
                    patch.object(service,'ProjectClosedLoopIO') as sender:
                    result=service.preflight(1,Path(tmp))
                self.assertEqual(result['stop_reason'],'preflight_complete',result.get('error'))
                self.assertEqual(result['window_context']['window']['dpi'],dpi)
                read.assert_called_once();sender.assert_not_called()
                self.assertEqual(result['actual_input_attempts'],0)


if __name__=='__main__':unittest.main()
