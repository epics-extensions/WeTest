"""Test testing.generator module."""

# Asserts are used here,
# ruff: noqa: S101

import unittest

from wetest.testing.generator import TestsGenerator, TestsSequence, get_key
from wetest.testing.reader import ScenarioReader


class TestTestsGenerator(unittest.TestCase):
    """Module's Unit Tests."""

    def test_generator(self):
        """Test generator can read and generates tests."""
        scenario = ScenarioReader("wetest/tests/mks946.yaml")
        tests = TestsGenerator(scenario.get_deserialized())
        tests.generates(TestsSequence)

    def test_device_prefix(self):
        """Device prefix is correctyl used."""
        scenario = ScenarioReader("wetest/tests/scenario_example03.yaml")
        tests = TestsGenerator(scenario.get_deserialized())
        tests.generates(TestsSequence)

    def test_get_prefix(self):
        """Prefix is correctly assembled from prefix fields."""
        scenario = ScenarioReader("wetest/tests/scenario_example03.yaml")
        tests = TestsGenerator(scenario.get_deserialized())
        assert tests.tests_list[0][0].prefix == "LOCATION:DEVICE:"

    def test_get_setter(self):
        """Setter is correctly defined."""
        scenario = ScenarioReader("wetest/tests/scenario_example03.yaml")
        tests = TestsGenerator(scenario.get_deserialized())
        setter = get_key(
            tests.data["tests"][0]["commands"][0],
            tests.data["tests"][0],
            "setter",
        )
        assert setter == "LockS"
        getter = get_key(
            tests.data["tests"][0]["commands"][0],
            tests.data["tests"][0],
            "getter",
        )
        assert getter == "LockR"