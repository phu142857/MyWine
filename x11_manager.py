import os

from Xlib import X
from Xlib import Xutil
from Xlib import display
from Xlib.ext import xtest
from Xlib.protocol import event

class X11WindowManager:
    def __init__(self):
        display_name = os.environ.get("DISPLAY")

        if not display_name:
            raise RuntimeError("DISPLAY not set")

        self.display = display.Display(display_name)

    def window(self, win_id):
        return self.display.create_resource_object("window", win_id)

    def get_geometry(self, win_id):
        g = self.window(win_id).get_geometry()

        return (g.x, g.y, g.width, g.height)

    def resize_window(self, win_id, width, height):
        win = self.window(win_id)
        win.configure(width = width, height = height)
        self.display.flush()

    def reparent_window(self, child_id, parent_id):
        child = self.window(child_id)
        parent = self.window(parent_id) 
        
        child.reparent(parent, 0, 0)
        child.map()
        self.display.flush()

    def configure_embedded_window(self, win_id, width, height):
        win = self.window(win_id)

        win.configure(x = 0, y = 0, width = width, height = height, border_width = 0)
        win.set_wm_normal_hints(
            hints = {
                "flags": (
                    Xutil.PPosition | Xutil.PSize | Xutil.PMinSize | Xutil.PMaxSize
                ),
                "width": width,
                "height": height,
                "min_width": width,
                "min_height": height,
                "max_width": width,
                "max_height": height,  
            }
        )

        self.display.flush()

    def set_focus(self, win_id):
        self.window(win_id).set_input_focus(X.RevertToParent, X.CurrentTime)
        self.Display.flush()

    def click(self, root_x, root_y):
        xtest.fake_input(self.display, X.MotionNotify, x = root_x, y = root_y)   
        xtest.fake_input(self.display, X.ButtonPress, detail = 1)
        xtest.fake_input(self.display, X.ButtonRelease, detail = 1)
        
        self.display.flush()
