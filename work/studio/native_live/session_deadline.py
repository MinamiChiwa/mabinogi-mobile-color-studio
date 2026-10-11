"""Pure evidence checks for a bounded correction of an unknown-age session cap."""
import copy
import json
import math


def verified_timer_extension(checkpoint, frames, *, initial_engineering_deadline,
        current_deadline, extension, timer_grace_until, now):
    """Return a justified later cap, never authority to send input or reset time.

    The optional metadata must come from the passive collector for this exact
    session. An intentionally shorter engineering deadline is never corrected.
    """
    finite=lambda value:type(value) in (int,float) and math.isfinite(value)
    clocks=(initial_engineering_deadline,current_deadline,timer_grace_until,now)
    if not all(finite(value) for value in clocks):return None
    if not isinstance(extension,dict) or extension.get('deadline_source')!='existing_active_unknown_age':return None
    initial=extension.get('initial_deadline');maximum=extension.get('maximum_deadline')
    if (not finite(initial) or not finite(maximum) or initial_engineering_deadline!=initial
            or not initial<=current_deadline<maximum or maximum-initial>20.
            or now>=current_deadline):return None
    if (not isinstance(checkpoint,dict) or checkpoint.get('checkpoint_valid') is not True
            or checkpoint.get('cpu_matches') is not True):return None
    try:binding=json.loads(checkpoint['binding'])
    except (ValueError,TypeError,KeyError):return None
    try:
        token=json.loads(json.dumps(extension.get('session_token'),allow_nan=False))
        identity=json.loads(json.dumps(extension.get('process_identity'),allow_nan=False))
    except (ValueError,TypeError):return None
    if (not isinstance(binding,list) or len(binding)<2 or not isinstance(token,list)
            or not isinstance(identity,list) or not token or not identity
            or binding[0]!=token or binding[1]!=identity):return None
    colors=checkpoint.get('client_hex')
    if not isinstance(colors,list) or len(colors) not in (2,3):return None
    if not isinstance(frames,(list,tuple)) or len(frames)!=2:return None
    times=[];seconds=[]
    for frame in frames:
        if (not isinstance(frame,dict) or frame.get('screenshot_hex_verified') is not True
                or frame.get('hex')!=colors or frame.get('screenshot_hex')!=colors
                or frame.get('hex_source')!=['screenshot']*len(colors)
                or frame.get('timer_confidence')!='two_pass_agree'):return None
        when=frame.get('captured_monotonic');value=frame.get('remaining_seconds')
        if (not finite(when) or when<timer_grace_until or type(value) is not int
                or not 1<=value<=120):return None
        times.append(when);seconds.append(value)
    elapsed=times[1]-times[0];drop=seconds[0]-seconds[1]
    if not .5<=elapsed<=10. or not 0<=now-times[1]<=5. or drop<1 or abs(drop-elapsed)>2.:return None
    implied=[when+value for when,value in zip(times,seconds)]
    if abs(implied[0]-implied[1])>2.:return None
    deadline=min(maximum,min(implied)-10.)
    if deadline<=current_deadline:return None
    evidence=dict(checkpoint=copy.deepcopy(checkpoint),frames=copy.deepcopy(list(frames)),
        timer_grace_until=timer_grace_until,initial_engineering_deadline=initial_engineering_deadline,
        previous_deadline=current_deadline,maximum_deadline=maximum,
        implied_timer_ends=implied,reserve_seconds=10.)
    return dict(deadline=deadline,evidence=evidence)
