"""Selected-window native acquisition and controller service; never confirms dye."""
import copy,ctypes,json,time,traceback,sys
from pathlib import Path
from platform_win import u
from window_target import resolve_target
from vision import configure_ocr
from native_palette_scoring import load_session
from native_input_response import InputSettings
from .native_provider_backend import CurrentBuildBackend
from .collect_dye_validation import collect_validation_session
from .project_probe_io import probe_layout_scale
from .project_closed_loop_io import ProjectClosedLoopIO
from .read_dye_input_backend import read_input_backend
from .probe_timer import prepare_timer_assets
from .dye_hex_glyphs import prepare_hex_assets
from .same_session_dye_planner import normalize_target_rules
from .controller import run_goal_loop
from .time_policy import SESSION_MAX_SECONDS
from dye_regions import session_region_count,bind_region_rules
from process_access import ProcessReadDenied
from .build_adapters import require_input_capability,enable_known_validation_input,KR_ADAPTER,JP_ADAPTER


def _prepare(pid,folder,check,hwnd=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    backend=None;diagnostic=dict(pid=pid,hwnd=hwnd,stage='ocr_assets',inputs_sent=0)
    def save():
        (folder/'native-preparation.json').write_text(json.dumps(diagnostic,indent=2,ensure_ascii=False),encoding='utf8')
    try:
        configure_ocr(strict=True);timer=prepare_timer_assets();glyphs=prepare_hex_assets()
        diagnostic['stage']='game_build';save()
        backend=CurrentBuildBackend(pid,output_root=folder/'native-captures')
        files=getattr(backend,'build_files',{})
        if isinstance(files,dict):diagnostic['build_files']={k:str(v) for k,v in files.items()}
        diagnostic['build_hashes']={k:v for k in ('version','metadata_version','unityplayer_version')
            if isinstance((v:=getattr(backend,k,None)),str)}
        if isinstance(getattr(backend,'build_diagnostic',None),dict):diagnostic['build_diagnostic']=backend.build_diagnostic
        if hwnd is not None:backend.window_hwnd=hwnd
        end=time.monotonic()+10.
        diagnostic['stage']='window_context';save()
        window=backend.observe_window_context(end,check)
        diagnostic['window_context']=window
        pixel_diagnostic=getattr(backend,'last_pixel_mapping_diagnostic',None)
        if isinstance(pixel_diagnostic,dict):diagnostic['pixel_mapping_diagnostics']=pixel_diagnostic
        if window['extent_one_to_one'] is not True and window.get('coordinate_mapping_verified') is not True:
            raise ValueError('Unity/client extents differ without verified input coordinate mapping')
        diagnostic['stage']='screenshot_layout';save()
        probe_layout_scale(*window['window']['client_size_physical'])
        diagnostic['stage']='input_backend';save()
        branch=read_input_backend(backend,end,check=check)
        diagnostic.update(stage='complete',input_backend=branch);save()
        selected_adapter=getattr(backend,'adapter',None)
        adapter_diagnostic=selected_adapter.diagnostic() if selected_adapter is not None else {}
        return backend,dict(window_context=window,input_backend=branch,timer_assets=timer,hex_assets=glyphs,
            build_adapter=adapter_diagnostic,
            pixel_mapping_diagnostics=diagnostic.get('pixel_mapping_diagnostics',{}))
    except BaseException as exc:
        from .build_adapters import BuildUnsupported
        if isinstance(exc,BuildUnsupported):diagnostic['build_diagnostic']=dict(hashes=exc.hashes,adapter='unsupported',inputs_sent=0)
        if backend is not None and isinstance(getattr(backend,'build_diagnostic',None),dict):diagnostic['build_diagnostic']=backend.build_diagnostic
        diagnostic['error']=type(exc).__name__+': '+str(exc)
        if isinstance(exc,ProcessReadDenied):
            diagnostic.update(stage='process_access',process_access=exc.diagnostic)
        failed=getattr(backend,'last_window_diagnostic',None)
        if isinstance(failed,dict):diagnostic['window_context']=failed
        try:save()
        except Exception as write_error:
            if not isinstance(exc,ProcessReadDenied):raise
            exc.diagnostic['preparation_write_error']=dict(error_type=type(write_error).__name__,
                win_error=getattr(write_error,'winerror',None),errno=getattr(write_error,'errno',None))
        if backend is not None:backend.close()
        raise


def unavailable_reason(error):
    if isinstance(error,ProcessReadDenied):return 'process_access'
    message=str(error)
    if '所选服务器与客户端版本不匹配' in message:return 'server_selection'
    if any(s in message for s in ('UnityPlayer module','GameAssembly module','supported game modules')):
        return 'module_resolution'
    if any(s in message for s in ('build','metadata')):return 'game_build'
    if any(s in message for s in ('extents differ','extent mismatch','viewport','coordinate','cursor conversion','pixel mapping')):
        return 'coordinate_mapping'
    if any(s in message for s in ('DPI','physical window','physical client')):return 'window_measurement'
    if any(s in message for s in ('Tesseract','OCR','文字识别组件')):return 'ocr_assets'
    return 'preparation'


def preflight(pid,folder,*,check=lambda:None,hwnd=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    backend=None;result=dict(actual_input_attempts=0,verified=False,accepted=False,server_confirmation_verified=False)
    try:
        backend,record=_prepare(pid,folder,check,hwnd)
        result.update(record,stop_reason='preflight_complete',pid=pid)
    except (ValueError,OSError,RuntimeError) as exc:
        result.update(stop_reason='unavailable',error=str(exc),unavailable_reason=unavailable_reason(exc),pid=pid)
        if isinstance(exc,ProcessReadDenied):result['process_access']=exc.diagnostic
    finally:
        if backend is not None:backend.close()
    (folder/'native-preflight.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def run_native_search(owner,rules,*,mode='search',target=None,activate=False,server=None,**unused):
    folder=Path(owner.folder);folder.mkdir(parents=True,exist_ok=True);backend=adapter=None
    result=dict(stop_reason='not_started',verified=False,accepted=False,target_exact=False,
        actual_colors=[None]*3,actual_deltas=[None]*3,actual_input_attempts=0,server_confirmation_verified=False)
    rules=normalize_target_rules(copy.deepcopy(rules));result['rules']=rules
    result['requested_rules']=copy.deepcopy(rules)
    u.GetAsyncKeyState.argtypes=[ctypes.c_int];u.GetAsyncKeyState.restype=ctypes.c_short
    def check():
        if owner.stop.is_set() or u.GetAsyncKeyState(0x78)&0x8000:
            owner.stop.set();raise InterruptedError('F9')
    def event(row):
        name=row['event'];stage={'armed':'waiting','session_discovered':'capture','palette_captured':'native_validate',
            'initial_validation':'native_validate','process_bound':'native_validate','window_validated':'native_validate',
            'discovery_progress':'discovery','discovery_blocked':'discovery',
            'planning':'search','action':'position','observed':'verify','initial_visual_wait':'native_validate',
            'compromise_selected':'position','observation_wait':'verify','target_approach':'position',
            'refinement_planning':'refinement','refinement_search_progress':'refinement'}.get(name)
        with (folder/'native-events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        if name=='native_observed':
            # Small actual-readback updates survive continuous routes, planning
            # references and full checks; predicted candidate colors stay out.
            owner.event('native_colors',colors=list(row['colors']),label=row.get('label'),
                screenshot_verified=row.get('screenshot_verified') is True)
            return
        if name in ('native_retry_available','native_retry_reset'):
            owner.event(name,**{key:value for key,value in row.items() if key!='event'})
            return
        if name in ('native_candidates','native_candidate_ready','native_candidate_selected','native_candidate_closed'):
            # Legacy diagnostic events never create predicted native choices.
            return
        message={'native_validate':'正在检查当前游戏与取色数据。','search':'正在计算可执行的目标方案。',
            'discovery':'正在准备寻色，暂时不要进入染色界面；等提示就绪后再开始。F9 可停止。',
            'position':'正在调整色板。','verify':'正在核对当前游戏色码。'}.get(stage)
        if name=='armed' or name=='discovery_progress' and row.get('phase')=='waiting':
            stage='waiting';message='寻色已就绪，请进入染色界面；工具正在等待活动色板。F9 可停止。'
        if name=='discovery_progress' and row.get('discovery',{}).get('eligible_addresses'):
            stage='binding';message='已检测到活动色板，正在完成本局识别；请保持游戏窗口前台。F9 可停止。'
        if name=='compromise_selected':message='未找到精准方案，正在定位并复核色差较小的妥协方案。'
        if name=='target_approach':message='已找到目标色板位置，正在定位并复核。'
        if name=='action' and row.get('purpose')=='refine':message='正在细化颜色，已预留恢复时间。'
        if name=='action' and row.get('purpose') in ('restore_refinement','restore_retry'):message='正在恢复已验证的颜色。'
        if stage:
            payload={k:v for k,v in row.items() if k not in ('event','stage','message','discovery','phase_seconds')}
            # Runner.event reserves ``kind`` for the event name. Native action
            # records also have a gesture kind, so forward it under a distinct
            # key instead of causing a duplicate-key TypeError.
            if 'kind' in payload:payload['action_kind']=payload.pop('kind')
            owner.event('native_progress',stage=stage,message=message,**payload)
    try:
        if mode!='search':raise ValueError('Native strategy only supports user color search')
        check();selected=resolve_target(target,server=server)
        owner.event('window_bound',title=selected.title,pid=selected.pid,hwnd=selected.hwnd)
        owner.event('native_progress',stage='native_validate',message='正在检查当前游戏与取色数据。')
        if activate:
            from window_target import activate_target_window
            check()
            if not activate_target_window(selected):raise InterruptedError('无法激活游戏。请点击游戏后按 F8。')
        backend,prepared=_prepare(selected.pid,folder,check,selected.hwnd)
        result['preflight']=prepared
        if server is not None:
            from .build_adapters import enable_selected_server_input
            enable_selected_server_input(backend,server)
            result['selected_server']=server
        validation=[a for flag,a in (('--validate-korean-build',KR_ADAPTER),('--validate-japanese-build',JP_ADAPTER)) if flag in sys.argv]
        if server is None:
            if len(validation)>1:raise ValueError('Choose one server validation launch')
            if validation:enable_known_validation_input(backend,validation[0].adapter_id)
        selected_adapter=getattr(backend,'adapter',None)
        if selected_adapter is not None:
            result['build_adapter']=dict(selected_adapter.diagnostic(),
                validation_input_enabled=getattr(backend,'validation_input_enabled',False) is True)
        require_input_capability(backend)
        baseline=collect_validation_session(backend,wait_seconds=300.,session_seconds=SESSION_MAX_SECONDS,check=check,event=event)
        (folder/'native-baseline.json').write_text(json.dumps(baseline,indent=2),encoding='utf-8')
        if baseline['stop_reason']!='passive_baseline_collected':result['stop_reason']=baseline['stop_reason']
        else:
            check();session=load_session(baseline['capture']['capture_folder'])
            count=session_region_count(session)
            result.update(region_count=count,available_regions=[i<count for i in range(3)],
                          actual_colors=[None]*count,actual_deltas=[None]*count)
            effective=copy.deepcopy(rules[:count])
            owner.event('region_layout',region_count=count,available_regions=result['available_regions'],rules=effective)
            if not any(r['enabled'] for r in effective):
                result.update(rules=effective,stop_reason='no_available_regions')
                raise ValueError('No enabled targets exist on this dye board')
            rules=normalize_target_rules(bind_region_rules(rules,count));result['rules']=rules
            settings=InputSettings(**baseline['baseline']['motion']['settings'])
            adapter=ProjectClosedLoopIO(backend,baseline,folder/'native-actions',stop=owner.stop)
            retry=getattr(owner,'consume_retry_request',None)
            options=dict(retry_requested=retry) if callable(retry) else {}
            extension=baseline.get('timer_deadline_extension')
            if isinstance(extension,dict):options['timer_deadline_extension']=extension
            if 'session_first_seen_monotonic' in baseline and 'timer_grace_until' in baseline:
                options['timer_grace_baseline']=baseline
            result.update(run_goal_loop(adapter,session,settings,rules,
                engineering_deadline=baseline['session_deadline_monotonic'],event=event,**options))
    except InterruptedError as exc:result.update(stop_reason='interrupted',error=str(exc))
    except (ValueError,OSError,RuntimeError) as exc:
        result.update(stop_reason='no_available_regions' if result.get('stop_reason')=='no_available_regions' else 'unavailable',error=type(exc).__name__+': '+str(exc),
            unavailable_reason=unavailable_reason(exc))
        if isinstance(exc,ProcessReadDenied):result['process_access']=exc.diagnostic
    except Exception as exc:result.update(stop_reason='internal_error',error=type(exc).__name__+': '+str(exc),
                                         error_traceback=traceback.format_exc())
    finally:
        if adapter is not None:
            result['actual_input_attempts']=adapter.input_attempts
            try:adapter.release()
            except Exception as exc:result['release_error']=str(exc)
        if backend is not None:backend.close()
    if result['stop_reason']=='interrupted':
        error=result.get('error','')
        result['interruption_reason']=('focus_lost' if '游戏失去焦点' in error else
            'window_changed' if '窗口位置或尺寸' in error else 'activation_failed' if '无法激活游戏' in error else 'user_stop')
    values=[v for v in result['actual_deltas'] if v is not None]
    result.update(maximum=max(values) if values else None,average=sum(values)/len(values) if values else None,
        outcome='matched' if result['accepted'] else 'compromise' if result['stop_reason'] in ('compromise_observed','user_candidate_observed')
            and result['verified'] else 'not_found' if result['stop_reason']=='not_found_in_budget' else 'stopped')
    (folder/'native-result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    # The full result is already persisted on disk. Keep the UI event small so
    # Tk can process the terminal event and re-enable controls immediately;
    # multi-megabyte planning rounds belong to the session artifact only.
    owner.event('native_result',**{key:result.get(key) for key in (
        'stop_reason','outcome','accepted','verified','target_exact',
        'actual_colors','actual_deltas','best_actual_colors',
        'actual_input_attempts','maximum','average','restored','best_current','screenshot_verified',
        'server_confirmation_verified','enabled_regions','rules','region_count','available_regions',
        'selected_server',
        'refinement_stop','unavailable_reason','session_stop_reason','interruption_reason',
        'last_verified_colors','last_verified_deltas','last_verified_captured_monotonic',
        'last_verified_screenshot')})
    return result
