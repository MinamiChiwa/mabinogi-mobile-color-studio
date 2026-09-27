"""One candidate ordering for search, automatic selection and execution."""
import math
import numpy as np


def candidate_order(exact_matches,maximum,average,accepted,landing_safe,
                    landing_maximum,distance):
    """Return vectorized candidate indices using :func:`candidate_rank` order."""
    exact_matches=np.asarray(exact_matches)
    maximum=np.asarray(maximum)
    average=np.asarray(average)
    accepted=np.asarray(accepted,dtype=bool)
    stable=accepted & np.asarray(landing_safe,dtype=bool)
    risk=np.where(stable,np.asarray(landing_maximum),maximum)
    distance=np.asarray(distance)
    return np.lexsort((distance,risk,~stable,~accepted,average,maximum,-exact_matches))


def exact_priority(colors,distances,rules):
    """Vectorized exact-region priority, before any similar-region errors."""
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


def candidate_rank(row):
    """Rank exact-region outcomes, then overall color error.

    This key is shared by Atlas search, automatic selection and execution.
    More exact HEX hits always win. When the count ties, compare the overall
    maximum and average color error across enabled regions; then consider
    tolerance acceptance, landing safety and movement cost.
    """
    accepted=bool(row.get('accepted',False))
    stable=accepted and bool(row.get('landing_safe',False))
    maximum=float(row.get('maximum',float('inf')))
    risk=float(row.get('landing_maximum',maximum)) if stable else maximum
    return (-int(row.get('exact_matches',0)),maximum,float(row.get('average',float('inf'))),
            not accepted,not stable,risk,
            math.hypot(row.get('dx',0),row.get('dy',0)),int(row['id']))
