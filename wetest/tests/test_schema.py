#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest
from pykwalify.core import Core


class TestReportGenerator(unittest.TestCase):
    """Module's Unit Tests."""

    def test_scenario_01(self):
        c = Core(
            source_file="wetest/tests/scenario_example01.yaml",
            schema_files=["wetest/resources/scenario_schema.yaml"],
        )
        c.validate()

    def test_scenario_02(self):
        c = Core(
            source_file="wetest/tests/scenario_example02.yaml",
            schema_files=["wetest/resources/scenario_schema.yaml"],
        )
        c.validate()

    def test_suite(self):
        c = Core(
            source_file="wetest/tests/suite_example01.yaml",
            schema_files=["wetest/resources/suite_schema.yaml"],
        )
        c.validate()
