"""Bounded capture of game HEX across small texture phase changes.

This diagnostic selects a visible edge in material 2 and records screenshots.
It never builds an atlas, publishes candidates, or confirms/cancels a dye.
The injected game object owns focus, geometry, stop and deadline guards.
"""
import cv2
import numpy as np
from vision import measure_board_motion


def choose_probe_target(image, scene):
    l,t,r,b=scene.board
    board=np.asarray(image[t:b,l:r],np.float32)
    h,w=board.shape[:2];y,x=np.mgrid[:h,:w]
    markers=np.asarray(scene.markers,float)-[l,t]
    spacing=markers[1,0]-markers[0,0];mx,my=markers[1]
    valid=(abs(x-mx)<min(60,spacing/2-12))&(abs(y-my)<60)&(y>16)&(y<h-16)
    for cx,cy in markers:
        valid &= ~(((abs(x-cx)<10)&(y<cy+5))|((x-cx)**2+(y-cy)**2<22**2))
    # The cursor was last placed at the board center during zooming.
    valid &= (x-w/2)**2+(y-h/2)**2>22**2
    gx=cv2.Sobel(board,cv2.CV_32F,1,0,ksize=3)/8
    gy=cv2.Sobel(board,cv2.CV_32F,0,1,ksize=3)/8
    gradient=np.sqrt((gx*gx+gy*gy).mean(axis=2))
    score=np.where(valid,gradient,-np.inf)
    if not valid.any() or float(np.max(score))<12:
        raise RuntimeError('未找到适合取样诊断的可见细色带；本局未开始点位扫描。')
    py,px=np.unravel_index(int(np.argmax(score)),score.shape)
    return dict(point=[int(px+l),int(py+t)],gradient=float(score[py,px]),region=2)


def checked_probe_motion(motion, small_step=False):
    if motion is None:
        raise RuntimeError('点位诊断无法测定图像位移，已停止。')
    matrix=np.asarray(motion.get('matrix'),float)
    if (matrix.shape!=(2,3) or not np.isfinite(matrix).all()
            or abs(float(motion.get('scale',0))-1)>.002
            or abs(float(motion.get('angle',999)))>.1
            or np.max(abs(matrix[:,:2]-np.eye(2)))>.003):
        raise RuntimeError('微移后的倍率或角度不一致，已停止点位诊断。')
    distance=float(np.linalg.norm(matrix[:,2]))
    if small_step and not .06<=distance<=1.0:
        raise RuntimeError('未测得可靠的小于一像素位移；不把滚轮指令当作实际位移。')
    return matrix[:,2]


def run_point_probe(game, scene, reference, snap, log):
    """One integer placement, then 8 X and 8 Y paired-wheel probes.

    The paired anchors *attempt* a fractional translation. Only image-measured
    movement counts; a game that ignores cursor zoom anchors stops immediately.
    No automatic retry, reset, or second session is performed on failure.
    """
    game.check()
    target=choose_probe_target(reference,scene)
    command=np.rint(np.asarray(scene.markers[1])-target['point']).astype(int)
    l,t,r,b=scene.board;anchor=np.array([(l+r)/2,(t+b)/2])
    gap=min(24.,(r-l)*.08,(b-t)*.08)
    if gap<8:raise RuntimeError('色板太小，无法安全安排点位诊断。')
    log('point_probe_plan',reference='max_sampling',target=target,
        drag=command.tolist(),steps_per_axis=8,anchor_gap=gap,
        purpose='Measure game HEX versus image phase; no candidate or dye selection')
    game.check();game.drag(scene.board,int(command[0]),int(command[1]))
    game.pause(.12)
    def capture(name):
        game.check()
        game.move_to((int(game.initial[2]*.5),int(game.initial[3]*.15)))
        game.pause(.10)
        return snap(name,scene)
    current=capture('probe_000')
    measured=measure_board_motion(reference,current,scene.board)
    delta=checked_probe_motion(measured)
    if np.linalg.norm(delta-command)>2:
        raise RuntimeError('初始点位移动与实测不一致，已停止。')
    log('point_probe_motion',frame='probe_000',reference='max_sampling',motion=measured)
    for index in range(16):
        axis=0 if index<8 else 1;end=anchor.copy();end[axis]+=gap
        game.check()
        game.wheel(scene.board,1,anchor=anchor.tolist());game.pause(.035)
        # No compensating input is sent if a guard interrupts the pair.
        game.check()
        game.wheel(scene.board,-1,anchor=end.tolist());game.pause(.12)
        name=f'probe_{index+1:03d}';after=capture(name)
        motion=measure_board_motion(current,after,scene.board)
        # Save the attempted measurement even if its validation fails.
        log('point_probe_motion',frame=name,reference=f'probe_{index:03d}',
            axis='x' if axis==0 else 'y',anchors=[anchor.tolist(),end.tolist()],motion=motion)
        checked_probe_motion(motion,small_step=True)
        current=after
    game.check()
    return current
