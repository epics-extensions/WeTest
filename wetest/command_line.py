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

"""WeTest is the main module of the testing tool."""

__author__ = "Nicolas Senaud <nicolas.senaud@cea.fr>"
__copyright__ = "(C) 2017 CEA (CEA/DRF/Irfu/SIS/LDISC)"
__license__ = ""
__version__ = "0.3.0"
__date__ = "2017-06-28"
__description__ = \
"""WeTest is a testing facility for EPICS modules. Tests are described in a 
YAML file, and executed over the Channel Access via Pyepics library. 
It also enables to monitor PVs (extracted from the tests and from specified DB).
"""
__status__ = "Beta"

import logging

import argparse
import multiprocessing
from multiprocessing import Queue
import os
import re
import signal
import sys
import Tkinter as tk
import time
import unittest

import colorlog
import epics

from Queue import Empty

from wetest.common.constants import (
    SELECTION_FROM_GUI, START_FROM_GUI, RESUME_FROM_GUI, PAUSE_FROM_GUI, ABORT_FROM_GUI,
    CONTINUE_FROM_TEST, PAUSE_FROM_TEST, ABORT_FROM_TEST,
    END_OF_TESTS, REPORT_GENERATED,
    PAUSE_FROM_MANAGER, ABORT_FROM_MANAGER, PLAY_FROM_MANAGER
    )

from wetest.common.constants import LVL_RUN_CONTROL, LVL_FORMAT_VAL
from wetest.common.constants import TERSE_FORMATTER, FILE_HANDLER

from wetest.gui.generator import GUIGenerator
from wetest.gui.specific import (
    STATUS_UNKNOWN, STATUS_RUN, STATUS_RETRY, STATUS_SKIP,
    STATUS_ERROR, STATUS_FAIL, STATUS_SUCCESS
    )

from wetest.pvs.core   import PVInfo, PVsTable
from wetest.pvs.naming import generate_naming, NamingError
from wetest.pvs.parse  import pvs_from_path

from wetest.report.generator import ReportGenerator

from wetest.testing.generator import TestsGenerator
from wetest.testing.generator import SelectableTestCase, SelectableTestSuite
from wetest.testing.reader import MacrosManager, ScenarioReader, FileNotFound

# logger setup
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(TERSE_FORMATTER)
logger.addHandler(stream_handler)
logger.addHandler(FILE_HANDLER)
## choose modules logging level
# print("\n".join(logging.Logger.manager.loggerDict))  # list loggers
logging.getLogger("wetest.gui.generator").setLevel(logging.ERROR)
logging.getLogger("wetest.gui.specific").setLevel(logging.ERROR)
logging.getLogger("wetest.gui.base").setLevel(logging.ERROR)
logging.getLogger("wetest.report.generator").setLevel(logging.ERROR)
logging.getLogger("wetest.testing.generator").setLevel(logging.ERROR)
logging.getLogger("wetest.testing.reader").setLevel(logging.WARNING)
## and for multiprocessing
mp_logger = multiprocessing.get_logger()
mp_logger.setLevel(multiprocessing.SUBWARNING)
mp_logger.addHandler(stream_handler)

# Global constants
PREFIX = ""
DELAY = 1
FILE_PREFIX = "TEST-wetest.testing.generator.TestsSequence-"
OUTPUT_DIR = "/tmp/"
END_OF_GUI = "GUI has been closed"

def quiet_exception(*args):
    """No traceback will be shown for the provided exceptions."""
    exception_tuple = tuple(args[:])

    def decorator(func):

        def wrapper(*args, **kwargs):
            try:
                func(*args, **kwargs)
            except exception_tuple:
                pass

        return wrapper

    return decorator

class MultithreadedQueueStream():
    """Multiprocessing Queue implementing methodes of sys.stdout used by
    logging.StreamHandler

    Apparently there is no way to inherit from this object,
    so wrapping on it instead.
    """

    def __init__(self):
        self.queue = multiprocessing.Queue()

    def put(self, data):
        self.queue.put(data)

    def get(self):
        return self.queue.get()

    def write(self, a_str=""):
        self.queue.put(a_str)

    def flush(self):
        self.write()

class ListStream(list):
    """List implementing methodes of sys.stdout used by logging.StreamHandler

    Apparently there is no way to inherit from this object,
    so wrapping on it instead.
    """
    def write(self, a_str=""):
        self.append(a_str)

    def flush(self):
        pass


def generate_tests(scenarios, macros_mgr=None):
    """Create a test suite from a YAML file (suite or scenario).

    :param scenario_file: A list of YAML scenario file path.
    :param macros_mgr:    MacrosManager with macros already defined

    :returns suite:       A unittest TestSuite object.
    :returns configs:     Scenarios config blocks.
    """
    suite = SelectableTestSuite()

    # get data from scenarios
    ## read the first file
    tests_data = ScenarioReader(scenarios.pop(0), macros_mgr=macros_mgr).get_deserialized()
    if "scenarios" not in tests_data:
        tests_data["scenarios"]=[]
    ## append scenario from remaining files
    for scenario in scenarios:
        new_tests_data = ScenarioReader(scenario, macros_mgr=macros_mgr).get_deserialized()
        tests_data["scenarios"] += new_tests_data["scenarios"]

    # Get titles
    ## Defaults title when several files from command line.
    configs = [{"name":"WeTest Suite"}]
    ## Overwise get top title from first file
    if len(scenarios) == 0 and "name" in tests_data:
        configs = [{"name":tests_data["name"]}]
    # and populate TestSuite
    for idx, scenario in enumerate(tests_data['scenarios']):
        logger.debug("Generate tests with TestGenerator...")
        tests_gen = TestsGenerator(scenario)
        configs.append(tests_gen.get_config())

        logger.debug("Append tests to suite...")
        tests_gen.append_to_suite(suite, scenario_index=idx)

    logger.debug("Created tests suite.")

    # display unit/functionnal info to user
    logger.warning("Loaded %s tests from `%s`:",suite.countTestCases(), configs[0]["name"])
    for scenario in tests_data['scenarios']:
        if str(scenario["config"]["type"]).lower() == "unit":
            type_str = "unit tests (random)  "
        elif str(scenario["config"]["type"]).lower() == "functional":
            type_str = "functional (ordered) "
        else:
            type_str = str(scenario["config"]["type"])+" (??)"
        logger.warning("\t- %s `%s`", type_str, scenario["config"].get("name", "Unnamed"))

    return suite, configs


def export_pdf(filename, tests, results, configs, naming):
    """Export tests results to PDF file.

    :param filename: The PDF filename.
    :param tests:    The ran test case(s).
    :param results:  The test result(s).
    :param configs:   The report's suite and scenario configs.
    """
    logger.info("Results will be exported as PDF...")
    report = ReportGenerator(tests, results, filename, configs, naming)
    report.save()


def main():
    """Program's main entry point."""
    logger.info("Launching WeTest...")

    # parse arguments
    parser = argparse.ArgumentParser(description=__description__)

    # tests relative arguments
    parser.add_argument("scenario_file", metavar="TEST_FILE",
                        type=str, nargs="*", default=[],
                        help="One or several scenario files (executed before scenarios from --scenario).")
    parser.add_argument("-s", "--scenario", metavar="TEST_FILE",
                        type=str, nargs="+", default=[],
                        help="One or several scenario files (executed after positional arguments).")
    parser.add_argument("-m", "--macros", metavar='MACRO=VALUE',
                        type=str, nargs="+", action="append",
                        help="Override macros defined in file.")

    # PVs relative arguments
    pvs_group = parser.add_mutually_exclusive_group(required=False)
    pvs_group.add_argument("-d", "--db", metavar="DB_PATH",
                        type=str, nargs='+', default=[],
                        help="EPICS DB files and directory to extract additional PVs from.")
    pvs_group.add_argument("-D", "--no-pv", action='store_true', default=False,
                        help="Run withtout monitoring any PVs.")
    parser.add_argument("-n", "--naming", type=str,
                        default="None", choices=["ESS", "RDS-81346", "SARAF", "None"],
                        help="Specifies naming convention to display PV name (defaults to None).")

    # run relative arguments
    parser.add_argument("-G", "--no-gui", action='store_true', default=False,
                        help="Do not open a GUI.")
    auto_play_group = parser.add_mutually_exclusive_group(required=False)
    auto_play_group.add_argument("-p", "--force-play", action='store_true', default=False,
                        help="Start runnning tests automatically even with disconnected PV.")
    auto_play_group.add_argument("-P", "--no-auto-play", action='store_true', default=False,
                        help="Tests will not start running automatically.")

    # output relative arguments
    report_group = parser.add_mutually_exclusive_group(required=False)
    report_group.add_argument("-o", "--pdf-output", metavar="OUTPUT_FILE", type=str,
                        default="wetest-results.pdf",
                        help="Specify PDF output file name (otherwise defaults to wetest-results.pdf).")
    report_group.add_argument("-O", "--no-pdf-output", action='store_true', default=False,
                        help="Do not generate the PDF report with tests results.")

    args = parser.parse_args()

    logger.info("Processing arguments...")

    with_gui = not args.no_gui

    scenarios = args.scenario_file + args.scenario
    # Check parameters are valid
    if len(scenarios) == 0 and len(args.db)==0:
        parser.print_usage()
        logger.error("A test scenario (--scenario) or a directory from which to extact PVs (--db) is required")
        sys.exit(2)

    # select naming convention
    naming = generate_naming(args.naming)

    # get PVs from DB files
    pvs_from_db = []
    if args.db and not args.no_pv:
        pvs_from_db = pvs_from_path(args.db)
    pvs_from_files = [ pv["name"] for pv in pvs_from_db ]

    # deal with CLI macros
    cli_macros = {}
    if args.macros:
        # we get a list of list because we enable "append" action mode
        for macros_list in args.macros:
            for macro in macros_list:
                try:
                    k,v = macro.split("=",1)
                    if k in cli_macros:
                        logger.error("`%s` already defined in CLI, using value: %s", k, cli_macros[k])
                    else:
                        cli_macros[k]=v
                except ValueError:
                    logger.critical("Could not parse a MACRO=VALUE in %s", macro)
                    raise
        logger.info(
            "using CLI macros:\n%s",
            "\n".join( ["\t%s: %s"%(k,v) for k,v in cli_macros.items()] )
            )
    macros_mgr = MacrosManager(known_macros = cli_macros)

    # file validation logging
    fv_list = ListStream()
    fv_handler = logging.StreamHandler(fv_list)
    fv_handler.setLevel(LVL_FORMAT_VAL)
    logging.getLogger("_wetest_format_validation").addHandler(fv_handler)

    # generate tests from file
    suite, configs = None, [{"name":"No tests to run"}]
    if len(scenarios) != 0:
        logger.info('Will load tests from files:\n\t-%s', "\n\t-".join(scenarios))
        try:
            suite, configs = \
                generate_tests(scenarios=scenarios, macros_mgr=macros_mgr)
        except FileNotFound as e:
            logger.error(e)
            exit(4)

    queue_to_gui = multiprocessing.Manager().Queue()
    queue_from_gui = multiprocessing.Manager().Queue()

    # stop here if no PVs to monitor and no test to run
    if len(pvs_from_files) == 0 and suite.countTestCases() == 0:
        logger.error("Please provide at least a test to run or PVs to monitor.")
        sys.exit(3)

    # monitor PVs
    if args.no_pv:
        all_connected, pv_refs = True, {}
    else:
        all_connected, pv_refs = PVsTable(queue_to_gui).register_pvs(
            pv_list=pvs_from_files,
            suite=suite)

    # show naming compatibility in CLI
    for pv_name, pv in pv_refs.items():
        try:
            naming.split(pv_name)
        except NamingError as e:
            logger.error(e)

    # decide whether to run tests or not
    autoplay = (all_connected or args.force_play) and not args.no_auto_play
    if  args.no_auto_play:
        logger.error("Not starting tests as required.")
    else:
        if not all_connected:
            if not args.force_play:
                logger.error("Not starting tests as some PVs are currently not reachable.")
            else:
                logger.error("Starting tests even though some PVs are currently not reachable.")

    # generate GUI
    if with_gui:

        logger.info("Opening GUI...")
        root = tk.Tk()
        gui = GUIGenerator(master=root, suite=suite, configs=configs, naming=naming,
            update_queue=queue_to_gui, request_queue=queue_from_gui,
            file_validation=fv_list)

    if args.no_pdf_output:
        pdf_output = None
    else:
        pdf_output = os.path.abspath(args.pdf_output)

    # run tests
    data = {
        "update_queue": queue_to_gui,
        "suite": suite,
        "configs": configs,
        "pdf_output": pdf_output,
        "naming": naming,
    }

    pm = ProcessManager(data, not with_gui, queue_to_gui, queue_from_gui)
    try:

        pm.run()

        if autoplay:
            if not with_gui:  # no GUI with a play button
                pm.start_play()
            else:
                gui.play()  # drawback: apply selection, although it is the same as from file
                            # advantage: reset the test and therefore set prev_status correctly
        else:
            logger.warning("Waiting for user.")
            if not with_gui:  # no GUI with a play button
                logger.warning(
                    "  - To start testing, press Ctrl+D then ENTER.\n"+
                    "  - To abort, press Ctrl+C.")
                sys.stdin.readlines()  # to flush previous inputs, requires Ctrl+D
                sys.stdin.readline()   # ENTER to return from this one
                pm.start_play()
            else:
                logger.warning(
                    "  - To start testing, use GUI play button.\n"+
                    "  - To abort, use GUI abort button, or press Ctrl+C.")

        if with_gui:
            root.mainloop()
            logger.warning("GUI closed.")
            queue_from_gui.put(END_OF_GUI)


        pm.join()
    except (KeyboardInterrupt, SystemExit):
        pm.terminate()
        logger.error("Aborting WeTest.")
    else:
        # clean ending
        logger.warning("Exiting WeTest.")


class ProcessManager:
    """Class that start/stop the runner and report process, and process their outputs."""

    def __init__(self, args, no_gui, queue_to_gui, queue_from_gui):
        self.queue_to_gui = queue_to_gui
        self.queue_from_gui = queue_from_gui

        self.suite = args["suite"]
        self.pdf_output = args["pdf_output"]
        self.configs = args["configs"]
        self.naming = args["naming"]

        # trace start request  (to unpause run process)
        self.evt_start = multiprocessing.Event()
        # stdin to subprocesses, for raw input use
        # https://stackoverflow.com/questions/13786974/raw-input-and-multiprocessing-in-python
        self.stdin = os.fdopen(os.dup(sys.stdin.fileno()))

        # access to runner output
        self.runner_output = MultithreadedQueueStream()
        queue_handler = logging.StreamHandler(self.runner_output)
        queue_handler.setLevel(LVL_RUN_CONTROL)
        logging.getLogger("_wetest_tests_results").addHandler(queue_handler)

        # process handles
        self.p_run_and_report = None
        self.p_parse_output = None
        self.p_gui_commands = None

        # process status
        self.p_run_and_report_started = multiprocessing.Event()
        self.p_parse_output_started = multiprocessing.Event()
        self.p_gui_commands_started = multiprocessing.Event()

        # process data sharing
        self.ns = multiprocessing.Manager().Namespace()
        self.ns.no_gui = no_gui
        ## applaying test selection to suite needs to be done in runner process
        self.selection_from_GUI = multiprocessing.Event()
        self.ns.selection = ()  # use an imutable type to ensure namespace update
        ## store process pids for use by other processes
        self.ns.pid_run_and_report = None
        self.ns.pid_p_parse_output = None
        self.ns.pid_p_gui_commands = None

        # results fill by test runner, used by report generator
        self.results = None

    def start_runner_process(self):
        """start runner in another process (also needs to be CA compatible)"""
        self.p_run_and_report = epics.CAProcess(
            target=self.run_and_report, name="run_and_report")
        self.p_run_and_report.start()
        self.ns.pid_run_and_report = self.p_run_and_report.pid
        logger.debug("pid_run_and_report: %s", self.ns.pid_run_and_report)
        self.p_run_and_report_started.wait() # to be able to abort from p_parse_output

    def start_parser_process(self):
        """start parse_output in another process"""
        self.p_parse_output = multiprocessing.Process(target=self.parse_output, name="parse_output")
        self.p_parse_output.start()
        self.ns.pid_p_parse_output = self.p_parse_output.pid
        logger.debug("pid_p_parse_output: %s", self.ns.pid_p_parse_output)
        self.p_parse_output_started.wait() # to be able to abort properly from p_gui_commands

    def start_gui_command_process(self):
        """sstart gui_commands in another process"""
        self.p_gui_commands = multiprocessing.Process(target=self.gui_commands, name="gui_commands")
        # self.p_gui_commands.daemon = True # so that it can restart the runner and parser process
        self.p_gui_commands.start()
        self.ns.pid_p_gui_commands = self.p_gui_commands.pid
        logger.debug("pid_p_gui_commands: %s", self.ns.pid_p_gui_commands)
        self.p_gui_commands_started.wait() # for homogeneity with other process start functions

    def run(self):
        """Start the various subprocess"""
        self.start_runner_process()
        self.start_parser_process()

        if not self.ns.no_gui:
            self.start_gui_command_process()

    def join(self):
        """Joins on the multiple process running"""
        self.p_run_and_report.join()
        self.p_parse_output.join()
        if self.p_gui_commands is not None:
            self.p_gui_commands.join()

    def terminate(self):
        """Terminates the multiple process running"""
        self.p_run_and_report.terminate()
        self.p_parse_output.terminate()
        if self.p_gui_commands is not None:
            self.p_gui_commands.terminate()

    @quiet_exception(KeyboardInterrupt)
    def run_and_report(self):
        """Runs the tests and generate the report"""
        self.p_run_and_report_started.set()
        logger.debug("Enter run_and_report (%d)", multiprocessing.current_process().pid)
        logger.warning("-----------------------")
        if self.ns.no_gui:
            logger.warning("Ready to start testing.")
        else:
            logger.warning("Ready to start testing, use GUI play button.")

        # do not start running before start requested
        self.evt_start.wait()
        self.evt_start.clear()

        if self.suite is not None:

            # update selection if necessary
            if self.selection_from_GUI.is_set():
                logger.info("Applying test selection...")
                selection = self.ns.selection
                logger.debug("runner selected tests: %s", selection)
                self.update_selection(selected = selection)

            logger.info("Running tests suite...")

            runner = unittest.TextTestRunner(verbosity=0) # use verbosity for debug

            # check that there are tests to run
            logger.info("Nbr tests: %d", self.suite.countTestCases())

            nbr_tests = len(self.suite._tests)
            if nbr_tests == 0:
                logger.error("No test to run.")
                self.results = []
            else:
                logger.info("Running %d tests...", nbr_tests)
                self.results = runner.run(self.suite)

            logger.info("Ran tests suite.")
            self.runner_output.put(END_OF_TESTS)

        logger.warning("Done running tests.")

        # Generate PDF
        if self.results and self.pdf_output is not None:
            logger.info('Will export result in PDF file: %s', self.pdf_output)
            export_pdf(self.pdf_output, self.suite, self.results, self.configs, self.naming)
            logger.warning("Done generating report: %s", self.pdf_output)
            self.queue_to_gui.put(REPORT_GENERATED + " " + self.pdf_output)
        else:
            logger.warning("No report to generate.")

        time.sleep(0.1) # Just enough to let the Queue finish
        # https://stackoverflow.com/questions/36359528/broken-pipe-error-with-multiprocessing-queue.
        # TODO is this solved now that Queue comes from a multiprocessing.Manager ?

        logger.debug("Leave run_and_report (%d)", multiprocessing.current_process().pid)

    def pause_runner(self):
        self.queue_to_gui.put(PAUSE_FROM_MANAGER)
        if self.ns.no_gui:
            logger.warning("Pausing execution."
                +"\n  - To continue press Ctrl+Z and enter `fg`."
                +"\n  - To abort press Ctrl+C twice.")
        else:
            logger.warning("Pausing execution."
                +"\n  - To continue, use GUI play button, or press Ctrl+Z and enter `fg`."
                +"\n  - To abort, use GUI abort button, or press Ctrl+C twice.")
        os.kill(self.ns.pid_run_and_report, signal.SIGSTOP)
        logger.debug("Paused run_and_report (%d)", self.ns.pid_run_and_report)

    def start_play(self):
        """Call play runner after setting evt_start"""
        self.evt_start.set()
        self.play_runner()

    def resume_play(self):
        """Call play runner without setting evt_start"""
        self.play_runner()

    def play_runner(self):
        self.queue_to_gui.put(PLAY_FROM_MANAGER)
        logger.info("Playing.")
        os.kill(self.ns.pid_run_and_report, signal.SIGCONT)
        logger.debug("Continue run_and_report (%d)", self.ns.pid_run_and_report)

    def stop_runner(self):
        logger.warning("Aborting execution.")
        self.queue_to_gui.put(ABORT_FROM_MANAGER) # notify GUI
        os.kill(self.ns.pid_run_and_report, signal.SIGKILL) # actually stop tests
        logger.debug("Killed run_and_report (%d)", self.ns.pid_run_and_report)

    def stop_parser(self):
        os.kill(self.ns.pid_p_parse_output, signal.SIGKILL)
        logger.debug("Killed parse_output (%d)", self.ns.pid_p_parse_output)

    @quiet_exception(KeyboardInterrupt)
    def gui_commands(self):
        """Process instructions from self.queue_from_gui"""
        self.p_gui_commands_started.set()
        logger.debug("Enter gui_commands (%d)", multiprocessing.current_process().pid)
        while True:
            cmd = self.queue_from_gui.get()
            logger.debug("command from gui: %s" % cmd)

            if str(cmd).startswith(SELECTION_FROM_GUI):
                # use an imutable type to ensure namespace update
                self.ns.selection = tuple(cmd[len(SELECTION_FROM_GUI)+1:].split(" "))
                logger.debug("gui commands selected tests: %s", self.ns.selection)
                self.selection_from_GUI.set()

            elif cmd == START_FROM_GUI:
                self.start_play()

            elif cmd == RESUME_FROM_GUI:
                self.resume_play()

            elif cmd == PAUSE_FROM_GUI:
                self.pause_runner()

            elif cmd == ABORT_FROM_GUI:
                self.stop_runner()
                self.start_runner_process() # enable replay from GUI

            elif cmd == END_OF_GUI:
                self.ns.no_gui = True
                self.stop_runner()
                self.stop_parser()
                break

            else:
                logger.critical("Unexpected gui command:\n%s" % cmd)

        logger.debug("Leave gui_commands (%d)", multiprocessing.current_process().pid)

    def update_selection(self, selected):
        """Select only the test provided in selected, otherwise skip them."""
        logger.warning("Applying selection may take some time.")
        self.suite.apply_selection(selected, "Skipped from GUI.")

    @quiet_exception(KeyboardInterrupt)
    def parse_output(self):
        """reads runner output and convert it to update data items
        in a new thread
        """
        self.p_parse_output_started.set()
        logger.debug("Enter parse_output (%d)", multiprocessing.current_process().pid)
        while True:

            # get next output to parse
            new_str = self.runner_output.get().rstrip("\n")
            logger.debug("from tests runner:>%s<"%new_str)
            # ignore empty lines
            if new_str == "":
                continue

            # check for start of test
            match_running = re.search(
                r"^Running\s*(?P<test_id>test-\d+-\d+-\d+)\s*.*$",
                new_str)
            # check for skipped test
            match_skipped = re.search(
                r"^Skipping\s*(?P<test_id>test-\d+-\d+-\d+)\s*.*$",
                new_str)
            # check for retry of test
            match_rerun = re.search(
                r"^Retry \(.*\)\s*(?P<test_id>test-\d+-\d+-\d+)\s*\(in (?P<duration>\d+\.\d+)s\)\s*(?P<trace>.*)$",
                new_str)
            # check for end of test
            match_result = re.match(
                r"^(?P<status>Success\s*of|Failure\s*of|Error\s*of)\s*(?P<test_id>test-\d+-\d+-\d+)\s*\(in (?P<duration>\d+\.\d+)s\)\s*(?P<trace>[\s\S]*)$",
                new_str)

            if match_running is not None:
                logger.debug("=> New test running")
                logger.debug("test_id: %s",match_running.group("test_id"))
                test_id = match_running.group("test_id")
                self.queue_to_gui.put([test_id, STATUS_RUN, None, None])

            elif match_skipped is not None:
                logger.debug("=> Test skipped")
                logger.debug("test_id: %s",match_skipped.group("test_id"))
                test_id = match_skipped.group("test_id")
                self.queue_to_gui.put([test_id, STATUS_SKIP, None, None])

            elif match_rerun is not None:
                logger.debug("=> Test retry")
                test_id = match_rerun.group("test_id")
                duration = match_rerun.group("duration")
                trace = match_rerun.group("trace")
                if trace == "":
                    trace = None
                self.queue_to_gui.put([test_id, STATUS_RETRY, duration, trace])

            elif match_result is not None:
                logger.debug("=> New test result")
                status = match_result.group("status")
                test_id = match_result.group("test_id")
                duration = match_result.group("duration")
                trace = match_result.group("trace")
                if trace == "":
                    trace = None
                if status.startswith("Error "):
                    status = STATUS_ERROR
                elif status.startswith("Failure "):
                    status = STATUS_FAIL
                elif status.startswith("Success "):
                    status = STATUS_SUCCESS
                else:
                    logger.error("Unexpected status "+status)
                    status = STATUS_UNKNOWN

                # finish running test
                self.queue_to_gui.put([test_id, status, duration, trace])

            # check for test requested continue
            elif new_str == CONTINUE_FROM_TEST:
                logger.debug("=> Continue from test")
                pass

            # check for test requested pause
            elif new_str == PAUSE_FROM_TEST:
                logger.debug("=> Pause from test")
                self.pause_runner()

            # check for test requested abort
            elif new_str == ABORT_FROM_TEST:
                logger.debug("=> Abort from test")
                self.stop_runner()
                if self.ns.no_gui:
                    break
                else:
                    self.start_runner_process() # enable replay from GUI

            # check for no more tests
            elif new_str == END_OF_TESTS:
                logger.debug("=> No more test to run.")
                self.queue_to_gui.put(END_OF_TESTS)
                if self.ns.no_gui:
                    break
                else:
                    self.start_runner_process() # enable replay from GUI

            # we should not reach here
            else:
                logger.critical("Unexpected test output:\n%s" % new_str)

        logger.debug("Leave parse_output (%d)", multiprocessing.current_process().pid)

if __name__ == "__main__":
    main()