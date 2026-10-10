"""Current-build typed pointer walk from dye instance to motion/animators.

Reads only an explicit instance, no global scan or game function calls.
The UI-slot handler delegates supply the reverse control binding; all links
and observed fields are re-read before returning. Native rect is unavailable.
"""
import math
import struct

INSTANCE='MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl'
SLOT='Client.CodeGenerated.UI.DyeingPaletteSlot'
CONTROL='MM.Client.Presentation.UI.Controls.Dyeing.DyeingPaletteControl'
MOTION='MM.Client.Presentation.UI.Controls.Dyeing.DyeingPaletteMotionControl'
GESTURE='MM.Client.Presentation.UI.Controls.Common.TouchGestureRecognizer'
TRACKER='MM.Client.Presentation.UI.Utility.TouchTracker'
ANIMATOR='MM.Client.Framework.UI.Animation.UIAnimator'
POSITION_ANIMATION='MM.Client.Presentation.UI.Controls.Dyeing.DyeingPalettePositionInertiaAnimation'
ROTATION_ANIMATION='MM.Client.Presentation.UI.Controls.Dyeing.DyeingPaletteRotationInertiaAnimation'


class UnsupportedSlotDelegate(ValueError):
    code='unsupported_slot_delegate_type'
    def __init__(self,actual_type,field,address):
        self.details=dict(actual_type=actual_type,expected_type='MM.Client.Framework.UI.Synch.Downward.Node.DataSynchHandlerDelegate`1',
                          field=field,delegate_address=address)
        super().__init__('Unrecognized slot delegate type: '+actual_type)


def read_dye_motion(reader,instance_address,*,check=lambda:None):
    """Observe motion, including running animators, without claiming stability.

    Caller must gate this build-specific walk on matching binary/metadata,
    process creation identity and an active palette probe. Raw snapshots can
    change during a frame; changed reads fail and should be retried boundedly.
    """
    observed={};class_layouts={}
    def read(a,size):
        check()
        if type(a) is not int or a<=0:raise ValueError('Invalid object/read address')
        raw=reader.read(a,size)
        if len(raw)!=size:raise ValueError('Short process read')
        prior=observed.setdefault((a,size),raw)
        if prior!=raw:raise ValueError('Motion changed during observation')
        check();return raw
    def ptr(a):
        p=struct.unpack('<Q',read(a,8))[0]
        if not p or p%8:raise ValueError('Null/unaligned managed object')
        return p
    def obj(a,name,required):
        cls=ptr(a);check()
        if reader.class_name(cls)!=name:raise ValueError('Unexpected runtime type: '+name)
        fs=reader.fields(cls)
        if any(key not in fs or type(fs[key]) is not int or not 0<=fs[key]<=512 for key in required):
            raise ValueError('Runtime field layout unavailable: '+name)
        class_layouts[cls]=dict(fs);check();return fs
    def f(a):
        value=struct.unpack('<f',read(a,4))[0]
        if not math.isfinite(value):raise ValueError('Nonfinite motion/animation value')
        return value
    def v(a):return [f(a),f(a+4)]
    def flag(a):
        b=read(a,1)[0]
        if b not in (0,1):raise ValueError('Invalid bool flag')
        return bool(b)

    fi=obj(instance_address,INSTANCE,('uiSlot','data','resultCache'))
    slot=ptr(instance_address+fi['uiSlot']);data=ptr(instance_address+fi['data']);result=ptr(instance_address+fi['resultCache'])
    sf=obj(slot,SLOT,('<Handlers>k__BackingField','<TouchArea>k__BackingField'))
    handlers=ptr(slot+sf['<Handlers>k__BackingField']);touch=ptr(slot+sf['<TouchArea>k__BackingField'])
    hf=obj(handlers,'.HandlerGroup',('uiSlot','__back_PaletteControlDataSourceHandler','__back_ColorPickerColorControlDataSourceHandler'))
    if ptr(handlers+hf['uiSlot'])!=slot:raise ValueError('Handler-group slot mismatch')
    targets=[]
    for key in ('__back_PaletteControlDataSourceHandler','__back_ColorPickerColorControlDataSourceHandler'):
        delegate=ptr(handlers+hf[key]);delegate_class=ptr(delegate)
        actual_type=reader.class_name(delegate_class)
        if actual_type!='MM.Client.Framework.UI.Synch.Downward.Node.DataSynchHandlerDelegate`1':
            raise UnsupportedSlotDelegate(actual_type,key,delegate)
        # Current build delegate constructor assigns m_target at +0x20.
        targets.append(ptr(delegate+0x20))
    if targets[0]!=targets[1]:raise ValueError('Data/color handler targets disagree')
    control=targets[0];cf=obj(control,CONTROL,('uiSlot','paletteMotionControl','gestureRecognizer'))
    if ptr(control+cf['uiSlot'])!=slot:raise ValueError('Control slot mismatch')
    motion=ptr(control+cf['paletteMotionControl']);gesture=ptr(control+cf['gestureRecognizer'])
    mf=obj(motion,MOTION,('settings','eventHandler','positionInertiaAnimator','positionInertiaAnimation',
        'rotationInertiaAnimator','rotationInertiaAnimation','<CurrentPosition>k__BackingField',
        '<CurrentScale>k__BackingField','<CurrentRotation>k__BackingField','currentPivot','isRecognizeFinished'))
    gf=obj(gesture,GESTURE,('touchTracker','settings','eventHandler','<RootObject>k__BackingField'))
    tracker=ptr(gesture+gf['touchTracker'])
    tf=obj(tracker,TRACKER,('moveThreshold','moveTolerance'))
    if ptr(motion+mf['eventHandler'])!=control or ptr(gesture+gf['eventHandler'])!=motion:
        raise ValueError('Motion/gesture handler mismatch')
    if ptr(gesture+gf['<RootObject>k__BackingField'])!=touch:raise ValueError('Gesture touch-area mismatch')
    # Motion and gesture settings are inline VALUE TYPES, not object pointers.
    ms=motion+mf['settings'];gs=gesture+gf['settings']
    raw=read(ms,56)
    values=struct.unpack('<6fi3fi3f',raw)
    motion_settings=dict(zip(('InitialPositionX','InitialPositionY','InitialScale','InitialRotation',
        'MinimumScale','MaximumScale','PositionInertiaEaseType','PositionInertiaSensitivity',
        'MaximumPositionVelocity','PositionInertiaDragRatio','RotationInertiaEaseType',
        'RotationInertiaSensitivity','MaximumRotationVelocity','RotationInertiaDragRatio'),values))
    configured=dict(move_threshold=f(gs),move_tolerance=f(gs+4),scroll_zoom_ratio=f(gs+8))
    # The constructor creates the tracker before copying gesture settings.
    # Its effective gate must be read from the actual tracker object.
    settings=dict(minimum_scale=values[4],maximum_scale=values[5],
                  move_threshold=f(tracker+tf['moveThreshold']),move_tolerance=f(tracker+tf['moveTolerance']),
                  scroll_zoom_ratio=configured['scroll_zoom_ratio'])
    if not all(math.isfinite(x) for x in values) or not 0<settings['minimum_scale']<=settings['maximum_scale']:
        raise ValueError('Invalid inline motion settings')
    if any(v<0 for v in configured.values()) or any(settings[k]<0 for k in ('move_threshold','move_tolerance','scroll_zoom_ratio')):
        raise ValueError('Invalid inline gesture settings')
    pose=dict(position=v(motion+mf['<CurrentPosition>k__BackingField']),
              scale=f(motion+mf['<CurrentScale>k__BackingField']),rotation_degrees=f(motion+mf['<CurrentRotation>k__BackingField']))
    if pose['scale']<=0:raise ValueError('Invalid motion scale')
    pivot=v(motion+mf['currentPivot']);finished=flag(motion+mf['isRecognizeFinished'])
    animators={}
    for kind,animation_type,last_key,target_key in (
        ('position',POSITION_ANIMATION,'lastPos','targetPos'),('rotation',ROTATION_ANIMATION,'lastRot','targetRot')):
        a=ptr(motion+mf[kind+'InertiaAnimator']);animation=ptr(motion+mf[kind+'InertiaAnimation'])
        af=obj(a,ANIMATOR,('currentAnimation','elapsedTime','<IsRunning>k__BackingField','<IsAnimationChangedBeforeNextUpdate>k__BackingField'))
        ef=obj(animation,animation_type,('duration',last_key,target_key))
        running=flag(a+af['<IsRunning>k__BackingField']);changed=flag(a+af['<IsAnimationChangedBeforeNextUpdate>k__BackingField'])
        current=struct.unpack('<Q',read(a+af['currentAnimation'],8))[0]
        if running and current!=animation:raise ValueError('Running animator points to another animation')
        elapsed=f(a+af['elapsedTime']);duration=f(animation+ef['duration'])
        if elapsed<0 or duration<0:raise ValueError('Invalid animator time')
        read_value=v if kind=='position' else f
        animators[kind]=dict(is_done=not running,is_running=running,
            animation_changed_before_next_update=changed,stop_requested=changed,
            stop_request_source='conservative_animation_changed_flag',elapsed=elapsed,elapsed_observed=True,
            duration=duration,last=read_value(animation+ef[last_key]),target=read_value(animation+ef[target_key]))
    for (a,size),raw in observed.items():
        check()
        if reader.read(a,size)!=raw:raise ValueError('Motion changed during observation')
    for cls,fs in class_layouts.items():
        check()
        if reader.fields(cls)!=fs:raise ValueError('Runtime class layout changed')
    return dict(binding=dict(instance_address=instance_address,ui_slot=slot,data_address=data,result_address=result,
        control_address=control,motion_address=motion,gesture_address=gesture,tracker_address=tracker,touch_area_address=touch),
        pose=pose,settings=settings,configured_gesture_settings=configured,
        input_settings_source='runtime_touch_tracker_and_gesture_scroll',motion_settings=motion_settings,current_pivot=pivot,
        is_recognize_finished=finished,animator=animators,
        animators_done=all(a['is_done'] and not a['stop_requested'] for a in animators.values()),
        geometry_available=False,execution_verified=False,game_response_verified=False,release_inertia_modelled=False,
        scope='Typed double-checked runtime motion observation; no screen geometry or live result certification')
