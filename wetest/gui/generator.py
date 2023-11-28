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

"""Create a GUI of running tests and there current status."""
# icons from https://iconmonstr.com/
# gifs from https://ezgif.com/

import copy
import logging
import multiprocessing
import re
import subprocess
import tkinter as tk
import tkinter.ttk
from queue import Empty

from PIL import Image, ImageTk
from pkg_resources import resource_filename

from wetest.common.constants import (
    ABORT_FROM_GUI,
    ABORT_FROM_MANAGER,
    END_OF_TESTS,
    FILE_HANDLER,
    PAUSE_FROM_GUI,
    PAUSE_FROM_MANAGER,
    PLAY_FROM_MANAGER,
    REPORT_GENERATED,
    RESUME_FROM_GUI,
    SELECTION_FROM_GUI,
    START_FROM_GUI,
    VERBOSE_FORMATTER,
)
from wetest.gui.base import ImageGif, Tooltip
from wetest.gui.specific import (
    PADDING_X_LABEL,
    SELECTED,
    STATUS_P_RETRY,
    STATUS_PAUSE,
    STATUS_RETRY,
    STATUS_RUN,
    STATUS_SKIP,
    STATUS_STOP,
    STATUS_WAIT,
    StatusIcon,
    Suite,
    status_priority,
)
from wetest.pvs.core import PVData

# configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(VERBOSE_FORMATTER)
logger.addHandler(stream_handler)
logger.addHandler(FILE_HANDLER)

PLAY_FROM_GUI = "GUI noticed tests are running"

# enable or not DEBUG displays
DEBUG_QUEUE = False  # open a GUI that list the update_queue content

# display settings
WIN_X = 800
WIN_Y = 800
BT_TXT_LEN = 6


def reorganise_subtests(tests_infos):
    """Return the tests_infos sorted by scenario and test numbers."""
    output = {}

    # expected subtest id template
    regex = r"test-(?P<sc_id>\d+)-(?P<test_id>\d+)-\d+$"

    for st_id, st_data in list(tests_infos.items()):
        match = re.match(regex, st_id)
        if match is None:
            logger.error("unexpected id format: %s", st_id)
        else:
            sc_id = int(match.group("sc_id"))
            test_id = int(match.group("test_id"))
        if sc_id not in output:
            output[sc_id] = {}
        if test_id not in output[sc_id]:
            output[sc_id][test_id] = {}
        output[sc_id][test_id][st_id] = st_data

    for sc_id in output:
        for test_id in output[sc_id]:
            for subtest in output[sc_id][test_id]:
                logger.debug(subtest)

    return output


def value_from_subtest(
    key,
    test_infos,
    scenario_id,
    test_id,
    subtest_id=None,
    fallback="VALUE NOT FOUND",
):
    """Extract a value corresponding to key in the infos of the subtest.

    Use fallback value if it is not available.
    """
    if subtest_id is None:
        value = getattr(
            next(iter(test_infos[scenario_id][test_id].values())),
            key,
            fallback,
        )
    else:
        value = getattr(test_infos[scenario_id][test_id][subtest_id], key, fallback)
    return value


def file_order_sort(subtest_id):
    """Return the scenario, test and subtest id as a tuple for numerical sort."""
    text, sc_id, tt_id, st_id = subtest_id.split("-")
    return (int(sc_id), int(tt_id), int(st_id))


class GUIGenerator:
    def __init__(
        self,
        master,
        suite,
        configs,
        naming,
        update_queue,
        request_queue,
        file_validation,
    ) -> None:
        # initialise attributes
        self.master = master
        self.suite = suite
        self.configs = copy.deepcopy(configs)
        self.naming = naming
        self.subtests_ref = {}
        self.update_queue = update_queue
        self.request_queue = request_queue

        self.current_test_id = None
        self.current_test_retrying = False

        self.playing = False  # tests are currently running (dactivate play action)
        self.finished = True  # discriminate between start and resume for play button

        self.buttons_refs = {
            "play": [],
            "pause": [],
            "stop": [],
            "report": [],
        }

        self.report_software = "evince"
        self.report_path = None

        # set title and main window size
        self.master.title("WeTest GUI")
        self.master.geometry(str(WIN_X) + "x" + str(WIN_Y))
        # window icon
        self.favicon = (
            ImageTk.PhotoImage(
                Image.open(
                    resource_filename("wetest", "resources/logo/wetest-icon.png"),
                ),
            ),
        )
        self.master.tk.call("wm", "iconphoto", self.master._w, self.favicon)

        # debug window
        if DEBUG_QUEUE:
            self.debugQueue = QueueDebug()

        # extract suite title
        suite_title = self.configs.pop(0)["name"]

        logger.debug("file_validation %s", file_validation)
        warning = [x.rstrip() for x in file_validation]

        display_warning = False
        for line in warning:
            if not line.startswith("Validation of YAML s"):
                display_warning = True
                break
        if not display_warning:
            warning = None

        # generate suite frame
        self.suite_frame = tk.Frame(self.master)
        self.suite_frame.pack(side="top", fill="both", expand=True)
        if suite_title is not None:
            self.suite_gui = Suite(
                self.suite_frame,
                self.subtests_ref,
                naming=self.naming,
                title=suite_title,
                warning=warning,
            )
        else:
            self.suite_gui = Suite(
                self.suite_frame,
                self.subtests_ref,
                naming=self.naming,
                warning=warning,
            )

        # check same number of scenarios configs and scenario in tests_info
        if self.suite is None:
            self.test_infos = {}
        else:
            self.test_infos = reorganise_subtests(self.suite.tests_infos)

        if len(self.test_infos) != len(self.configs):
            logger.info(
                "Not the same number of configs(%d) and scenarios(%d)",
                len(self.configs),
                len(self.test_infos),
            )

        # add scenario, tests and subtests
        for sc_id, sc_config in enumerate(self.configs):
            sc = self.suite_gui.add_scenario(config=sc_config)
            if sc_id not in self.test_infos:
                sc.add_traceback("UNEXPECTED", "", "No tests in this scenario.")
            for test_id in sorted(self.test_infos.get(sc_id, [])):
                test_title = value_from_subtest(
                    "test_title",
                    self.test_infos,
                    sc_id,
                    test_id,
                )
                test_desc = [
                    value_from_subtest("test_message", self.test_infos, sc_id, test_id),
                ]
                if test_desc[0] is None:
                    test_desc.pop(0)
                test = sc.add_test(test_title, test_desc)
                for st_id in sorted(
                    self.test_infos[sc_id][test_id],
                    key=file_order_sort,
                ):
                    subtest_title = value_from_subtest(
                        "desc",
                        self.test_infos,
                        sc_id,
                        test_id,
                        st_id,
                    )
                    test.add_subtest(
                        st_id,
                        subtest_title,
                        self.test_infos[sc_id][test_id][st_id],
                    )

        # if only one scenario for expand it
        if len(self.configs) == 1:
            sc.tests_expand()
            sc.bind_title_frame("<Button-1>", sc.subtests_click)
            sc.toogle_label.config(state="disable")

        # Add play/pause and stop buttons
        self.footer_frame = tk.Frame(self.master, borderwidth=1, relief="raised")
        self.footer_frame.pack(side="bottom", fill="both")

        self.buttons_frame = tk.Frame(self.footer_frame)
        self.buttons_frame.pack()

        self.button_img = {
            "play": ImageTk.PhotoImage(
                Image.open(
                    resource_filename(
                        "wetest",
                        "resources/icons/iconmonstr-media-control-48-24.png",
                    ),
                ),
            ),
            "pause": ImageTk.PhotoImage(
                Image.open(
                    resource_filename(
                        "wetest",
                        "resources/icons/iconmonstr-media-control-49-24.png",
                    ),
                ),
            ),
            "stop": ImageTk.PhotoImage(
                Image.open(
                    resource_filename(
                        "wetest",
                        "resources/icons/iconmonstr-media-control-50-24.png",
                    ),
                ),
            ),
            "report": ImageTk.PhotoImage(
                Image.open(
                    resource_filename(
                        "wetest",
                        "resources/icons/iconmonstr-clipboard-6-24.png",
                    ),
                ),
            ),
            "quit": ImageTk.PhotoImage(
                Image.open(
                    resource_filename(
                        "wetest",
                        "resources/icons/iconmonstr-log-out-7-24.png",
                    ),
                ),
            ),
            "ok": ImageTk.PhotoImage(
                Image.open(
                    resource_filename(
                        "wetest",
                        "resources/icons/iconmonstr-speech-bubble-35-24.png",
                    ),
                ),
            ),
        }
        self.button_gif = {
            "processing": ImageGif(
                self.master,
                resource_filename(
                    "wetest",
                    "resources/icons/iconmonstr-time-15-24.gif",
                ),
            ),
        }

        play_button = tk.Button(
            self.buttons_frame,
            text="Play".center(BT_TXT_LEN),
            command=self.play,
            compound="left",
            image=self.button_img["play"],
        )
        Tooltip(play_button, text="Start or resume testing")
        play_button.pack(side="left")
        self.buttons_refs["play"].append(play_button)

        pause_button = tk.Button(
            self.buttons_frame,
            text="Pause".center(BT_TXT_LEN),
            command=self.pause,
            compound="left",
            image=self.button_img["pause"],
            state="disable",
        )
        pause_button.pack(side="left")
        Tooltip(pause_button, text="Pause testing")
        self.buttons_refs["pause"].append(pause_button)

        stop_button = tk.Button(
            self.buttons_frame,
            text="Abort".center(BT_TXT_LEN),
            command=self.abort,
            compound="left",
            image=self.button_img["stop"],
            state="disable",
        )
        stop_button.pack(side="left")
        Tooltip(stop_button, text="Abort testing\nNo report generated")
        self.buttons_refs["stop"].append(stop_button)

        report_button = tk.Button(
            self.buttons_frame,
            text="Report".center(BT_TXT_LEN),
            command=self.report,
            compound="left",
            image=self.button_img["report"],
            state="disable",
        )
        report_button.pack(side="left")
        Tooltip(report_button, text="Open generated report")
        self.buttons_refs["report"].append(report_button)

        close_button = tk.Button(
            self.buttons_frame,
            text="Quit".center(BT_TXT_LEN),
            command=self.quit,
            compound="left",
            image=self.button_img["quit"],
            state="normal",
        )
        close_button.pack(side="left")
        Tooltip(close_button, text="Abort testing\nNo report generated\nClose GUI")

        # if no tests disable play button and enlarge PV frame
        if self.suite is None:
            self.disable("play")
            self.suite_gui.toogle_pvs(show=True)

        # run update function
        self.update_status()

    def enable(self, key):
        """Enable all the buttons corresponding to key."""
        deprecated_widgets = []
        for b in self.buttons_refs[key]:
            try:
                b.config(state="normal")
            except tk.TclError:  # button does not exist anymore
                deprecated_widgets.append(b)
        for b in deprecated_widgets:
            self.buttons_refs[key].remove(b)

    def disable(self, key):
        """Disable all the buttons corresponding to key."""
        deprecated_widgets = []
        for b in self.buttons_refs[key]:
            try:
                b.config(state="disable")
            except tk.TclError:  # button does not exist anymore
                deprecated_widgets.append(b)
        for b in deprecated_widgets:
            self.buttons_refs[key].remove(b)

    def attach_key(self, key, image_gif):
        """Attach all "key" buttons to provided gif."""
        deprecated_widgets = []
        for b in self.buttons_refs[key]:
            try:
                image_gif.attach(b)
            except tk.TclError:  # button does not exist anymore
                deprecated_widgets.append(b)
        for b in deprecated_widgets:
            self.buttons_refs[key].remove(b)

    def detach_key(self, key, image_gif, image=None):
        """Detach all "key" buttons from provided gif, set image instead."""
        deprecated_widgets = []
        for b in self.buttons_refs[key]:
            try:
                image_gif.detach(b, image)
            except tk.TclError:  # button does not exist anymore
                deprecated_widgets.append(b)
        for b in deprecated_widgets:
            self.buttons_refs[key].remove(b)

    def play(self) -> None:
        """Start or resume tests execution."""
        if self.playing:
            return

        self.disable("play")
        if not self.finished:
            logger.debug("RESUME !")
            self.request_queue.put(RESUME_FROM_GUI)
        else:
            self.attach_key("play", self.button_gif["processing"])
            logger.debug("START !")
            selection = self.suite_gui.apply_selection()
            self.request_queue.put(
                SELECTION_FROM_GUI + " " + " ".join(selection[SELECTED]),
            )
            self.request_queue.put(START_FROM_GUI)

    def pause(self):
        """Pause tests execution."""
        self.disable("pause")
        logger.debug("PAUSE !")
        self.request_queue.put(PAUSE_FROM_GUI)

    def abort(self):
        """Abort tests execution."""
        self.disable("pause")
        self.disable("stop")
        logger.debug("ABORT !")
        self.request_queue.put(ABORT_FROM_GUI)

    def report(self):
        logger.debug("REPORT !")
        logger.debug("report_software: %s", self.report_software)
        logger.debug("report_path: %s", self.report_path)
        subprocess.Popen([self.report_software, self.report_path])

    def quit(self):
        logger.debug("QUIT !")
        self.master.destroy()

    def update_status(self):
        try:
            while True:
                update = self.update_queue.get(block=False)
                if DEBUG_QUEUE:
                    self.debugQueue.add_item(update)

                if update in [END_OF_TESTS, ABORT_FROM_MANAGER]:
                    self.playing = False
                    self.finished = True
                    EndTestsPopUp(root=self.master, gui=self)
                    # update available controls
                    self.enable("play")
                    self.disable("pause")
                    self.disable("stop")

                    if update == ABORT_FROM_MANAGER:
                        logger.warning("Abort all tests.")
                        # mark all tests as stopped
                        for sc in self.suite_gui.status_children:
                            sc.set_children_status(status=STATUS_STOP, dynamic=False)
                        if (
                            self.current_test_id is not None
                        ):  # aborting in the middle of a test:
                            self.subtests_ref[self.current_test_id].update_status(
                                STATUS_STOP,
                                dynamic=False,
                            )
                            self.current_test_id = (
                                None  # ignore this id in case of replay
                            )

                elif update == PAUSE_FROM_MANAGER:
                    self.playing = False
                    self.finished = False
                    logger.warning("Pause all tests.")
                    # mark all tests as paused
                    for sc in self.suite_gui.status_children:
                        sc.set_children_status(status=STATUS_PAUSE, dynamic=False)
                    if (
                        self.current_test_id is not None
                    ):  # pausing in the middle of a test:
                        if self.current_test_retrying:
                            self.subtests_ref[self.current_test_id].update_status(
                                STATUS_P_RETRY,
                                dynamic=True,
                            )
                        else:
                            self.subtests_ref[self.current_test_id].update_status(
                                STATUS_PAUSE,
                                dynamic=True,
                            )
                    PausedPopUp(root=self.master, gui=self)
                    # update available controls
                    self.enable("play")
                    self.disable("pause")
                    self.enable("stop")

                elif update in [PLAY_FROM_MANAGER, PLAY_FROM_GUI]:
                    self.playing = True
                    self.finished = False
                    logger.warning("Tests are playing.")
                    # mark all tests as waiting or running
                    for sc in self.suite_gui.status_children:
                        sc.set_children_status(status=STATUS_WAIT, dynamic=False)
                    if (
                        self.current_test_id is not None
                    ):  # continuing in the middle of a test:
                        if self.current_test_retrying:
                            self.subtests_ref[self.current_test_id].update_status(
                                STATUS_RETRY,
                                dynamic=True,
                            )
                        else:
                            self.subtests_ref[self.current_test_id].update_status(
                                STATUS_RUN,
                                dynamic=True,
                            )

                elif str(update).startswith(REPORT_GENERATED):
                    logger.warning("Report available.")
                    self.report_path = update[len(REPORT_GENERATED) + 1 :]
                    self.enable("report")

                elif isinstance(update, list) and len(update) == 4:
                    test_id = update[0]
                    test_status = update[1]
                    test_duration = update[2]
                    test_trace = update[3]

                    # check GUI knows tests are running (in case play was sent from CLI)
                    if not self.playing:
                        self.update_queue.put(PLAY_FROM_GUI)
                    # update available controls
                    self.detach_key(
                        "play",
                        self.button_gif["processing"],
                        self.button_img["play"],
                    )
                    self.disable("play")
                    self.enable("pause")
                    self.enable("stop")

                    # nothing more to do if the test was skipped
                    if test_status in [STATUS_SKIP]:
                        continue

                    # keep track of a test currently running
                    if test_status in [STATUS_RUN, STATUS_RETRY]:
                        self.current_test_id = test_id
                        self.current_test_retrying = test_status == STATUS_RETRY
                    else:
                        self.current_test_id = None
                        self.current_test_retrying = False

                    # update tests status
                    if test_id not in self.subtests_ref:
                        logger.error("No %s in GUI", test_id)
                    else:
                        dynamic = test_status in [STATUS_RUN, STATUS_RETRY]
                        self.subtests_ref[test_id].update_status(
                            test_status,
                            dynamic,
                            test_duration,
                        )
                        if test_status == STATUS_RETRY:
                            self.subtests_ref[test_id].set_traceback(
                                test_trace,
                                tooltip_only=True,
                            )
                        elif test_trace is not None:
                            self.subtests_ref[test_id].set_traceback(test_trace)

                elif isinstance(update, PVData):
                    self.suite_gui.update_pv(update)

                else:
                    logger.critical("Unexpected update in queue.")
                    logger.critical("Received: >%s<", update)

        except Empty:
            pass

        self.master.after(50, self.update_status)


class PopUp:
    """A generic pop-up window."""

    def __init__(
        self,
        root,
        gui,
        title,
        message,
        width=None,
        height=None,
        centered=True,
    ) -> None:
        self.root = root
        self.gui = gui
        self.top = tk.Toplevel()
        self.top.title(title)

        # set window icon
        self.root.tk.call("wm", "iconphoto", self.top._w, self.gui.favicon)

        # display text
        self.text_frame = tk.Frame(self.top)
        self.text_frame.pack(fill="both", expand=1)

        tk.Label(self.text_frame).pack()  # mock label for space
        msg = tk.Label(self.text_frame, text=message)  # , wraplength=width*0.9)
        msg.pack(fill="x", expand=1, padx=PADDING_X_LABEL)
        tk.Label(self.text_frame).pack()  # mock label for space

        # prepare for status
        self.status_frame = tk.Frame(self.top)
        # self.status_frame.pack(fill="both", expand=1)
        self.status_frame.pack(expand=1)

        # display buttons
        self.footer_frame = tk.Frame(self.top)
        self.footer_frame.pack(side="bottom", fill="both")

        self.buttons_frame = tk.Frame(self.footer_frame)
        self.buttons_frame.pack()

        self.ok_button = tk.Button(
            self.buttons_frame,
            text="Ok".center(BT_TXT_LEN),
            command=self.top.destroy,
            compound="left",
            image=self.gui.button_img["ok"],
        )
        self.ok_button.pack(side="left")

        Tooltip(self.ok_button, text="Close PopUp")

        # place window
        # self.top.minsize(200, 140)
        top_x = self.top.winfo_rootx()
        if centered:
            root_x = self.root.winfo_rootx()
            root_y = self.root.winfo_rooty()
            root_h = self.root.winfo_height()
            root_w = self.root.winfo_width()
            position = "+%d+%d" % (root_x + root_w / 2 - top_x / 2, root_y + root_h / 3)
            self.top.geometry(position)
        # msg.config(wraplength=top_x*0.9)

    def add_status(self, status, text=None):
        one_status_frame = tk.Frame(self.status_frame)
        one_status_frame.pack(anchor="w")
        StatusIcon(one_status_frame, status=status).pack(side="left")
        if text is not None:
            tk.Label(one_status_frame, text=text).pack(side="left")

    def show_statuses(self):
        """Display the different substests status."""
        status_count = {}
        for subtest in list(self.gui.subtests_ref.values()):
            status = subtest.status_icon.status
            if status in status_count:
                status_count[status] += 1
            else:
                status_count[status] = 1

        for status in sorted(status_count, key=status_priority, reverse=True):
            text = "%4d %s" % (status_count[status], status.lower())
            self.add_status(status, text)

        tk.Label(self.status_frame).pack()  # mock label for space


class PausedPopUp(PopUp):
    """A popup to show when tests are paused."""

    def __init__(self, root, gui, status=None) -> None:
        PopUp.__init__(
            self,
            root,
            gui,
            "Tests paused.",
            "Tests execution\nhas been paused.",
        )

        play_button = tk.Button(
            self.buttons_frame,
            text="Play".center(BT_TXT_LEN),
            command=self.play,
            compound="left",
            image=self.gui.button_img["play"],
        )
        play_button.pack(side="left")
        Tooltip(play_button, text="Start or resume testing")
        self.gui.buttons_refs["play"].append(play_button)

        stop_button = tk.Button(
            self.buttons_frame,
            text="Abort".center(BT_TXT_LEN),
            command=self.abort,
            compound="left",
            image=self.gui.button_img["stop"],
        )
        stop_button.pack(side="left")
        Tooltip(stop_button, text="Abort testing\nNo report generated")
        self.gui.buttons_refs["stop"].append(stop_button)

        self.ok_button.config(text="Ok".center(BT_TXT_LEN))

        self.show_statuses()

    def play(self):
        """Close pop-up and continue testing when clicking on play button."""
        self.gui.play()
        self.top.destroy()

    def abort(self):
        """Close pop-up and abort tests."""
        self.gui.abort()
        self.top.destroy()


class EndTestsPopUp(PopUp):
    """A popup to show when tests are finished."""

    def __init__(self, root, gui, status=None) -> None:
        PopUp.__init__(self, root, gui, "Tests finished.", "Done running tests.")

        report_button = tk.Button(
            self.buttons_frame,
            text="Report".center(BT_TXT_LEN),
            command=self.report,
            compound="left",
            image=self.gui.button_img["report"],
            state="disable",
        )
        report_button.pack(side="left")
        Tooltip(report_button, text="Open generated report")
        self.gui.buttons_refs["report"].append(report_button)

        close_button = tk.Button(
            self.buttons_frame,
            text="Quit".center(BT_TXT_LEN),
            command=self.quit,
            compound="left",
            image=self.gui.button_img["quit"],
        )
        close_button.pack(side="left")
        Tooltip(close_button, text="Close GUI")

        self.ok_button.config(text="  Ok  ")

        self.show_statuses()

    def report(self):
        """Close pop-up and open report."""
        self.gui.report()
        self.top.destroy()

    def quit(self):
        """Close GUI when clicking on close button."""
        self.gui.master.destroy()


class QueueDebug:
    def __init__(self) -> None:
        top = tk.Toplevel()
        top.title("Queue Debug")

        top.geometry("800x800")

        scrollbar = tk.Scrollbar(top)
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(top, yscrollcommand=scrollbar.set)
        self.listbox.pack(fill="both", expand=1)

    def add_item(self, item):
        try:
            self.listbox.insert(0, str(item))
            self.listbox.update_idletasks()
        except tk.TclError:  # the debug window has been closed ?
            pass


if __name__ == "__main__":  # tests
    root = tk.Tk()

    class Object:
        pass

    suite = Object()
    suite.tests_infos = {}
    suite.tests_infos["subtest01_0-1"] = {
        "id": "test_1",
        "desc": "sc 0 test 1 subtest 1",
        "subtest_message": None,
        "setter": None,
        "getter": None,
    }
    suite.tests_infos["subtest02_0-1"] = {
        "id": "test_2",
        "desc": "sc 0 test 1 subtest 2",
        "subtest_message": None,
        "setter": None,
        "getter": None,
    }
    suite.tests_infos["subtest01_0-2"] = {
        "id": "test_3",
        "desc": "sc 0 test 1 subtest 1",
        "subtest_message": None,
        "setter": None,
        "getter": None,
    }
    suite.tests_infos["subtest01_1-0"] = {
        "id": "test_4",
        "desc": "sc 1 test 0 subtest 1",
        "subtest_message": None,
        "setter": None,
        "getter": None,
    }
    suite.tests_infos["subtest01_1-2"] = {
        "id": "test_5",
        "desc": "sc 1 test 2 subtest 1",
        "subtest_message": None,
        "setter": None,
        "getter": None,
    }
    suite.tests_infos["subtest02_1-0"] = {
        "id": "test_6",
        "desc": "sc 1 test 0 subtest 2",
        "subtest_message": None,
        "setter": None,
        "getter": None,
    }
    suite.tests_infos["subtest03_1-0"] = {
        "id": "test_7",
        "desc": "sc 1 test 0 subtest 3",
        "subtest_message": None,
        "setter": None,
        "getter": None,
    }

    # app = GUIGenerator(suite=None, configs=[{'name': "scenario title"}])

    GUIGenerator(
        master=root,
        suite=suite,
        configs=[
            "suite title",
            {"name": "scenario 1 title"},
            {"name": "scenario 2 title"},
        ],
        update_queue=multiprocessing.Queue(),
        request_queue=multiprocessing.Queue(),
        file_validation=["warning text"] * 5,
    )
    root.mainloop()
