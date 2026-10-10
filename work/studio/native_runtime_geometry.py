"""Validate measured RectTransform screen/UI-local geometry.

Only the explicit axis-aligned, null-camera conversion used by the current
input model is accepted. This module does not inspect Unity or infer size from
a screenshot/prefab.
"""
import math
import numpy as np
from native_input_response import InputGeometry


def _finite(values,name,length):
    value=np.asarray(values,dtype=float)
    if value.shape!=(length,) or not np.isfinite(value).all():raise ValueError(f'Invalid {name}')
    return value


def validate_runtime_geometry(record, *, check=lambda:None):
    check()
    if not isinstance(record,dict) or record.get('source')!='runtime_recttransform' or record.get('camera')!='null':
        raise ValueError('Only measured runtime null-camera geometry is accepted')
    board=_finite(record.get('screen_bounds'),'screen bounds',4)
    size=_finite(record.get('local_size'),'local size',2)
    if board[2]<=board[0] or board[3]<=board[1] or np.any(size<=0):raise ValueError('Invalid geometry extents')
    tolerance=record.get('tolerance',1e-3)
    tolerance=float(tolerance)
    if not math.isfinite(tolerance) or not 0<=tolerance<=.1:raise ValueError('Invalid geometry tolerance')
    samples=record.get('samples')
    if not isinstance(samples,(list,tuple)) or len(samples)!=4:raise ValueError('Four runtime corner samples required')
    screen=[];local=[]
    for row in samples:
        check()
        if not isinstance(row,dict):raise ValueError('Malformed geometry sample')
        screen.append(_finite(row.get('screen'),'sample screen',2));local.append(_finite(row.get('local'),'sample local',2))
    screen=np.asarray(screen);local=np.asarray(local)
    expected_screen=np.asarray([[board[0],board[1]],[board[2],board[1]],[board[0],board[3]],[board[2],board[3]]])
    # RectTransform samples must identify each physical corner, regardless of order.
    distance=np.linalg.norm(screen[:,None,:]-expected_screen[None,:,:],axis=2)
    corners=np.argmin(distance,axis=1)
    if len(set(corners.tolist()))!=4 or np.max(distance[np.arange(4),corners])>1e-3:
        raise ValueError('Samples do not cover runtime screen corners')
    x=np.column_stack((screen[:,0],np.ones(4)));y=np.column_stack((screen[:,1],np.ones(4)))
    ax,bx=np.linalg.lstsq(x,local[:,0],rcond=None)[0];ay,by=np.linalg.lstsq(y,local[:,1],rcond=None)[0]
    predicted=np.column_stack((x@np.array([ax,bx]),y@np.array([ay,by])))
    residual=np.linalg.norm(predicted-local,axis=1)
    if not np.isfinite(residual).all() or float(np.max(residual))>float(tolerance):raise ValueError('Non-axis-aligned or unstable geometry')
    expected_local=np.column_stack(((screen[:,0]-board[0])/(board[2]-board[0])*size[0]-size[0]/2,
                                    (board[3]-screen[:,1])/(board[3]-board[1])*size[1]-size[1]/2))
    if float(np.max(np.linalg.norm(expected_local-local,axis=1)))>float(tolerance):raise ValueError('Local transform disagrees with board extents')
    geometry=InputGeometry(tuple(board),tuple(size))
    return dict(source='runtime_recttransform',camera='null',screen_bounds=board.tolist(),local_size=size.tolist(),
        samples=[dict(screen=s.tolist(),local=p.tolist()) for s,p in zip(screen,local)],
        max_residual_local=float(np.max(residual)),tolerance=float(tolerance),input_geometry=geometry,
        mapping_consistent=True,runtime_measurement_verified=False,
        scope='Numerical consistency of supplied samples; source label is not proof of an actual runtime measurement',
        execution_verified=False,game_response_verified=False)
