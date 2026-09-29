"""One candidate ordering for search, automatic selection and execution."""
import math
import numpy as np


def candidate_order(exact_matches,maximum,average,accepted,landing_safe,
                    landing_maximum,distance,*,exact_maximum=None,exact_average=None,
                    family_maximum=None,family_average=None,
                    neighborhood_present=False,candidate_ids=None):
    """Vectorized :func:`candidate_rank`, including compromise landing risk.

    ``neighborhood_present`` distinguishes a sampled acceptance check from an
    early search risk proxy. Supplying a risk never makes it disappear merely
    because the center misses tolerance. None/NaN samples mean unknown risk.
    """
    def values(value,default=0.):
        result=np.broadcast_to(np.asarray(default if value is None else value,float),shape)
        return np.where(np.isfinite(result)&(result>=0),result,np.inf)
    shape=np.asarray(maximum).shape
    maximum=values(maximum,np.inf);average=values(average,np.inf)
    risk=np.maximum(maximum,values(landing_maximum,np.inf))
    accepted=np.asarray(accepted,float);landing_safe=np.asarray(landing_safe,float)
    accepted=(np.isfinite(accepted)&(accepted!=0)&np.isfinite(risk)&np.isfinite(average)&
              (~np.asarray(neighborhood_present,dtype=bool)|
               (np.isfinite(landing_safe)&(landing_safe!=0))))
    hits=np.asarray(exact_matches,float)
    hits=np.where(np.isfinite(hits)&(hits>=0),hits,0)
    ids=np.arange(maximum.size) if candidate_ids is None else np.asarray(candidate_ids)
    return np.lexsort((ids,values(distance,np.inf),values(family_average),values(family_maximum),
                       values(exact_average),values(exact_maximum),-hits,
                       average,maximum,risk,~accepted))


def exact_priority(colors,distances,rules):
    """Vectorized exact matches, used after balanced overall colour quality."""
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
    """Acceptance, sampled worst error, balanced center, then Exact ties.

    Observed results carry actual HEX acceptance and no landing forecast.
    Predictions with a sampled neighborhood need all samples accepted before
    entering the full-acceptance tier. The worst sample is a conservative
    comparison score, not a calibrated game-response confidence bound.
    """
    maximum=_number(row.get('maximum'));average=_number(row.get('average'))
    observed=_truth(row.get('verified',False))
    risk=(maximum if observed else
          max(maximum,_number(row['landing_maximum']) if 'landing_maximum' in row else maximum))
    neighborhood=not observed and ('landing_safe' in row or _number(row.get('landing_radius',0))>0)
    accepted=(_truth(row.get('observed_accepted',row.get('accepted',False)) if observed else row.get('accepted',False))
              and math.isfinite(risk) and math.isfinite(average)
              and (not neighborhood or _truth(row.get('landing_safe',False))))
    hits=_number(row.get('exact_matches',0));hits=hits if math.isfinite(hits) else 0.
    return (not accepted,risk,maximum,average,-hits,
            _number(row.get('exact_maximum',0)),_number(row.get('exact_average',0)),
            _number(row.get('family_maximum',0)),_number(row.get('family_average',0)))


def _number(value):
    try: value=float(value)
    except (ValueError,TypeError): return math.inf
    return value if math.isfinite(value) and value>=0 else math.inf


def _truth(value):
    try:return bool(np.isfinite(value) and value)
    except (TypeError,ValueError):return False


def candidate_rank(row):
    """Use the same balanced color priority throughout search and execution."""
    return (*candidate_quality(row),_number(math.hypot(row.get('dx',0),row.get('dy',0))),
            int(row['id']))
