"""Translation-only colour search at a measured, physically reachable pose."""
import numpy as np
from atlas_pose import homogeneous, pose_fields
from periodic_atlas import translation_candidates


class MeasuredAtlas:
    def __init__(self, atlas, pose, capture_offset):
        self.atlas=atlas
        self.pose=homogeneous(pose)
        self.inverse=np.linalg.inv(self.pose)
        self.capture_offset=np.asarray(capture_offset,float)
        self.basis=self.pose[:2,:2]@atlas.basis
        self.resolution=atlas.resolution

    def sample(self, region, points):
        source=(np.asarray(points)-self.pose[:2,2])@self.inverse[:2,:2].T
        return self.atlas.sample(region,source,self.capture_offset)


def reachable_candidates(atlas, capture_offset, actual_pose, markers, board, rules,
                         candidate_id, check=lambda:None, reference_pose=None,
                         limit=32, max_move=None):
    """Keep measured angle/scale; search real integer mouse translations.

    actual_pose is relative to the execution reference. reference_pose maps
    the capture frame to that reference, including after a user selection.
    All three material masks and the existing colour ranking remain in use.
    """
    actual=homogeneous(actual_pose)
    reference=np.eye(3) if reference_pose is None else homogeneous(reference_pose)
    view=MeasuredAtlas(atlas,actual@reference,capture_offset)
    local=np.asarray(markers,float)-np.asarray(board[:2])
    def cancelled():
        check()
        return False
    rows=translation_candidates(view,local,rules,integer_moves=True,
                                landing_radius=1.,cancelled=cancelled,
                                limit=limit,max_move=max_move)
    result=[]
    for row in rows:
        shift=homogeneous([[1,0,row['dx']],[0,1,row['dy']]])
        result.append(dict(row,**pose_fields(shift@actual,board),
                           id=candidate_id,search_space='measured_pose_translation',
                           replanned=True,remaining_translation=[row['dx'],row['dy']]))
    return result
