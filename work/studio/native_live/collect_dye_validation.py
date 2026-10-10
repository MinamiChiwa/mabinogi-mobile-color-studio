"""Arm a bounded, passive new-session palette/geometry validation baseline."""
import argparse
import copy
import datetime
import json
import math
import time
from pathlib import Path
from .read_dye_motion import UnsupportedSlotDelegate


def collect_validation_session(backend, *, wait_seconds=300.,session_seconds=90.,poll_seconds=.2,
        dwell_seconds=.5,max_errors=30,max_samples=100,clock=time.monotonic,pause=time.sleep,
        check=lambda:None,event=lambda row:None):
    for value,upper in ((wait_seconds,300),(session_seconds,120),(poll_seconds,2),(dwell_seconds,5)):
        if isinstance(value,bool) or not math.isfinite(value) or not 0<value<=upper:
            raise ValueError('Invalid passive validation time bound')
    if type(max_errors) is not int or not 1<=max_errors<=100:raise ValueError('Invalid error bound')
    if type(max_samples) is not int or not 3<=max_samples<=500:raise ValueError('Invalid sample bound')
    result=dict(stop_reason='not_started',samples=[],errors=[],inputs_sent=0,ready_for_input=False,
        existing_active_palette=False,
        actual_corner_measurement_verified=False,screenshot_hex_verified=False,server_confirmation_verified=False)
    check();start=clock();deadline=start+30.
    class Expired(Exception):pass
    def guard():
        check()
        if clock()>=deadline:raise Expired()
    def emit(name,**data):
        event(dict(event=name,at_monotonic=clock(),**data))
    address=None;capture=None;binding=None;stable=None;stable_since=None;sample_count=0
    try:
        identity=backend.process_identity();guard()
        context=backend.observe_window_context(deadline,guard,clock=clock)
        if context.get('extent_one_to_one') is not True and context.get('coordinate_mapping_verified') is not True:
            raise ValueError('Unity/client extents differ without verified input coordinate mapping')
        old=backend.discover(deadline,guard);guard()
        result['preflight_window_context']=context;result['process_identity']=identity
        deadline=clock()+wait_seconds;result['waiting_deadline_monotonic']=deadline
        existing=old is not None and backend.probe(old,deadline,guard).get('active') is True
        emit('armed',waiting_deadline_monotonic=deadline,inputs_sent=0,
             existing_active_palette=bool(existing))
        if existing:
            result['existing_active_palette']=True;address=old
            # A palette already open at arming has an unknown age. Additional
            # caller allowance cannot establish that a fresh 120 s round began.
            deadline=clock()+min(session_seconds,90.)
            result['instance_address']=address;result['session_deadline_monotonic']=deadline
            guard();emit('session_discovered',instance_address=address,
                         session_deadline_monotonic=deadline,existing_active_palette=True)
        while address is None:
            guard();scan_started=clock()
            candidate=backend.discover(deadline,guard);guard()
            if backend.process_identity()!=identity:raise OSError('Process changed after arming')
            if candidate is None:
                pause(min(poll_seconds,max(0.,deadline-clock())));continue
            address=candidate
            deadline=scan_started+session_seconds
            result['instance_address']=address;result['session_deadline_monotonic']=deadline
            guard();emit('session_discovered',instance_address=address,session_deadline_monotonic=deadline)
        while sample_count<max_samples:
            guard();read_start=clock()
            try:
                if capture is None:
                    capture=backend.capture_validation_bundle(address,deadline,guard,clock=clock)
                    if capture.get('session_binding_verified') is not True:raise ValueError('Unbound palette export')
                    if capture.get('process_identity')!=identity:raise ValueError('Capture process identity mismatch')
                    result['capture']=capture
                    emit('palette_captured',capture_folder=capture['capture_folder'],cpu_comparison=capture['cpu_comparison'])
                    comparison=capture['cpu_comparison']
                    if comparison.get('client_float_hex_equal') is not True or comparison.get('float_within_tolerance') is not True:
                        result['stop_reason']='cpu_color_mismatch';break
                observation=backend.observe_motion(address,deadline,guard,clock=clock,
                    include_geometry=True,include_window=True)
                guard()
                if observation.get('active') is not True:
                    result['stop_reason']='palette_ended';break
                if (observation.get('session_token')!=capture['session_token']
                        or observation.get('process_identity')!=identity):
                    result['stop_reason']='binding_changed';break
                motion=observation['motion'];geometry=observation['geometry_diagnostic']
                if motion['pose']!=capture['pose']:
                    result['stop_reason']='pose_changed_since_capture';break
                mapping=observation['window_mapping_candidate'];window=observation['window_context']
                key=(motion['binding'],motion['settings'],window)
                if binding is None:binding=copy.deepcopy(key)
                elif binding!=key:
                    result['stop_reason']='binding_changed';break
                now=clock();sample_count+=1
                state=(motion['pose'],geometry,mapping)
                cache=geometry['rect']['cache']
                settled=(motion['animators_done'] is True and cache.get('local_refresh_pending') is False
                         and cache.get('cache_origin_consistent') is True)
                if not settled:stable=stable_since=None
                elif stable!=state:stable=copy.deepcopy(state);stable_since=now
                dwell=0. if stable_since is None else now-stable_since
                result['samples'].append(dict(index=sample_count-1,read_started_monotonic=read_start,
                    read_finished_monotonic=now,read_seconds=now-read_start,observation=observation,
                    stable_observed_seconds=dwell))
                if settled and dwell>=dwell_seconds-1e-9:
                    result['baseline']=observation;result['stop_reason']='passive_baseline_collected'
                    emit('baseline_collected',client_board_candidate=mapping.get('client_board_candidate'),
                         session_deadline_monotonic=deadline,ready_for_input=False)
                    break
                emit('sample',index=sample_count-1,read_seconds=now-read_start,settled_candidate=settled)
            except (ValueError,OSError) as exc:
                stable=stable_since=None
                diagnostic=dict(time=clock(),type=type(exc).__name__,message=str(exc))
                if isinstance(exc,UnsupportedSlotDelegate):
                    diagnostic.update(code=exc.code,details=exc.details)
                result['errors'].append(diagnostic)
                if isinstance(exc,UnsupportedSlotDelegate):
                    result['stop_reason']='unsupported_motion_binding'
                    emit('binding_rejected',code=exc.code,details=exc.details)
                    break
                emit('read_retry',attempt=len(result['errors']),error=str(exc))
                if len(result['errors'])>=max_errors:
                    result['stop_reason']='read_failure_limit';break
            pause(min(poll_seconds,max(0.,deadline-clock())))
        else:result['stop_reason']='sample_limit'
    except Expired:
        result['stop_reason']='no_active_palette_timeout' if address is None else 'session_deadline'
    finally:
        result['elapsed_seconds']=max(0.,clock()-start)
    return result


def main():
    from .native_provider_backend import CurrentBuildBackend
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pid',type=int);parser.add_argument('--wait-seconds',type=float,default=300.)
    parser.add_argument('--session-seconds',type=float,default=90.)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();utc=datetime.datetime.now(datetime.timezone.utc)
    destination=args.output or Path('outputs/verification/validation_run_'+utc.strftime('%Y%m%dT%H%M%S_%fZ')+'.json')
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():raise ValueError('Validation destination already exists')
    state_file=destination.with_suffix('.state.json');events_file=destination.with_suffix('.events.jsonl')
    if state_file.exists() or events_file.exists():raise ValueError('Validation sidecars already exist')
    backend=None;result=None
    def emit(row):
        payload=dict(row,pid=args.pid,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     output=str(destination.resolve()),inputs_sent=0,ready_for_input=False)
        encoded=json.dumps(payload,ensure_ascii=False)
        with events_file.open('a',encoding='utf-8') as stream:stream.write(encoded+'\n')
        state_file.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
        print(encoded,flush=True)
    try:
        backend=CurrentBuildBackend(args.pid)
        result=collect_validation_session(backend,wait_seconds=args.wait_seconds,
            session_seconds=args.session_seconds,event=emit)
    except KeyboardInterrupt:
        result=dict(stop_reason='interrupted',inputs_sent=0,ready_for_input=False)
    except (ValueError,OSError) as exc:
        result=dict(stop_reason='unavailable',error=type(exc).__name__+': '+str(exc),inputs_sent=0,ready_for_input=False)
    finally:
        if backend is not None:backend.close()
        if result is not None:
            result.update(pid=args.pid,started_at_utc=utc.isoformat(),finished_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            destination.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
            emit(dict(event='finished',stop_reason=result['stop_reason'],samples=len(result.get('samples',[]))))
