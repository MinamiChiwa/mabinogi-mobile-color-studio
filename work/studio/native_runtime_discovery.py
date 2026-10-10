"""Pure fail-closed selection of a runtime PaletteControl candidate.

The caller supplies candidates from a separately guarded read-only scanner.
No memory scan, address arithmetic, process access, or input occurs here.
"""

INSTANCE_CLASS='MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl'
CONTROL_CLASS='MM.Client.Presentation.UI.Controls.Dyeing.DyeingPaletteControl'


def _address(value,name):
    if type(value) is not int or value<=0: raise ValueError(f'Invalid {name} address')
    return value


def select_palette_control(instance,candidates):
    """Return the unique control sharing the instance uiSlot and full links."""
    if not isinstance(instance,dict) or instance.get('class_name')!=INSTANCE_CLASS:
        raise ValueError('Unexpected palette instance type')
    instance_address=_address(instance.get('address'),'instance')
    slot=_address(instance.get('ui_slot'),'instance uiSlot')
    _address(instance.get('data'),'instance data');_address(instance.get('result'),'instance result')
    if not isinstance(candidates,(list,tuple)) or not candidates: raise ValueError('No control candidates')
    matches=[]
    for candidate in candidates:
        if not isinstance(candidate,dict) or candidate.get('class_name')!=CONTROL_CLASS: continue
        if candidate.get('ui_slot')!=slot or candidate.get('root_object')!=slot: continue
        try:
            address=_address(candidate.get('address'),'control')
            motion=_address(candidate.get('motion_control'),'motion control')
            gesture=_address(candidate.get('gesture_recognizer'),'gesture recognizer')
        except ValueError: continue
        matches.append((address,motion,gesture))
    if len(matches)!=1: raise ValueError('Control link is missing or ambiguous')
    address,motion,gesture=matches[0]
    return dict(instance_address=instance_address,control_address=address,ui_slot=slot,
                motion_address=motion,gesture_address=gesture,
                execution_verified=False,game_response_verified=False,
                release_inertia_modelled=False,
                discovery='unique_explicit_runtime_candidate_shared_ui_slot')
