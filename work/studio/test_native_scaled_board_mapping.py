"""Visual continuous edges and mouse integer mapping remain distinct at DPI scale."""
import copy,unittest
from native_live.map_unity_window import map_unity_geometry_to_client


class ScaledBoardMappingTests(unittest.TestCase):
    def setUp(self):
        self.geometry=dict(screen_origin='unity_bottom_left',axis_aligned_candidate=True,
            predicted_unity_corners=[[700,40],[1200,40],[700,540],[1200,540]])
        self.window=dict(source='win32_client_physical',physical_coordinates=True,minimized=False,visible=True,
            client_size_physical=[1920,1440],client_origin_physical=[-1920,200])
        self.screen=dict(source='current_build_native_screen_fields',size=[1280,960])
        self.mapping=dict(source='win32_target_awareness_pixel_lattice',physical_client_size=[1920,1440],
            native_screen_size=[1280,960],target_client_size=[1280,960],viewport_origin=[0,0],viewport_scale=[1.,1.],
            coordinate_validation=dict(verified=True,scheme='physical_to_logical_for_hwnd_then_target_context_screen_to_client'))
    def test_verified_dpi_mapping_projects_native_edges_to_physical_screenshot(self):
        try:result=map_unity_geometry_to_client(self.geometry,self.window,self.screen,pixel_mapping=self.mapping)
        except TypeError:self.fail('Scaled board mapping interface missing')
        self.assertEqual(result['client_board_candidate'],[1050.,630.,1800.,1380.])
        self.assertEqual(result['desktop_board_candidate'],[-870.,830.,-120.,1580.])
        self.assertEqual(result['pixel_mapping']['native_board_top_left'],[700.,420.,1200.,920.])
        self.assertFalse(result['extent_one_to_one'])
    def test_extent_ratio_without_coordinate_proof_is_rejected(self):
        with self.assertRaises(ValueError):map_unity_geometry_to_client(self.geometry,self.window,self.screen)
    def test_packet_dimensions_cannot_refer_to_another_window(self):
        bad=copy.deepcopy(self.mapping);bad['physical_client_size']=[2560,1920]
        with self.assertRaises(ValueError):
            map_unity_geometry_to_client(self.geometry,self.window,self.screen,pixel_mapping=bad)
    def test_one_to_one_mapping_preserves_legacy_edges_without_packet(self):
        self.window['client_size_physical']=[1280,960]
        result=map_unity_geometry_to_client(self.geometry,self.window,self.screen)
        self.assertEqual(result['client_board_candidate'],[700.,420.,1200.,920.])
        self.assertTrue(result['extent_one_to_one'])
    def test_exported_enriched_packet_has_a_valid_content_hash(self):
        from test_native_window_mapping import MappingAPI
        from native_live.read_dye_window_mapping import read_pixel_mapping,validate_pixel_mapping
        api=MappingAPI()
        window=dict(source='win32_client_physical',hwnd=10,pid=20,client_origin_physical=[-150,45],
            client_size_physical=[12,9],window_dpi_awareness=0,physical_coordinates=True,visible=True,minimized=False)
        screen=dict(source='current_build_native_screen_fields',size=[8,6])
        raw=read_pixel_mapping(window,screen,10.,clock=lambda:0.,api=api)
        geometry=dict(screen_origin='unity_bottom_left',axis_aligned_candidate=True,
            predicted_unity_corners=[[2,1],[6,1],[2,5],[6,5]])
        result=map_unity_geometry_to_client(geometry,window,screen,pixel_mapping=raw)
        self.assertTrue(validate_pixel_mapping(result['pixel_mapping'],window,screen,10.,clock=lambda:0.,api=api))
        self.assertNotEqual(raw['mapping_sha256'],result['pixel_mapping']['mapping_sha256'])


if __name__=='__main__':unittest.main()
