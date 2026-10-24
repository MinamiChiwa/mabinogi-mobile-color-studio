"""TDD contract for fail-closed PaletteInstance -> Control discovery."""
import importlib,importlib.util,unittest


class NativeRuntimeDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('native_runtime_discovery'))
        self.m=importlib.import_module('native_runtime_discovery')
        self.instance=dict(address=0x1000,class_name='MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl',
                           ui_slot=0x2000,data=0x3000,result=0x4000)
        self.candidate=dict(address=0x5000,class_name='MM.Client.Presentation.UI.Controls.Dyeing.DyeingPaletteControl',
                            ui_slot=0x2000,motion_control=0x6000,gesture_recognizer=0x7000,root_object=0x2000)

    def test_unique_shared_slot_candidate_is_accepted(self):
        result=self.m.select_palette_control(self.instance,[self.candidate])
        self.assertEqual(result['control_address'],0x5000)
        self.assertEqual(result['motion_address'],0x6000)
        self.assertEqual(result['gesture_address'],0x7000)
        self.assertFalse(result['execution_verified'])

    def test_wrong_type_slot_or_missing_links_fail_closed(self):
        for change in (dict(class_name='Other'),dict(ui_slot=0x9999),dict(motion_control=0),dict(gesture_recognizer=0),dict(root_object=0)):
            with self.assertRaises(ValueError):
                self.m.select_palette_control(self.instance,[dict(self.candidate,**change)])

    def test_ambiguous_or_missing_candidates_fail_closed(self):
        with self.assertRaises(ValueError):self.m.select_palette_control(self.instance,[])
        with self.assertRaises(ValueError):
            self.m.select_palette_control(self.instance,[self.candidate,dict(self.candidate,address=0x5100)])

    def test_instance_identity_and_slot_are_required(self):
        for change in (dict(class_name='Other'),dict(ui_slot=0),dict(address=0)):
            with self.assertRaises(ValueError):self.m.select_palette_control(dict(self.instance,**change),[self.candidate])

    def test_candidate_extra_objects_cannot_satisfy_shared_slot(self):
        other=dict(self.candidate,address=0x5100,ui_slot=0x2000,motion_control=0x6100,gesture_recognizer=0x7100,root_object=0x2000)
        with self.assertRaises(ValueError):self.m.select_palette_control(self.instance,[self.candidate,other])


if __name__=='__main__':unittest.main()
