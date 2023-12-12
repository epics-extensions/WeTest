"""Test testing.reader module."""

# Asserts are used here,
# ruff: noqa: S101

import pytest

from wetest.testing.reader import ScenarioReader, UnsupportedFileFormatError


def test_yaml_version_checker():
    """Test supported versions are well identified."""
    assert ScenarioReader.supports_version(major=1, minor=0, bugfix=0)
    assert ScenarioReader.supports_version(major=1, minor=1, bugfix=0)
    assert ScenarioReader.supports_version(major=1, minor=2, bugfix=0)
    assert ScenarioReader.supports_version(major=1, minor=2, bugfix=2)
    with pytest.raises(UnsupportedFileFormatError):
        ScenarioReader.supports_version(major=0, minor=0, bugfix=0)
    with pytest.raises(UnsupportedFileFormatError):
        ScenarioReader.supports_version(major=2, minor=1, bugfix=0)
    with pytest.raises(UnsupportedFileFormatError):
        ScenarioReader.supports_version(major=1, minor=3, bugfix=1)


def test_scenario_example01_syntax():
    assert ScenarioReader("tests/scenario_example01.yaml").is_valid()


def test_scenario_example02_syntax():
    assert ScenarioReader("tests/scenario_example02.yaml").is_valid()


def test_scenario_example03_syntax():
    assert ScenarioReader("tests/scenario_example03.yaml").is_valid()


def test_scenario_example04_syntax():
    assert ScenarioReader("tests/scenario_example04.yaml").is_valid()


def test_scenario_example05_syntax():
    assert ScenarioReader("tests/scenario_example05.yaml").is_valid()


def test_scenario_acceptance_demo_syntax():
    assert ScenarioReader("tests/acceptance-demo.yaml").is_valid()


def test_scenario_mks946_testing_syntax():
    assert ScenarioReader("tests/mks946-testing.yaml").is_valid()


def test_scenario_mks946_syntax():
    assert ScenarioReader("tests/mks946.yaml").is_valid()


def test_suite_example01_syntax():
    assert ScenarioReader("tests/suite_example01.yaml").is_valid()


def test_scenario_are_deserialized_in_suite():
    num_scenarios = 3
    suite = ScenarioReader("tests/suite_example01.yaml").get_deserialized()
    assert len(suite["scenarios"]) == num_scenarios


def test_bad_syntax():
    assert not ScenarioReader("tests/bad.yml").is_valid()
