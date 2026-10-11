import unittest
import copy
import json

from native_live.session_deadline import verified_timer_extension


class VerifiedTimerExtensionTests(unittest.TestCase):
    def extension(self):
        return dict(
            deadline_source='existing_active_unknown_age',
            initial_deadline=180.,
            maximum_deadline=200.,
            process_identity=['pid', 'token'],
            session_token=['session'],
        )

    def frames(self):
        checkpoint = dict(
            checkpoint_valid=True, cpu_matches=True,
            client_hex=['#FFFFFF', '#FFFFFF'],
            binding='[["session"], ["pid", "token"]]',
        )
        frames = [
            dict(captured_monotonic=150., remaining_seconds=50,
                 timer_confidence='two_pass_agree', screenshot_hex_verified=True,
                 screenshot_hex=['#FFFFFF', '#FFFFFF'], hex=['#FFFFFF', '#FFFFFF'],
                 hex_source=['screenshot', 'screenshot'], timer_advisory=True),
            dict(captured_monotonic=154., remaining_seconds=46,
                 timer_confidence='two_pass_agree', screenshot_hex_verified=True,
                 screenshot_hex=['#FFFFFF', '#FFFFFF'], hex=['#FFFFFF', '#FFFFFF'],
                 hex_source=['screenshot', 'screenshot'], timer_advisory=True),
        ]
        return checkpoint, frames

    def test_qualified_pair_extends_only_to_bounded_timer_end(self):
        checkpoint, frames = self.frames()
        result = verified_timer_extension(checkpoint, frames,
            initial_engineering_deadline=180., current_deadline=180.,
            extension=self.extension(), timer_grace_until=130., now=154.)
        self.assertIsNotNone(result)
        self.assertEqual(result['deadline'], 190.)

    def test_new_session_source_cannot_extend(self):
        checkpoint, frames = self.frames(); extension = self.extension()
        extension['deadline_source'] = 'new_session'
        self.assertIsNone(verified_timer_extension(checkpoint, frames,
            initial_engineering_deadline=180., current_deadline=180.,
            extension=extension, timer_grace_until=130., now=154.))

    def test_timer_jump_and_unverified_hex_are_rejected(self):
        checkpoint, frames = self.frames(); frames[1]['remaining_seconds'] = 17
        self.assertIsNone(verified_timer_extension(checkpoint, frames,
            initial_engineering_deadline=180., current_deadline=180.,
            extension=self.extension(), timer_grace_until=130., now=154.))

    def test_live_tuple_tokens_match_recorded_binding_arrays(self):
        checkpoint, frames = self.frames(); extension = self.extension()
        extension['session_token'] = ('session', ('palette', ('pixel-hash', .5)))
        extension['process_identity'] = ('pid', ('token', 7))
        checkpoint['binding'] = json.dumps([extension['session_token'], extension['process_identity']])
        self.assertIsNotNone(verified_timer_extension(checkpoint, frames,
            initial_engineering_deadline=180., current_deadline=180.,
            extension=extension, timer_grace_until=130., now=154.))

    def test_maximum_bound_and_remaining_timer_reserve_are_both_preserved(self):
        checkpoint, frames = self.frames(); extension = self.extension()
        frames[0]['remaining_seconds'] = 70; frames[1]['remaining_seconds'] = 66
        result = verified_timer_extension(checkpoint, frames,
            initial_engineering_deadline=180., current_deadline=180.,
            extension=extension, timer_grace_until=130., now=154.)
        self.assertEqual(result['deadline'], 200.)
        extension['maximum_deadline'] = 201.
        self.assertIsNone(verified_timer_extension(checkpoint, frames,
            initial_engineering_deadline=180., current_deadline=180.,
            extension=extension, timer_grace_until=130., now=154.))

    def test_invalid_or_weak_evidence_does_not_correct_deadline(self):
        checkpoint, frames = self.frames()
        cases = []
        for key,value in [('timer_confidence','single_pass'), ('remaining_seconds',True),
                          ('captured_monotonic',150.), ('screenshot_hex',['#000000','#FFFFFF']),
                          ('hex_source',['native_checkpoint','screenshot'])]:
            altered=copy.deepcopy(frames);altered[1][key]=value;cases.append(altered)
        same=copy.deepcopy(frames);same[1]['remaining_seconds']=50;cases.append(same)
        for altered in cases:
            with self.subTest(frames=altered):
                self.assertIsNone(verified_timer_extension(checkpoint, altered,
                    initial_engineering_deadline=180., current_deadline=180.,
                    extension=self.extension(), timer_grace_until=130., now=154.))

    def test_short_caller_cutoff_and_expired_cutoff_cannot_be_extended(self):
        checkpoint, frames = self.frames()
        for initial,current,now in [(179.,179.,154.),(180.,180.,180.),(180.,179.,154.)]:
            with self.subTest(initial=initial,current=current,now=now):
                self.assertIsNone(verified_timer_extension(checkpoint, frames,
                    initial_engineering_deadline=initial, current_deadline=current,
                    extension=self.extension(), timer_grace_until=130., now=now))

    def test_stale_session_and_startup_evidence_cannot_extend(self):
        checkpoint, frames = self.frames()
        for key,value in [('session_token',['other']),('process_identity',['other','pid'])]:
            extension=self.extension();extension[key]=value
            self.assertIsNone(verified_timer_extension(checkpoint, frames,
                initial_engineering_deadline=180., current_deadline=180.,
                extension=extension, timer_grace_until=130., now=154.))
        for grace,now in [(155.,154.),(130.,160.)]:
            self.assertIsNone(verified_timer_extension(checkpoint, frames,
                initial_engineering_deadline=180., current_deadline=180.,
                extension=self.extension(), timer_grace_until=grace, now=now))
        checkpoint, frames = self.frames(); frames[1]['screenshot_hex_verified'] = False
        self.assertIsNone(verified_timer_extension(checkpoint, frames,
            initial_engineering_deadline=180., current_deadline=180.,
            extension=self.extension(), timer_grace_until=130., now=154.))


if __name__ == '__main__':
    unittest.main()
