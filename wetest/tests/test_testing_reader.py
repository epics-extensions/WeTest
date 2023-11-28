"""Test testing.reader module."""

import unittest

import pytest

from wetest.testing.reader import (
    Reader,
    ScenarioReader,
    SuiteReader,
    UnsupportedFileFormatError,
)


class TestYAMLReading(unittest.TestCase):
    """Module's Unit Tests."""

    def test_yaml_version_checker(self):
        """Test supported versions are well identified."""
        assert True is Reader()._version_is_supported(major=1, minor=0, bugfix=0)
        assert True is Reader()._version_is_supported(major=0, minor=1, bugfix=0)
        assert True is Reader()._version_is_supported(major=0, minor=0, bugfix=1)
        with pytest.raises(UnsupportedFileFormatError):
            Reader()._version_is_supported(major=2, minor=0, bugfix=0)
        with pytest.raises(UnsupportedFileFormatError):
            Reader()._version_is_supported(major=1, minor=1, bugfix=0)
        with pytest.raises(UnsupportedFileFormatError):
            Reader()._version_is_supported(major=1, minor=0, bugfix=1)

    def test_scenario_example01_syntax(self):
        assert True is ScenarioReader("wetest/tests/scenario_example01.yaml").is_valid()

    def test_scenario_example02_syntax(self):
        assert True is ScenarioReader("wetest/tests/scenario_example02.yaml").is_valid()

    def test_scenario_example03_syntax(self):
        assert True is ScenarioReader("wetest/tests/scenario_example03.yaml").is_valid()

    def test_scenario_example04_syntax(self):
        assert True is ScenarioReader("wetest/tests/scenario_example04.yaml").is_valid()

    def test_scenario_example05_syntax(self):
        assert True is ScenarioReader("wetest/tests/scenario_example05.yaml").is_valid()

    def test_scenario_acceptance_demo_syntax(self):
        assert True is ScenarioReader("wetest/tests/acceptance-demo.yaml").is_valid()

    def test_scenario_mks946_testing_syntax(self):
        assert True is ScenarioReader("wetest/tests/mks946-testing.yaml").is_valid()

    def test_scenario_mks946_syntax(self):
        assert True is ScenarioReader("wetest/tests/mks946.yaml").is_valid()

    def test_suite_example01_syntax(self):
        assert True is SuiteReader("wetest/tests/suite_example01.yaml").is_valid()

    def test_scenario_are_deserialized_in_suite(self):
        suite = SuiteReader("wetest/tests/suite_example01.yaml").get_deserialized()
        assert len(suite["scenarios"]) == 2

    # TODO: Issue 10 - Bad parsing should fail
    # def test_bad_syntax(self):
    # self.assertEqual(False,     "wetest/tests/bad.yml"))
