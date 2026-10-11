"""Pure evidence checks for session-bound timer grace and bounded cap correction."""
import copy
import json
import math


def verified_timer_grace_until(metadata, *, session_token, process_identity, now):
    """Validate a collector-bound advisory interval, never infer a game start.

    A first eligible observation establishes how long the same discovered
    palette has already been available. It is not proof of its actual age.
    """
    def reject():raise ValueError('Invalid timer grace baseline or session binding')
    finite=lambda value:type(value) in (int,float) and math.isfinite(value) and value>=0
    if not isinstance(metadata,dict) or not finite(now):reject()
    seen=metadata.get('session_first_seen_monotonic');until=metadata.get('timer_grace_until')
    observed=metadata.get('session_origin_observed_monotonic')
    collected=metadata.get('baseline_collected_monotonic');end=metadata.get('session_deadline_monotonic')
    if (not all(finite(value) for value in (seen,until,observed,collected,end))
            or until!=seen+30. or not seen<=observed<=collected<=now<end
            or not 0<end-seen<=120.):reject()
    if metadata.get('stop_reason')!='passive_baseline_collected':reject()
    capture=metadata.get('capture');baseline=metadata.get('baseline');evidence=metadata.get('session_origin_evidence')
    if (not isinstance(capture,dict) or capture.get('session_binding_verified') is not True
            or not isinstance(baseline,dict) or baseline.get('active') is not True
            or not isinstance(evidence,dict)):reject()
    try:
        normalize=lambda value:json.loads(json.dumps(value,allow_nan=False))
        token=normalize(session_token);identity=normalize(process_identity)
        if (not isinstance(token,list) or not token or not isinstance(identity,list) or not identity
                or any(normalize(row.get('session_token'))!=token for row in (capture,baseline))
                or any(normalize(row.get('process_identity'))!=identity
                       for row in (metadata,capture,baseline,evidence))):reject()
    except (ValueError,TypeError):reject()
    address=metadata.get('instance_address')
    if type(address) is not int or address<=0 or evidence.get('selected_address')!=hex(address):reject()
    source=metadata.get('session_first_seen_source')
    if source=='first_eligible_observation':
        scan_started=evidence.get('scan_started_monotonic')
        if (not finite(scan_started) or scan_started>seen
                or evidence.get('first_eligible_seen_monotonic')!=seen
                or evidence.get('eligible_addresses')!=[hex(address)]):reject()
    elif source=='active_validation_observation':
        if seen!=observed:reject()
    else:reject()
    return until


def _verified_timer_pair(checkpoint, frames, timer_grace_until, now):
    """Independent screenshot colors and a fresh, decreasing countdown pair."""
    finite=lambda value:type(value) in (int,float) and math.isfinite(value)
    if not all(finite(value) for value in (timer_grace_until,now)):return None
    if (not isinstance(checkpoint,dict) or checkpoint.get('checkpoint_valid') is not True
            or checkpoint.get('cpu_matches') is not True):return None
    try:binding=json.loads(checkpoint['binding'])
    except (ValueError,TypeError,KeyError):return None
    if (not isinstance(binding,list) or len(binding)<2
            or any(not isinstance(part,list) or not part for part in binding[:2])):return None
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
    return implied if abs(implied[0]-implied[1])<=2. else None


def verified_timer_shortening(checkpoint, frames, *, current_deadline, timer_grace_until, now):
    """A qualified late pair may reduce the current cap with a 10 s reserve."""
    if (type(current_deadline) not in (int,float) or not math.isfinite(current_deadline)
            or type(now) not in (int,float) or not math.isfinite(now) or now>=current_deadline):return None
    implied=_verified_timer_pair(checkpoint,frames,timer_grace_until,now)
    if implied is None:return None
    deadline=min(implied)-10.
    if deadline>=current_deadline:return None
    return dict(deadline=deadline,evidence=dict(checkpoint=copy.deepcopy(checkpoint),frames=copy.deepcopy(list(frames)),
        timer_grace_until=timer_grace_until,previous_deadline=current_deadline,
        implied_timer_ends=implied,reserve_seconds=10.))


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
    implied=_verified_timer_pair(checkpoint,frames,timer_grace_until,now)
    if implied is None:return None
    deadline=min(maximum,min(implied)-10.)
    if deadline<=current_deadline:return None
    evidence=dict(checkpoint=copy.deepcopy(checkpoint),frames=copy.deepcopy(list(frames)),
        timer_grace_until=timer_grace_until,initial_engineering_deadline=initial_engineering_deadline,
        previous_deadline=current_deadline,maximum_deadline=maximum,
        implied_timer_ends=implied,reserve_seconds=10.)
    return dict(deadline=deadline,evidence=evidence)
