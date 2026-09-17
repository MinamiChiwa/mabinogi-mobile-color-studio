from i18n import tr
"""Frozen desktop eyedropper: the preview never contaminates sampled pixels."""
import tkinter as tk
from PIL import ImageGrab,ImageTk
import platform_win

def pixel_hex(image,x,y):
    x=max(0,min(image.width-1,int(x)));y=max(0,min(image.height-1,int(y)))
    return '#%02X%02X%02X'%image.convert('RGB').getpixel((x,y))

def pick_screen(root,callback):
    if getattr(root,'picking',False) or root.busy:return
    root.picking=True;root.withdraw()
    def open_overlay():
        try:
            screen=ImageGrab.grab(all_screens=True).convert('RGB')
            x0,y0=platform_win.u.GetSystemMetrics(76),platform_win.u.GetSystemMetrics(77)
            overlay=tk.Toplevel(root);overlay.title(tr('屏幕吸管 · 单击取色 / Esc 取消'));overlay.attributes('-fullscreen',True);overlay.attributes('-topmost',True)
            overlay.geometry(f'{screen.width}x{screen.height}+0+0')
            canvas=tk.Canvas(overlay,highlightthickness=0,cursor='crosshair');canvas.pack(fill='both',expand=True)
            photo=ImageTk.PhotoImage(screen);canvas.create_image(0,0,image=photo,anchor='nw');overlay.photo=photo
            label=tk.Label(overlay,text=tr('移动预览 · 单击取色 · Esc 取消'),bg='#10151F',fg='white',font=('Microsoft YaHei UI',12),padx=14,pady=10)
            label.place(x=20,y=20)
            def finish(color=None):
                overlay.destroy();root.picking=False;root.deiconify();root.lift()
                if color:callback(color)
            def preview(event):
                color=pixel_hex(screen,event.x,event.y)
                label.configure(text=tr(f'{color}   单击取色 · Esc 取消'),bg=color,fg='black' if sum(int(color[i:i+2],16) for i in (1,3,5))>400 else 'white')
                label.place(x=min(max(0,event.x+20),max(0,screen.width-320)),y=min(max(0,event.y+20),max(0,screen.height-60)))
            canvas.bind('<Motion>',preview);canvas.bind('<Button-1>',lambda e:finish(pixel_hex(screen,e.x,e.y)))
            overlay.bind('<Escape>',lambda e:finish());overlay.bind('<Button-3>',lambda e:finish())
            overlay.update_idletasks()
            hwnd=platform_win.u.GetParent(overlay.winfo_id()) or overlay.winfo_id()
            platform_win.u.SetWindowPos(hwnd,-1,x0,y0,screen.width,screen.height,0x0040)
            overlay.focus_force()
        except Exception as e:
            root.picking=False;root.deiconify();root.status.configure(text=f'屏幕取色失败：{e}')
    root.after(180,open_overlay)
