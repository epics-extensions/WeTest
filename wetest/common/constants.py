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

import logging
from logging.handlers import RotatingFileHandler
import colorlog


# Base Exception
class WeTestError(Exception):
    """Base class for exceptions generated by WeTest"""

    pass


# interprocess communication value

## messages from GUI
SELECTION_FROM_GUI = "new selection from GUI"
START_FROM_GUI = "starting tests from GUI"
RESUME_FROM_GUI = "resuming paused tests from GUI"
PAUSE_FROM_GUI = "pausing tests from GUI"
ABORT_FROM_GUI = "aborting test from GUI"

## messages from tests (then forwarded by runner output parser)
CONTINUE_FROM_TEST = "continue requested by test"
PAUSE_FROM_TEST = "pause requested by test"
ABORT_FROM_TEST = "abort requested by test"

## message from runner process
END_OF_TESTS = "runner has finished executing tests"
REPORT_GENERATED = "report is now ready"

## message from process manager
PAUSE_FROM_MANAGER = "pausing tests by manager"
ABORT_FROM_MANAGER = "aborting tests by manager"
PLAY_FROM_MANAGER = "executing tests by manager"


# logger configuration

## custom log levels
# CRITICAL  50
LVL_PV_DISCONNECTED = 46
LVL_FORMAT_VAL = 44
LVL_TEST_ERRORED = 42
# ERROR     40
LVL_PV_CONNECTED = 38
LVL_TEST_FAILED = 36
LVL_TEST_SUCCESS = 34
LVL_TEST_RUNNING = 32
LVL_TEST_SKIPPED = 31
# WARNING   30
LVL_RUN_CONTROL = 22
# INFO      20
# DEBUG     10
# NOTSET    0
logging.addLevelName(LVL_PV_DISCONNECTED, "DISCONNECTED")  # for PV connection change
logging.addLevelName(LVL_FORMAT_VAL, "FORMAT")  # for file validation
logging.addLevelName(LVL_TEST_ERRORED, "ERRORED")  # for errored tests
logging.addLevelName(LVL_PV_CONNECTED, "CONNECTED")  # for PV connection change
logging.addLevelName(LVL_TEST_FAILED, "FAILED")  # for failed tests
logging.addLevelName(LVL_TEST_SUCCESS, "SUCCESS")  # for successful tests
logging.addLevelName(LVL_TEST_RUNNING, "RUNNING")  # for running info
logging.addLevelName(LVL_TEST_SKIPPED, "SKIPPED")  # for skipped tests
logging.addLevelName(LVL_RUN_CONTROL, "CONTROL")  # for control from tests

log_colors = {
    "CRITICAL": "black,bg_purple",
    "DISCONNECTED": "black,bg_red",
    "FORMAT": "purple",
    "ERRORED": "yellow",
    "ERROR": "red",
    "CONNECTED": "black,bg_green",
    "FAILED": "red",
    "SUCCESS": "green",
    "RUNNING": "blue",
    "SKIPPED": "white",
    "WARNING": "yellow",
    "CONTROL": "black,bg_blue",
    # 'INFO':         'normal',
    "DEBUG": "blue",
}

## formaters
TIME_FORMATTER = logging.Formatter("%(asctime)s :: %(levelname)-8s :: %(message)s")
TERSE_FORMATTER = colorlog.ColoredFormatter(
    "%(log_color)s%(message)s%(reset)s", log_colors=log_colors
)
VERBOSE_FORMATTER = colorlog.ColoredFormatter(
    "%(log_color)s[ %(name)s:%(lineno)s - %(funcName)s() ] %(message)s%(reset)s",
    log_colors=log_colors,
)

## file log
FILE_HANDLER = RotatingFileHandler("activity.log", "a", 1000000, 1)
FILE_HANDLER.setFormatter(TIME_FORMATTER)
FILE_HANDLER.setLevel(logging.INFO)


# convertion function
def to_string(a_value):
    """Return a string representation of the value, with quote if it's already a string"""
    if isinstance(a_value, str):
        return "`" + a_value + "`"
    else:
        return str(a_value)
