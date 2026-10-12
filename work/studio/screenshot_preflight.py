"""Capture-only diagnostics for screenshot search; never constructs an input sender."""
import argparse,datetime,json,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageGrab
from vision import configure_ocr,recognize
from screenshot_text import read_visible,read_timer

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hwnd',type=int)
    parser.add_argument('--image',type=Path,help='Inspect a saved screenshot without accessing a game')
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args(argv)
    folder=args.output_dir or Path('outputs/screenshot-preflight')/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    folder.mkdir(parents=True,exist_ok=True)
    result=dict(backend='screenshot',input_count=0,no_game_memory=True,board_visible=False)
    try:
        result['ocr_available']=bool(configure_ocr())
        if args.image:
            frame=np.array(Image.open(args.image).convert('RGB'))
            result['source']='saved_image'
        else:
            import ctypes as C
            from ctypes import wintypes as W
            from window_target import resolve_target,list_windows,valid_target
            from window_dpi import target_pixel_context,physical_pixel_context
            from overlay_native import capture_scope
            from platform_win import u
            if args.hwnd is not None:
                target=next((v for v in list_windows() if v.hwnd==args.hwnd),None)
                if target is None:raise ValueError('Selected window is not visible')
            else:target=resolve_target()
            if not valid_target(target) or u.IsIconic(target.hwnd):raise ValueError('Game window is unavailable or minimized')
            with target_pixel_context(target.hwnd):
                rect=W.RECT();origin=W.POINT();lower=W.POINT()
                if not u.GetClientRect(target.hwnd,C.byref(rect)):raise OSError('GetClientRect failed')
                lower.x=rect.right;lower.y=rect.bottom
                for point in (origin,lower):
                    if not u.ClientToScreen(target.hwnd,C.byref(point)):raise OSError('ClientToScreen failed')
                    if not u.LogicalToPhysicalPointForPerMonitorDPI(target.hwnd,C.byref(point)):raise OSError('Physical coordinate conversion failed')
            foreground=u.GetForegroundWindow()
            result.update(source='visible_client',hwnd=target.hwnd,pid=target.pid,title=target.title,
                client=[origin.x,origin.y,lower.x-origin.x,lower.y-origin.y],
                foreground=bool(foreground) and int(foreground)==target.hwnd,
                dpi=int(u.GetDpiForWindow(target.hwnd)))
            with physical_pixel_context(),capture_scope():
                frame=np.array(ImageGrab.grab(bbox=(origin.x,origin.y,lower.x,lower.y),all_screens=True).convert('RGB'))
        result['capture_size']=[int(frame.shape[1]),int(frame.shape[0])]
        Image.fromarray(frame).save(folder/'client.png')
        try:scene=recognize(frame,with_ocr=False,read_colors=False)
        except ValueError:scene=None
        if scene is not None:
            colors,diagnostics=read_visible(frame,scene.cards,deadline=time.monotonic()+3.5)
            result.update(board_visible=True,region_count=len(scene.cards),board=scene.board,
                cards=scene.cards,markers=scene.markers,actual_colors=colors,text=diagnostics,
                timer_seconds=read_timer(frame,scene.cards[0][2]))
        result['status']='capture_complete'
    except Exception as exc:
        result.update(status='unavailable',error=str(exc))
    (folder/'screenshot-preflight.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='capture_complete' else 1

if __name__=='__main__':raise SystemExit(main())
