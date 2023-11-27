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

"""Generates tests from YAML file."""

import logging
import numpy
import random
import time
import timeit
import unittest

import epics

from wetest.common.constants import CONTINUE_FROM_TEST, PAUSE_FROM_TEST, ABORT_FROM_TEST
from wetest.common.constants import LVL_TEST_ERRORED, LVL_TEST_FAILED, LVL_TEST_SKIPPED
from wetest.common.constants import LVL_TEST_SUCCESS, LVL_TEST_RUNNING, LVL_RUN_CONTROL
from wetest.common.constants import VERBOSE_FORMATTER, TERSE_FORMATTER, FILE_HANDLER
from wetest.common.constants import WeTestError, to_string

from wetest.testing.reader import ABORT, PAUSE, CONTINUE

NO_KIND = "Missing test kind (values, range or commands)"

# configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(VERBOSE_FORMATTER)
logger.addHandler(stream_handler)
logger.addHandler(FILE_HANDLER)

## logger to share test results
tr_logger = logging.getLogger("_wetest_tests_results")
tr_logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(TERSE_FORMATTER)
stream_handler.setLevel(logging.WARNING)
tr_logger.addHandler(stream_handler)
tr_logger.addHandler(FILE_HANDLER)


class EmptyTest(WeTestError):
    """Test does not do anything.

    Exception raised executing a test without getter nor setter.
    """

    pass


class InconsistantTest(WeTestError):
    """Test filed missing with regards to other fields.

    Exception raised executing a test that misses a field,
    for instance a setter was provided but not set_value.
    """

    pass


class InvalidTest(WeTestError):
    """Something is wrong with test data."""


class TestNotFound(WeTestError):
    """Test is not in the sequence."""


class TestData(object):
    """A generic test representation."""

    def __init__(
        self,
        on_failure,
        test_title,
        subtest_title,
        test_id="",
        skip=False,
        retry=0,
        getter=None,
        setter=None,
        get_value=None,
        set_value=None,
        prefix="",
        delay=0,
        margin=None,
        delta=None,
        test_message=None,
        subtest_message=None,
    ):
        """Initialize a TestData structure.

        :param test_title: The test name.
        :param subtest_title: A subtest name.
        :param id: Test's id.
        :param on_failure: Defines test behavior in case of failure
        :param retry: How many time to retry
        :param getter: Test's getter.
        :param setter: Test's setter.
        :param get_value: Value to read back.
        :param set_value: Value to send.
        :param prefix: Commands prefix (prefix of getter and setter).
        :param delay: Delay between two commands (a float in seconds).
        :param margin: Allowed percentage of margin of read-back value.
        :param delta: Allowed interval around read-back value.
        :param test_message: If any a test message.
        :param subtest_message: If any a subtest message.
        """
        if on_failure.lower() not in [ABORT, PAUSE, CONTINUE]:
            logger.critical("Unexpected on_failure value: %s" % on_failure)
            self.on_failure = ABORT
        else:
            self.on_failure = on_failure.lower()
        self.test_title = test_title
        self.subtest_title = subtest_title
        self.id = test_id
        self.skip = skip
        self.retry = float(retry)
        self.getter = getter
        self.setter = setter
        self.get_value = get_value
        self.set_value = set_value
        self.prefix = prefix
        self.delay = delay
        self.margin = margin
        self.delta = delta
        self.test_message = test_message
        self.subtest_message = subtest_message
        logger.debug("set_value: %s (%s)", set_value, type(set_value))
        logger.debug("get_value: %s (%s)", get_value, type(get_value))

        if self.retry != float("inf"):
            self.retry = int(self.retry)

        if self.retry < 0:
            self.retry = float("inf")

        if self.setter is not None and self.prefix is not None:
            self.setter = self.prefix + self.setter

        if self.getter is not None and self.prefix is not None:
            self.getter = self.prefix + self.getter

        self.desc = (
            str(self.test_title).replace("\n", " ")
            + ": "
            + str(self.subtest_title).replace("\n", " ")
        )

        logger.debug("%s", self)

    def __str__(self):
        output = self.__repr__()
        output += "\n\ttest_title: %s" % self.test_title
        output += "\n\tsubtest_title: %s" % self.subtest_title
        output += "\n\tid: %s" % self.id
        output += "\n\ton_failure: %s" % self.on_failure
        output += "\n\tretry: %s" % self.retry
        output += "\n\tgetter: %s" % self.getter
        output += "\n\tsetter: %s" % self.setter
        output += "\n\tget_value: %s" % self.get_value
        output += "\n\tset_value: %s" % self.set_value
        output += "\n\tprefix: %s" % self.prefix
        output += "\n\tdelay: %s" % self.delay
        output += "\n\tmargin: %s" % self.margin
        output += "\n\tdelta: %s" % self.delta
        output += "\n\ttest_message: %s" % self.test_message
        output += "\n\tsubtest_message: %s" % self.subtest_message
        output += "\n\tdesc: %s" % self.desc
        return output


def add_doc(value):
    """Add docstring programatically to a function via a decorator.

    :param value: Docstring value.

    :returns: Function's docstring.

    """

    def _doc(func):
        func.__doc__ = value
        return func

    return _doc


def skipped_test_factory(test_data, reason):
    def skipped_test(self):
        tr_logger.log(LVL_TEST_SKIPPED, "")
        tr_logger.log(
            LVL_TEST_SKIPPED, "Skipping   %s    %s", test_data.id, test_data.desc
        )
        raise unittest.SkipTest(reason)

    return skipped_test


class SelectableTestCase(unittest.TestCase):
    """A unittest.TestCase to be filled with test methods, which can be skipped and unskipped"""

    test_data = {}
    func_backup = {}

    @classmethod
    def add_test(cls, test_data, func):
        """Adds a test method, mark the test as selected"""
        cls.test_data[test_data.id] = test_data
        cls.func_backup[test_data.id] = func
        cls.select(test_data.id)

    @classmethod
    def skip(cls, test_id, reason):
        """Skip the test method `test_id`"""
        setattr(cls, test_id, skipped_test_factory(cls.test_data[test_id], reason))

    @classmethod
    def select(cls, test_id):
        """Unskip the test method `test_id`"""
        setattr(cls, test_id, cls.func_backup[test_id])


class SelectableTestSuite(unittest.TestSuite):
    """A unittest.TestSuite with conveniency method to skip and unskip tests."""

    def __init__(self, *args, **kargs):
        unittest.TestSuite.__init__(self, *args, **kargs)
        self._tests_data = {}
        self._skipped_tests = {}
        self._selected_tests = {}

    @property
    def tests_infos(self):
        """Keep test data available for later."""
        return self._tests_data

    def add_skipped_test(self, Test_case, test_id, reason):
        """Add a test to and its data to the suite and reference it as skipped."""
        self._skipped_tests[test_id] = Test_case
        Test_case.skip(test_id, reason)
        self.addTest(Test_case(test_id))
        self._tests_data[test_id] = Test_case.test_data[test_id]

    def add_selected_test(self, Test_case, test_id):
        """Add a test to and its data to the suite and reference it as selected."""
        self._selected_tests[test_id] = Test_case
        Test_case.select(test_id)
        self.addTest(Test_case(test_id))
        self._tests_data[test_id] = Test_case.test_data[test_id]

    def select(self, test_id):
        """Ensure test is selected"""
        if test_id in self._skipped_tests:
            test_case = self._skipped_tests.pop(test_id)
            test_case.select(test_id)
            self._selected_tests[test_id] = test_case

    def skip(self, test_id, reason):
        """Ensure test is skipped"""
        if test_id in self._selected_tests:
            test_case = self._selected_tests.pop(test_id)
            test_case.skip(test_id, reason)
            self._skipped_tests[test_id] = test_case

    def apply_selection(self, selection, reason):
        """Tests and skip tests, based on test ids in selection list."""
        already_selected = dict(self._selected_tests)
        already_skipped = dict(self._skipped_tests)
        for test_id in already_selected:
            if test_id not in selection:
                self.skip(test_id, reason)
        for test_id in selection:
            if test_id in already_skipped:
                self.select(test_id)

    # def __str__(self):
    #     """Debug display for the suite."""
    #     output = ""
    #     output += "selected tests:\n"+" ".join(self._selected_tests)
    #     output += "\n"
    #     output += "skipped tests:\n"+" ".join(self._skipped_tests)
    #     return output


# TODO: Move this method to TestData
def get_margin(data):
    """Get allowed margin between setter and getter values.

    :param data: Test properties.

    :returns: allowed margin.
    """
    if "margin" in data:
        margin = float(data["margin"]) / 100
        logger.debug("Margin will be: " + str(margin * 100) + "%")
    else:
        logger.debug("No margin")
        margin = None

    return margin


def get_delta(data):
    """Get allowed delta between setter and getter values.

    :param data: Test properties.

    :returns: allowed delta.
    """
    return data.get("delta", None)


def get_key(prefered, backup, key):
    """Get key by priority.

    If the `key` exists in `prefered`, it value will be returned, or the `key`
    will be searched in `backup` instead. If it fails, returns None.

    :param prefered: Prefered source.
    :param backup:   Backup source.
    :param key:      Key name.

    :returns: value found for key, or None.
    """
    return prefered.get(key, backup.get(key))


def test_generator(test_data):
    """Generates a test function from test's data.

    :param test_data: a TestData instance (usually extracted from a YAML file).
    :param description: the test's docstring.

    :returns: a test function, to be add to a unittest.TestCase.
    """
    logger.info("Generating test: %s", test_data.desc)

    @add_doc(test_data.desc)
    def test(self):
        """A test case generated from test's data.

        If margin is used, the comparison is not a strict equality, but more
        or less the given percentage. For instance, if margin is used with a
        value of 10%, all values between 9V and 11V will be considered as good
        value.

        """
        if test_data.on_failure == CONTINUE:
            on_failure = CONTINUE_FROM_TEST
        elif test_data.on_failure == PAUSE:
            on_failure = PAUSE_FROM_TEST
        else:
            on_failure = ABORT_FROM_TEST
        tr_logger.log(LVL_TEST_RUNNING, "")
        tr_logger.log(
            LVL_TEST_RUNNING, "Running    %s    %s", test_data.id, test_data.desc
        )

        nb_exec = 0
        setter_error = False
        getter_error = False
        while nb_exec <= test_data.retry:
            start_time = time.time()
            nb_exec += 1
            try:
                # Check for empty or inconsistant test
                if test_data.subtest_title == NO_KIND:
                    raise EmptyTest("Test has no range, values nor commands.")

                if test_data.setter is None and test_data.getter is None:
                    raise EmptyTest("No setter nor getter set for this test.")

                if test_data.setter is not None and test_data.set_value is None:
                    raise InconsistantTest(
                        "[setter error] No value associated to setter."
                    )

                if test_data.getter is not None and test_data.get_value is None:
                    raise InconsistantTest(
                        "[getter error] No value associated to getter."
                    )

                if test_data.set_value is not None and test_data.setter is None:
                    raise InconsistantTest(
                        "[setter error] No setter associated to set value."
                    )

                if test_data.get_value is not None and test_data.getter is None:
                    raise InconsistantTest(
                        "[getter error] No getter associated to get value."
                    )

                # Set PV if required

                setter_error = True
                if test_data.setter and test_data.set_value is not None:
                    setter = epics.PV(test_data.setter)
                    self.assertIsNotNone(
                        setter.status,
                        "Unable to connect to setter PV %s" % (setter.pvname),
                    )

                    # pyepics expect single characters to be passed as integer
                    # convert string to int or float where possible
                    if isinstance(test_data.set_value, list):
                        set_value = []
                        for v in test_data.set_value:
                            if isinstance(v, str):
                                if len(v) == 1:
                                    set_value.append(ord(v))
                                else:
                                    try:
                                        set_value.append(int(v))
                                    except ValueError:
                                        set_value.append(float(v))
                            else:
                                set_value.append(v)
                    else:
                        set_value = test_data.set_value

                    setter.put(set_value)

                setter_error = False

                # Delay
                time.sleep(test_data.delay)

                # Get and test if required
                getter_error = True
                if test_data.getter and test_data.get_value is not None:
                    getter = epics.PV(test_data.getter)
                    self.assertIsNotNone(
                        getter.status,
                        "Unable to connect to getter PV %s" % (getter.pvname),
                    )

                    # check a string value
                    if isinstance(test_data.get_value, str):
                        expected_value = test_data.get_value
                        measured_value = getter.get(as_string=True)

                        self.assertEqual(
                            expected_value,
                            measured_value,
                            "Expected %s to be %s, but got %s"
                            % (
                                getter.pvname,
                                to_string(expected_value),
                                to_string(measured_value),
                            ),
                        )

                    # check a table of values
                    elif isinstance(test_data.get_value, list):
                        # get the measured value to know the lenght of the table to compare
                        measured_value = getter.get()
                        if not isinstance(measured_value, numpy.ndarray):
                            if len(test_data.get_value) == 1:
                                # pyepics get does not return a list in case of
                                # a single-element waveform
                                measured_value = numpy.array([measured_value])
                            else:
                                raise ValueError(
                                    "Expected %s to be an array but got %s"
                                    % (getter.pvname, to_string(measured_value))
                                )

                        # pyepics expect single characters to be passed as integer
                        # convert string to int or float where possible
                        expected_value = []
                        for v in test_data.get_value:
                            if isinstance(v, str):
                                if len(v) == 1:
                                    expected_value.append(ord(v))
                                else:
                                    try:
                                        expected_value.append(int(v))
                                    except ValueError:
                                        expected_value.append(float(v))
                            else:
                                expected_value.append(v)

                        # add zero after the expected values
                        expected_value += [0] * (
                            len(measured_value) - len(test_data.get_value)
                        )

                        self.assertTrue(
                            len(expected_value) == len(measured_value),
                            "Expected %s to be %s elements long, and not %s: %s"
                            % (
                                getter.pvname,
                                len(expected_value),
                                len(measured_value),
                                to_string(measured_value),
                            ),
                        )

                        # recover margin and delta
                        margin_delta_str = ""
                        rtol = None
                        atol = None
                        if test_data.margin is not None:
                            margin_delta_str += " ±%.3G%%" % (test_data.margin * 100)
                            rtol = test_data.margin
                        if test_data.margin is not None and test_data.delta is not None:
                            margin_delta_str += " or"
                        if test_data.delta is not None:
                            margin_delta_str += " ±%.3G" % test_data.delta
                            atol = test_data.delta

                        # compare and allow margin and delta
                        isclose = numpy.equal(measured_value, expected_value)
                        if rtol is not None:
                            isclose_marging = numpy.isclose(
                                measured_value, expected_value, rtol=rtol, atol=0
                            )
                            isclose = numpy.logical_or(isclose, isclose_marging)
                        if atol is not None:
                            isclose_delta = numpy.isclose(
                                measured_value, expected_value, rtol=0, atol=atol
                            )
                            isclose = numpy.logical_or(isclose, isclose_delta)

                        # show "OK" if close otherwise show difference
                        all_close = numpy.all(isclose)
                        if not all_close:  # compute diff only if not OK
                            diff = numpy.abs(measured_value - expected_value)
                            diff[isclose == True] = 0
                            diff_str = ["OK" if x == 0 else x for x in diff]

                            self.assertTrue(
                                all_close,
                                "Expected %s to be %s%s,\nbut got %s,\ndifference is %s"
                                % (
                                    getter.pvname,
                                    to_string(expected_value),
                                    margin_delta_str,
                                    to_string(measured_value),
                                    to_string(diff_str),
                                ),
                            )

                    # check a number or boolean without margin or delta
                    elif not test_data.margin and not test_data.delta:
                        expected_value = test_data.get_value
                        measured_value = getter.get()
                        self.assertEqual(
                            expected_value,
                            measured_value,
                            "Expected %s to be %s, but got %s"
                            % (
                                getter.pvname,
                                to_string(expected_value),
                                to_string(measured_value),
                            ),
                        )

                    # check a number or boolean with margin or delta
                    else:
                        if test_data.margin is not None:
                            margin = abs(
                                float(test_data.get_value) * float(test_data.margin)
                            )
                        else:
                            margin = 0
                        if test_data.delta is not None:
                            delta = abs(float(test_data.delta))
                        else:
                            delta = 0

                        if margin > delta:
                            max_delta = margin
                            margin_delta_str = "±%.3G%%" % (test_data.margin * 100)
                        else:
                            max_delta = delta
                            margin_delta_str = "±%.3G" % delta

                        expected_value = (
                            float("NaN")
                            if test_data.get_value is None
                            else float(test_data.get_value)
                        )
                        measured_value = (
                            float("NaN")
                            if getter.get() is None
                            else float(getter.get())
                        )

                        self.assertAlmostEqual(
                            test_data.get_value,
                            measured_value,
                            delta=max_delta,
                            msg="Expected %s to be %.3G %s (ie. within [%.3G,%.3G]), but got %.3G"
                            % (
                                getter.pvname,
                                expected_value,
                                margin_delta_str,
                                expected_value - max_delta,
                                expected_value + max_delta,
                                measured_value,
                            ),
                        )

                getter_error = False
                elapsed = time.time() - start_time
                tr_logger.log(
                    LVL_TEST_SUCCESS,
                    "Success of %s    (in %.3fs) ",
                    test_data.id,
                    elapsed,
                )
                break  # no exception then no need for retry

            # test fails
            except AssertionError as e:
                # loop again if they are retries left
                if nb_exec <= test_data.retry:
                    elapsed = time.time() - start_time
                    tr_logger.log(
                        LVL_TEST_RUNNING,
                        "Retry (%d/%s) %s    (in %.3fs) %s",
                        nb_exec,
                        test_data.retry,
                        test_data.id,
                        elapsed,
                        e,
                    )

                    if on_failure != CONTINUE:
                        tr_logger.log(LVL_RUN_CONTROL, "%s", on_failure)
                        # give time to pause or abort runner before retrying
                        time.sleep(0.1)

                    continue

                # otherwise mark as failed
                elapsed = time.time() - start_time
                tr_logger.log(
                    LVL_TEST_FAILED,
                    "Failure of %s    (in %.3fs) %s",
                    test_data.id,
                    elapsed,
                    e,
                )
                tr_logger.log(LVL_RUN_CONTROL, "%s", on_failure)
                if on_failure != CONTINUE:
                    # give time to pause or abort runner before running next test
                    time.sleep(0.1)

                raise

            # something is not right with this test (ignore retry)
            except (EmptyTest, InconsistantTest, Exception) as e:
                elapsed = time.time() - start_time
                tr_logger.log(
                    LVL_TEST_ERRORED,
                    "Error   of %s    (in %.3fs) %s%s%s",
                    test_data.id,
                    elapsed,
                    "[setter error] " * setter_error,
                    "[getter error] " * getter_error,
                    e,
                )
                tr_logger.log(LVL_RUN_CONTROL, "%s", on_failure)
                if on_failure != CONTINUE:
                    # give time to pause or abort runner before running next test
                    time.sleep(0.1)
                raise

    return test, test_data


class TestsGenerator(object):
    """TestGenerator generates unittest test cases from a YAML file."""

    def __init__(self, tests_data):
        """Initialize a TestsGenerator object.

        :param tests_data: Deserialized YAML file(s) with tests data.
        """
        logger.debug("Initializing TestGenerator...")

        self.data = tests_data

        self._create_tests_list()

        logger.debug("Initialized TestGenerator.")

    def _create_tests_list(self):
        """Create a list of TestData objects from deserialized file."""
        # TODO: use functions that return a subtestlist instead.
        logger.info("Test list initialization...")
        self.tests_list = []

        for test_raw_data in self.data["tests"]:
            # default values for setter and getter
            setter = None
            getter = None

            # append prefix or not
            prefix = test_raw_data.get("prefix", "")
            if test_raw_data.get("use_prefix", self.get_config("use_prefix")):
                prefix = self.get_config("prefix") + prefix

            # get value or fall back to default
            delay = test_raw_data.get("delay", self.get_config("delay"))
            ignore = test_raw_data.get("ignore", self.get_config("ignore"))
            skip = test_raw_data.get("skip", self.get_config("skip"))
            on_failure = test_raw_data.get("on_failure", self.get_config("on_failure"))
            retry = test_raw_data.get("retry", self.get_config("retry"))

            # generate subtests
            subtests_list = []
            if ignore:
                logger.info("Ignore %s ", test_raw_data["name"])
                # If ignore is True then test should not be read,
                # but index taken into account nonetheless
                # hence adding it in the test list as empty
                subtests_list = None

            elif "range" in test_raw_data:
                try:
                    setter = test_raw_data["setter"]
                except KeyError:
                    logger.info("No setter in : %s", test_raw_data)
                try:
                    getter = test_raw_data["getter"]
                except KeyError:
                    logger.info("No getter in : %s", test_raw_data)

                # Define the values (range) that will be tested
                start = test_raw_data["range"]["start"]
                stop = test_raw_data["range"]["stop"]
                step = abs(test_raw_data["range"].get("step", 0))
                lin = abs(test_raw_data["range"].get("lin", 0))
                geom = abs(test_raw_data["range"].get("geom", 0))
                include_start = test_raw_data["range"].get("include_start", True)
                include_stop = test_raw_data["range"].get("include_stop", True)
                sort = str(test_raw_data["range"].get("sort", True))

                # default to step of 1 in case of nothing defined
                if step == 0 and lin == 0 and geom == 0:
                    step = 1

                # add more values in between if start is not included
                if not include_start:
                    if lin != 0:
                        lin += 1
                    if geom != 0:
                        geom += 1

                # generate the list from step, lin and geom
                value_list = set()
                if step != 0:
                    value_list.update(numpy.arange(start, stop, step))
                if lin != 0:
                    value_list.update(
                        numpy.linspace(start, stop, lin, endpoint=include_stop)
                    )
                if geom != 0:
                    value_list.update(
                        numpy.geomspace(start, stop, geom, endpoint=include_stop)
                    )

                # check if stop value should be tested or not
                if include_stop and stop not in value_list:
                    value_list.add(stop)
                if not include_stop and stop in value_list:
                    value_list.remove(stop)

                # check if start value should be tested or not
                if include_start and start not in value_list:
                    value_list.add(start)
                if not include_start and start in value_list:
                    value_list.remove(start)

                ordered_values = list(value_list)
                # sort or randomize the values
                if sort.lower() in ["true"]:
                    ordered_values = sorted(value_list)
                elif sort.lower() in ["reverse"]:
                    ordered_values = sorted(value_list, reverse=True)
                elif sort.lower() in ["false", "random"]:
                    random.shuffle(ordered_values)
                else:
                    logging.error("Unexpected value for `sort` field: %s", sort)

                for value in ordered_values:
                    # use value only if setter or getter
                    set_value = value if setter is not None else None
                    get_value = value if getter is not None else None
                    if set_value is not None and get_value is not None:
                        subtest_title = str(set_value)
                    elif set_value is not None:
                        subtest_title = " set " + str(set_value)
                    elif get_value is not None:
                        subtest_title = " get " + str(get_value)
                    else:
                        subtest_title = "no setter nor getter"

                    logger.debug("adding new range subtest")
                    test_data = TestData(
                        on_failure=on_failure,
                        retry=retry,
                        test_title=test_raw_data["name"],
                        subtest_title=subtest_title,
                        skip=skip,
                        getter=getter,
                        setter=setter,
                        get_value=get_value,
                        set_value=set_value,
                        prefix=prefix,
                        delay=delay,
                        margin=get_margin(test_raw_data),
                        delta=get_delta(test_raw_data),
                        test_message=test_raw_data.get("message", None),
                    )

                    subtests_list.append(test_data)

            elif "values" in test_raw_data:
                # subtests_list = []
                try:
                    setter = test_raw_data["setter"]
                except KeyError:
                    logger.info("No setter in : %s", test_raw_data)
                try:
                    getter = test_raw_data["getter"]
                except KeyError:
                    logger.info("No setter in : %s", test_raw_data)

                for value in test_raw_data["values"]:
                    # use value only if setter or getter
                    set_value = value if setter is not None else None
                    get_value = value if getter is not None else None
                    if set_value is not None and get_value is not None:
                        subtest_title = str(set_value)
                    elif set_value is not None:
                        subtest_title = " set " + str(set_value)
                    elif get_value is not None:
                        subtest_title = " get " + str(get_value)
                    else:
                        subtest_title = "no setter nor getter"

                    logger.debug("adding new value subtest")
                    test_data = TestData(
                        on_failure=on_failure,
                        retry=retry,
                        test_title=test_raw_data["name"],
                        subtest_title=subtest_title,
                        skip=skip,
                        getter=getter,
                        setter=setter,
                        get_value=get_value,
                        set_value=set_value,
                        prefix=prefix,
                        delay=delay,
                        margin=get_margin(test_raw_data),
                        delta=get_delta(test_raw_data),
                        test_message=test_raw_data.get("message", None),
                    )

                    subtests_list.append(test_data)

            elif "commands" in test_raw_data:
                for command in test_raw_data["commands"]:
                    if command.get("ignore", False):
                        # ignore has already been checked at test level
                        continue

                    setter = None
                    getter = None
                    set_value = None
                    get_value = None
                    # Setter is optional
                    try:
                        setter = get_key(command, test_raw_data, "setter")
                    except KeyError:
                        logger.info("No setter in : %s", test_raw_data)

                    # Getter is optional
                    try:
                        getter = get_key(command, test_raw_data, "getter")
                    except KeyError:
                        logger.info("No getter in : %s", test_raw_data)

                    # Setter is optional, and so is set_value
                    if setter is not None:
                        set_value = command.get("value", command.get("set_value"))

                    # Getter is optional, and so is get_value
                    if getter is not None:
                        get_value = command.get("value", command.get("get_value"))

                    delay = command.get(
                        "delay", test_raw_data.get("delay", self.get_config("delay"))
                    )
                    skip = command.get(
                        "skip", test_raw_data.get("skip", self.get_config("skip"))
                    )
                    on_failure = command.get(
                        "on_failure",
                        test_raw_data.get("on_failure", self.get_config("on_failure")),
                    )
                    retry = command.get(
                        "retry", test_raw_data.get("retry", self.get_config("retry"))
                    )

                    logger.debug("adding new command subtest")
                    test_data = TestData(
                        on_failure=on_failure,
                        retry=retry,
                        test_title=test_raw_data["name"],
                        subtest_title=command["name"],
                        skip=skip,
                        getter=getter,
                        setter=setter,
                        get_value=get_value,
                        set_value=set_value,
                        prefix=prefix,
                        delay=delay,
                        margin=get_margin(command),
                        delta=get_delta(command),
                        test_message=test_raw_data.get("message", None),
                        subtest_message=command.get("message", None),
                    )

                    subtests_list.append(test_data)

            else:  # missing test kind (range, values or command)
                if "finally" in test_raw_data:
                    pass  # finally only test are acceptatble
                else:  # show an error "NO_KIND"
                    test_data = TestData(
                        on_failure=on_failure,
                        test_title=test_raw_data["name"],
                        subtest_title=NO_KIND,
                        skip=skip,
                    )

                    subtests_list.append(test_data)

            if "finally" in test_raw_data and not ignore:
                logger.debug("Found finally statement in %s", test_raw_data)
                if subtests_list is None:
                    # for instance no subtest
                    subtests_list = []

                command = None
                if "setter" in test_raw_data["finally"]:
                    command = test_raw_data["finally"]["setter"]
                elif "setter" in test_raw_data:
                    command = test_raw_data["setter"]
                else:
                    raise InvalidTest("Undefined setter for finally block")

                value = None
                if "value" in test_raw_data["finally"]:
                    value = test_raw_data["finally"]["value"]
                else:
                    raise InvalidTest("Undefined value in finally block")

                logger.debug("adding new finally subtest")
                finally_data = TestData(
                    on_failure=on_failure,
                    retry=test_raw_data.get("retry", self.get_config("retry")),
                    test_title=test_raw_data["name"],
                    subtest_title="Final statement",
                    skip=skip,
                    setter=command,
                    set_value=value,
                    prefix=prefix,
                )

                subtests_list.append(finally_data)

            self.tests_list.append(subtests_list)

        logger.info("Test list initialized")

    def _randomize_order(self):
        """Generate a random order for test execution.

        :returns: a list of integers from zero to tests count minus one, to
                  access each test once in a random order from its index.
        """
        logger.debug("Randomizing order…")
        count = len(self.tests_list)
        random_list = [int(i) for i in range(0, count)]

        logger.info("Tests type: %s", self.get_config("type"))
        if self.get_config("type") == "unit":
            random.shuffle(random_list)
        logger.info("Tests will be executed in that order: %s", random_list)

        return random_list

    def get_test_id(self, scenario, test, subtest):
        """Generate test id
        The test id are not sortable in alphabetical order anymore.
        """
        return "test-%d-%d-%d" % (scenario, test, subtest)

    def get_config(self, field=None):
        """Getter to access config fields

        :param field:  config field name

        :returns: The config.field value or whole config dictionnary if field is None
        """
        if field is None:
            return self.data["config"]
        else:
            return self.data["config"][field]

    def append_to_suite(self, tests_suite, scenario_index=0):
        """Generate `unittest` tests from configuration file.

        :param tests_suite:      A TestSuite to add the tests to
        :param scenario_index:   Index of the scenario, usefull when running a
                                suite with multiple scenarios.
        """
        order = self._randomize_order()

        # add each test with the new id to define the order
        Test_case = SelectableTestCase

        for idx in order:
            if self.tests_list[idx] is None:
                # None when test is ignored
                continue
            for test_data in self.tests_list[idx]:
                test_id = self.get_test_id(
                    scenario=scenario_index,
                    test=idx,
                    subtest=self.tests_list[idx].index(test_data),
                )
                test_data.id = test_id

                # generate test case
                test_func, test_data = test_generator(test_data)
                skip = test_data.skip

                logger.debug(
                    'Add test named "%s", with description "%s": %s',
                    test_id,
                    test_data.desc,
                    test_func,
                )

                # test_case = SelectableTestCase(test_data, test_func)
                Test_case.add_test(test_data, test_func)

                # add test case to test suite
                if skip:
                    tests_suite.add_skipped_test(
                        Test_case, test_id, "Test skipped from file."
                    )
                else:
                    tests_suite.add_selected_test(Test_case, test_id)
