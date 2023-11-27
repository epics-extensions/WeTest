#!/usr/bin/env python

# Copyright (c) 2019 by CEA
#
# The full license specifying the redistribution, modification, usage and other
# rights and obligations is included with the distribution of this project in
# the file "LICENSE".
#
# THIS SOFTWARE IS PROVIDED AS-IS WITHOUT WARRANTY OF ANY KIND, NOT EVEN THE
# IMPLIED WARRANTY OF MERCHANTABILITY. THE AUTHOR OF THIS SOFTWARE, ASSUMES
# _NO_ RESPONSIBILITY FOR ANY CONSEQUENCE RESULTING FROM THE USE, MODIFICATION,
# OR REDISTRIBUTION OF THIS SOFTWARE.

"""Generic classes used in gui.specific and gui.generator."""


import logging
import tkinter as tk
import tkinter.ttk

from PIL import Image, ImageTk

from wetest.common.constants import FILE_HANDLER, VERBOSE_FORMATTER, WeTestError

# configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(VERBOSE_FORMATTER)
logger.addHandler(stream_handler)
logger.addHandler(FILE_HANDLER)

# display settings
BORDERWIDTH = 1

# display constants
INFO_WRAPLENGTH = 800


# exception definition
class ExistingTreeItem(WeTestError):
    """Item already exists in tree"""


# class definitions
class MyTreeview(tkinter.ttk.Treeview):
    """Adding convenience methods to Treeview
    Keep track of item last parent, useful for reattaching.

    ttk.Treeview get_children method and MyTreeview get_all_attached_children
    return only the list of attached children.
    MyTreeview get_direct_children and get_all_children also return the detached children.
    """

    def __init__(self, *args, **kwargs):
        tkinter.ttk.Treeview.__init__(self, *args, **kwargs)
        self._parent_ref = {"": ""}  # root parent is root

    def get_parent(self, item):
        """Return the item parent id"""
        return self._parent_ref[item]

    def add_tag(self, item, tag):
        """Add the given tag to item if not already present.
        Return true if the tag was added, false if it was already present.
        """
        logger.debug("add `%s` to %s", tag, item)
        current_tags = list(self.item(item, option="tags"))
        need_update = tag not in current_tags
        if need_update:
            current_tags.append(tag)
            self.item(item, tags=current_tags)
        logger.debug("%s tags : %s", item, current_tags)
        return need_update

    def remove_tag(self, item, tag):
        """Remove the given tag to item if present.
        Return true if the tag was removed, false if it was already absent.
        """
        logger.debug("remove `%s` from %s", tag, item)
        current_tags = list(self.item(item, option="tags"))
        changed = False
        try:
            current_tags.remove(tag)
        except ValueError:
            pass
        else:
            changed = True
        self.item(item, tags=current_tags)
        logger.debug("%s tags : %s", item, current_tags)
        return changed

    def add_tag_parents(self, item, tag):
        """Add the tag to all the item's parents"""
        parent = self.get_parent(item)
        self.add_tag(parent, tag)
        if parent != "":
            self.add_tag_parents(parent, tag)

    def remove_tag_parents(self, item, tag):
        """Remove the tag from all the item's parents"""
        parent = self.get_parent(item)
        self.remove_tag(parent, tag)
        if parent != "":
            self.remove_tag_parents(parent, tag)

    def get_all_attached_children(self, item_id=""):
        """Recursively get the children of an item (excluding detached)"""
        direct_children = list(self.get_children(item_id))
        deeper_children = []
        for child_id in direct_children:
            deeper_children += list(self.get_all_attached_children(child_id))
        return tuple(direct_children + deeper_children)

    def get_all_children(self, item_id=""):
        """Recursively get the children of an item (including detached)"""
        direct_children = self.get_direct_children(item_id)

        deeper_children = []
        for child_id in direct_children:
            deeper_children += list(self.get_all_children(child_id))
        return tuple(direct_children + deeper_children)

    def get_direct_children(self, item_id=""):
        """Returns the children of an item (including detached)"""
        direct_children = []
        for child, parent in list(self._parent_ref.items()):
            if parent == item_id:
                direct_children.append(child)

        return tuple(direct_children)

    def get_all(self, with_tag=None):
        """Returns all the item inserted in the Treeview, even if detached.
        If with_tag provided only return the item with one or more of the tags provided
        """
        if with_tag is None:
            output = list(self._parent_ref.keys())
        else:
            output = []
            if not isinstance(with_tag, list):
                with_tag = [with_tag]

            for item in list(self._parent_ref.keys()):
                for tag in with_tag:
                    if tag in self.item(item, option="tags"):
                        output.append(item)
                        break

        return output

    def open_all(self, item_list=None):
        """Set open to True for each item of the list."""
        if item_list is None:
            item_list = self.get_all()
        for item in item_list:
            self.item(item, open=True)

    def close_all(self, item_list=None):
        """Set open to False for each item of the list."""
        if item_list is None:
            item_list = self.get_all()
        for item in item_list:
            self.item(item, open=False)

    def set_children(self, item, *newchildren):
        """Same as ttk.Treeview set_children, and update the parent references"""
        super(MyTreeview, self).set_children(item, *newchildren)
        for child in newchildren:
            self._parent_ref[child] = item

    def insert(self, parent, index, iid, **kw):
        """Same as ttk.Treeview insert, and reference the parent.
        Raise an ExistingTreeItem if iid is already used.
        """
        try:
            iid_exists = self.item(iid)
        except tk.TclError:
            pass
        else:
            raise ExistingTreeItem(
                "Item with iid %s already exists: %s" % (iid, iid_exists),
            )
        item = super(MyTreeview, self).insert(parent, index, iid, **kw)
        self._parent_ref[item] = parent
        return item

    def move(self, item, parent, index):
        """Same as ttk.Treeview move, but add the tag 'attached'"""
        super(MyTreeview, self).move(item, parent, index)
        self._parent_ref[item] = parent

    def reattach(self, item, parent, index):
        """Same as ttk.Treeview reattach, but add the tag 'attached'"""
        self.move(item, parent, index)


class Tooltip:
    # https://stackoverflow.com/questions/3221956/how-do-i-display-tooltips-in-tkinter
    """It creates a tooltip for a given widget as the mouse goes on it.

    see:

    http://stackoverflow.com/questions/3221956/
           what-is-the-simplest-way-to-make-tooltips-
           in-tkinter/36221216#36221216

    http://www.daniweb.com/programming/software-development/
           code/484591/a-tooltip-class-for-tkinter

    - Originally written by vegaseat on 2014.09.09.

    - Modified to include a delay time by Victor Zaccardo on 2016.03.25.

    - Modified
        - to correct extreme right and extreme bottom behavior,
        - to stay inside the screen whenever the tooltip might go out on
          the top but still the screen is higher than the tooltip,
        - to use the more flexible mouse positioning,
        - to add customizable background color, padding, waittime and
          wraplength on creation
      by Alberto Vassena on 2016.11.05.

      Tested on Ubuntu 16.04/16.10, running Python 3.5.2

    TODO: themes styles support
    """

    def __init__(
        self,
        widget,
        bg="#FFFFEA",
        pad=(5, 3, 5, 3),
        text="widget info",
        waittime=400,
        wraplength=INFO_WRAPLENGTH,
    ):
        self.waittime = waittime  # in miliseconds, originally 500
        self.wraplength = wraplength  # in pixels, originally 180
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.onEnter)
        self.widget.bind("<Leave>", self.onLeave)
        # self.widget.bind("<ButtonPress>", self.onLeave)
        self.bg = bg
        self.pad = pad
        self.id = None
        self.tw = None

    def onEnter(self, event=None):
        self.schedule()

    def onLeave(self, event=None):
        self.unschedule()
        self.hide()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(self.waittime, self.show)

    def unschedule(self):
        id_ = self.id
        self.id = None
        if id_:
            self.widget.after_cancel(id_)

    def show(self):
        # if self.text == "":
        #     return

        def tip_pos_calculator(widget, label, tip_delta=(10, 5), pad=(5, 3, 5, 3)):
            w = widget

            s_width, s_height = w.winfo_screenwidth(), w.winfo_screenheight()

            width, height = (
                pad[0] + label.winfo_reqwidth() + pad[2],
                pad[1] + label.winfo_reqheight() + pad[3],
            )

            mouse_x, mouse_y = w.winfo_pointerxy()

            x1, y1 = mouse_x + tip_delta[0], mouse_y + tip_delta[1]
            x2, y2 = x1 + width, y1 + height

            x_delta = x2 - s_width
            if x_delta < 0:
                x_delta = 0
            y_delta = y2 - s_height
            if y_delta < 0:
                y_delta = 0

            offscreen = (x_delta, y_delta) != (0, 0)

            if offscreen:
                if x_delta:
                    x1 = mouse_x - tip_delta[0] - width

                if y_delta:
                    y1 = mouse_y - tip_delta[1] - height

            offscreen_again = y1 < 0  # out on the top

            if offscreen_again:
                # No further checks will be done.

                # TIP:
                # A further mod might automagically augment the
                # wraplength when the tooltip is too high to be
                # kept inside the screen.
                y1 = 0

            return x1, y1

        bg = self.bg
        pad = self.pad
        widget = self.widget

        # creates a toplevel window
        self.tw = tk.Toplevel(widget)

        # Leaves only the label and removes the app window
        self.tw.wm_overrideredirect(True)

        win = tk.Frame(self.tw, background=bg, borderwidth=0)
        label = tk.Label(
            win,
            text=self.text,
            justify=tk.LEFT,
            background=bg,
            relief=tk.SOLID,
            borderwidth=0,
            wraplength=self.wraplength,
        )

        label.grid(padx=(pad[0], pad[2]), pady=(pad[1], pad[3]), sticky=tk.NSEW)
        win.grid()

        x, y = tip_pos_calculator(widget, label)

        self.tw.wm_geometry("+%d+%d" % (x, y))

    def hide(self):
        tw = self.tw
        if tw:
            tw.destroy()
        self.tw = None

    def update_text(self, text):
        """New text to display"""
        self.text = text


class Icon(tk.Label):
    """An image used as an icon.
    The icon can be dynamic, going through the images list.
    Images are expected to be PIL.ImageTk objects.
    """

    def __init__(self, master, images, dynamic=False, *args, **kargs):
        tk.Label.__init__(self, master=master, *args, **kargs)

        # make images a list
        if isinstance(images, list):
            self.images = images
        else:
            self.images = [images]

        # initialise dynamic parameters
        self.dynamic = dynamic  # boolean to run or not through the image list
        self.cur_img = 0  # index of the image to use
        self._already_updating = False  # _update_dynamic-updating is already on

        # run a first update to initialize image
        # and launch automatic update if necessary
        self.update()

    def disable(self):
        self.config(state="disable")

    def start_dynamic(self):
        """Start changing images"""
        self.dynamic = True
        self.update()

    def stop_dynamic(self):
        """Stop changing images"""
        self.dynamic = False
        self.reset()

    def reset(self, idx=0):
        """Go back to specified image index"""
        self.cur_img = idx % len(self.images)
        self.update()

    def update(self):
        """Updates image and increase image index if dynamic."""
        self.configure(image=self.images[self.cur_img % len(self.images)])
        if not self._already_updating:  # only update dynamic if not already on
            self._update_dynamic()

    def _update_dynamic(self):
        if self.dynamic:
            self.cur_img = (self.cur_img + 1) % len(self.images)
            self.configure(image=self.images[self.cur_img])
            self._already_updating = True
            self.after(300, self._update_dynamic)
        else:
            self.cur_img = 0
            self.configure(image=self.images[self.cur_img])
            self._already_updating = False


class ImageGif:
    """Usable as an object, will display the several images of the provided Gif

    master:    tkinter root or any object providing after method
    filepath:  the gif filepath
    delay:     enable to override the delay defined in the gif
    repeat:    number of time the gif should be played, 0 for forever
    start:     whether to start gif as soon as the ImageGif is instanciated
    """

    def __init__(self, master, filepath, delay=None, repeat=0, start=True):
        self.attached = set()

        self._master = master
        self._repeat = repeat  # number of repeatition requested

        self._loc = 0  # frame index to display
        self._count = 0  # current repeat number
        self._is_running = False  # animation status
        self._callback_id = None  # keep after id, for after_cancel

        # extract frames from file
        im = Image.open(filepath)
        self._frames = []
        i = 0
        try:
            while True:
                photoframe = ImageTk.PhotoImage(im.copy().convert("RGBA"))
                self._frames.append(photoframe)
                i += 1
                im.seek(i)
        except EOFError:
            pass

        self._last_index = len(self._frames) - 1

        # extract delay from file
        if delay is None:
            try:
                self._delay = im.info["duration"]
            except:
                self._delay = 100
        else:
            self._delay = delay

        # start at creation
        if start:
            self.start_animation()

    def attach(self, widget, show=True):
        """Use gif on widget `image` porperty."""
        self.attached.add(widget)
        if show:
            self.update_attached(image=self._frames[self._loc])

    def detach(self, widget, image=None):
        """Stop using gif on widget"""
        try:
            self.attached.remove(widget)
        except KeyError:
            pass

        if image is not None:
            widget.configure(image=image)

    def update_attached(self, image):
        """Set image on all attached widgets."""
        unreachable_widgets = []
        for w in self.attached:
            try:
                w.configure(image=image)
            except tk.TclError:
                unreachable_widgets.append()
        for w in unreachable_widgets:
            self.detach(w)

    def set_frame(self, frame):
        """Set a frame on all attached widgets."""
        frame = max(abs(frame), self._last_index)
        self._loc = frame
        self.update_attached(image=self._frames[frame])

    def start_animation(self, frame=None):
        """Begin changing gif frames"""
        if self._is_running:
            return

        if frame is not None:
            self.set_frame(frame)

        self._master.after(self._delay, self._animate_GIF)
        self._is_running = True

    def stop_animation(self, frame=None):
        """Stop changing gif frames"""
        if not self._is_running:
            return

        if self._callback_id is not None:
            self._master.after_cancel(self._callback_id)
            self._callback_id = None

        if frame is not None:
            self.set_frame(frame)

        self._is_running = False

    def _animate_GIF(self, idx=None):
        """Callback function for update with after"""
        self._loc = (self._loc + 1) % self._last_index
        self.update_attached(image=self._frames[self._loc])

        if self._loc == 0:  # end the frame sequence
            if self._repeat <= 0 or self._count < self._repeat:
                if self._repeat > 0:
                    self._count += 1
                self._callback_id = self._master.after(self._delay, self._animate_GIF)
            else:
                self._callback_id = None
                self._is_running = False
        else:
            self._callback_id = self._master.after(self._delay, self._animate_GIF)


class PopUpMenu(tk.Menu):
    """It creates a floating menu near the mouse when right-clicking a widget.
    http://effbot.org/zone/tkinter-popup-menu.htm
    """

    def __init__(
        self, master, bound_widgets, bindings=["<Button-3>"], tearoff=0, **options,
    ):
        tk.Menu.__init__(self, master=master, tearoff=tearoff, **options)

        if isinstance(bound_widgets, str):
            self.bound_widgets = [bound_widgets]
        elif not isinstance(bound_widgets, list):
            self.bound_widgets = list(bound_widgets)
        else:
            self.bound_widgets = bound_widgets

        if isinstance(bindings, str):
            self.bindings = [bindings]
        elif not isinstance(bound_widgets, list):
            self.bindings = list(bindings)
        else:
            self.bindings = bindings

        for widget in self.bound_widgets:
            for binding in self.bindings:
                self.add_binding(widget, binding)

    def do_popup(self, event):
        # display the popup menu
        try:
            self.tk_popup(event.x_root, event.y_root, 0)
        finally:
            # make sure to release the grab (Tk 8.0a1 only)
            self.grab_release()

    def add_binding(self, widget, binding):
        widget.bind(binding, self.do_popup)


def clip_generator(to_clip):
    """Return a function that will write text to clipboard when called.
    https://stackoverflow.com/questions/579687/how-do-i-copy-a-string-to-the-clipboard-on-windows-using-python
    """

    def clip(event=None):
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(str(to_clip))
        r.update()  # now it stays on the clipboard after the window is closed
        r.destroy()

    return clip


if __name__ == "__main__":
    root = tk.Tk()

    g = ImageGif(
        root,
        "wetest/resources/icons/iconmonstr-loading-10-24.gif",
        start=False,
        delay=100,
    )

    b = tk.Button(root, text="Test", compound="left")
    b.pack(side="left")

    g.attach(b)

    tk.Button(root, text="Start", command=g.start_animation).pack()
    tk.Button(root, text="Stop", command=g.stop_animation).pack()
    tk.Button(root, text="Frame", command=lambda: g.set_frame(3)).pack()

    l = tk.Label()
    l.pack()
    g.attach(l)

    root.mainloop()
