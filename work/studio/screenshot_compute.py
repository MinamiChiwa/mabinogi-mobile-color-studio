"""Cooperative waiting for one pure native computation; never game input."""
import threading

_slot=threading.Semaphore(1)


def cooperative_compute(function,check=lambda:None):
    check()
    while not _slot.acquire(timeout=.03):check()
    finished=threading.Event();result={}
    def compute():
        try:result['value']=function()
        except BaseException as exc:result['error']=exc
        finally:_slot.release();finished.set()
    try:threading.Thread(target=compute,name='color-index-compute',daemon=True).start()
    except BaseException:
        _slot.release()
        raise
    while not finished.wait(.03):check()
    check()
    if 'error' in result:raise result['error']
    return result['value']
