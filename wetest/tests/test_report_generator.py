#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test report.generator module."""

import unittest

from wetest.report.generator import ReportGenerator
import wetest.command_line


class TestReportGenerator(unittest.TestCase):
    """Module's Unit Tests."""

    def test_generates_report_without_error(self):
        """Check a report can be generated."""
        suite, _ = wetest.command_line.new_suite_from(
            scenario_file="wetest/tests/acceptance-demo.yaml", skip_all=True
        )
        _, results, _ = wetest.command_line.Runner(suite).run()
        ReportGenerator(
            suite, results, ".test-report.pdf", title="ReportGenerator Test"
        ).save()
        # os.remove('.test-report.pdf')

    def test_generates_another_report_without_error(self):
        """Check a report can be generated with many commands."""
        suite, _ = wetest.command_line.new_suite_from(
            scenario_file="wetest/tests/source-at-0-reference.yml", skip_all=True
        )
        _, results, _ = wetest.command_line.Runner(suite).run()
        ReportGenerator(
            suite,
            results,
            ".test-report2.pdf",
            title="ReportGenerator Test with many commands",
        ).save()
        # os.remove('.test-report2.pdf')

    def test_generates_unit_testing_report_without_error(self):
        """Check a report can be generated with many commands."""
        suite, _ = wetest.command_line.new_suite_from(
            scenario_file="wetest/tests/mks946.yaml", skip_all=True
        )
        _, results, _ = wetest.command_line.Runner(suite).run()
        ReportGenerator(
            suite,
            results,
            ".test-report3.pdf",
            title="ReportGenerator Test with many commands",
        ).save()
        # os.remove('.test-report3.pdf')
