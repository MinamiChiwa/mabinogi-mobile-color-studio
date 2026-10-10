"""Fail-closed schema for future read-only live dye observations.

This module validates records produced by a process reader. It never opens a
process, resolves an address, sends input, or treats saved captures as live.
"""
import math
import re
import numpy as np

_HEX64=re.compile(r'^[0-9a-fA-F]{64}$')


def _finite(values, name):
    values=list(values)
    if not values or not all(math.isfinite(float(v)) for v in values):
        raise ValueError(f'Invalid finite {name}')
    return values


def _pose(pose):
    if not isinstance(pose,dict): raise ValueError('Pose record required')
    p=_finite(pose.get('position',()),'position')
    if len(p)!=2: raise ValueError('Position must have two components')
    scale=float(pose.get('scale'));rotation=float(pose.get('rotation_degrees'))
    if not math.isfinite(scale) or scale<=0 or not math.isfinite(rotation):
        raise ValueError('Invalid pose scalars')
    return dict(position=[float(v) for v in p],scale=scale,rotation_degrees=rotation)


def _animator(value,name):
    if not isinstance(value,dict): raise ValueError(f'{name} animator record required')
    if type(value.get('is_done')) is not bool or type(value.get('stop_requested')) is not bool:
        raise ValueError(f'{name} animator flags required')
    elapsed=value.get('elapsed');duration=float(value.get('duration'))
    unknown_elapsed=elapsed is None and value.get('elapsed_observed') is False
    if elapsed is None and not unknown_elapsed:raise ValueError('Unknown elapsed time needs provenance')
    if not math.isfinite(duration) or duration<0 or (not unknown_elapsed and (not math.isfinite(float(elapsed)) or float(elapsed)<0)):
        raise ValueError(f'Invalid {name} animator timing')
    last=value.get('last');target=value.get('target')
    for field,number in (('last',last),('target',target)):
        if name=='position':
            if not isinstance(number,(list,tuple)) or len(number)!=2:raise ValueError('Position animation vector required')
            _finite(number,f'{name} {field}')
        elif isinstance(number,(list,tuple)) or not math.isfinite(float(number)):
            raise ValueError('Finite rotation animation scalar required')
    return dict(value)


def validate_observation(record):
    """Validate one atomic-ish read before it can enter a planner."""
    if not isinstance(record,dict) or record.get('active') is not True:
        raise ValueError('Observation is not active')
    build=record.get('build_sha256');
    if not isinstance(build,str) or not _HEX64.fullmatch(build): raise ValueError('Build fingerprint required')
    if type(record.get('pid')) is not int or record['pid']<=0: raise ValueError('Process identity required')
    if type(record.get('process_creation_token')) is not int or record['process_creation_token']<=0:
        raise ValueError('Process creation identity required')
    if not isinstance(record.get('capture_id'),str) or not record['capture_id']:
        raise ValueError('Capture identity required')
    if not isinstance(record.get('session_token'),str) or not record['session_token']:
        raise ValueError('Live session token required')
    pixels=record.get('pixel_sha256')
    if not isinstance(pixels,(list,tuple)) or len(pixels)!=3 or any(not isinstance(v,str) or not _HEX64.fullmatch(v) for v in pixels):
        raise ValueError('Three pixel fingerprints required')
    pose=_pose(record.get('pose'))
    anim=record.get('animator')
    if not isinstance(anim,dict): raise ValueError('Animator records required')
    animators=dict(position=_animator(anim.get('position'),'position'),rotation=_animator(anim.get('rotation'),'rotation'))
    geom=record.get('geometry');
    if not isinstance(geom,dict) or geom.get('source')!='runtime_recttransform': raise ValueError('Runtime geometry required')
    board=_finite(geom.get('board',()),'board');size=_finite(geom.get('local_size',()),'local size')
    if len(board)!=4 or len(size)!=2 or board[2]<=board[0] or board[3]<=board[1] or min(size)<=0:
        raise ValueError('Invalid runtime geometry')
    if geom.get('camera')!='null': raise ValueError('Only null-camera geometry path validated')
    settings=record.get('settings')
    if not isinstance(settings,dict): raise ValueError('Motion settings required')
    required=('minimum_scale','maximum_scale','move_threshold','move_tolerance','scroll_zoom_ratio')
    if any(key not in settings for key in required): raise ValueError('Incomplete motion settings')
    values={key:float(settings[key]) for key in required}
    if values['minimum_scale']<=0 or values['maximum_scale']<values['minimum_scale'] or any(not math.isfinite(v) or v<0 for v in values.values()):
        raise ValueError('Invalid motion settings')
    scroll=record.get('scroll')
    if not isinstance(scroll,dict) or scroll.get('sign_verified') is not True or type(scroll.get('observed_events')) is not int or scroll['observed_events']<1:
        raise ValueError('Observed scroll calibration required')
    for key in ('project_delta','game_delta'):
        if not math.isfinite(float(scroll.get(key))) or float(scroll[key])==0: raise ValueError('Invalid scroll calibration')
    monotonic=float(record.get('monotonic_time'))
    if not math.isfinite(monotonic) or monotonic<=0: raise ValueError('Monotonic observation time required')
    return dict(schema=1,active=True,build_sha256=build,pid=record['pid'],process_creation_token=record['process_creation_token'],
        capture_id=record['capture_id'],session_token=record['session_token'],pixel_sha256=tuple(pixels),pose=pose,
        animator=animators,geometry=dict(board=board,local_size=size,camera='null',source='runtime_recttransform'),
        settings=values,scroll=dict(project_delta=float(scroll['project_delta']),game_delta=float(scroll['game_delta']),
            sign_verified=True,observed_events=scroll['observed_events']),monotonic_time=monotonic,
        execution_verified=False,game_response_verified=False,release_inertia_modelled=False)


def validate_stable_pair(first, second, *, position_tolerance=1e-5, scale_tolerance=1e-6, rotation_tolerance=1e-4):
    """Require same live identity, completed animators and a close second read."""
    if not all(math.isfinite(v) and v>=0 for v in (position_tolerance,scale_tolerance,rotation_tolerance)):
        raise ValueError('Finite nonnegative stability tolerances required')
    first=validate_observation(first);second=validate_observation(second)
    if second['monotonic_time']<=first['monotonic_time']: raise ValueError('Second observation must be later')
    for key in ('build_sha256','pid','process_creation_token','capture_id','session_token','pixel_sha256','geometry','settings','scroll'):
        if first[key]!=second[key]: raise ValueError(f'Observation binding changed: {key}')
    p1=np.asarray(first['pose']['position']);p2=np.asarray(second['pose']['position'])
    if np.max(np.abs(p1-p2))>position_tolerance or abs(first['pose']['scale']-second['pose']['scale'])>scale_tolerance or abs(first['pose']['rotation_degrees']-second['pose']['rotation_degrees'])>rotation_tolerance:
        raise ValueError('Pose is not stable')
    if any(not first['animator'][name]['is_done'] or not second['animator'][name]['is_done'] for name in ('position','rotation')):
        raise ValueError('Animator is still running')
    if any(first['animator'][name]['stop_requested'] or second['animator'][name]['stop_requested'] for name in ('position','rotation')):
        raise ValueError('Animator stop request is unresolved')
    return dict(stable=True,animators_done=True,session_token=first['session_token'],capture_id=first['capture_id'],
        pose=second['pose'],observation_times=[first['monotonic_time'],second['monotonic_time']],
        execution_verified=False,game_response_verified=False,release_inertia_modelled=False)
