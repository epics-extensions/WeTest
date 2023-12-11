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

"""Read tests in YAML file."""

# TODO(gohierf): command option to choose to stop if the scenario or the facultative
# check are not validated (aka safe run)
# TODO(gohierf): margin should only be used with numbers

import contextlib
import importlib.metadata
import logging
import os
import re
import sys

import yaml
from pkg_resources import resource_filename
from pykwalify import errors
from pykwalify.core import Core
from semver import Version

from wetest.common.constants import (
    FILE_HANDLER,
    LVL_FORMAT_VAL,
    TERSE_FORMATTER,
    WeTestError,
)

# configure logging
logging.getLogger("pykwalify").setLevel(
    logging.CRITICAL,
)  # otherwise we get a No handler exception
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(TERSE_FORMATTER)
logger.addHandler(stream_handler)
logger.addHandler(FILE_HANDLER)

## logger to share file validation
fv_logger = logging.getLogger("_wetest_format_validation")
fv_logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(TERSE_FORMATTER)
stream_handler.setLevel(LVL_FORMAT_VAL)
fv_logger.addHandler(stream_handler)
fv_logger.addHandler(FILE_HANDLER)

WETEST_METADATA = importlib.metadata.metadata("WeTest")

# Maximum file version supported
VERSION = Version.parse(importlib.metadata.version("WeTest"))

REPOSITORY = WETEST_METADATA["Home-page"]

# Constants used elsewhere
ABORT = "abort"
PAUSE = "pause"
CONTINUE = "continue"


class FileNotFound(WeTestError):
    """Unable to find file corresponding to provided path."""


class UnsupportedFileFormatError(WeTestError):
    """Bad YAML file format exception.

    Exception raised if YAML configuration file format version is newer than
    supported one.
    """

    def __init__(self, version):
        super().__init__(
            f"Scenario version '{version}' not supported. "
            f"Current WeTest version: '{VERSION}'.\n"
            f"Look at the WeTest repository for the CHANGELOG:\n{REPOSITORY}"
        )


class InvalidFileContentError(WeTestError):
    """Somethings not right in YAML file.

    Exception raised if post-schema YAML validation is not passed.
    """


class MacroError(WeTestError):
    """Something went wrong when parsing the macros."""


class MacrosManager:
    """A class to keep track of known, used and unknown variable.

    You should use the same manager if you want to keep updating the same
    known_macros, used_macros and unknown_macros.
    Giving these mutable to the constructor will not update them.
    """

    def __init__(
        self,
        known_macros=None,
        used_macros=None,
        unknown_macros=None,
    ) -> None:
        self.known_macros = {}
        self.used_macros = set()
        self.unknown_macros = {}

        self._trace_unknown = True
        self.read_errors = []

        if known_macros is not None:
            self.known_macros.update(known_macros)
        if used_macros is not None:
            self.used_macros.update(used_macros)
        if unknown_macros is not None:
            self.unknown_macros.update(unknown_macros)

    def __str__(self) -> str:
        output = "MacrosManager:"
        output += "\nknown macros:\n" + str(sorted(self.known_macros))
        output += "\nused macros:\n" + str(sorted(self.used_macros))
        output += "\nunknown macros:\n" + str(sorted(self.unknown_macros))
        return output

    def deep_copy(self):
        """Return an independent copy of this instance."""
        return MacrosManager(
            known_macros=self.known_macros,
            used_macros=self.used_macros,
            unknown_macros=self.unknown_macros,
        )

    def mark_as_used(self, macros):
        """Complete used_macros with the provided list."""
        if isinstance(macros, str):
            macros = [macros]
        self.used_macros.update(macros)

    def add_new_macros(self, new_macros, priority_to_known=True):
        """Add new known macros to the manager.

        Provided new_macros is a dict or a list of dict that are to be used as macros.

        priority_to_known: is boolean stating whether knwon macros should be updated or kept
        """
        if isinstance(new_macros, list):
            for x in new_macros:
                self.add_new_macros(x, priority_to_known)
        elif isinstance(new_macros, dict):
            for k, v in list(new_macros.items()):
                if str(k) in self.known_macros and priority_to_known:
                    pass
                else:
                    self.known_macros[str(k)] = self.substitute_macros(
                        v,
                        trace_unknown=False,
                    )
        else:
            msg = "Input can not be read as a macro: %s"
            raise MacroError(msg, new_macros)

    def substitute_macros(self, a_value, trace_unknown=True):
        """Return the substituted value using known_macros, and update used_macros and unknown_macros.

        a_value: if value is a string then tries to substitute macros in it

        returns the same value if no macros was found in it
        returns an appropriately typed value (not necessarily a string)
        if macros have been substituted in it
        """
        # recurse for lists and dictionaries
        if isinstance(a_value, list):
            return [self.substitute_macros(x, trace_unknown) for x in a_value]
        if isinstance(a_value, dict):
            output = {}
            for k, v in list(a_value.items()):
                output[k] = self.substitute_macros(v, trace_unknown=trace_unknown)
            return output

        # return same value if not a string
        if not isinstance(a_value, str):
            return a_value

        # old regex was r"(\${.*?}|\$\(.*?\))" it was non greedy but incompatible with imbricated macros
        # new is non geedy because forbiding '${}()' characters in the macro name
        # and works with imbricated macros
        self._trace_unknown = trace_unknown
        new_str, nb_sub = re.subn(
            r"\$[({]{1}[^${}()]*[)}]{1}",
            self.corresponding_macro,
            a_value,
        )
        self._trace_unknown = True

        # try to type the returned value (boolean, int, float, dict, list... instead of a string)
        # but only if we did a substitution, otherwise give it back as it is
        if nb_sub == 0:
            return a_value

        logger.debug("substitute found: `%s`", new_str)
        # fallback value
        output = new_str

        # we can use yaml load to convert a string into a list, a dict, or a boolean
        # however if a string ends with a colon it will be considered as a
        # dict by yaml load, but we want to keep it a string
        if not new_str.endswith(":"):
            try:
                output = yaml.safe_load(new_str)
            except (ValueError, yaml.scanner.ScannerError) as e:
                # we get a ScannerError when substituting with a macro that
                # ends by a colon, in a multiline string:
                # "mapping values are not allowed here"
                logger.debug(e)
                logger.debug("in: %s\n", new_str)

        # however we can not rely on yaml load to parse an int or a float
        # especially for exponential notation or infinity or NAN
        # they might endup being read as string
        if isinstance(output, str):
            # go back to raw new_str if yaml.safe_load returned a string,
            # in order to maintain linebreaks
            output = new_str

            # is it a float ?
            with contextlib.suppress(ValueError):
                output = float(new_str)

            # or even better is it an integer ?
            with contextlib.suppress(ValueError):
                output = int(new_str)

        logger.debug("cast into %s (%s)", output, type(output))

        # call substitute macro again on the result if it changed
        # in order to substitute imbricated macros
        if isinstance(output, str) and output != a_value:
            try:
                return self.substitute_macros(new_str, trace_unknown=trace_unknown)
            except RuntimeError:
                self.read_errors.append(
                    "- Recusivity issue with macros:\n%s" % output,
                )

        return output

    def corresponding_macro(self, match):
        """Return the string to substitute for regex match.

        :param match: substring match
        :returns: replacement string
        """
        # extract the match
        match = match.group(0)

        repl = match  # default return

        macro_match = re.match(r"\$[({]\s*(?P<macro_name>\S+)\s*[)}]", match)

        if not macro_match:  # Cannot workout the macro name
            logger.debug("invalid macro syntax: %s", match)

        else:  # the macro is valid
            macro_name = macro_match.group("macro_name")

            if macro_name not in self.known_macros:  # the macro is not defined
                logger.debug("unknown macro: %s", match)
                if self._trace_unknown:
                    if macro_name in self.unknown_macros:
                        self.unknown_macros[macro_name] += 1
                    else:
                        self.unknown_macros[macro_name] = 1

            else:  # the macro is defined
                repl = self.known_macros[macro_name]
                self.used_macros.add(macro_name)
        return str(repl)

    def raise_errors(self):
        """Raise a MacroError exception if self.read_errors is not empty."""
        if self.read_errors:
            logger.critical("Issue when dealing with macros:")
            for error_txt in self.read_errors:
                logger.critical(error_txt)
            raise MacroError


class ScenarioReader:
    """Read WeTest YAML Scenario file.

    :param yaml_file: A YAML suite configuration file.
    :param macros_mgr: a MacrosManager of macros already defined before reading
    :param suite_macros: list of macros name defined in the suite and therefore
                        not necessarily for this scenario, should not be checked
                        when looking for unused macros
    :param propagate: a boolean, whether or not to share all macros with included files
    """

    def __init__(
        self,
        yaml_file,
        macros_mgr=None,
        suite_macros=None,
        propagate=False,
    ) -> None:
        """Initialize Reader."""
        self.file_path = os.path.abspath(yaml_file)
        try:
            self.file = open(self.file_path)
        except OSError as exc:
            raise FileNotFound from exc

        self.macros_mgr = macros_mgr if macros_mgr is not None else MacrosManager()
        self.suite_macros = suite_macros if suite_macros is not None else []
        self.propagate = propagate

        self.deserialized_scenarios = []
        self.deserialized = self._deserialize()

        self.major = self.deserialized["version"]["major"]
        self.minor = self.deserialized["version"]["minor"]
        self.bugfix = self.deserialized["version"]["bugfix"]
        self.version = f"{self.major!s}.{self.minor!s}.{self.bugfix!s}"

        self.version_is_supported = ScenarioReader.supports_version(
            int(self.major), int(self.minor), int(self.bugfix)
        )

        # Check YAML file schema and other validation
        tempo_file_path = "/tmp/no_macros.yml"
        with open(tempo_file_path, "w") as yml_wo_macros:
            yaml.dump(self.deserialized, yml_wo_macros, default_flow_style=False)
        self.file_is_valid = self._validate_file(tempo_file_path)

        self.deserialized["scenarios"] = self.deserialized_scenarios

    def _deserialize(self):
        """Deserialize the YAML file and its included scenarios.

        :returns: The deserialized file and scenarios.
        """
        logger.info("Reading file...")
        wetest_file = self._substitute_macros(yaml.safe_load(self.file))
        logger.info("Read file.")

        # initialise include, tests and config block if not defined
        if "include" not in wetest_file:
            wetest_file["include"] = []

        # initialise local test position if not defined
        if "tests" in wetest_file and "tests" not in wetest_file["include"]:
            wetest_file["include"].append("tests")

        # set default configuration
        if "config" in wetest_file:
            wetest_file["config"].setdefault("name", "Unnamed scenario.")
            wetest_file["config"].setdefault("type", "functional")
            wetest_file["config"].setdefault("prefix", "")
            wetest_file["config"].setdefault("use_prefix", True)
            wetest_file["config"].setdefault("delay", 1)
            wetest_file["config"].setdefault("ignore", False)
            wetest_file["config"].setdefault("skip", False)
            wetest_file["config"].setdefault(
                "on_failure",
                CONTINUE if wetest_file["config"]["type"] == "unit" else PAUSE,
            )
            wetest_file["config"].setdefault("retry", 0)

        # transform local tests into something similar to an imported scenario
        local_tests = {
            block: content
            for block, content in list(wetest_file.items())
            if block in ["config", "tests"]
        }

        # Read each scenario listed in wetest_file and add them to `scenarios` block
        logger.info("Reading scenario file(s)...")
        self.deserialized_scenarios = []

        for scenario in wetest_file["include"]:
            if self.propagate:
                sc_macros_mgr = self.macros_mgr.deep_copy()
            else:
                sc_macros_mgr = MacrosManager()

            logger.debug("Processing: %s", scenario)
            if isinstance(scenario, str) and scenario == "tests":
                self.deserialized_scenarios.append(local_tests)
                continue

            if isinstance(scenario, list):
                if not isinstance(scenario[0], str):
                    msg = "First item of include should be a file path."
                    raise InvalidFileContentError(
                        msg,
                    )
                scenario_path = scenario[0]
                # remains a list of one or several dicts
                sc_macros_mgr.add_new_macros(scenario[1:], priority_to_known=False)
            elif isinstance(scenario, dict):
                scenario_path = scenario["path"]
                sc_macros_mgr.mark_as_used("path")
                sc_macros_mgr.add_new_macros(scenario, priority_to_known=False)
            else:  # case with no macros
                scenario_path = scenario

            scenario_path = self.get_full_path(scenario_path)
            logger.debug("Reading: %s", scenario_path)
            logger.debug("with macros: %s", sc_macros_mgr.known_macros)

            # deserialize scenario and append
            new_sc = ScenarioReader(
                scenario_path,
                macros_mgr=sc_macros_mgr,
                suite_macros=self.macros_mgr.known_macros,
            )
            self.deserialized_scenarios += new_sc.deserialized_scenarios

            # mark macro used in scenario as used for wetest_file
            self.macros_mgr.mark_as_used(new_sc.macros_mgr.used_macros)

        logger.debug("Read scenario file(s).")

        return wetest_file

    def get_full_path(self, file_path):
        """Return the absolute path of a file.

        Trying in this order:
        1- provided file_path is already absolute
        2- provided file_path is relative to current folder
        3- provided file_path is relative to current file.

        :param file_path: absolute or relative file path.

        :returns: absolute path or raise a FileNotFoundError if nothings match.
        """
        if os.path.isfile(
            os.path.abspath(file_path),
        ):  # absolute or relative to current location
            return os.path.abspath(file_path)

        current_file_location = os.path.dirname(self.file_path)
        abs_path = os.path.abspath(os.path.join(current_file_location, file_path))

        if os.path.isfile(abs_path):
            return abs_path

        raise FileNotFound(
            "Could not find either of these files:"
            "\n- " + os.path.abspath(file_path) + "\n- " + abs_path,
        )

    def _validate_file(self, file_path=None):
        """Check if YAML file format is valid. Check if all found macro was defined.

        :param file_path: Specify the path of the file to check (should be
                          useful for testing only).

        :returns: a boolean on whether it succeeded or not.
        """
        file_path = file_path or self.file_path
        # we actually validate file_path and not self.filepath,
        # but self.file_path holds more useful information to display
        fv_logger.log(
            LVL_FORMAT_VAL,
            "Validation of YAML scenario file: %s",
            self.file_path,
        )

        schema_path = resource_filename("wetest", "resources/scenario_schema.yaml")
        config = Core(source_file=file_path, schema_files=[schema_path])

        return self.validate_file(config)

    def mandatory_validation(self):
        """Additional tests not possible through schema.

        Note: Only check tests that are not skipped.

        Check the following rules:
         - `config` block requires a `tests` block
         - `tests` block requires a `tests` block
         - `on_failure` field must have a known value
         - a `name` must be set in `config`
         - fields in `config` block must be of correct type

        Return a list of trace when these rules are not respected.
        """
        errors = []

        if "config" in self.deserialized and "tests" not in self.deserialized:
            errors.append("""`config` found but no `tests`""")

        if "tests" in self.deserialized and "config" not in self.deserialized:
            errors.append("""`tests` found but no `config`""")

        for test in self.deserialized.get("tests", []):
            # ignore skipped tests
            if "skip" in test and test["skip"]:
                continue

            if "on_failure" in test and test["on_failure"] not in [
                "continue",
                "pause",
                "abort",
            ]:
                errors.append(
                    """'{}' requires unknown on_failure mode: {}""".format(
                        test["name"],
                        test["on_failure"],
                    ),
                )

        if "config" in self.deserialized:
            config = self.deserialized["config"]

            if "name" not in config:
                errors.append("""`name` is mandatory in `config`: %s""" % config)
            elif not isinstance(config["name"], str):
                errors.append(
                    "`name` in `config` is supposed to be a string but got: {}".format(
                        config["name"],
                    ),
                )

            if "type" in config and config["type"] not in ["unit", "functional"]:
                errors.append(
                    "`type` in `config` is supposed to be "
                    "either `unit` or `functional` but got: {}".format(config["type"]),
                )

            if "prefix" in config and not isinstance(config["prefix"], str):
                errors.append(
                    "`prefix` in `config` is supposed to be a string "
                    "but got: {}".format(config["prefix"]),
                )

            if "use_prefix" in config and not isinstance(config["use_prefix"], bool):
                errors.append(
                    "`use_prefix` in `config` is supposed to be a boolean "
                    "but got: {}".format(config["use_prefix"]),
                )

            if "delay" in config and not isinstance(config["delay"], (int, float)):
                errors.append(
                    "`delay` in `config` is supposed to be a numerical value "
                    "but got: {}".format(config["delay"]),
                )

            if "ignore" in config and not isinstance(config["ignore"], bool):
                errors.append(
                    "`ignore` in `config` is supposed to be a boolean but got: {}".format(
                        config["ignore"],
                    ),
                )

            if "skip" in config and not isinstance(config["skip"], bool):
                errors.append(
                    "`skip` in `config` is supposed to be a boolean but got: {}".format(
                        config["skip"],
                    ),
                )

            if "on_failure" in config and config["on_failure"] not in [
                "continue",
                "pause",
                "abort",
            ]:
                errors.append(
                    "`on_failure` in `config` is supposed to be "
                    "either `continue`, `pause` or `functional` but got: {}".format(
                        config["on_failure"],
                    ),
                )

            if "retry" in config and not isinstance(config["retry"], int):
                errors.append(
                    "`retry` in `config` is supposed to be an integer "
                    "but got: {}".format(config["retry"]),
                )

        return errors

    def noncompulsory_validation(self):
        """Additional tests not possible through schema.

        Note: Only check tests that are not skipped.

        Check the following rules:
         - a test can be only of one kind (range, values and commands should be exclusive)
         - a test should have at least one kind (range, values or commands)
         - range and values tests require a setter or a getter field
         - in commands value is not compatible with set_value or get_value
         - a commands expects at least a value or a set_value or a get_value
         - all macros should have been used at least once
         - all macros should have been replaced

        Return a list of trace when these rules are not respected.
        """
        errors = []

        for test in self.deserialized.get("tests", []):
            # ignore skipped tests
            if "skip" in test and test["skip"]:
                continue

            # get test kind(s)
            kinds = ["range", "commands", "values"]
            test_kind = [kind for kind in kinds if kind in test]

            # a test should have at least one kind (range, values or commands)
            if len(test_kind) == 0:
                errors.append(
                    """'{}' should have a at least one of {}""".format(
                        test["name"],
                        ", ".join(kinds),
                    ),
                )

            # a test can be only of one kind (range, values and commands should be exclusive)
            if len(test_kind) > 1:
                errors.append(
                    """'%s' should have a uniq kind but has %d (%s)"""
                    % (test["name"], len(test_kind), test_kind),
                )

            # range and values tests require a setter or a getter field
            if (
                ("range" in test_kind or "values" in test_kind)
                and "setter" not in test
                and "getter" not in test
            ):
                errors.append(
                    """'{}' is of kind '{}' but has no setter or getter""".format(
                        test["name"],
                        test_kind[0],
                    ),
                )

            # in commands value is not compatible with set_value or get_value
            # a commands expects at least a value or a set_value or a get_value
            if "commands" in test_kind:
                for cmd in test["commands"]:
                    if "value" in cmd and "set_value" in cmd:
                        errors.append(
                            "'{}'>'{}' should not have a 'value' and a 'set_value'".format(
                                test["name"],
                                cmd["name"],
                            ),
                        )
                    if "value" in cmd and "get_value" in cmd:
                        errors.append(
                            "'{}'>'{}' should not have a 'value' and a 'get_value'".format(
                                test["name"],
                                cmd["name"],
                            ),
                        )
                    if not ("value" in cmd or "get_value" in cmd or "set_value" in cmd):
                        errors.append(
                            "'{}'>'{}' should have one of 'value', 'set_value' or 'get_value'".format(
                                test["name"],
                                cmd["name"],
                            ),
                        )

        # all macros should have been used at least once
        for k, v in list(self.macros_mgr.known_macros.items()):
            if k not in self.macros_mgr.used_macros and k not in self.suite_macros:
                errors.append(f"""Unused macro "{k}": {v}""")

        # all macros should have been replaced
        for k, v in list(self.macros_mgr.unknown_macros.items()):
            errors.append(
                """Unknown macro "%s" (%d occurrence%s)"""
                % (k, v, "" if v == 1 else "s"),
            )

        return errors

    @staticmethod
    def supports_version(major: int, minor: int, bugfix: int) -> bool:
        """Check if configuration file format version is supported.

        :param major:  major version
        :param minor:  minor version
        :param bugfix: patch version

        :returns: True if version is supported,
        otherwise raises an UnsupportedFileFormatError

        """
        file_version = Version(major, minor, bugfix)

        logger.debug("scenario file version is: %s", file_version)

        if not file_version.is_compatible(VERSION):
            raise UnsupportedFileFormatError(file_version)

        if file_version.minor < VERSION.minor:
            logger.warning(
                "A new file version is available: '%s'. "
                "Current scenario file version: '%s'",
                VERSION,
                file_version,
            )
            logger.warning(
                "Look at the WeTest repository for the CHANGELOG:\n%s", REPOSITORY
            )
        return True

    def is_valid(self):
        """YAML file format is valid.

        :returns: a boolean on whether it is valid or not.
        """
        return self.file_is_valid

    def is_supported(self):
        """YAML file format version is supported.

        :returns: a boolean on whether it is supported or not.
        """
        return self.version_is_supported

    def get_deserialized(self):
        """Get the deserialized object.

        :returns: the deserialized object.
        """
        return self.deserialized

    def _substitute_macros(self, deserialized):
        """Update the deserialized dictionary with macros values.

        :param deserialized: yaml file content as a dict.
        :returns: The deserialized file.
        """
        # check for new macros
        if "macros" in deserialized:
            self.macros_mgr.add_new_macros(deserialized["macros"])

        deserialized = self.macros_mgr.substitute_macros(
            {k: v for k, v in list(deserialized.items()) if k != "macros"},
        )

        self.macros_mgr.raise_errors()

        return deserialized

    def validate_file(self: "ScenarioReader", config: Core) -> bool:
        """Run the schema, non-compulsory and compylsory validation.

        if compulsory validation fails, terminate the program with error code 1.

        :param config: an instance of pkwalify.core.Core

        :returns: wrether or not all the validation succeeded.
        """
        fv_logger.info("Validating input file against schema.")
        try:
            config.validate()
            schema_valid = True
        except errors.SchemaError as err:
            fv_logger.log(LVL_FORMAT_VAL, "%s", err.msg)
            schema_valid = False

        ncmp_valid = self.noncompulsory_validation()
        if len(ncmp_valid) != 0:
            fv_logger.log(LVL_FORMAT_VAL, "Non-compulsory validation failed:")
            fv_logger.log(LVL_FORMAT_VAL, " - %s", "\n - ".join(ncmp_valid))
        else:
            fv_logger.info("Validated non compulsory rules.")

        mand_valid = self.mandatory_validation()
        if len(mand_valid) != 0:
            fv_logger.log(LVL_FORMAT_VAL, "Mandatory validation failed:")
            fv_logger.log(LVL_FORMAT_VAL, " - %s", "\n - ".join(mand_valid))
            sys.exit(1)
        else:
            fv_logger.info("Validated mandatory rules.")

        return schema_valid and ncmp_valid == [] and mand_valid == []
