import unittest
from unittest.mock import Mock

from search_overlay import SearchOverlay


class Label:
    def __init__(self):self.values=[]
    def configure(self,**values):self.values.append(values)


class Button:
    def __init__(self):self.states=[]
    def configure(self,**values):self.states.append(values)


class SearchOverlayAtlasTests(unittest.TestCase):
    def test_f9_dismisses_all_phases_and_late_events_cannot_restore_overlay(self):
        for phase in ('waiting','positioning','choosing','verified','invalidated','unavailable'):
            with self.subTest(phase=phase):
                overlay=SearchOverlay.__new__(SearchOverlay)
                overlay.phase=phase;overlay.batch_id='batch';overlay.candidate_rows={7:Button()}
                overlay.withdraw=Mock();overlay.render=Mock();overlay.show_candidates=Mock()
                overlay.select_candidate=Mock()
                overlay.dismiss()
                for kind in ('atlas_candidates','atlas_default_verified','atlas_invalidated','interrupted','finished'):
                    overlay.handle(kind,{})
                overlay.choose('batch',7)
                self.assertEqual(overlay.phase,'stopped');self.assertIsNone(overlay.batch_id)
                overlay.withdraw.assert_called_once();overlay.render.assert_not_called()
                overlay.show_candidates.assert_not_called();overlay.select_candidate.assert_not_called()

    def test_expired_choice_disables_candidates_and_rejects_late_clicks(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        overlay.phase='choosing';overlay._text=None;overlay.batch_id='batch-1'
        overlay.selection_sent=False;overlay.candidate_rows={7:Button()}
        overlay.heading=Label();overlay.copy=Label()
        overlay.select_candidate=Mock()

        overlay.handle('atlas_selection_expired',{})
        overlay.choose('batch-1',7)

        self.assertEqual(overlay.phase,'verified')
        self.assertIsNone(overlay.batch_id)
        self.assertIn({'state':'disabled'},overlay.candidate_rows[7].states)
        overlay.select_candidate.assert_not_called()

    def test_choice_rejection_keeps_automatic_result_and_disables_rows(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        overlay.phase='positioning';overlay._text=None;overlay.batch_id='batch-1'
        overlay.candidate_rows={7:Button()};overlay.heading=Label();overlay.copy=Label()
        overlay.handle('atlas_choice_rejected',{'message':'Not enough time.'})
        self.assertEqual(overlay.phase,'verified')
        self.assertIsNone(overlay.batch_id)
        self.assertIn({'state':'disabled'},overlay.candidate_rows[7].states)

    def test_stop_invalidates_visible_choices_and_finished_event_keeps_overlay(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        overlay.phase='choosing';overlay._text=None;overlay.batch_id='batch-1'
        overlay.candidate_rows={7:Button()};overlay.heading=Label();overlay.copy=Label()
        overlay.select_candidate=Mock()
        overlay.handle('interrupted',{'message':'Stopped.'})
        overlay.handle('finished',{})
        overlay.choose('batch-1',7)
        self.assertEqual(overlay.phase,'interrupted')
        self.assertIsNone(overlay.batch_id)
        self.assertIn({'state':'disabled'},overlay.candidate_rows[7].states)
        overlay.select_candidate.assert_not_called()


if __name__=='__main__':unittest.main()
