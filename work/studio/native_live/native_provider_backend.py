"""Experimental current-build backend; readonly, no Runner or UI wiring."""
import sys, struct, hashlib, ctypes, time, math, json
import numpy as np
from pathlib import Path
from dye_regions import region_count,session_region_count
from .runtime_read import Reader, K
from .capture_dye_state import checked_object, mm_items, snapshot
from .scan_live_dye import inspect, scan
from native_palette_scoring import load_session
from native_palette_model import picker_view_uv,distort_cpu_uv,sample_cpu,color32
from native_runtime_bridge import read_bound_stable_pair
from .read_dye_motion import read_dye_motion
from .read_toucharea_geometry import read_toucharea_geometry_cache
from .read_dye_window import read_window_state, _Win32WindowAPI
from .read_unity_screen import unityplayer_module_base, read_unity_screen_extent
from .read_dye_window_mapping import read_pixel_mapping,validate_pixel_mapping
from .read_native_mouse_diagnostic import read_native_mouse_cache
from .map_unity_window import map_unity_geometry_to_client
from .build_layout import resolve_build_files
from ctypes import wintypes

EXPECTED_BUILD='1675c2131534d0ab2fc053af8a2e394d326ba7d22eff0019734be96b1808678f'
EXPECTED_METADATA='3f6827a41d26ab50ef0051b881cb2c6dcab0c12aab5e95cc7da0071fae63a847'
UNINITIALIZED_DYE_CLASS_TOKEN=0x20035507

class DyeClassUnavailable(ValueError):
    pass

class GuardedReader(Reader):
    guard = staticmethod(lambda: None)
    def read(self, address, size):
        self.guard()
        result = super().read(address, size)
        self.guard()
        return result
    def regions(self):
        for region in super().regions():
            self.guard()
            yield region


class CurrentBuildBackend:
    def __init__(self, pid, *, output_root=None):
        self.reader = GuardedReader(pid)
        self.output_root=Path(output_root) if output_root is not None else Path.cwd()/'native-captures'
        creation, exit_time, kernel, user = (wintypes.FILETIME() for _ in range(4))
        K.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        if not K.GetProcessTimes(self.reader.h, *(ctypes.byref(v) for v in (creation, exit_time, kernel, user))):
            self.reader.close()
            raise OSError('Process creation identity unavailable')
        self.creation = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        try:
            self.build_files=resolve_build_files(self.reader.module_files)
            self.version = hashlib.sha256(self.build_files['gameassembly'].read_bytes()).hexdigest()
            self.metadata_version = hashlib.sha256(self.build_files['metadata'].read_bytes()).hexdigest()
            self.unityplayer_version = hashlib.sha256(self.build_files['unityplayer'].read_bytes()).hexdigest()
        except BaseException:
            self.reader.close();raise
        if self.version!=EXPECTED_BUILD or self.metadata_version!=EXPECTED_METADATA:
            self.reader.close()
            raise ValueError('Unsupported game/metadata build for static object walk')
        self.base = self.reader.base
        self.scans = self.exports = 0

    def process_identity(self):
        code = wintypes.DWORD()
        K.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        if not K.GetExitCodeProcess(self.reader.h, ctypes.byref(code)) or code.value != 259:
            raise OSError('Process ended')
        return (self.reader.pid, self.creation, self.base, self.version)

    def _bind(self, check):
        self.reader.guard = check
        check()
        cls = self.reader.u64(self.base + 0x106c9010)
        if cls in (0,UNINITIALIZED_DYE_CLASS_TOKEN):
            raise DyeClassUnavailable('Dye class not initialized')
        if cls < 0x100000000 or self.reader.class_name(cls) != 'MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl':
            raise ValueError('Dye class not initialized or build mismatch')
        return cls

    def discover(self, deadline, check):
        try:
            self._bind(check)
        except DyeClassUnavailable:
            return None
        self.scans += 1
        hits, _, _, _ = scan(self.reader, capture=False)
        eligible = [h for h in hits if h['capture_eligible']]
        if len(eligible) != 1:
            return None
        return int(eligible[0]['address'], 16)

    def probe(self, address, deadline, check):
        r = self.reader
        cls = self._bind(check)
        state = inspect(r, address, cls)
        if not state or not state['capture_eligible']:
            return dict(active=False, session_token=None, pose=None)
        fields = checked_object(r, address, 'MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl')
        result = r.u64(address + fields['resultCache'])
        before = r.read(result + 16, 16)
        data = r.u64(address + fields['data'])
        df = checked_object(r, data, 'Client.CodeGenerated.UI.DyeingPaletteControlData')
        fragment_list = r.u64(data + df['PaletteFragmentDataList'])
        array, count = mm_items(r, fragment_list)
        count = region_count(count)
        if len(state['native_textures']) != count:
            raise ValueError('Fragment and texture region counts disagree')
        colors_list = r.u64(address + fields['colorPickerColors'])
        color_array, color_count = mm_items(r, colors_list)
        if color_count != count:
            raise ValueError('Fragment and picker color region counts disagree')
        fingerprints = []
        for i in range(count):
            fragment = r.u64(array + 32 + i * 8)
            ff = checked_object(r, fragment, 'Client.CodeGenerated.UI.DyeingPaletteFragmentData')
            palette = r.u64(fragment + ff['Palette'])
            pf = checked_object(r, palette, 'Shared.DyePalette.DyePalette')
            dimensions = tuple(struct.unpack('<i', r.read(palette + pf[key], 4))[0] for key in ('Width','Height','Channels'))
            raw_array = r.u64(palette + pf['Data'])
            if dimensions != (254,254,3) or r.u64(raw_array + 24) != 254*254*3:
                raise ValueError('Unexpected palette byte layout')
            fingerprints.append((palette, hashlib.sha256(r.read(raw_array + 32, 254*254*3)).hexdigest(),
                                 r.read(fragment + ff['NormalizedPositionY'], 4).hex()))
        ratio = r.read(data + df['ColorPreserveRatio'], 4).hex()
        after = r.read(result + 16, 16)
        if (before != after or state != inspect(r, address, cls)
                or fragment_list != r.u64(data + df['PaletteFragmentDataList'])
                or mm_items(r, fragment_list) != (array, count)
                or colors_list != r.u64(address + fields['colorPickerColors'])
                or mm_items(r, colors_list) != (color_array, count)):
            raise ValueError('Palette changed during probe')
        x,y,scale,rotation = struct.unpack('<4f', after)
        token = (address, data, state['active_result'], tuple(state['native_textures']), state['native_material'],
                 tuple(fingerprints), ratio)
        return dict(active=True, session_token=token,region_count=count,
                    pose=dict(position=[x,y], scale=scale, rotation_degrees=rotation))

    def capture(self, address, deadline, check):
        self._bind(check)
        folder, _ = snapshot(self.reader, address, 'provider_capture',output_root=self.output_root)
        check()
        self.exports += 1
        return load_session(folder)

    def capture_validation_bundle(self,address,deadline,check,*,clock=time.monotonic):
        """Export a bound active palette and compare CPU with recorded float colors."""
        if not math.isfinite(deadline):raise ValueError('Finite capture deadline required')
        def guard():
            check()
            if clock()>=deadline:raise TimeoutError('Validation capture deadline expired')
        guard();identity=self.process_identity();before=self.probe(address,deadline,guard)
        if before.get('active') is not True:raise ValueError('No active palette for validation capture')
        count=region_count(before['region_count'])
        self.reader.guard=guard;started=clock()
        folder,record=snapshot(self.reader,address,'validation_capture',output_root=self.output_root)
        folder=Path(folder);binding_file=folder/'validation_binding.json'
        binding=dict(session_binding_verified=False,ready_for_input=False,screenshot_hex_verified=False,
            server_confirmation_verified=False,process_identity=identity,session_token=before['session_token'],region_count=count)
        binding_file.write_text(json.dumps(binding,indent=2),encoding='utf-8')
        try:
            guard();after=self.probe(address,deadline,guard)
            if (after.get('active') is not True or after.get('session_token')!=before['session_token']
                    or after.get('pose')!=before.get('pose') or after.get('region_count')!=count):
                raise ValueError('Session/pose changed during palette export')
            if self.process_identity()!=identity:raise OSError('Process changed during palette export')
            token=after['session_token'];fragments=record['fragments']
            pose=dict(position=record['position'],scale=record['scale'],rotation_degrees=record['rotation_degrees'])
            if (record['pid']!=identity[0] or int(record['instance_address'],16)!=address
                    or pose!=after['pose'] or len(fragments)!=count or record.get('region_count')!=count
                    or len(token[3])!=count or len(token[5])!=count
                    or int(record['active_result_pointer'],16)!=int(token[2],16)):
                raise ValueError('Export attribution/pose mismatch')
            captured=tuple((int(f['resource_object'],16),f['raw_sha256'],struct.pack('<f',f['normalized_picker_y']).hex()) for f in fragments)
            if captured!=token[5] or struct.pack('<f',record['color_preserve_ratio']).hex()!=token[6]:
                raise ValueError('Export pixel/picker fingerprint mismatch')
            guard();session=load_session(folder);predicted=[]
            if session_region_count(session)!=count:raise ValueError('Export session region count mismatch')
            for index,uv in enumerate(session['picker_uv']):
                guard()
                coord=distort_cpu_uv(picker_view_uv(index,count,uv[1],pose['position'],pose['scale'],pose['rotation_degrees']))
                predicted.append(sample_cpu(session['pixels'][index],coord,session['color_preserve_ratio'])/np.float32(255))
            predicted=np.asarray(predicted,dtype=np.float32);observed=np.asarray(record['picker_colors_rgba'],dtype=np.float32)
            if observed.shape!=(count,4) or not np.isfinite(observed).all():raise ValueError('Invalid captured client colors')
            codes=lambda rows:['#%02X%02X%02X'%tuple(int(v) for v in color32(row)) for row in rows]
            predicted_hex=codes(predicted);client_hex=codes(observed[:,:3])
            difference=float(np.max(np.abs(predicted-observed[:,:3])))
            comparison=dict(predicted_rgb=predicted.tolist(),client_float_rgb=observed[:,:3].tolist(),
                predicted_hex=predicted_hex,client_float_hex=client_hex,client_float_hex_equal=predicted_hex==client_hex,
                max_float_channel_error=difference,float_tolerance=2e-7,float_within_tolerance=difference<=2e-7,
                screenshot_hex_verified=False,server_confirmation_verified=False)
            guard();binding.update(session_binding_verified=True,read_seconds=clock()-started,cpu_comparison=comparison)
            binding_file.write_text(json.dumps(binding,indent=2),encoding='utf-8');self.exports+=1
            return dict(capture_folder=str(folder.resolve()),pose=pose,**binding)
        except BaseException as exc:
            binding['error']=type(exc).__name__+': '+str(exc)
            binding_file.write_text(json.dumps(binding,indent=2),encoding='utf-8')
            raise

    def observe_bound_stable(self, instance, control_candidates, first_context,
                             second_context, layout, check):
        """Read a settled bound control chain; never discovers by guessing.

        ``control_candidates`` and the explicit RuntimeLayout must come from a
        guarded, build-specific discoverer. This method only adds process
        identity, performs two read-only observations, and verifies identity
        remains unchanged before returning.
        """
        check()
        identity=self.process_identity()
        def bind_context(context):
            if not isinstance(context,dict):
                raise ValueError('Observation context must be a mapping')
            for key,value in (('pid',identity[0]),('process_creation_token',identity[1]),
                              ('build_sha256',identity[3])):
                if key in context and context[key]!=value:
                    raise ValueError(f'Runtime identity mismatch: {key}')
            result=dict(context,pid=identity[0],process_creation_token=identity[1],build_sha256=identity[3])
            return result
        first=bind_context(first_context);second=bind_context(second_context)
        result=read_bound_stable_pair(self.reader,instance,control_candidates,first,second,layout,check=check)
        check()
        if self.process_identity()!=identity:
            raise OSError('Process identity changed during observation')
        return result

    def observe_window_context(self,deadline,check,*,clock=time.monotonic,window_api=None):
        """Repeated physical client and native Unity extent, no focus/input changes."""
        if not math.isfinite(deadline):raise ValueError('Finite window observation deadline required')
        def guard():
            check()
            if clock()>=deadline:raise TimeoutError('Window observation deadline expired')
        guard();identity=self.process_identity();self.reader.guard=guard
        if not hasattr(self,'unityplayer_base'):
            files=getattr(self,'build_files',{})
            self.unityplayer_base=unityplayer_module_base(self.reader,
                expected_path=files.get('unityplayer'),check=guard)
        screen=read_unity_screen_extent(self.reader,self.unityplayer_base,
            unityplayer_sha256=self.unityplayer_version,check=guard)
        api=window_api or _Win32WindowAPI()
        hwnd=getattr(self,'window_hwnd',None) or screen.get('hwnd') or None
        self.last_window_diagnostic=dict(unity_screen=screen,process_identity=identity,ready_for_input=False)
        def read_bound_window(handle):
            try:return read_window_state(identity[0],hwnd=handle,api=api,check=guard)
            except (ValueError,OSError) as exc:
                partial=getattr(exc,'diagnostic',None)
                if isinstance(partial,dict):self.last_window_diagnostic['window']=partial
                raise
        if hwnd is None:
            # Auxiliary windows can appear when the game receives focus.
            # Bind once by independently read Unity extent, never by list order.
            candidates=[]
            for handle in api.windows(identity[0]):
                guard()
                row=read_bound_window(handle)
                if row['client_size_physical']==screen['size']:candidates.append(row)
            if len(candidates)!=1:raise ValueError('Expected one game window matching native Unity extent')
            first=candidates[0]
        else:first=read_bound_window(hwnd)
        second=read_bound_window(first['hwnd'])
        screen_after=read_unity_screen_extent(self.reader,self.unityplayer_base,
            unityplayer_sha256=self.unityplayer_version,check=guard)
        self.last_window_diagnostic=dict(window=first,unity_screen=screen,
            process_identity=identity,extent_one_to_one=first['client_size_physical']==screen['size'],
            ready_for_input=False)
        if first!=second or screen!=screen_after:raise ValueError('Window/Unity screen context changed')
        if screen.get('hwnd') is not None and screen['hwnd']!=first['hwnd']:
            raise ValueError('Native Screen window handle differs from selected game window')
        equal=first['client_size_physical']==screen['size'];pixel_mapping=None
        diagnostics={}
        if not equal:
            # Real runtime Screen reads include the selected native HWND. Old
            # offline records cannot authorize an unmeasured scaled lattice.
            if not screen.get('hwnd'):raise ValueError('Bound game window/Unity extents differ; native window binding unavailable')
            previous=getattr(self,'win_pixel_mapping',None)
            if previous is None:
                pixel_mapping=read_pixel_mapping(first,screen,deadline,guard,clock=clock,diagnostics=diagnostics)
            else:
                validate_pixel_mapping(previous,first,screen,deadline,guard,clock=clock,diagnostics=diagnostics)
                pixel_mapping=previous
            final_window=read_bound_window(first['hwnd'])
            final_screen=read_unity_screen_extent(self.reader,self.unityplayer_base,
                unityplayer_sha256=self.unityplayer_version,check=guard)
            if final_window!=first or final_screen!=screen:
                raise ValueError('Window/Unity context changed during pixel mapping')
            self.win_pixel_mapping=pixel_mapping
            diagnostics['native_mouse_cache']=read_native_mouse_cache(self.reader,self.unityplayer_base,
                self.unityplayer_version,min(deadline,clock()+.02),check=guard,clock=clock)
        self.last_pixel_mapping_diagnostic=diagnostics
        if self.process_identity()!=identity:raise OSError('Process changed during window read')
        guard()
        self.window_hwnd=first['hwnd']
        context=dict(window=first,unity_screen=screen,process_identity=identity,
            extent_one_to_one=equal,coordinate_mapping_verified=equal or bool(pixel_mapping),ready_for_input=False)
        if pixel_mapping is not None:context['pixel_mapping']=pixel_mapping
        self.last_window_diagnostic=context
        return context

    def observe_motion(self, address, deadline, check, *, clock=time.monotonic, include_geometry=False,include_window=False):
        """Read typed slot delegates -> Control -> Motion/animators.

        Returns a partial diagnostic, never an input-ready observation. The
        palette must pass active probing before and after this walk. Optional
        geometry is a cache diagnostic, never a measured input mapping.
        """
        if not math.isfinite(deadline):raise ValueError('Finite observation deadline required')
        if type(include_geometry) is not bool:raise ValueError('Boolean geometry option required')
        if type(include_window) is not bool or (include_window and not include_geometry):
            raise ValueError('Window mapping requires geometry diagnostics')
        def guard():
            check()
            if clock()>=deadline:raise TimeoutError('Motion observation deadline expired')
        guard();identity=self.process_identity()
        before=self.probe(address,deadline,guard)
        if not before.get('active'):
            guard()
            return dict(active=False,ready_for_input=False,reason='no_active_palette',
                        execution_verified=False,game_response_verified=False)
        started=clock();self.reader.guard=guard
        window_context=self.observe_window_context(deadline,guard,clock=clock) if include_window else None
        motion=read_dye_motion(self.reader,address,check=guard)
        geometry=None
        if include_geometry:
            geometry=read_toucharea_geometry_cache(self.reader,motion['binding']['ui_slot'],
                gameassembly_sha256=self.version,metadata_sha256=self.metadata_version,
                unityplayer_sha256=self.unityplayer_version,
                expected_touch_area=motion['binding']['touch_area_address'],check=guard)
            if read_dye_motion(self.reader,address,check=guard)!=motion:
                raise ValueError('Motion changed during geometry observation')
        mapping=None
        if include_window:
            if self.observe_window_context(deadline,guard,clock=clock)!=window_context:
                raise ValueError('Window context changed during geometry observation')
            mapping=map_unity_geometry_to_client(geometry,window_context['window'],window_context['unity_screen'],
                pixel_mapping=window_context.get('pixel_mapping'))
        after=self.probe(address,deadline,guard)
        if not after.get('active') or before.get('session_token')!=after.get('session_token'):
            raise ValueError('Palette session changed during motion read')
        if self.process_identity()!=identity:raise OSError('Process identity changed during motion read')
        guard()
        result=dict(active=True,ready_for_input=False,motion=motion,session_token=after['session_token'],
                    region_count=after['region_count'],
                    process_identity=identity,read_started_monotonic=started,read_finished_monotonic=clock(),
                    missing_requirements=['runtime_geometry','scroll_calibration'],
                    execution_verified=False,game_response_verified=False,release_inertia_modelled=False)
        if include_geometry:result['geometry_diagnostic']=geometry
        if include_window:
            result['window_context']=window_context
            result['window_mapping_candidate']=mapping
        return result

    def close(self):
        self.reader.close()
