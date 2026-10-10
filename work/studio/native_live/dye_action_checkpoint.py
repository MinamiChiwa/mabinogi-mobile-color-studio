"""Bounded read-only checkpoints and conditional assessment of external UI actions."""
import copy,json,math,re,time
import numpy as np
from .read_dye_motion import UnsupportedSlotDelegate


def _binding(observation):
    motion=observation['motion']
    # Session artifacts use JSON arrays; live backend tokens use tuples.
    # Compare their content, preserving every identity and geometry field.
    window=copy.deepcopy(observation['window_context'])
    window.get('window',{}).pop('foreground',None)
    return json.dumps((observation['session_token'],observation['process_identity'],motion['binding'],
            motion['settings'],window),sort_keys=True,allow_nan=False)


def _settled(observation):
    cache=observation['geometry_diagnostic']['rect']['cache']
    return (observation.get('active') is True and observation['motion']['animators_done'] is True
            and cache.get('local_refresh_pending') is False and cache.get('cache_origin_consistent') is True)


def record_action_checkpoint(backend,baseline,label,*,timeout_seconds=5.,dwell_seconds=.3,
        poll_seconds=.1,max_errors=10,clock=time.monotonic,pause=time.sleep,check=lambda:None):
    if not isinstance(label,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}',label):raise ValueError('Invalid checkpoint label')
    for value,upper in ((timeout_seconds,10),(dwell_seconds,2),(poll_seconds,1)):
        if isinstance(value,bool) or not math.isfinite(value) or not 0<value<=upper:raise ValueError('Invalid checkpoint time bound')
    if type(max_errors) is not int or not 1<=max_errors<=30:raise ValueError('Invalid checkpoint retry bound')
    check();start=clock();session_end=baseline['session_deadline_monotonic']
    if not math.isfinite(session_end) or session_end<=start:raise TimeoutError('Session deadline already expired')
    end=min(session_end,start+timeout_seconds);original=baseline['baseline'];expected=_binding(original)
    result=dict(label=label,checkpoint_valid=False,ready_for_input=False,inputs_sent=0,errors=[],samples=[],
                screenshot_hex_verified=False,read_started_monotonic=start,stop_reason='not_started')
    stable=None;since=None
    def guard():
        check()
        if clock()>=end:raise TimeoutError('Checkpoint deadline expired')
    while clock()<end:
        try:
            guard();row=backend.observe_motion(baseline['instance_address'],end,guard,clock=clock,
                include_geometry=True,include_window=True)
            if row.get('active') is not True:result['stop_reason']='palette_ended';break
            if _binding(row)!=expected:result['stop_reason']='binding_changed';break
            state=(row['motion']['pose'],row['geometry_diagnostic'],row['window_mapping_candidate'])
            result['samples'].append(dict(time=clock(),observation=row))
            if not _settled(row):stable=since=None
            elif state!=stable:stable=copy.deepcopy(state);since=clock()
            if since is not None and clock()-since>=dwell_seconds-1e-9:
                captured=backend.capture_validation_bundle(baseline['instance_address'],end,guard,clock=clock)
                final=backend.observe_motion(baseline['instance_address'],end,guard,clock=clock,
                    include_geometry=True,include_window=True)
                if _binding(final)!=expected:result['stop_reason']='binding_changed';break
                final_state=(final['motion']['pose'],final['geometry_diagnostic'],final['window_mapping_candidate'])
                if (captured.get('session_binding_verified') is not True or captured['session_token']!=row['session_token']
                    or captured['process_identity']!=row['process_identity'] or captured['pose']!=row['motion']['pose']
                    or final_state!=state or not _settled(final)):
                    raise ValueError('Checkpoint pose/session changed during color export')
                result.update(observation=final,capture=captured,checkpoint_valid=True,stop_reason='checkpoint_collected')
                break
        except UnsupportedSlotDelegate as exc:
            result['errors'].append(dict(type=type(exc).__name__,message=str(exc),code=exc.code,details=exc.details))
            result['stop_reason']='unsupported_motion_binding';break
        except (ValueError,OSError) as exc:
            result['errors'].append(dict(type=type(exc).__name__,message=str(exc)))
            stable=since=None
            if isinstance(exc,TimeoutError) and clock()>=end:break
            if len(result['errors'])>=max_errors:result['stop_reason']='read_failure_limit';break
        pause(min(poll_seconds,max(0.,end-clock())))
    if result['stop_reason']=='not_started':result['stop_reason']='checkpoint_deadline'
    diagnostics=getattr(backend,'last_pixel_mapping_diagnostic',None)
    if isinstance(diagnostics,dict):result['pixel_mapping_diagnostics']=copy.deepcopy(diagnostics)
    result['read_finished_monotonic']=clock()
    return result


def assess_checkpoint_transition(before,after,action):
    if before.get('checkpoint_valid') is not True or after.get('checkpoint_valid') is not True:
        raise ValueError('Two valid checkpoints required')
    first=before['observation'];last=after['observation']
    if _binding(first)!=_binding(last) or not _settled(first) or not _settled(last):
        raise ValueError('Checkpoint binding/settled state mismatch')
    times=[before[k] for k in ('read_started_monotonic','read_finished_monotonic')]+[after[k] for k in ('read_started_monotonic','read_finished_monotonic')]
    if not all(math.isfinite(v) for v in times) or not times[0]<=times[1]<times[2]<=times[3]:
        raise ValueError('Checkpoint time order invalid')
    if first['geometry_diagnostic']!=last['geometry_diagnostic'] or first['window_mapping_candidate']!=last['window_mapping_candidate']:
        raise ValueError('Geometry changed across action')
    if action.get('input_source')!='computer_use_sky' or action.get('kind') not in ('drag','wheel'):
        raise ValueError('Explicit supported UI action receipt required')
    points=np.asarray(action.get('client_points'),dtype=float);kind=action['kind']
    if points.shape!=((2,2) if kind=='drag' else (1,2)) or not np.isfinite(points).all():raise ValueError('Invalid action points')
    l,t,r,b=first['window_mapping_candidate']['client_board_candidate']
    if not np.all((points[:,0]>l)&(points[:,0]<r)&(points[:,1]>t)&(points[:,1]<b)):raise ValueError('Action outside board')
    p0=first['motion']['pose'];p1=last['motion']['pose'];settings=first['motion']['settings']
    result=dict(kind=kind,measured_position_change=(np.asarray(p1['position'])-p0['position']).tolist(),
        measured_scale_ratio=p1['scale']/p0['scale'],measured_rotation_change=p1['rotation_degrees']-p0['rotation_degrees'],
        cpu_client_colors_consistent=all(c['capture']['cpu_comparison']['client_float_hex_equal'] and
            c['capture']['cpu_comparison']['float_within_tolerance'] for c in (before,after)),
        actual_point_sampling_verified=False,adapter_calibration_verified=False,screenshot_hex_verified=False,
        ready_for_input=False,server_confirmation_verified=False,
        scope='Bound separated stable read checkpoints and external UI receipt; no hidden events, release velocity or action timing inferred')
    if kind=='drag':
        delta=points[1]-points[0];rect=first['geometry_diagnostic']['rect']['cache']['cached_local_rect']
        local_delta=delta*np.asarray(rect[2:])/[r-l,b-t]
        result.update(requested_drag_pixels=delta.tolist(),endpoint_local_distance=float(np.linalg.norm(local_delta)),
            endpoint_crosses_start_gate=bool(np.linalg.norm(local_delta)>=settings['move_threshold']),
            conditional_normalized_displacement=[float(delta[0]/(r-l)),float(-delta[1]/(b-t))])
    else:
        scroll=action.get('scroll_y')
        if type(scroll) not in (int,float) or not math.isfinite(scroll) or scroll==0:raise ValueError('Explicit nonzero scroll submission required')
        ratio=result['measured_scale_ratio'];zoom=settings['scroll_zoom_ratio']
        clamped=(p1['scale']<=settings['minimum_scale'] or p1['scale']>=settings['maximum_scale'])
        inferred=(ratio-1)/zoom if zoom>0 and not clamped else None
        result.update(submitted_scroll_y=scroll,inferred_game_scroll_delta=inferred,
            inference_assumptions='One recognized scroll event, no clamp and no concurrent gesture; a net delta is not event instrumentation')
    return result
