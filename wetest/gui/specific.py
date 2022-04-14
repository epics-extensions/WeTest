#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

"""WeTest entities classes for GUI."""
# icons from https://iconmonstr.com/
# gifs from https://ezgif.com/
# colors from:
# - http://www.tcl.tk/man/tcl8.5/TkCmd/colors.htm
# - https://www.color-blindness.com/color-name-hue/



import logging
import multiprocessing
import re
import subprocess
import tkinter as tk
import tkinter.ttk

from multiprocessing import Queue
from queue import Empty
from PIL import ImageTk, Image
from pkg_resources import resource_filename

from wetest.common.constants import (
    SELECTION_FROM_GUI, START_FROM_GUI, RESUME_FROM_GUI,
    PAUSE_FROM_GUI, ABORT_FROM_GUI,
    END_OF_TESTS, REPORT_GENERATED,
    PAUSE_FROM_MANAGER, ABORT_FROM_MANAGER, PLAY_FROM_MANAGER
    )
from wetest.common.constants import VERBOSE_FORMATTER, FILE_HANDLER, to_string

from wetest.pvs.core   import PVData
from wetest.pvs.naming import NamingError

from wetest.gui.base import (
    BORDERWIDTH, INFO_WRAPLENGTH,
    ExistingTreeItem, MyTreeview, Tooltip, Icon, PopUpMenu, clip_generator,
    )
# enable or not DEBUG displays
DEBUG_INFOS = False  # show all subtest data in subtests tooltip

# configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(VERBOSE_FORMATTER)
logger.addHandler(stream_handler)
logger.addHandler(FILE_HANDLER)

# possible icon status
STATUS_UNKNOWN = "UNKOWN"
STATUS_NOT_SET = "Status to bet set"
STATUS_RUN = "Running"
STATUS_RETRY = "Retrying"
STATUS_P_RETRY = "Retry paused"
STATUS_PAUSE = "Paused"
STATUS_WAIT = "Pending"
STATUS_SKIP = "Skipped"
STATUS_STOP = "Stopped"
STATUS_ERROR = "ERRORED"
STATUS_FAIL = "FAILED"
STATUS_SUCCESS = "Succeeded"

# display settings
PADDING_X_LABEL = 4
PADDING_X_FRAME = 20
PADDING_Y_LABEL = 4
PADDING_Y_FRAME = 0

## Color used already (for icons too)
GREY    = "#8F8F8F"
ORANGE  = "#FF8C00"
RED     = "#FF0000"
GREEN   = "#32CD32"
MAGENTA = "#FF00FF"
BLACK   = "#000000"

# Treeview tags
TAG_CONNECTED = "connected"
TAG_DISCONNECTED = "disconnected"
TAG_SECTION = "section"
TAG_PV = "pv"
TAG_AS_SETTER = "as setter"
TAG_AS_GETTER = "as getter"
TAG_UPDATE = "updated"
PVS_FRAME_TEXT = " Process Variables "

# toggle constants
COLLAPSED = 0
EXPANDED = 1
SELECTED = "selected"
PARTIAL = "partially selected"
SKIPPED = "skipped"


class PVsTreeview(MyTreeview):
    """Adds special support for TAG_CONNECTED, TAG_DISCONNECTED and TAG_PV"""

    def __init__(self, *args, **kwargs):
        MyTreeview.__init__(self, *args, **kwargs)
        self.pvs_refs = {}  # root parent is root

    def _update_pvs_status(self, item):
        """method to call to populate or update self.pvs_refs"""
        item_tags = list(self.item(item, option="tags"))
        if TAG_PV in item_tags:
            self.pvs_refs[item] = None
            if TAG_DISCONNECTED in item_tags and TAG_CONNECTED in item_tags:
                logger.error("PV tagged as both connected and disconnected: %s", item)
            elif TAG_DISCONNECTED in item_tags:
                self.pvs_refs[item] = TAG_DISCONNECTED
            elif TAG_CONNECTED in item_tags:
                self.pvs_refs[item] = TAG_CONNECTED

    def insert(self, parent, index, iid=None, **kw):
        """Same as MyTreeview insert, but register the pvs their status"""
        item = super(PVsTreeview, self).insert(parent, index, iid, **kw)
        self._update_pvs_status(item)
        return item

    def add_tag(self, item, tag):
        """Same as MyTreeview add_tag, but register the pvs and their status"""
        changed = super(PVsTreeview, self).add_tag(item, tag)
        if changed:
            self._update_pvs_status(item)
        return changed

    def total_pvs_nb(self):
        return len(self.pvs_refs)

    def connected_pvs_nb(self):
        return len([ pv for pv, status in list(self.pvs_refs.items()) if status == TAG_CONNECTED])

    def disconnected_pvs_nb(self):
        return len([ pv for pv, status in list(self.pvs_refs.items()) if status == TAG_DISCONNECTED])

    def unknown_pvs_nb(self):
        return len([ pv for pv, status in list(self.pvs_refs.items()) if status == None])

    def update_connection(self, item):
        """Set item TAG_CONNECTED and TAG_DISCONNECTED based on children tags"""
        # find out children connection status
        mark_as_connected = False
        mark_as_disconnected = False
        for child in self.get_direct_children(item):
            mark_as_connected |= TAG_CONNECTED in self.item(child, option="tags")
            mark_as_disconnected |= TAG_DISCONNECTED in self.item(child, option="tags")
            if mark_as_connected and mark_as_disconnected:
                # no need to look further
                break
        # apply corresponding tags
        changed = False
        if not mark_as_connected:
            changed |= self.remove_tag(item, TAG_CONNECTED)
        if not mark_as_disconnected:
            changed |= self.remove_tag(item, TAG_DISCONNECTED)
        if mark_as_connected:
            changed |= self.add_tag(item, TAG_CONNECTED)
        if mark_as_disconnected:
            changed |= self.add_tag(item, TAG_DISCONNECTED)

        # propagate to parents if needed
        if changed:
            self.update_connection(self.get_parent(item))



class StatusIcon(Icon):
    """An Icon with various images set, corresponding to diffrent statuses.
    Expected statuses are:
        STATUS_UNKNOWN
        STATUS_NOT_SET
        STATUS_RUN
        STATUS_RETRY
        STATUS_P_RETRY
        STATUS_PAUSE
        STATUS_WAIT
        STATUS_SKIP
        STATUS_STOP
        STATUS_ERROR
        STATUS_FAIL
        STATUS_SUCCESS
    """

    def __init__(self, master,
                status=STATUS_NOT_SET, dynamic=False,
                *args, **kargs):

        self.status_images = {
                STATUS_UNKNOWN:[
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-help-2-24.png"))),
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-help-2-24_OFF.png"))),
                    ],
                STATUS_NOT_SET:[
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-help-2-24_OFF.png"))),
                    ],
                STATUS_RUN: [
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-media-control-3-24.png"))),
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-media-control-3-24_OFF.png"))),
                    ],
                STATUS_RETRY: [
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-media-control-3-24_RED.png"))),
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-media-control-3-24_OFF.png"))),
                    ],
                STATUS_P_RETRY: [
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-media-control-7-24_RED.png"))),
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-media-control-7-24_OFF.png"))),
                    ],
                STATUS_PAUSE: [
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-media-control-7-24_OFF.png"))),
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-media-control-7-24.png"))),
                    ],
                STATUS_WAIT: [
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-time-18-24.png")))
                    ],
                STATUS_SKIP: [
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-media-control-31-24.png")))
                    ],
                STATUS_STOP: [
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-media-control-11-24_OFF.png")))
                    ],
                STATUS_ERROR: [
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-warning-7-24.png"))),
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-warning-7-24_OFF.png"))),
                    ],
                STATUS_FAIL: [
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-x-mark-4-24.png"))),
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-x-mark-4-24_OFF.png"))),
                    ],
                STATUS_SUCCESS: [
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-check-mark-7-24.png"))),
                    ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-check-mark-7-24_OFF.png"))),
                    ]
                }

        self.tooltip_text = None
        self.status = status if status in list(self.status_images.keys()) else STATUS_UNKNOWN
        self.images = self.status_images[self.status]
        Icon.__init__(self, master=master, images=self.images, dynamic=dynamic, *args, **kargs)

        self.tooltip = Tooltip(self, text=status)

    def change_status(self, status=None, dynamic=None):
        """Can change status, and start or stop dynamic mode, updates tooltip."""
        self.tooltip.update_text(self.tooltip_text if self.tooltip_text is not None else status)
        if dynamic is not None:
            if dynamic:
                self.start_dynamic()
            else:
                self.stop_dynamic()
        if status is not None:
            self.status = status if status in list(self.status_images.keys()) else STATUS_UNKNOWN
            self.images = self.status_images[self.status]
        self.update()


def status_priority(status):
    """Function to use for sorting status priority"""
    scores = {
        STATUS_SKIP:     0,
        STATUS_SUCCESS:  5,
        STATUS_WAIT:    10,
        STATUS_RUN:     40,
        STATUS_FAIL:    50,
        STATUS_ERROR:   60,
        # STATUS_UNKNOWN:  70,
        STATUS_RETRY:   80,
        STATUS_PAUSE:   90,
        STATUS_P_RETRY: 95,
        STATUS_STOP:    100,
        STATUS_UNKNOWN: 110,
        STATUS_NOT_SET: 120
    }
    return scores[status]


def duration_str(duration):
    """Compute duration string to show, change format based on duration value."""
    if duration == None: # do not show
        duration_text = "-----"

    elif duration < 1: # show in ms
        duration_text = "% 3.0fms"%(duration*1000)

    elif duration <10: # show on 2 digits
        duration_text = "%.2fs"%duration

    elif duration <100: # show on 3 digits
        duration_text = "%.1fs"%duration

    else: # show with 0 digits precision
        duration_text = "%.0fs"%duration

    return duration_text


class InfosStatusFrame(tk.Frame, object):
    # object is required to use super on with tk.Frame "old-Style" class
    # https://stackoverflow.com/questions/1713038/super-fails-with-error-typeerror-argument-1-must-be-type-not-classobj-when
    """A Frame with a title, a StatusIcon and tooltip infos."""

    def __init__(self, parent,
                title="", infos="",
                status=None, dynamic=False,
                indent="", select=SELECTED,
                *args, **options):

        self.title = title  # not used, for debug purposes
        self.infos = infos  # not used, for debug purposes

        self.indent = indent
        self.status_children = []
        self.traceback = []  # actually a string for SubTests.
        self.durations = []

        self.icons={
            # collapse icons
            "right_arrow": ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-arrow-63-12.png"))),
            "left_arrow": ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-arrow-64-12.png"))),
            "down_arrow": ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-arrow-65-12.png"))),
            "up_arrow": ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-arrow-66-12.png"))),
            # tooltip icons
            "info": ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-speech-bubble-20-16.png"))),
            # selection icons
            SELECTED: ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-checkbox-9-16.png"))),
            PARTIAL: ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-checkbox-10-16.png"))),
            SKIPPED: ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-checkbox-11-16.png"))),
            # test type
            "random":  ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-media-control-55-16.png"))),
        }

        # default options if not already defined
        if "relief" not in options: options["relief"]="raised"
        if "borderwidth" not in options: options["borderwidth"]=1
        # tk.Frame.__init__(self, parent, *args, **options)

        # configure and display self
        tk.Frame.__init__(self, parent, *args, **options)

        # configure and display title frame
        self.title_frame = tk.Frame(self)
        self.title_frame.pack(fill="x", expand=1)

        # configure and display a StatusIcon
        self.status_frame = tk.Frame(self.title_frame)
        self.status_frame.pack(side="right")
        self.prev_status = None
        self.status_icon = StatusIcon(
            master=self.status_frame, status=status, dynamic=False)
        self.status_icon.pack(side="left", pady=1, padx=1 )

        # add a frame that show tooltip information
        self.infos_frame = tk.Frame(self.title_frame)
        self.infos_frame.pack(side="left", fill="x", expand=1)

        # display title
        self.select_label = tk.Label(self.infos_frame, text=self.indent, anchor="w", compound="right")#, background="#FFFFFF")
        self.select_label.pack(side="left", pady=PADDING_Y_LABEL, padx=(PADDING_X_LABEL,0))
        self.toogle_label = tk.Label(self.infos_frame, anchor="w", state="disabled", image=self.icons["right_arrow"], compound="right")
        self.toogle_label.pack(side="left", pady=PADDING_Y_LABEL, padx=(PADDING_X_LABEL,0))
        self.title_label = tk.Label(self.infos_frame, text=title, anchor="w")
        self.title_label.pack(side="left", fill="x", pady=PADDING_Y_LABEL, padx=(PADDING_X_LABEL,0))

        # add infos to infos_frame
        # infos = infos if infos is not None else [""]
        self.infos_label = tk.Label(self.infos_frame, text="(i)", anchor="w",
            image=self.icons["info"], state="disable")
        self.infos_label.pack(side="right", padx=(PADDING_X_LABEL,0))
        if infos is not None and "\n".join(infos) != "":
            self.infos_label.config(state="normal")
            Tooltip(self.infos_frame, text="\n".join(infos))

        # show execution duration
        self.duration_label = tk.Label(self.title_frame, text=" %s "%duration_str(None), anchor="w")
        self.duration_label.pack(side="left")  # padding in text
        self.prev_duration = None  # store previous duration for duration colorization
        self.prev_duration_str = "Test duration"  # tooltip will be updated if replay
        self.duration_color = BLACK  # change label foreground in case of significant (10%) change
        self.duration_tooltip = Tooltip(self.duration_label, text=self.prev_duration_str)

        # configure and collapsable frame
        frame_bg = self.cget("bg")
        self.sub_frame_bg = "#"+hex(
            min(
                int("0xffffff",16),
                int(frame_bg[1:],16) + int("101010",16))
            )[2:]
        self.sub_frame = tk.Frame(
            self, relief="sunken", borderwidth=BORDERWIDTH, background=self.sub_frame_bg)

        # call refresh icon status
        self.update_status()

        # apply initial select
        self.toogle_select(selected=select)

        # bindings
        # see also bind_title_frame
        self.select_label.bind("<Button-1>", self.toogle_select)

    def reset(self, status=None):
        """Reinitialize for replay, keep previous result but empty traceback."""
        # discriminate the first run
        if self.prev_status is None:
            self.prev_status = []
            if status is not None:
                self.status_icon.change_status(status)
            return

        if status is None:
            status=STATUS_NOT_SET

        # backup previous duration
        duration = sum(self.durations)
        if duration != 0.0:
            self.prev_duration = duration
            self.prev_duration_str = "Last run: %s"%duration_str(duration).strip()
        self.duration_tooltip.update_text(self.prev_duration_str)

        # backup previous icon status
        self.status_icon.disable()
        self.prev_status.append(self.status_icon)
        if len(self.prev_status)>1:
            self.prev_status.pop(0).forget()

        # reset traceback
        self.traceback = []

        # reset status
        self.status_icon = StatusIcon(
            master=self.status_frame, status=status, dynamic=False)
        self.status_icon.pack(side="left", pady=1, padx=1 )

        # reset duration
        self.durations=[]
        self.duration_label.config(text=" %s "%duration_str(None))
        self.duration_color=BLACK
        self.duration_label.config(fg=self.duration_color)

        # refresh display
        self.update_idletasks()  # nicer display that way


    def update_status(self, status=None, dynamic=None):
        """Convenience method to update status_icon."""
        status = status if status is not None else self.status_icon.status
        dynamic = dynamic if dynamic is not None else self.status_icon.dynamic
        self.status_icon.change_status(status, dynamic)

    def bind_title_frame(self, event, callback=None):
        """Bind the event and callback to info_frame, title_label and toogle_label
        to unbind set callback to None
        """
        if callback is None:
            self.infos_frame.bind(event, lambda e: None)
            self.title_label.bind(event, lambda e: None)
            self.toogle_label.bind(event, lambda e: None)
            if hasattr(self, "test_type_widget"):
                self.test_type_widget.bind(event, lambda e: None)
            self.infos_label.bind(event, lambda e: None)
            self.duration_label.bind(event, lambda e: None)
        else:
            self.infos_frame.bind(event, callback)
            self.title_label.bind(event, callback)
            self.toogle_label.bind(event, callback)
            if hasattr(self, "test_type_widget"):
                self.test_type_widget.bind(event, callback)
            self.infos_label.bind(event, callback)
            self.duration_label.bind(event, callback)

    def bind_status_icon(self, event, callback=None):
        """Bind the event and callback to status_icon
        to unbind set callback to None
        """
        if callback is None:
            self.status_icon.bind(event, lambda e: None)
        else:
            self.status_icon.bind(event, callback)

    def update_icon_tooltip(self, traceback_text):
        """Change status_icon tooltip and update"""
        self.status_icon.tooltip_text = traceback_text
        self.status_icon.change_status()

    def set_children_status(self,status, dynamic=None):
        """Requires all the tests and subtests to a given status."""
        for child in self.status_children:
            child.set_children_status(status, dynamic)
        self.update_status()

    def toogle_select(self, event=None, selected=None):
        """Change select value and icon."""
        if selected is None:
            if self.selected in [SELECTED]:
                self.selected = SKIPPED
            else:
                self.selected = SELECTED
        elif selected in [SELECTED, PARTIAL, SKIPPED]:
            self.selected = selected
        else:
            raise NotImplementedError(
                "Unexpected value for selected: %s"%selected)

        self.select_label.config(image=self.icons[self.selected])

        select = SKIPPED if self.selected == SKIPPED else SELECTED
        for child in self.status_children:
            child.toogle_select(selected=select)

        self.check_selection()

    def check_selection(self):
        """Check children status, updates own status
        if multiple status then use partial select icon.
        """
        children_selection = { child.selected for child in self.status_children }
        if len(children_selection) == 0:
            pass # no children do not update self.selected nor icon
        else:
            if len(children_selection) == 1:
                if SELECTED in children_selection:
                    self.selected = SELECTED
                elif PARTIAL in children_selection:
                    self.selected = PARTIAL
                elif SKIPPED in children_selection:
                    self.selected = SKIPPED
                else:
                    raise NotImplementedError(
                        "Unexpected value for selected: %s"%children_selection)
            elif len(children_selection) > 1:
                self.selected = PARTIAL
            self.select_label.config(image=self.icons[self.selected])


class SubtestFrame(InfosStatusFrame):
    """An InfosStatusFrame with an id, which updates its parents status"""

    def __init__(self, parent_widget, parent_test, ids_handle, st_id,
                 title="", infos=None,
                 status=STATUS_WAIT, dynamic=False,
                 select=SELECTED,
                 *args, **options):

        # initialise attributes
        self.parent_test = parent_test
        self.id = st_id
        self.test_data = infos

        # add self to ids_handles
        ids_handle[self.id]=self

        # configure and display self
        InfosStatusFrame.__init__(
            self, parent=parent_widget, title=title,
            infos=build_subtest_desc(st_id, self.test_data), indent=" "*6,
            status=status, dynamic=dynamic, select=select, *args, **options)

        # initalise toogle
        self.traceback_show = tk.IntVar()
        self.traceback_show.set(COLLAPSED)
        self.traceback_label = None

        # set up popup menu
        self.popup_menu = PopUpMenu(master=self,
            bound_widgets=[self.infos_frame, self.title_label, self.infos_label, self.sub_frame]
            )
        self.popup_menu.add_command(
            label="copy setter (%s)"%self.test_data.setter,
            state="disabled" if self.test_data.setter is None else "normal",
            command=clip_generator(self.test_data.setter)
            )
        self.popup_menu.add_command(
            label="copy getter (%s)"%self.test_data.getter,
            state="disabled" if self.test_data.getter is None else "normal",
            command=clip_generator(self.test_data.getter)
            )
        self.popup_menu.add_command(
            label="copy setter and getter",
            state="disabled" if self.test_data.setter is None or self.test_data.getter is None else "normal",
            command=clip_generator("%s %s"%(self.test_data.setter, self.test_data.getter))
            )
        self.popup_menu.add_separator()
        self.popup_menu.add_command(
            label="copy failure or error traceback",
            state="disabled"
            )
        self.index_ref = {"setter":0, "getter":1, "all":2, "sep":3, "traceback":4}

    def update_status(self, status=None, dynamic=None, duration=None):
        """Update own status and and tells parent to update."""
        super(SubtestFrame, self).update_status(status, dynamic)
        # display duration
        if duration is not None:
            self.durations.append(float(duration))
            total_duration = sum(self.durations)
            # deal with retries
            if len(self.durations) > 1:
                tooltip_text="Retry durations:"
                for i,x in enumerate(self.durations):
                    tooltip_text+="\n%d/%d: %.3fs"%(i+1, len(self.durations), x)
                self.duration_tooltip.update_text(self.prev_duration_str+"\n"+tooltip_text)
                self.duration_label.config(text="[%s]"%duration_str(total_duration))
            else:
                self.duration_label.config(text=" %s "%duration_str(total_duration))
            # change color if duration change by more than 10%
            self.duration_color=BLACK
            if self.prev_duration is not None:
                if total_duration > self.prev_duration*1.1:
                    self.duration_color=RED
                elif total_duration < self.prev_duration*0.9:
                    self.duration_color=GREEN
            self.duration_label.config(fg=self.duration_color)

        self.parent_test.update_status()

    def reset(self, status):
        """Reset and collapse."""
        # cancel set_traceback if necessary
        if self.traceback_label is not None:
            # close traceback display
            self.traceback_show.set(COLLAPSED)
            self.traceback_toggle()
            self.toogle_label.config(state="disabled")
            self.popup_menu.entryconfig(self.index_ref["traceback"], state="disabled")
            # clear traceback
            self.traceback_label.forget()
            self.traceback_label = None
            self.bind_status_icon("<Button-1>")
            self.bind_title_frame("<Button-1>")

        super(SubtestFrame, self).reset(status=status)

    def check_selection(self):
        """Request parent to check selection."""
        self.parent_test.check_selection()

    def set_children_status(self, status, dynamic=None):
        """Mark as required when not a definitive status, call parent status update"""
        if self.status_icon.status in [STATUS_STOP, STATUS_PAUSE, STATUS_WAIT]:
            self.update_status(status=status, dynamic=dynamic)
        self.update_status()

    def set_traceback(self, traceback_text, tooltip_only=False):
        """update status_icon tooltip, sub_frame content and parent traceback

        Unless tooltip only is set to True, then only the tooltip is updated.
        """

        # change status icon tooltip
        self.update_icon_tooltip(traceback_text)

        if not tooltip_only:

            self.traceback = traceback_text

            # show traceback in sub_frame
            self.traceback_label = tk.Label(
                self.sub_frame, text=self.traceback,
                background=self.sub_frame_bg, anchor='w',
                wraplength=INFO_WRAPLENGTH)
            self.traceback_label.pack(
                side="bottom", fill="x", expand=1,
                pady=PADDING_Y_LABEL, padx=PADDING_X_LABEL)

            # enable popupmenu on subframe label
            self.popup_menu.add_binding(self.traceback_label, "<Button-3>")
            # update traceback entry of popupmenu
            self.popup_menu.entryconfig(
                self.index_ref["traceback"],
                state="normal",
                command=clip_generator(self.traceback)
            )

            # enable click on subtest
            self.bind_status_icon("<Button-1>", self.traceback_click)
            self.bind_title_frame("<Button-1>", self.traceback_click)
            self.toogle_label.config(state="normal")

            # send traceback to parent
            self.parent_test.add_traceback(self.status_icon.status, self.id, self.traceback)

    def traceback_click(self, event=None):
        if self.traceback_show.get() == EXPANDED:
            self.traceback_show.set(COLLAPSED)
        else:
            self.traceback_show.set(EXPANDED)
        self.traceback_toggle()

    def traceback_toggle(self):
        """Toogle sub_frame visibility and toggle_button displayed character"""
        if self.traceback_show.get() == EXPANDED:
            self.sub_frame.pack(side="bottom", fill="x", expand=1)
            self.toogle_label.config(image=self.icons["down_arrow"])
        else:
            self.sub_frame.forget()
            self.toogle_label.config(image=self.icons["right_arrow"])


class TestFrame(InfosStatusFrame):
    """An InfosStatusFrame with subtests content"""

    def __init__(self, parent_widget, parent_scenario, ids_handle,
                 title="", infos="", status=None, dynamic=False,
                 *args, **options):

        # initialise attributes
        self.parent_scenario = parent_scenario
        self.ids_handle = ids_handle
        self.traceback = []

        # configure and display self
        InfosStatusFrame.__init__(
            self, parent=parent_widget, title="Test: "+title, infos=infos, indent=" "*3,
            status=status, dynamic=dynamic, *args, **options)
        # self.infos_children = self.status_children

        # initalise toogle
        self.subtests_show = tk.IntVar()
        self.subtests_show.set(COLLAPSED)

        # configure title_frame click
        self.bind_status_icon("<Button-1>", self.subtests_click)
        self.bind_title_frame("<Button-1>", self.subtests_click)
        self.toogle_label.config(state="normal")

        # empty label for padding at sub_frame bottom
        self.padding_label = tk.Label(
            self.sub_frame, text="", background=self.sub_frame_bg)
        self.padding_label.pack(
            side="bottom", fill="x", pady=PADDING_Y_LABEL, expand=1)
        Tooltip(self.padding_label, text=title)

    def subtests_click(self, event=None):
        if self.subtests_show.get() == EXPANDED:
            self.subtests_show.set(COLLAPSED)
        else:
            self.subtests_show.set(EXPANDED)
        self.subtests_toggle()

    def subtests_toggle(self):
        """Toogle sub_frame visibility and toggle_button displayed character"""
        if self.subtests_show.get() == EXPANDED:
            self.sub_frame.pack(side="bottom", fill="x", expand=1)
            self.toogle_label.config(image=self.icons["down_arrow"])
        else:
            self.sub_frame.forget()
            self.toogle_label.config(image=self.icons["right_arrow"])

    def subtests_expand(self):
        """Call toggle method if not already expanded."""
        if self.subtests_show.get() != EXPANDED:
            self.subtests_show.set(EXPANDED)
            self.subtests_toggle()

    def subtests_collapse(self):
        """Call toggle method if not already collapsed."""
        if self.subtests_show.get() != COLLAPSED:
            self.subtests_show.set(COLLAPSED)
            self.subtests_toggle()

    def add_subtest(self, st_id, title, infos):
        """Add a subtest in the sub_frame and to status_children.
        Returns the created subtest.
        """
        status = STATUS_WAIT
        select = SELECTED
        if infos.skip:
            status = STATUS_SKIP
            select = SKIPPED

        subtest = SubtestFrame(
            parent_widget = self.sub_frame, parent_test = self,
            ids_handle = self.ids_handle, st_id=st_id,
            title=title, infos=infos, status=status, select=select)
        self.status_children.append(subtest)
        subtest.pack(side="top", fill="x", expand=1,
            pady=PADDING_Y_FRAME, padx=(0, PADDING_X_FRAME), anchor="n")
        self.update_status()
        self.check_selection()
        return subtest

    def update_status(self):
        """Update status based on children statuses and and tells parent to update."""
        if len(self.status_children) == 0:
            return

        # update status
        new_status = max(
            [child.status_icon.status for child in self.status_children],
            key=status_priority)
        new_dynamic = any([child.status_icon.dynamic for child in self.status_children])
        super(TestFrame, self).update_status(new_status, new_dynamic)

        # display durations
        self.durations = [ sum(c.durations) for c in self.status_children if len(c.durations)>0 ]
        if len(self.durations) == 0:
            total_duration = None
        else:
            total_duration = sum(self.durations)
        self.duration_label.config(text=" %s "%duration_str(total_duration))
        # get colors from children
        durations_colors = { c.duration_color for c in self.status_children }
        if RED in durations_colors:
            self.duration_color = RED
        elif GREEN in durations_colors:
            self.duration_color = GREEN
        else:
            self.duration_color = BLACK
        self.duration_label.config(fg=self.duration_color)

        # tell parent to update
        self.parent_scenario.update_status()

    def check_selection(self):
        """Check children selection and Request parent to check selection."""
        super(TestFrame, self).check_selection()
        self.parent_scenario.check_selection()

    def add_traceback(self, status, id, traceback):
        """Register the traceback and update status_icon tooltip"""
        self.traceback.append("%s %s: %s"%(status, id, traceback))
        self.update_icon_tooltip("\n".join(self.traceback))
        self.parent_scenario.add_traceback(status, id, traceback)


class ScenarioFrame(InfosStatusFrame):
    """An InfosStatusFrame with tests content"""

    def __init__(self, parent_widget, ids_handle,
                 title="", test_type=None, infos="", status=None, dynamic=False,
                 *args, **options):

        # initialise attributes
        self.ids_handle = ids_handle

        # configure and display self
        InfosStatusFrame.__init__(
            self, parent=parent_widget, title="Scenario: "+title, infos=infos,
            status=status, dynamic=dynamic, *args, **options)
        # self.infos_children = self.status_children

        # set type status
        self.test_type_widget = tk.Label(self.infos_frame,
            anchor="w", image=self.icons["random"], compound="right",
            state="normal" if test_type == "unit" else "disabled")
        self.test_type_widget.pack(side="right", pady=PADDING_Y_LABEL, padx=(PADDING_X_LABEL,0))
        # self.infos_label.pack(side="right", padx=(PADDING_X_LABEL,0))

        # initalise toogle
        self.subtests_show = tk.IntVar()
        self.subtests_show.set(COLLAPSED)
        self.tests_show = tk.IntVar()
        self.tests_show.set(COLLAPSED)

        # configure toggle on title_frame click
        self.bind_status_icon("<Button-1>", self.subtests_click)
        self.bind_title_frame("<Button-1>", self.tests_click)
        self.toogle_label.config(state="normal")

        # empty label for padding at sub_frame bottom
        self.padding_label = tk.Label(
            self.sub_frame, text="", background=self.sub_frame_bg)
        self.padding_label.pack(
            side="bottom", fill="x", pady=PADDING_Y_LABEL, expand=1)
        Tooltip(self.padding_label, text=title)

    def subtests_click(self, event=None):
        if self.subtests_show.get() == EXPANDED:
            self.subtests_show.set(COLLAPSED)
        else:
            self.subtests_show.set(EXPANDED)
        self.subtests_toggle()

    def tests_click(self, event=None):
        if self.tests_show.get() == EXPANDED:
            self.tests_show.set(COLLAPSED)
        else:
            self.tests_show.set(EXPANDED)
        self.tests_toggle()

    def subtests_toggle(self, event=None):
        """Toogle sub_frame visibility and toggle_button displayed character"""
        if self.subtests_show.get() == EXPANDED:
            self.tests_expand()
            for test in self.status_children:
                test.subtests_expand()
        else:
            for test in self.status_children:
                test.subtests_collapse()

    def tests_toggle(self, event=None):
        """Toogle sub_frame visibility and toggle_button displayed character"""
        if self.tests_show.get() == EXPANDED:
            self.sub_frame.pack(side="bottom", fill="x", expand=1)
            self.toogle_label.config(image=self.icons["down_arrow"])
        else:
            self.sub_frame.forget()
            self.toogle_label.config(image=self.icons["right_arrow"])

    def tests_expand(self):
        """Call toggle method if not already expanded."""
        if self.tests_show.get() != EXPANDED:
            self.tests_show.set(EXPANDED)
            self.tests_toggle()

    def tests_collapse(self):
        """Call toggle method if not already collapsed."""
        if self.tests_show.get() != COLLAPSED:
            self.tests_show.set(COLLAPSED)
            self.tests_toggle()

    def add_test(self, title, infos):
        """Add a test in the sub_frame and to status_children.
        Returns the created test.
        """
        test = TestFrame(
            parent_widget = self.sub_frame, parent_scenario = self,
            ids_handle = self.ids_handle, title=title, infos=infos)
        self.status_children.append(test)
        test.pack(side="top", fill="x", expand=1,
            pady=PADDING_Y_FRAME, padx=(0, PADDING_X_FRAME), anchor="n")
        self.update_status()
        self.check_selection()
        return test

    def update_status(self):
        """Update own status based on children statuses"""
        if len(self.status_children) == 0:
            return

        # update status
        new_status = max(
            [child.status_icon.status for child in self.status_children],
            key=status_priority)
        new_dynamic = any([child.status_icon.dynamic for child in self.status_children])
        super(ScenarioFrame, self).update_status(new_status, new_dynamic)

        # display durations
        self.durations = [ sum(c.durations) for c in self.status_children if len(c.durations)>0 ]
        if len(self.durations) == 0:
            total_duration = None
        else:
            total_duration = sum(self.durations)
        self.duration_label.config(text=" %s "%duration_str(total_duration))

        # get colors from children
        durations_colors = { c.duration_color for c in self.status_children }
        if RED in durations_colors:
            self.duration_color = RED
        elif GREEN in durations_colors:
            self.duration_color = GREEN
        else:
            self.duration_color = BLACK
        self.duration_label.config(fg=self.duration_color)

    def add_traceback(self, status, id, traceback):
        """Register the traceback and update status_icon tooltip"""
        self.traceback.append("%s %s: %s"%(status, id, traceback))
        self.update_icon_tooltip("\n".join(self.traceback))


class Suite(tk.Frame):
    """A scrollable frame holding Scenarios.

        ids_handle: (dict)  keep a reference to added subtests (using id as key)
        title:      (str)   Suite title
        infos:      (list)  Lines of suite description to display after the title
    """

    def __init__(self, parent, ids_handle, naming,
                title=None, infos=None, warning=None,
                *args, **options):
        tk.Frame.__init__(self, parent, *args, **options)

        self.parent = parent
        self.ids_handle = ids_handle
        self.status_children = []  # keep a handle to each scenario
        self.naming = naming

        # configure and display the scrollable frame
        ## frame are not nativelly scrollable, hence a canvas holding the frame
        self.canvas = tk.Canvas(self.parent)
        self.vsb = tkinter.ttk.Scrollbar(self.parent, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.frame = tk.Frame(self.canvas)
        self.window = self.canvas.create_window(
            (4,4), window=self.frame, anchor="nw")

        # mock label for space before title
        tk.Label(self.frame).pack()

        # display suite title
        if title is not None:
            tk.Label(self.frame, text=title)\
                .pack(fill="x", expand=1, anchor="n",
                    pady=PADDING_Y_LABEL, padx=PADDING_X_LABEL)
            # mock label for space after title
            tk.Label(self.frame).pack()

        # display suite description text
        infos = infos if infos is not None else []
        for line in infos:
            tk.Label(self.frame, text=line, anchor="w")\
                .pack(fill="x", expand=1, anchor="nw", padx=PADDING_X_LABEL*2)

        # display suite warning text
        if warning is not None:
            self.warning_frame = tk.LabelFrame(self.frame, text=" Warning ", fg="red")
            self.warning_frame.pack(fill="x", expand=1, anchor="nw", padx=PADDING_X_LABEL*2)
            self.warning_frame.bind("<Button-1>", self.toogle_warnings)
            # mock label for space at the begining of the warning box
            tk.Label(self.warning_frame).pack()
            # mock label for space after the warning box
            tk.Label(self.frame).pack()

            self.show_warning_widget = tk.Frame(self.warning_frame)
            for line in warning:
                warn = tk.Label(self.show_warning_widget, text=line, anchor="w", justify="left")
                warn.pack(fill="x", anchor="nw", padx=PADDING_X_LABEL*2)
            # mock label for space at the end of warning box
            mock_label = tk.Label(self.show_warning_widget)
            mock_label.pack(fill="both")
            mock_label.bind("<Button-1>", self.toogle_warnings)

            # toogle logic
            self.show_warning = True
            self.toogle_warnings(show=True)

        # display PVs status
        self.images={
            "connected": ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-check-mark-2-12.png"))),
            "disconnected": ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-x-mark-2-12.png"))),
            "connected_section": ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-folder-open-thin-12_GREEN.png"))),
            "disconnected_section": ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-folder-open-thin-12_RED.png"))),
            "mixed_section": ImageTk.PhotoImage(Image.open(resource_filename("wetest",
                    "resources/icons/iconmonstr-folder-open-thin-12.png"))),
        }
        self.pvs_updates = {}
        self.pvs_need_refreshing = False
        self.pvs_refreshing = False
        self.pvs_frame_placeholder = tk.Frame(self.frame)
        self.pvs_frame_placeholder.pack(fill="x")
        self.pvs_frame = tk.LabelFrame(self.pvs_frame_placeholder, text=PVS_FRAME_TEXT)
        self.pvs_frame.bind("<Button-1>", self.toogle_pvs)
        # mock label for space at the begining of the pvs box
        tk.Label(self.pvs_frame).pack()
        # frame to hold tree and scrollbar
        self.tree_frame = tk.Frame(self.pvs_frame)
        treeScroll = tkinter.ttk.Scrollbar(self.tree_frame)
        treeScroll.pack(side="right", fill="y", padx=(0,PADDING_X_LABEL*2))
        # tree to display PVs
        self.pvs_tree = PVsTreeview(self.tree_frame,
            selectmode="browse",
            columns=("col_status", "col_setter", "col_getter"),
            )
        self.pvs_tree.pack(side="right", fill="x", expand=1, padx=(PADDING_X_LABEL*2,0))

        self.pvs_tree.column("#0", stretch=True)
        self.pvs_tree.column("col_status", width=100, stretch=False, anchor="c")
        self.pvs_tree.column("col_setter", width=100, stretch=False, anchor="c")
        self.pvs_tree.column("col_getter", width=100, stretch=False, anchor="c")

        self.pvs_tree.heading("#0",         command=self.pvs_tree_collapse_toogle)
        self.pvs_tree.heading("col_status", command=self.pvs_tree_show_connected)
        self.pvs_tree.heading("col_setter", command=self.pvs_tree_show_not_setter)
        self.pvs_tree.heading("col_getter", command=self.pvs_tree_show_not_getter)

        self.pvs_tree.tag_configure(TAG_CONNECTED)
        self.pvs_tree.tag_configure(TAG_DISCONNECTED)
        self.pvs_tree.tag_configure(TAG_SECTION, image=self.images["mixed_section"])
        self.pvs_tree.tag_configure(TAG_PV)

        # mock label for space at the end of the pvs box
        self.pv_status_mock = tk.Label(self.pvs_frame)
        self.pv_status_mock.bind("<Button-1>", self.toogle_pvs)
        # mock label for space after the pvs box
        tk.Label(self.frame).pack()
        # toogle logic
        self.pvs_show_connected=True
        self.pvs_show_not_setter=True
        self.pvs_show_not_getter=True
        self.show_pvs = True
        self.toogle_pvs(show=False)
        self.show_hide_pvs() # initialise column titles
        self.pvs_collapsed = True
        self.pvs_tree_collapse_toogle()
        # start updating PVs
        self.check_pvs_needs_refreshing()

        # configure tree scrollbar
        treeScroll.configure(command=self.pvs_tree.yview)
        self.pvs_tree.configure(yscrollcommand=treeScroll.set)

        # mock label for space after scenarios
        tk.Label(self.frame).pack(side="bottom")

        # configure bindings
        ## canvas scroll region
        self.bind("<Configure>", self.on_frame_configure) # based on main windows update
        self.frame.bind("<Configure>", self.on_frame_configure) # based on frame update
        ## mouse scroll
        self.bind_all("<MouseWheel>", self.mouse_scroll)  # for Windows
        self.bind_all("<Button-4>", self.mouse_scroll)    # for Linux
        self.bind_all("<Button-5>", self.mouse_scroll)    # for Linux
        self.bind_all("<Up>", self.scroll_down)           # arrow up
        self.bind_all("<Down>", self.scroll_up)           # arrow down
        self.bind_all("<Prior>", self.scroll_start)       # page up
        self.bind_all("<Next>", self.scroll_end)          # page down
        ## unbind for pvs_tree, we do not want to scroll
        ## the main window when scrolling the tree
        self.pvs_tree.bindtags((
            str(self.pvs_tree),
            self.pvs_tree.winfo_class(),
            self.pvs_tree.winfo_toplevel(),
            # all
            )
        )
        ## maximise scenario width
        self.canvas.bind("<Configure>", self.scenario_width)

    def add_scenario(self, config, infos=None, tests=None,
                *args, **options):
        """Add a new scenario to the suite display."""
        if infos is None:
            infos = [
                "name:       %s"% config["name"],
                "type:       %s"% config["type"],
                "prefix:     %s"% config["prefix"],
                "on_failure: %s"% config["on_failure"],
                "retry:      %s"% config["retry"],
                "delay:      %s"% config["delay"],
            ]
            max_len=max([len(x) for x in infos])
            max_len = max_len+1 if max_len % 2 else max_len
            infos.insert(2, "-- default settings --".center(max_len, "-"))

        scenario = ScenarioFrame(self.frame, self.ids_handle,
                    title=config["name"],
                    test_type=config["type"],
                    infos=infos)
        scenario.pack(
            side="top", fill="x", expand=1, anchor="n",
            pady=PADDING_Y_FRAME, padx=PADDING_X_FRAME)
        self.status_children.append(scenario)
        return scenario

    def on_frame_configure(self, event=None):
        """Update canvas scroll region"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def scenario_width(self, event):
        """Update scenario width based on event width"""
        window_width = event.width
        self.canvas.itemconfig(self.window, width = window_width-5)

    def scroll_down(self, event):
        """Scroll once upward"""
        self.scroll(-1)

    def scroll_up(self, event):
        """Scroll once downward"""
        self.scroll(1)

    def scroll_start(self, event):
        """Scroll a bunch toward the begining"""
        self.scroll(-10**1)

    def scroll_end(self, event):
        """Scroll a bunch toward the end"""
        self.scroll(10**1)

    def mouse_scroll(self, event):
        """scrolls if it helps to show more of the scenarios"""
        # workout scroll direction
        if event.num == 5 or event.delta == -120:  # for linux or windows
            move = 1
        else:
            move = -1
        self.scroll(move)

    def scroll(self, step, what="units"):
        """Scroll but only if the content is bigger thatn the window."""
        # enable scroll only when frame is bigger than canvas
        if self.canvas.winfo_height() < self.frame.winfo_height():
            self.canvas.yview_scroll(step, what)

    def toogle_warnings(self, event=None, show=None):
        """Show or hides the warning frame"""
        if show is None:
            self.show_warning = not self.show_warning
        else:
            self.show_warning = show

        if self.show_warning:
            self.show_warning_widget.pack(fill="both", expand=1)
        else:
            self.show_warning_widget.forget()

        # need to update scroll region
        self.update_idletasks()
        self.on_frame_configure()

    def toogle_pvs(self, event=None, show=None):
        """Change between show all or hide some pvs"""
        if show is None:
            self.show_pvs = not self.show_pvs
        else:
            self.show_pvs = show

        self.pvs_need_refreshing = True

    def update_pv(self, pv):
        """Update tested PV list and their infos and status."""
        self.pvs_updates[pv.name] = pv
        self.pvs_need_refreshing = True

    def check_pvs_needs_refreshing(self):
        """Check periodically if need to call self.refresh_pvs"""
        if self.pvs_need_refreshing and not self.pvs_refreshing:
            self.refresh_pvs()
        self.parent.after(200, self.check_pvs_needs_refreshing)

    def refresh_pvs(self):
        """Updates PVs tree view"""
        # reinitialize
        self.pvs_frame.config(fg=BLACK)
        nb_changes = len(self.pvs_updates)
        if nb_changes > 0:
            self.pvs_frame.config(text=PVS_FRAME_TEXT+"(%d updates) "%nb_changes)
        else:
            self.pvs_frame.config(text=PVS_FRAME_TEXT+"(updating) ")
        self.update_idletasks()

        # get updates once and lock "refreshing"
        update_buffer = {}
        update_buffer.update(self.pvs_updates)
        self.pvs_updates.clear()
        self.pvs_refreshing = True
        self.pvs_need_refreshing = False

        # add new PVs if necessary or update values and tags
        updated_sections = set()
        for pv_name, pv in list(update_buffer.items()):
            # pv = update_buffer[pv_name]
            values = [
                "connected" if pv.connected else "unreachable",
                len(pv.setter_subtests),
                len(pv.getter_subtests)
                ]

            # ensure parents exists
            parent = self.create_sections(pv_name)
            updated_sections.add(parent)

            # create pv is new
            if pv_name not in self.pvs_tree.get_all():
                self.pvs_tree.insert(parent, "end", iid=pv_name, open=True, tags=[TAG_PV])

            # update pv
            self.pvs_tree.item(pv_name, text=" "+pv_name, values=values)

            if pv.connected:
                self.pvs_tree.remove_tag(pv_name, TAG_DISCONNECTED)
                self.pvs_tree.add_tag(pv_name, TAG_CONNECTED)
                self.pvs_tree.item(pv_name, image=self.images["connected"])
            else:
                self.pvs_tree.remove_tag(pv_name, TAG_CONNECTED)
                self.pvs_tree.add_tag(pv_name, TAG_DISCONNECTED)
                self.pvs_tree.item(pv_name, image=self.images["disconnected"])

            if len(pv.setter_subtests):
                self.pvs_tree.add_tag(pv_name, TAG_AS_SETTER)
            else:
                self.pvs_tree.remove_tag(pv_name, TAG_AS_SETTER)
            if len(pv.getter_subtests):
                self.pvs_tree.add_tag(pv_name, TAG_AS_GETTER)
            else:
                self.pvs_tree.remove_tag(pv_name, TAG_AS_GETTER)

        # update section connection tags
        for section in updated_sections:
            self.pvs_tree.update_connection(section)

        # set LabelFrame color
        if len(self.pvs_tree.get_all(with_tag=TAG_DISCONNECTED)) > 0:
            self.pvs_frame.config(fg=RED)
        elif len(self.pvs_tree.get_all(with_tag=TAG_CONNECTED)) > 0:
            self.pvs_frame.config(fg=GREEN)
        self.update_idletasks()

        # refresh section status
        for section in self.pvs_tree.get_all(with_tag=TAG_SECTION):
            # set icon
            section_tags = self.pvs_tree.item(section, option="tags")
            if TAG_CONNECTED in section_tags and TAG_DISCONNECTED in section_tags:
                self.pvs_tree.item(section, image=self.images["mixed_section"])
            elif TAG_CONNECTED in section_tags:
                self.pvs_tree.item(section, image=self.images["connected_section"])
            elif TAG_DISCONNECTED in section_tags:
                self.pvs_tree.item(section, image=self.images["disconnected_section"])
            else:
                logger.error("section wihtout connection station:%s", section)
                self.pvs_tree.item(section, image=self.images["mixed_section"])

        # sort and show/hide items
        # sections need to be marked as disconnected before here otherwise
        # they will might not be displayed
        self.pvs_tree_show_connected(show=self.show_pvs)

        # change tree size based on show toogle and number of elements
        self.pvs_tree.remove_tag("", TAG_CONNECTED)
        self.pvs_tree.remove_tag("", TAG_DISCONNECTED)
        if self.show_pvs:
            self.pvs_tree["height"] = min(30, len(self.pvs_tree.get_all())-1)
        else:
            self.pvs_tree["height"] = min(10, len(self.pvs_tree.get_all(with_tag=TAG_DISCONNECTED)))
            # force open
            self.pvs_tree.open_all(self.pvs_tree.tag_has(TAG_DISCONNECTED))
            self.pvs_collapsed = False

        self.pvs_refreshing = False

        # hide tree if nothing attached
        if len(self.pvs_tree.get_all_attached_children()) > 0:
            self.tree_frame.pack(fill="both")
            self.pv_status_mock.pack()
        else:
            self.tree_frame.forget()
            self.pv_status_mock.forget()

        # update frame display
        nb_total = self.pvs_tree.total_pvs_nb()
        nb_connected = self.pvs_tree.connected_pvs_nb()
        nb_disconnected = self.pvs_tree.disconnected_pvs_nb()
        nb_unknown = self.pvs_tree.unknown_pvs_nb()
        frame_txt = PVS_FRAME_TEXT +"("
        if nb_total == 0:
            frame_txt += "no pvs monitored) "
            self.pvs_frame.forget()
        else:
            self.pvs_frame.pack(fill="x", expand=1, anchor="nw", padx=PADDING_X_LABEL*2)

        if nb_connected > 0:
            frame_txt = frame_txt.rstrip(") ")
            if frame_txt[-1] != "(":
                frame_txt += ", "
            frame_txt += "%d connected) "%nb_connected
        if nb_disconnected > 0:
            frame_txt = frame_txt.rstrip(") ")
            if frame_txt[-1] != "(":
                frame_txt += ", "
            frame_txt += "%d unreachable) "%nb_disconnected
        if nb_unknown > 0:
            frame_txt = frame_txt.rstrip(") ")
            if frame_txt[-1] != "(":
                frame_txt += ", "
            frame_txt += "%d unknown) "%nb_unknown

        self.pvs_frame.config(text=frame_txt)

    def create_sections(self, pv_name):
        """Create the section of pv_name if necessary, return the parent to attach to."""

        # check if pv already exists
        try:
            return self.pvs_tree.get_parent(pv_name)
        except KeyError:
            pass # pv not already in tree

        # otherwise create parent if necesssary
        parent = ""
        try:
            sections = self.naming.split(pv_name)
        except NamingError:
            sections = ["invalid_name", pv_name]

        if len(sections) > 1: # otherwise no sections
            # check each section exists
            for idx, sec in enumerate(sections[:-1]):
                whole_section_name = "we_test_section_"+"_".join(sections[:idx+1])
                try:
                    self.pvs_tree.insert(parent, "end",
                        iid=whole_section_name,
                        text=" "+sec,
                        tags=[TAG_SECTION, TAG_AS_SETTER, TAG_AS_GETTER],
                        open=True
                        )
                except ExistingTreeItem:
                    pass
                parent = whole_section_name

        return parent

    def pvs_tree_collapse_toogle(self, event=None):
        if self.pvs_collapsed:
            self.pvs_collapsed = False
            self.pvs_tree.open_all()
            self.pvs_tree.heading("#0", text="PV name and section    [close all]")
        else:
            self.pvs_collapsed = True
            self.pvs_tree.close_all()
            self.pvs_tree.heading("#0", text="PV name and section    [open  all]")

    def pvs_tree_show_connected(self, event=None, show=None):
        if show is None:
            self.pvs_show_connected = not self.pvs_show_connected
        else:
            self.pvs_show_connected = show
        self.show_hide_pvs()

    def pvs_tree_show_not_setter(self, event=None, show=None):
        if show is None:
            self.pvs_show_not_setter = not self.pvs_show_not_setter
        else:
            self.pvs_show_not_setter = show
        self.show_hide_pvs()

    def pvs_tree_show_not_getter(self, event=None, show=None):
        if show is None:
            self.pvs_show_not_getter = not self.pvs_show_not_getter
        else:
            self.pvs_show_not_getter = show
        self.show_hide_pvs()

    def show_hide_pvs(self):
        logger.info("show connected:  %s", self.pvs_show_connected)
        logger.info("show not setter: %s", self.pvs_show_not_setter)
        logger.info("show not getter: %s", self.pvs_show_not_getter)

        if self.pvs_show_connected:
            self.pvs_tree.heading("col_status", text="status [+]")
        else:
            self.pvs_tree.heading("col_status", text="status [-]")

        if self.pvs_show_not_setter:
            self.pvs_tree.heading("col_setter", text="as setter [+]")
        else:
            self.pvs_tree.heading("col_setter", text="as setter [-]")

        if self.pvs_show_not_getter:
            self.pvs_tree.heading("col_getter", text="as getter [+]")
        else:
            self.pvs_tree.heading("col_getter", text="as getter [-]")

        for item in sorted(self.pvs_tree.get_all(), key=self.naming.sort):
            item_tags = self.pvs_tree.item(item, option="tags")
            logger.debug("%s tags: %s", item, item_tags)

            # show or hide item
            if item ==  "":  # always show root
                continue
            elif (
                (TAG_DISCONNECTED in item_tags or self.pvs_show_connected)
                and
                    (
                    (TAG_AS_SETTER in item_tags or self.pvs_show_not_setter)
                    or
                    (TAG_AS_GETTER in item_tags or self.pvs_show_not_getter)
                    )
                ):
                self.pvs_tree.reattach(
                    item,
                    self.pvs_tree.get_parent(item),
                    "end")
            else:
                self.pvs_tree.detach(item)

    def apply_selection(self):
        """Change status icon based on selection
        Return a dict with to lists, selected and skipped subtest_ids"""
        output = {SELECTED:[], SKIPPED:[]}
        for st_id, st in list(self.ids_handle.items()):
            # st.select_label.config(state="disable")
            if st.selected == SELECTED:
                output[SELECTED].append(st_id)
                st.reset(status=STATUS_WAIT)
            elif st.selected == SKIPPED:
                output[SKIPPED].append(st_id)
                st.reset(status=STATUS_SKIP)
            else:
                raise NotImplementedError("Unexpected selection value for a subtest: %s"%st.selected)

        for sc in self.status_children:
            for test in sc.status_children:
                test.reset()
            sc.reset()

        return output


def get_default(iterable, idx, default=None):
    """Return the default value if required idx or key is not available"""
    try:
        return iterable[idx]
    except (IndexError, KeyError):
        return default


def build_subtest_desc(st_id, subtest_infos):
    """Format the description of a subtest, based on subtest_infos dict."""
    # initialize description
    subtest_desc = [st_id]

    # add message if any
    if subtest_infos.subtest_message is not None:
        subtest_desc.append(subtest_infos.subtest_message)

    # add setter if any
    if subtest_infos.setter is not None:
        subtest_desc.append(
            "set   "
            +str(subtest_infos.setter)
            +" to "
            +to_string(subtest_infos.set_value)
            )

    # add getter and margin if any
    if subtest_infos.getter is not None:
        subtest_desc.append(
            "check "
            +str(subtest_infos.getter)
            +" is "
            +to_string(subtest_infos.get_value)
            )
        if subtest_infos.margin is not None and subtest_infos.margin != 0.0:
            subtest_desc[-1] += " +/- "+str(subtest_infos.margin*100)+"%"
        if subtest_infos.delta is not None and subtest_infos.delta != 0.0:
            subtest_desc[-1] += " +/- "+str(subtest_infos.delta)

    detailed_desc=[
        "prefix:     %s"% subtest_infos.__dict__["prefix"],
        "on_failure: %s"% subtest_infos.__dict__["on_failure"],
        "retry:      %s"% subtest_infos.__dict__["retry"],
        "delay:      %s"% subtest_infos.__dict__["delay"],
    ]

    # debug display
    debug_desc = []
    if DEBUG_INFOS:
        debug_desc = [str(k) + ": " + str(v) for k,v in list(subtest_infos.__dict__.items())]
    else:
        debug_desc = []


    max_len=max([len(x) for x in detailed_desc+subtest_desc+debug_desc])
    max_len = max_len+1 if max_len % 2 else max_len
    detailed_desc.insert(0, "-- detailled infos --".center(max_len, "-"))

    if DEBUG_INFOS:
        debug_desc.insert(0, "-- debug infos --".center(max_len, "-"))

    subtest_desc += detailed_desc
    subtest_desc += debug_desc

    return subtest_desc
