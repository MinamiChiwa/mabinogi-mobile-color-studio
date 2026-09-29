"""One candidate ordering for search, automatic selection and execution."""
import math
import numpy as np


def candidate_order(exact_matches,maximum,average,accepted,landing_safe,
                    landing_maximum,distance,*,exact_maximum=None,exact_average=None,
                    family_maximum=None,family_average=None):
    """Return vectorized candidate indices using :func:`candidate_rank` order."""
    exact_matches=np.asarray(exact_matches)
    maximum=np.asarray(maximum)
    average=np.asarray(average)
    accepted=np.asarray(accepted,dtype=bool)
    stable=accepted & np.asarray(landing_safe,dtype=bool)
    risk=np.where(stable,np.asarray(landing_maximum),maximum)
    distance=np.asarray(distance)
    exact_maximum=np.zeros_like(maximum) if exact_maximum is None else np.asarray(exact_maximum)
    exact_average=np.zeros_like(average) if exact_average is None else np.asarray(exact_average)
    family_maximum=np.zeros_like(maximum) if family_maximum is None else np.asarray(family_maximum)
    family_average=np.zeros_like(average) if family_average is None else np.asarray(family_average)
    return np.lexsort((distance,risk,~stable,~accepted,-exact_matches,average,maximum,
                       exact_average,exact_maximum,family_average,family_maximum))


def exact_priority(colors,distances,rules):
    """Vectorized exact-region priority, after all enabled colour families."""
    from vision import rgb
    enabled=[i for i,r in enumerate(rules) if r.get('enabled')]
    count=len(colors[enabled[0]])
    hits=np.zeros(count,int);worst=np.zeros(count);average=np.zeros(count)
    exact=[i for i in enabled if rules[i].get('exact')]
    for i in exact:
        targets=np.array([rgb(c) for c in rules[i]['colors']])
        hits+=np.any(np.all(np.asarray(colors[i])[:,None,:]==targets,axis=2),axis=1)
        worst=np.maximum(worst,distances[i]);average+=distances[i]/len(exact)
    return hits,worst,average,len(exact)


def exact_fields(hits,worst,average,total,index):
    return dict(exact_matches=int(hits[index]),exact_total=total,
                exact_maximum=float(worst[index]),exact_average=float(average[index]))


def candidate_quality(row):
    """Color priority shared by predictions and verified game results.

    Preserve every enabled region's colour family before balancing Exact
    errors. Exact hits cannot compensate for turning a Similar blue grey.
    Within the family envelope, minimize worst/mean Exact error, then overall
    error. Similar-only searches have zero Exact-region metrics.
    """
    return (float(row.get('family_maximum',0)),float(row.get('family_average',0)),
            float(row.get('exact_maximum',0)),float(row.get('exact_average',0)),
            float(row.get('maximum',float('inf'))),float(row.get('average',float('inf'))),
            -int(row.get('exact_matches',0)))


def candidate_rank(row):
    """Use the same balanced color priority throughout search and execution."""
    accepted=bool(row.get('accepted',False))
    stable=accepted and bool(row.get('landing_safe',False))
    maximum=float(row.get('maximum',float('inf')))
    risk=float(row.get('landing_maximum',maximum)) if stable else maximum
    # Cross-family rows are published only as the final fallback tier.  Once
    # that tier is active, minimize the actual colour error first; otherwise a
    # barely-in-family but very distant colour could outrank a visibly closer
    # compromise.  Normal same-family and exact-priority ordering is unchanged.
    if row.get('cross_family_fallback'):
        return (maximum,float(row.get('average',float('inf'))),
                float(row.get('family_maximum',float('inf'))),risk,
                math.hypot(row.get('dx',0),row.get('dy',0)),int(row['id']))
    return (*candidate_quality(row),not accepted,not stable,risk,
            math.hypot(row.get('dx',0),row.get('dy',0)),int(row['id']))
