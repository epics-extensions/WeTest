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

import logging

from wetest.common.constants import FILE_HANDLER, TERSE_FORMATTER, WeTestError

# configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(TERSE_FORMATTER)
logger.addHandler(stream_handler)
logger.addHandler(FILE_HANDLER)


class NamingError(WeTestError):
    """Exception raise when a PV does not fit the naming."""

    def __init__(self, message=None, pv_name=None, naming=None) -> None:
        msg = ""
        if pv_name is not None:
            msg += str(pv_name) + " "
        if naming is not None:
            msg += "incompatible with " + naming.name + " naming."
        if message is not None:
            msg += message
        super().__init__(msg)


def generate_naming(identifier):
    if identifier.upper() == "NONE":
        return NoNaming()
    if identifier.upper() == "SARAF":
        return SARAFNaming()
    if identifier.upper() == "ESS":
        ess_naming = SARAFNaming
        ess_naming.name = "ESS"
        return ess_naming()
    if identifier.upper() == "RDS-81346":
        return RDS81346Naming()

    raise NotImplementedError


class Naming:
    def __init__(self, name="Abstract Naming") -> None:
        self.name = name

    def sort(self, pv_name):
        """Key function for sorting.

        This function should not raise exception.
        """
        raise NotImplementedError("%s has no sort method" % self.name)

    def split(self, pv_name):
        """Return the PV name decomposed into a list.

        For instance:
            Sec-Subx:Dis-Dev-Idx:Signal
        is returned as:
            [Sec, Subx, Dis, Dev-Idx, Signal]
        This decomposition can then be used to display PV names as a tree form.

        It should raise NamingError exception in case of error.
        """
        raise NotImplementedError("%s has no split method" % self.name)

    def ssplit(self, pv_name):
        """Return the PV name decomposed into a short list.

        For instance:
            Sec-Subx:Dis-Dev-Idx:Signal
        is returned as:
            [Sec-Subx, Dis-Dev-Idx, Signal]
        This decomposition can then be used to display PV names as a tree form.

        It should raise NamingError exception in case of error.
        """
        raise NotImplementedError("%s has no ssplit method" % self.name)


class NoNaming(Naming):
    """Default naming, sort by alphabetical order.

    Distance is always 0.
    """

    def __init__(self) -> None:
        Naming.__init__(self, "Undefined")

    def sort(self, pv_name):
        return self.split(pv_name)

    def split(self, pv_name):
        return [pv_name]

    def ssplit(self, pv_name):
        return [pv_name]


class SARAFNaming(Naming):
    """Naming from the SARAF project.

    Expecting PV name following:
    Sec-Sub(x):Dis-Dev-Idx:Signal.FIELD
    Basing sort on alphabetical order for each ":" and "-" separated section.
    Determining distance based on ":" separated section.
    """

    def __init__(self) -> None:
        Naming.__init__(self, "SARAF")

    def sort(self, pv_name):
        return str(pv_name).split(":")

    def split(self, pv_name):
        # try:
        #     sec_sub, dis_dev_idx, signal = pv_name.split(":")
        #     sec, sub =  sec_sub.rsplit("-",1)
        #     dis, dev = dis_dev_idx.split("-",1)
        #     # return [sec, "-", sub, ":", dis, "-", dev, ":", signal]
        #     return [sec, sub, dis, dev, signal]
        # except ValueError:
        #     raise NamingError(pv_name=pv_name, naming=self)
        return self.ssplit(pv_name)

    def ssplit(self, pv_name):
        try:
            sec_sub, dis_dev_idx, signal = pv_name.split(":")
        except ValueError as exc:
            raise NamingError(pv_name=pv_name, naming=self) from exc
        else:
            return [sec_sub, dis_dev_idx, signal]


class RDS81346Naming(Naming):
    """Expecting PV name following:
    A1-B1-C1-D1:EpicsPart
    Basing sort on alphabetical order for each ":" and "-" separated section.
    Determining distance based most common of  pre ":" part.
    """

    def __init__(self) -> None:
        Naming.__init__(self, "RDS-81346")

    def sort(self, pv_name):
        return str(pv_name).split(":")

    def split(self, pv_name):
        try:
            device_name, epics_name = pv_name.split(":")
            decomp = device_name.split("-")
            sections = []
            prepend = None
            for sec in decomp:
                if sec == "":
                    continue

                if sec == "SL":
                    prepend = "SL-"
                elif prepend is not None:
                    sections.append(prepend + sec)
                    prepend = None
                else:
                    sections.append(sec)

            sections.append(epics_name)
        except ValueError as exc:
            raise NamingError(pv_name=pv_name, naming=self) from exc
        else:
            return sections

    def ssplit(self, pv_name):
        return self.split(pv_name)
