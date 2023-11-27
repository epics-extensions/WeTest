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

import argparse
import os
import logging
import re
import sys

from wetest.common.constants import TERSE_FORMATTER, FILE_HANDLER, WeTestError


# configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(TERSE_FORMATTER)
logger.addHandler(stream_handler)
logger.addHandler(FILE_HANDLER)


class ParsingError(WeTestError):
    """Failed to parse DB file"""


def parseDbFile(filepath):
    """Parse the given EPICS DB file to extract records.

    Args:
        filepath (str): Path of the EPICS .db file

    Returns:
        found_records (lsit): list of PV as a dictionnaries

    """
    found_records = list()
    current_record = None
    with open(filepath, "r") as dbfile:
        for index, line in enumerate(dbfile):
            # make sure the line is in unicode
            line = line.decode("utf-8")
            # try:
            # except UnicodeDecodeError as e:
            #         logger.error(
            #             "Could not decode line %d, from %s, ignoring it:"
            #             % (index+1, filepath))
            #         logger.error(line)

            # ignore comment lines
            if line.strip().startswith("#"):
                continue

            # looking for new record or new field
            new_record = re.search(
                r"""record\(\s*(?P<type>\S+)\s*,\s*["'](?P<name>\S+)["']\s*\)""", line
            )
            new_field = re.search(
                r"field\(\s*(?P<name>\S+)\s*,\s*(?P<value>.+)\s*\)", line
            )

            # apparently the regex did not match
            if not new_record and line.strip().startswith("record("):
                raise ParsingError("Did not find the new record in line:\n" + line)
            if not new_field and line.strip().startswith("field("):
                raise ParsingError("Did not find the new field in line:\n" + line)

            # start a new record in content_dict
            if new_record:
                # instanciate a new record assuming previous one is finished
                current_record = dict()
                current_record["name"] = new_record.group("name")
                current_record["type"] = new_record.group("type")
                # add to record list
                found_records.append(current_record)

            # add field to the current record
            if new_field:
                current_field_name = new_field.group("name")
                current_field_value = new_field.group("value")
                if current_record is None:
                    logger.error(
                        "Field without record line %d in %s", index + 1, filepath
                    )
                    raise ParsingError("Found a field but did not start a record yet.")
                if current_field_name in current_record:
                    logger.warning(
                        "Field redefined in same record line %d in %s",
                        index + 1,
                        filepath,
                    )

                current_record[current_field_name] = current_field_value

    return found_records


def dir2files(dirpath, prefix="", suffix=""):
    """
    Look for file in the given directory and subdirectories.
    If defined, only keep files starting by prefix and ending by suffix.

    Args:
        dirpath (str): Path of the EPICS .db file

    Returns:
        found_files (str): list of file path found in directory
    """
    logger.info("Looking for input files in " + dirpath)
    found_files = list()
    found_files.extend(
        [
            os.path.join(dp, f)
            for dp, dn, fn in os.walk(dirpath)
            for f in fn
            if f.endswith(suffix) and f.startswith(prefix)
        ]
    )
    return found_files


def prettyDict(input_dict, indent=0, print_function=print):
    """Prints a directory."""
    for key, value in list(input_dict.items()):
        print_function("\t" * indent + str(key) + " :\t" + str(value))


def pvs_from_path(path_list):
    pvs_from_db = []
    db_files = []
    logger.info("Searching for DB files.")
    for path in path_list:
        if os.path.isfile(path):
            db_files.append(path)
        elif os.path.isdir(path):
            db_files.extend(dir2files(dirpath=path, suffix=".db"))
        else:  # bad path given
            logger.error("Unable to explore: %s", path)

    if not db_files:
        logger.error("No DB file found with provided paths.")

    logger.debug("DB files found:\n" + "\n".join(db_files))

    logger.info("Extracting PVs from DB files.")
    for a_file in db_files:
        logger.info("Processing file " + a_file)
        pvs_from_db += parseDbFile(a_file)

    logger.info("Number of records found: %d" % len(pvs_from_db))

    return pvs_from_db
