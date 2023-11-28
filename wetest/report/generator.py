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

"""Create a PDF report from testing results."""

import datetime
import logging
import re

from pkg_resources import resource_filename
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Table, TableStyle

from wetest.common.constants import FILE_HANDLER, VERBOSE_FORMATTER
from wetest.pvs.core import pvs_from_suite
from wetest.pvs.naming import NamingError

# configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(VERBOSE_FORMATTER)
logger.addHandler(stream_handler)
logger.addHandler(FILE_HANDLER)
INCH = 72


def get_para_with_style(
    text="",
    bold=False,
    italic=False,
    style="BodyText",
    align="left",
    color=None,
):
    """Get an initialized Paragraph object.

    :param text: The text to be rendered.
    :param bold: A boolean on whether the text must be bold or not.
    :param style: The text style (from SampleStyleSheet object).
    :param align: The text alignment.

    :returns: An Initialized Paragraph.

    Note:
    ----
    SampleStyleSheet available styles:
        'BodyText', 'Title', 'Italic', 'Normal', 'Code', 'Definition',
        'Heading1', 'Heading2', 'Heading3', 'Heading4', 'Heading5', 'Heading6'
        'Bullet', 'OrderedList', 'UnorderedList,

    See Also:
    --------
        - https://www.reportlab.com/documentation/
        - https://www.reportlab.com/docs/reportlab-userguide.pdf
    """
    if text is None:
        return None

    paragraph_style = getSampleStyleSheet()[style]

    # get starting and ending spaces
    lspaces = len(text) - len(text.lstrip(" "))
    lspaces += (len(text) - len(text.lstrip("\t"))) * 10
    rspaces = len(text) - len(text.rstrip(" "))
    rspaces += (len(text) - len(text.rstrip("\t"))) * 10
    paragraph_style.leftIndent += lspaces
    paragraph_style.rightIndent += rspaces

    header = f"<para align={align} spaceb=3>"
    footer = "</para>"
    body = text.replace("\n", "<br/>\n")

    if bold:
        body = f"<b>{body}</b>"

    if italic:
        body = f"<i>{body}</i>"

    if color:
        body = f"<font color={color}>{body}</font>"

    html = header + body + footer

    return Paragraph(html, paragraph_style)


class _TestInfo:
    """Combine information about tests success status."""

    def __init__(self, test_suite, test_results) -> None:
        """Initialize _TestInfo.

        :param test_suite:   The ran TestSuite.
        :param test_results: The TestResults object.
        """
        logger.debug("init _TestInfo object")

        logger.debug("test_suite: %s", test_suite)
        self.test_suite = test_suite
        logger.debug("test_results: %s", test_results)
        self.test_results = test_results

        self.combined = []

        for test in self.test_suite:
            short_id = test.id().split(".")[-1]
            logger.debug("test with id %s in test_suite", test.id())
            success = True
            for result, trace in self.test_results.failures:
                logger.debug("test with id %s in test_results", result.id())
                logger.debug("test trace: %s", trace)
                if test.id() == result.id():
                    self._append_to_combined(
                        test,
                        "Failure",
                        "red",
                        trace,
                        infos=test_suite.tests_infos[short_id],
                    )
                    success = False

            for result, trace in self.test_results.errors:
                logger.debug("test with id %s in test_results", result.id())
                logger.debug("test trace: %s", trace)
                if test.id() == result.id():
                    self._append_to_combined(
                        test,
                        "Error",
                        "orange",
                        trace,
                        infos=test_suite.tests_infos[short_id],
                    )
                    success = False

            for result, trace in self.test_results.skipped:
                logger.debug("test with id %s in test_results", result.id())
                logger.debug("test trace: %s", trace)
                if test.id() == result.id():
                    self._append_to_combined(
                        test,
                        "Skipped",
                        "grey",
                        infos=test_suite.tests_infos[short_id],
                    )
                    success = False

            if success:
                self._append_to_combined(
                    test,
                    "Success",
                    "green",
                    infos=test_suite.tests_infos[short_id],
                )

        # # Reorder results by their execution order
        # self.combined = sorted(self.combined, key=lambda k: k['id'])
        # iterating through suite now returns the tests in execution order

    def _append_to_combined(self, test, status, color, trace=None, infos=None):
        """Append test information to combined test list.

        :param test:   The test function.
        :param status: A string describing the result status.
        :param color:  The text color.
        :param trace:  In case of failure, the stacktrace.
        :param infos:  A dictionary of original test attributes.
        """
        logger.debug("test info: %s#####################", infos)

        self.combined.append(
            {
                "id": test.id(),
                "result": status,
                "trace": shorten_trace(trace),
                "color": color,
                "infos": infos,
            },
        )


class ReportGenerator:
    """Generates a PDF report from test unit results."""

    def __init__(
        self,
        test_suite,
        test_results,
        filename,
        scenario_data,
        naming,
    ) -> None:
        """Initialize ReportGenerator.

        :param test_suite:   The ran TestSuite.
        :param test_results: The tests results.
        :param filename:     The PDF filename.
        :param scenario_data:        The suite and scenarios config from yaml file.
        """
        self.test_suite = test_suite
        self.test_results = test_results
        self.filename = filename
        self.scenario_data = scenario_data
        self.naming = naming

        self.pvs_infos = pvs_from_suite(self.test_suite)
        self.test_info = _TestInfo(self.test_suite, self.test_results)

    def _parse_id(self, test_id):
        """Return a scn_nb and test_nb from the id string."""
        pattern = r"test-(?P<scn_nb>\d+)-(?P<test_nb>\d+)-\d+"

        match = re.search(pattern, test_id)
        if match is not None:
            scn_nb = int(match.group("scn_nb"))
            test_nb = int(match.group("test_nb"))
        else:
            scn_nb = 0
            test_nb = 0

        return scn_nb, test_nb

    def save(self):
        """Save the report as a PDF file."""
        now = datetime.datetime.now()

        # Setup document:
        doc = SimpleDocTemplate(self.filename, pagesize=A4)
        elements = []

        ess_logo_path = resource_filename("wetest", "resources/ess.jpg")
        irfu_logo_path = resource_filename("wetest", "resources/irfu-logo.png")
        ess_logo = Image(ess_logo_path, 2 * INCH, 1.1 * INCH)
        irfu_logo = Image(irfu_logo_path, 1 * INCH, 1.1 * INCH)
        logo_array = [[ess_logo, irfu_logo]]
        logo_table = Table(logo_array)

        title = get_para_with_style(
            self.scenario_data[0]["name"],
            bold=True,
            style="Title",
            align="center",
        )

        date = get_para_with_style(
            str(now.year)
            + "-"
            + str(now.month).zfill(2)
            + "-"
            + str(now.day).zfill(2)
            + " "
            + str(now.hour).zfill(2)
            + ":"
            + str(now.minute).zfill(2),
            bold=True,
            align="center",
        )

        # PVs table
        pv_array = [
            [
                get_para_with_style("Tested PVs", bold=True, align="left"),
                get_para_with_style("as setter", bold=True, align="center"),
                get_para_with_style("as getter", bold=True, align="center"),
            ],
        ]

        # work out column width
        sec_max_length = [1]
        for pv in list(self.pvs_infos.values()):
            try:
                new_sec_length = [len(x) for x in self.naming.split(pv.name)[:-1]]
            except NamingError:
                continue
            sec_max_length = max(sec_max_length, new_sec_length)

        nbr_sec = len(sec_max_length)

        prev_sections = [None] * nbr_sec
        for pv_key in sorted(self.pvs_infos, key=self.naming.sort):
            pv = self.pvs_infos[pv_key]

            # show sections when new
            new_section = None
            try:
                sections = self.naming.ssplit(pv.name)[:-1]
            except NamingError:
                sections = ["name incompatible with %s naming" % self.naming.name]
            sections += [None] * (nbr_sec - len(sections))
            for idx, sec in enumerate(sections):
                if sec != prev_sections[idx]:
                    if new_section is None:
                        new_section = idx

                    section_txt = "{}{}".format("\t\t" * idx, sec)

                    prev_sections[idx] = sec
                    prev_sections[idx + 1 :] = [None] * (nbr_sec - idx - 1)

                    pv_array.append(
                        [
                            get_para_with_style(section_txt, align="left", bold=True),
                            "",
                            "",
                        ],
                    )

            # show pv name
            pv_name = pv.name if pv.tested else "[" + pv.name + "]"

            # show test count
            setter_str = "-"
            getter_str = "-"
            if len(pv.setter_subtests) > 0:
                setter_str = str(len(pv.setter_subtests))
            if len(pv.getter_subtests) > 0:
                getter_str = str(len(pv.getter_subtests))

            pv_array.append(
                [
                    get_para_with_style(pv_name, align="left"),
                    get_para_with_style(setter_str, align="center"),
                    get_para_with_style(getter_str, align="center"),
                ],
            )

        # Create main table
        array = [
            [
                get_para_with_style("Test", bold=True, align="center"),
                get_para_with_style("Description", bold=True, align="center"),
                get_para_with_style("Result", bold=True, align="center"),
            ],
        ]

        # File main table with tests results
        test_count = 1
        prev_scn_nb = None
        prev_test_nb = None
        for test in self.test_info.combined:
            scn_nb, test_nb = self._parse_id(test["id"])

            # check for scenario change (then add scenario title in case of suite)
            if prev_scn_nb != scn_nb and len(self.scenario_data) > 1:
                prev_scn_nb = scn_nb
                scn_title = (
                    self.scenario_data[scn_nb + 1]["name"]
                    if len(self.scenario_data) >= scn_nb + 2
                    else ""
                )
                array.append(
                    ["", get_para_with_style(scn_title, style="h2", bold=True), ""],
                )

            # check for test change (then print test title and message)
            if prev_test_nb != test_nb:
                prev_test_nb = test_nb
                if test["infos"].test_message is None:
                    array.append(
                        [
                            "",
                            get_para_with_style(test["infos"].test_title, bold=True),
                            "",
                        ],
                    )
                else:
                    array.append(
                        [
                            "",
                            [
                                get_para_with_style(
                                    test["infos"].test_title,
                                    bold=True,
                                ),
                                get_para_with_style(
                                    test["infos"].test_message,
                                    style="Definition",
                                    italic=True,
                                ),
                            ],
                            "",
                        ],
                    )

            # Add message and trace if provided
            middle_cell = [
                get_para_with_style(
                    test["infos"].test_title + ": " + test["infos"].subtest_title,
                ),
            ]
            if test["infos"].subtest_message is not None:
                middle_cell.append(
                    get_para_with_style(
                        test["infos"].subtest_message,
                        style="Definition",
                        italic=True,
                    ),
                )
            if test["trace"] is not None:
                middle_cell.append(
                    get_para_with_style(
                        test["trace"],
                        align="left",
                        color=test["color"],
                        style="Italic",
                    ),
                )

            array.append(
                [
                    get_para_with_style(str(test_count), align="center"),
                    middle_cell,
                    get_para_with_style(
                        test["result"],
                        align="center",
                        color=test["color"],
                    ),
                ],
            )

            test_count = test_count + 1

        logger.debug("Array:")
        logger.debug(array)

        list_style = TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 2, colors.black),
                ("LINEABOVE", (0, 1), (-1, -1), 0.25, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 2, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "LEFT"),
            ],
        )

        pv_table = Table(
            pv_array,
            style=list_style,
            splitByRow=True,
            colWidths=[295, 70, 70],
            spaceBefore=50,
        )

        table = Table(
            array,
            style=list_style,
            splitByRow=True,
            colWidths=[35, 350, 50],
            spaceBefore=50,
        )

        # Fill document:
        elements.append(logo_table)
        elements.append(title)
        elements.append(date)
        elements.append(pv_table)
        elements.append(table)

        # Build and save document:
        doc.build(elements)


def shorten_trace(trace):
    """Reduce trace text for specific expected exceptions.

    Expected exceptions are:
    - AssertionError
    - InconsistentTestError
    - EmptyTest exceptions
    """
    if trace is None:
        return None

    failed_test = trace.find("AssertionError: ")
    inconsistent_test = trace.find("InconsistentTestError: ")
    empty_test = trace.find("EmptyTest: ")

    if failed_test != -1:
        return trace[failed_test + 16 :]
    if inconsistent_test != -1:
        return trace[inconsistent_test:]
    if empty_test != -1:
        return trace[empty_test:]

    return trace
