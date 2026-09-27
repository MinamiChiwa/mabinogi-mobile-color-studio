"""Independent, visible RGB fixture for the production ImageGrab path.

This program only displays/captures its own window. It has no game targeting,
input injection, focus activation, or dye-session code.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import tkinter as tk
import numpy as np
from PIL import Image, ImageTk, ImageGrab


def reference_pixels():
    colors=[]
    for channel in (-1,0,1,2):
        for value in range(256):
            c=[0,0,0]
            if channel==-1:c=[value]*3
            else:c[channel]=value
            colors.append(c)
    colors.extend([(8,8,3),(0,4,6),(0,5,8),(113,65,42),(0,22,31),
                   (148,101,49),(6,97,114),(134,128,135)])
    rng=np.random.default_rng(20260926)
    colors.extend(rng.integers(0,256,(2048-len(colors),3)).tolist())
    cells=np.array(colors,np.uint8).reshape(32,64,3)
    return cells.repeat(16,axis=0).repeat(16,axis=1)


def compare(expected,actual):
    if actual.shape!=expected.shape:raise ValueError('Unexpected capture dimensions')
    diff=np.abs(actual.astype(int)-expected.astype(int))
    return dict(exact=bool(np.array_equal(expected,actual)),
                maximum_channel_error=int(diff.max()),
                changed_pixels=int(np.any(diff,axis=2).sum()),
                rgb_rmse=float(np.sqrt(np.mean(diff.astype(float)**2))))


def main(output,auto=False):
    user=C.windll.user32
    try:user.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    except (AttributeError,OSError):pass
    user.GetForegroundWindow.restype=W.HWND
    user.GetAncestor.argtypes=[W.HWND,W.UINT];user.GetAncestor.restype=W.HWND
    user.WindowFromPoint.argtypes=[W.POINT];user.WindowFromPoint.restype=W.HWND
    user.GetDpiForWindow.argtypes=[W.HWND];user.GetDpiForWindow.restype=W.UINT
    output.mkdir(parents=True,exist_ok=False)
    expected=reference_pixels();Image.fromarray(expected).save(output/'reference.png')
    root=tk.Tk();root.title('Color Studio - RGB capture calibration')
    root.resizable(False,False)
    tk.Label(root,text='Independent RGB capture check - no game input',font=('Segoe UI',13)).pack(pady=8)
    photo=ImageTk.PhotoImage(Image.fromarray(expected))
    surface=tk.Label(root,image=photo,borderwidth=0,highlightthickness=0)
    surface.pack(padx=12)
    status=tk.StringVar(value='Ready: 2048 RGB tiles, original pixels, three captures.')
    # Keep button/pointer visual effects outside the reference surface.
    tk.Label(root,textvariable=status,font=('Segoe UI',10)).pack(pady=(100,8))
    report=dict(game_input_sent=False,capture='PIL.ImageGrab.grab(all_screens=True).convert(RGB)',
                reference_shape=list(expected.shape),tile_count=2048,control_gap=100,frames=[],passed=False,
                limitations=['Controlled Tk/SDR fixture on this desktop; does not certify a game-specific HDR or rendering path.'])
    def save_report():
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    def capture_once():
        try:
            root.update_idletasks()
            owner=user.GetAncestor(root.winfo_id(),2)
            if user.GetForegroundWindow()!=owner:raise RuntimeError('Calibration window is not foreground')
            x,y=surface.winfo_rootx(),surface.winfo_rooty();h,w=expected.shape[:2]
            if (surface.winfo_width(),surface.winfo_height())!=(w,h):raise RuntimeError('Fixture is not displayed at 1:1 size')
            for dx in (1,w//2,w-2):
                for dy in (1,h//2,h-2):
                    hit=user.WindowFromPoint(W.POINT(x+dx,y+dy))
                    if user.GetAncestor(hit,2)!=owner:raise RuntimeError('Fixture is occluded')
            actual=np.array(ImageGrab.grab(bbox=(x,y,x+w,y+h),all_screens=True).convert('RGB'))
            index=len(report['frames']);filename=f'grab_{index:02d}.png'
            Image.fromarray(actual).save(output/filename)
            result=compare(expected,actual)
            result.update(file=filename,bbox=[x,y,x+w,y+h],dpi=int(user.GetDpiForWindow(owner)),
                          png_roundtrip_exact=bool(np.array_equal(actual,np.array(Image.open(output/filename)))))
            report['frames'].append(result);save_report()
            if len(report['frames'])<3:root.after(250,capture_once)
            else:
                report['passed']=all(f['exact'] and f['png_roundtrip_exact'] for f in report['frames']);save_report()
                status.set('PASS - all pixels identical' if report['passed'] else 'FAIL - see report.json')
                button.configure(text='Completed',state='disabled')
        except Exception as exc:
            report['error']=str(exc);save_report();status.set('Stopped: '+str(exc));button.configure(state='normal')
    def begin():
        report['frames']=[];report['passed']=False;report.pop('error',None)
        button.configure(state='disabled');status.set('Capturing only this test surface...')
        root.after(1500,capture_once)
    button=tk.Button(root,text='Run capture check',command=begin,width=24)
    button.pack(pady=(0,12))
    root.update_idletasks();sw,sh=root.winfo_screenwidth(),root.winfo_screenheight()
    root.geometry(f'+{max(0,(sw-root.winfo_width())//2)}+{max(0,(sh-root.winfo_height())//2)}')
    if auto:
        status.set('Automatic capture in 8 seconds; no click during measurement.')
        root.after(8000,begin)
    root.mainloop()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--auto',action='store_true')
    args=parser.parse_args();main(args.output,args.auto)
