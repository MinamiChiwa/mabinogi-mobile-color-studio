"""Narrow extension of existing project IO for the known-target protocol."""
import json,re,time
from pathlib import Path
import numpy as np
from .project_probe_io import ProjectProbeIO
from .dye_action_checkpoint import _binding
from input_gestures import PointerGesture
from .read_dye_input_backend import read_input_backend, input_backend_binding
from .dye_visual_readiness import VisualNotReady, INITIAL_LAYOUT_ERRORS
from .dye_hex_glyphs import read_card_glyphs, prepare_hex_assets


class InputNotStarted(TimeoutError):
    """A protected phase expired while its input attempt count was unchanged."""


def validate_research_gesture(record,board):
    points=record.get('points');kind=record.get('kind');l,t,r,b=board
    if kind not in ('drag','wheel','rotate') or not isinstance(points,(list,tuple)) or not 1<=len(points)<=128:
        raise ValueError('Only bounded standard pointer candidates supported')
    if any(not isinstance(p,(list,tuple)) or len(p)!=2 or any(type(v) is not int for v in p)
           or not l+12<p[0]<r-12 or not t+12<p[1]<b-12 for p in points):
        raise ValueError('Candidate outside safe physical board')
    if kind=='drag':
        array=np.asarray(points,dtype=int)
        if len(points)<2 or np.max(np.abs(np.diff(array,axis=0)))>max(1,(r-l)*.04,(b-t)*.04):
            raise ValueError('Smooth visible drag samples required')
        gesture=PointerGesture('drag',tuple(tuple(p) for p in points),absolute=record.get('absolute',True))
    elif kind=='wheel':
        if len(points)!=1 or type(record.get('wheel_steps')) is not int or not 1<=abs(record['wheel_steps'])<=32:
            raise ValueError('One to32 signed wheel steps required')
        gesture=PointerGesture('wheel',tuple(tuple(p) for p in points),wheel_steps=record['wheel_steps'])
    else:
        if record.get('right') is not True or type(record.get('arc_start')) is not int or not 0<=record['arc_start']<len(points)-1:
            raise ValueError('Explicit standard right rotation required')
        gesture=PointerGesture('rotate',tuple(tuple(p) for p in points),right=True,
            absolute=record.get('absolute',True),requested_angle=record.get('requested_angle'),arc_start=record['arc_start'])
    if not gesture.has_effect or json.dumps(gesture.record(),sort_keys=True)!=json.dumps(record,sort_keys=True):
        raise ValueError('Candidate schema/timing/right-button descriptor differs')
    return gesture


class ProjectClosedLoopIO(ProjectProbeIO):
    def __init__(self,*args,**kwargs):
        prepare_hex_assets()
        super().__init__(*args,**kwargs);self.input_reference=None;self.input_attempts=0;self.hex_fallback=read_card_glyphs
        self._planning_probe_at=None
    def planning_check(self,deadline):
        self.deadline=min(deadline,self.reference['session_deadline_monotonic'])
        self._input_guard()
        now=time.monotonic()
        if self._planning_probe_at is None or now-self._planning_probe_at>=.25 or now<self._planning_probe_at:
            self.check(deadline)
            self._planning_probe_at=now
    def input_backend(self,deadline):
        self.check(deadline)
        record=read_input_backend(self.backend,deadline,check=self._input_guard)
        if self.input_reference is None:self.input_reference=record
        elif input_backend_binding(record)!=input_backend_binding(self.input_reference):
            raise ValueError('Input backend/calibration changed')
        return record
    def frames(self,label,deadline):
        try:return super().frames(label,deadline)
        except ValueError as exc:
            retryable=str(exc) in (*INITIAL_LAYOUT_ERRORS,'Screenshot and checkpoint HEX disagree')
            (self.folder/(label+'.visual_failure.json')).write_text(json.dumps(dict(
                error=type(exc).__name__+': '+str(exc),retryable_observation=bool(retryable),
                observed_monotonic=time.monotonic(),inputs_sent=self.input_attempts),indent=2),encoding='utf-8')
            if retryable:raise VisualNotReady(str(exc)) from exc
            raise
    def perform_candidate(self,record,label,deadline):
        return self._perform_candidate(record,label,deadline,feedback_reserve_seconds=8.)
    def perform_protected_candidate(self,record,label,deadline):
        # The controller has already reserved complete return/verification
        # phases outside this deadline; do not reserve the same eight twice.
        before=self.input_attempts
        try:return self._perform_candidate(record,label,deadline,feedback_reserve_seconds=0.)
        except TimeoutError as exc:
            if self.input_attempts==before:raise InputNotStarted(str(exc)) from exc
            raise
    def _perform_candidate(self,record,label,deadline,*,feedback_reserve_seconds):
        if not isinstance(label,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}',label):raise ValueError('Bad input label')
        self.check(deadline)
        if self.input_attempts>=64:raise ValueError('Maximum input attempt accounting reached')
        gesture=validate_research_gesture(record,self.last_observation['window_mapping_candidate']['client_board_candidate'])
        if time.monotonic()+gesture.duration+feedback_reserve_seconds>=self.deadline:raise TimeoutError('Input/feedback reserve insufficient')
        first=self.input_backend(self.deadline)
        fresh=self.backend.observe_motion(self.reference['instance_address'],self.deadline,self._input_guard,
            include_geometry=True,include_window=True)
        if (fresh.get('active') is not True or _binding(fresh)!=_binding(self.last_observation)
            or fresh['motion']['pose']!=self.last_observation['motion']['pose']
            or fresh['geometry_diagnostic']!=self.last_observation['geometry_diagnostic']
            or fresh['window_mapping_candidate']!=self.last_observation['window_mapping_candidate']
            or fresh['motion']['animators_done'] is not True):
            raise ValueError('Pre-input pose/geometry binding changed')
        self.input_backend(self.deadline);self._input_guard()
        if time.monotonic()+gesture.duration+feedback_reserve_seconds>=self.deadline:
            raise TimeoutError('Input preparation consumed phase allowance')
        started=time.monotonic();self.sent_any=True;self.input_attempts+=1
        receipt=dict(input_source='project_windows_sendinput',gesture=gesture.record(),started_monotonic=started,
            input_backend_before=first,completed=False)
        try:
            self._performing_input=True
            receipt['completed']=bool(self.game.perform_gesture(gesture))
            return receipt
        finally:
            self._performing_input=False
            receipt.update(finished_monotonic=time.monotonic(),actual_trace=self.game.last_input_trace)
            (self.folder/(label+'.input.json')).write_text(json.dumps(receipt,indent=2),encoding='utf-8')
