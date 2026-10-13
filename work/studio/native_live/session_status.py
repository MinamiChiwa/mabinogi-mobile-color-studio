"""Observed session stops, distinct from a temporarily inconsistent read."""
import copy,json


class ObservationInterrupted(InterruptedError):
    """A capture transport failed while F9/focus/session guards still pass."""
    recoverable=True


class SessionStatusError(ValueError):
    stop_reason='session_observation_unstable'
    classification='retryable_observation'
    recoverable=True
    def __init__(self,message,diagnostic):
        super().__init__(message)
        self.diagnostic=diagnostic


class PaletteEnded(SessionStatusError):
    stop_reason='palette_ended'
    classification='normal_stop'
    recoverable=False


class SessionBindingChanged(SessionStatusError):
    stop_reason='session_binding_changed'
    classification='binding_changed'
    recoverable=False


class SessionProbeUnstable(SessionStatusError):
    stop_reason='session_probe_unstable'


def _same(first,last):
    return json.dumps(first,sort_keys=True,allow_nan=False)==json.dumps(last,sort_keys=True,allow_nan=False)


def changed_token_fields(expected,observed):
    if _same(expected,observed):return []
    if not (isinstance(expected,(list,tuple)) and isinstance(observed,(list,tuple))
            and len(expected)==len(observed)==7):return ['session_token']
    fields=[]
    for index,name in ((0,'instance_address'),(1,'data_address'),(2,'result_address'),
            (3,'native_textures'),(4,'native_material'),(6,'color_preserve_ratio')):
        if not _same(expected[index],observed[index]):fields.append(name)
    first,last=expected[5],observed[5]
    if not (isinstance(first,(list,tuple)) and isinstance(last,(list,tuple)) and len(first)==len(last)):
        fields.append('palette_region_count')
    else:
        for index,(before,after) in enumerate(zip(first,last)):
            if not (isinstance(before,(list,tuple)) and isinstance(after,(list,tuple)) and len(before)==len(after)==3):
                if not _same(before,after):fields.append('palette_fragment['+str(index)+']')
                continue
            for column,name in ((0,'palette_address'),(1,'palette_pixels'),(2,'picker_position_y')):
                if not _same(before[column],after[column]):fields.append(name+'['+str(index)+']')
    return fields


def session_diagnostic(expected,observed,*,error_type,stage,observed_monotonic,changed_fields=None,error=None):
    """Keep identity metadata only; no screenshot, account or full UI objects."""
    before={key:copy.deepcopy(expected.get(key)) for key in ('active','session_token','process_identity')}
    after={key:copy.deepcopy(observed.get(key)) for key in ('active','session_token','process_identity')}
    if changed_fields is None:
        changed_fields=[]
        if not _same(before['process_identity'],after['process_identity']):changed_fields.append('process_identity')
        if before['active']!=after['active']:changed_fields.append('active')
        changed_fields.extend(changed_token_fields(before['session_token'],after['session_token']))
    diagnostic=dict(schema=1,stop_reason=error_type.stop_reason,classification=error_type.classification,
        stage=stage,observed_monotonic=observed_monotonic,session_identity=before['process_identity'],
        expected=before,observed=after,changed_fields=list(changed_fields),inputs_sent=0,ready_for_input=False)
    if isinstance(observed.get('active_diagnostic'),dict):
        diagnostic['active_diagnostic']=copy.deepcopy(observed['active_diagnostic'])
    if error is not None:diagnostic['error']=str(error)
    return diagnostic
