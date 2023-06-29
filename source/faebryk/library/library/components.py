from enum import Enum, IntEnum
from functools import total_ordering
import logging

logger = logging.getLogger("local_library")

from typing import List

# Faebryk library imports
from faebryk.library.core import Component, Interface, Parameter
from faebryk.library.trait_impl.component import (
    has_symmetric_footprint_pinmap,
    has_defined_footprint_pinmap,
    has_defined_type_description,
    can_bridge_defined,
    has_defined_footprint,
)
from faebryk.library.kicad import KicadFootprint
from faebryk.library.traits.component import (
    has_type_description,
)
from faebryk.library.library.interfaces import Electrical, Power
from faebryk.library.library.parameters import Constant, Range
from faebryk.library.traits.parameter import (
    is_representable_by_single_value,
)

# Faebryk function imports
from faebryk.library.util import times, unit_map


class MOSFET(Component):
    class ChannelType(Enum):
        N_CHANNEL = 1
        P_CHANNEL = 2

    class SaturationType(Enum):
        ENHANCEMENT = 1
        DEPLETION = 2

    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls)
        self._setup_traits()
        return self

    def __init__(self, channel_type: Parameter, saturation_type: Parameter) -> None:
        super().__init__()
        self._setup_interfaces()
        self.set_channel_type(channel_type)
        self.set_saturation_type(saturation_type)

    def _setup_traits(self):
        self.add_trait(has_defined_type_description("Q"))

    def _setup_interfaces(self):
        class _IFs(Component.InterfacesCls()):
            source = Electrical()
            gate = Electrical()
            drain = Electrical()

        self.IFs = _IFs(self)
        self.add_trait(can_bridge_defined(self.IFs.source, self.IFs.drain))

    def set_channel_type(self, channel_type: Parameter):
        self.channel_type = channel_type

    def set_saturation_type(self, saturation_type: Parameter):
        self.saturation_type = saturation_type


class Diode(Component):
    def _setup_interfaces(self):
        # interfaces
        class _IFs(Component.InterfacesCls()):
            anode = Electrical()
            cathode = Electrical()

        self.IFs = _IFs(self)

    def _setup_traits(self):
        self.add_trait(can_bridge_defined(self.IFs.anode, self.IFs.cathode))

    def __init__(self):
        super().__init__()
        self._setup_interfaces()
        self._setup_traits()


class TVS(Diode):
    def set_reverse_working_voltage(self, reverse_working_voltage: Parameter):
        self.reverse_working_voltage = reverse_working_voltage

    def __init__(self, reverse_working_voltage: Parameter):
        super().__init__()
        self.set_reverse_working_voltage(reverse_working_voltage)
        self.add_trait(has_defined_type_description("D"))


class TVS_Array_Common_Anode(Component):
    """
    Array of TVS diodes with a common anode

    Anodes are connected to the same pin, and supplies N channels to protect N signals from ESD.
    """

    def set_reverse_working_voltage(self, reverse_working_voltage: Parameter):
        self.reverse_working_voltage = reverse_working_voltage

    def __init__(self, num_channels: Constant, reverse_working_voltage: Parameter):
        super().__init__()

        self.num_channels = num_channels
        self.reverse_working_voltage = reverse_working_voltage

        # setup
        self.add_trait(has_defined_type_description("D"))

        class _IFs(Component.InterfacesCls()):
            anode = Electrical()
            cathodes = times(self.num_channels.value, Electrical)

        self.IFs = _IFs(self)

        class _CMPs(Component.ComponentsCls()):
            tvs = times(
                self.num_channels.value, lambda: TVS(self.reverse_working_voltage)
            )

        self.CMPs = _CMPs(self)

        # workaround
        for tvs in self.CMPs.tvs:
            tvs.add_trait(has_symmetric_footprint_pinmap())

        # connect all anodes
        self.IFs.anode.connect_all([tvs.IFs.anode for tvs in self.CMPs.tvs])

        # connect corresponding cathode pairs
        for tvs, cathode in zip(self.CMPs.tvs, self.IFs.cathodes):
            cathode.connect(tvs.IFs.cathode)


class TVS_Array_Common_Anode_Power(Component):
    """
    TVS Diode with N channels and one power connection

    Internally the channels are connected with two diodes to ground and VDD, so that the do not exceed -0.7V and VDD+0.7V.
    There is also a TVS diode connected from ground to VDD, which prevents the transients for all channels + power.
    """

    def set_reverse_working_voltage(self, reverse_working_voltage: Parameter):
        self.reverse_working_voltage = reverse_working_voltage

    def __init__(self, num_channels: Constant, reverse_working_voltage: Parameter):
        self.num_channels = num_channels
        self.reverse_working_voltage = reverse_working_voltage

        # setup
        self.add_trait(has_defined_type_description("D"))

        class _IFs(Component.InterfacesCls()):
            power = Power()
            channels = times(self.num_channels.value, Electrical)

        self.IFs = _IFs(self)

        class _CMPs(Component.ComponentsCls()):
            tvs = TVS(self.reverse_working_voltage)
            diodes_pos = times(self.num_channels.value, Diode)
            diodes_neg = times(self.num_channels.value, Diode)

        self.CMPs = _CMPs(self)

        # workaround
        for cmp in [self.CMPs.tvs] + self.CMPs.diodes_pos + self.CMPs.diodes_neg:
            cmp.add_trait(has_symmetric_footprint_pinmap())
        for cmp in self.CMPs.diodes_pos:
            cmp.add_trait(has_symmetric_footprint_pinmap())
        for cmp in self.CMPs.diodes_neg:
            cmp.add_trait(has_symmetric_footprint_pinmap())
        self.CMPs.tvs.add_trait(has_symmetric_footprint_pinmap())

        # connect TVS
        self.CMPs.tvs.IFs.anode.connect(self.IFs.power.IFs.lv)
        self.CMPs.tvs.IFs.cathode.connect(self.IFs.power.IFs.hv)

        # connect all diodes_pos cathodes to power hv
        self.IFs.power.IFs.hv.connect_all([d.IFs.cathode for d in self.CMPs.diodes_pos])

        # connect all diodes_neg anodes to power lv
        self.IFs.power.IFs.lv.connect_all([d.IFs.anode for d in self.CMPs.diodes_neg])

        # connect all diodes_neg cathodes to diodes_pos anodes and to the channel
        for channel, diode_pos, diode_neg in zip(
            self.IFs.channels, self.CMPs.diodes_pos, self.CMPs.diodes_neg
        ):
            channel.connect_all([diode_neg.IFs.cathode, diode_pos.IFs.anode])


class Fuse(Component):
    class FuseType(Enum):
        NON_RESETTABLE = 1
        RESETTABLE = 2

    class ResponseType(Enum):
        SLOW = 1
        FAST = 2

    def set_trip_current(self, trip_current: Parameter):
        self.trip_current = trip_current

    def set_response_type(self, response_type: Parameter):
        self.response_type = response_type

    def set_fuse_type(self, fuse_type: Parameter):
        self.fuse_type = fuse_type

    def __init__(
        self, fuse_type: Parameter, response_type: Parameter, trip_current: Parameter
    ):
        super().__init__()

        self.set_fuse_type(fuse_type)
        self.set_response_type(response_type)
        self.set_trip_current(trip_current)

        # interfaces
        class _IFs(Component.InterfacesCls()):
            unnamed = times(2, Electrical)

        self.IFs = _IFs(self)

        self.add_trait(has_symmetric_footprint_pinmap())
        self.add_trait(can_bridge_defined(self.IFs.unnamed[0], self.IFs.unnamed[1]))
        self.add_trait(has_defined_type_description("F"))


class Capacitor(Component):
    class CapacitorType(Enum):
        MLCC = 1
        Electrolytic = 2

    @total_ordering
    class TemperatureCoefficient(IntEnum):
        Y5V = 1
        Z5U = 2
        X7S = 3
        X5R = 4
        X6R = 5
        X7R = 6
        X8R = 7
        C0G = 8

    @total_ordering
    class CaseSize(IntEnum):
        C01005 = 1
        C0402 = 2
        C0603 = 3
        C0805 = 4
        C1008 = 5
        C1206 = 6
        C1210 = 7
        C1806 = 8
        C1812 = 9
        C1825 = 10
        C2010 = 11
        C2512 = 12

    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls)
        self._setup_traits()
        return self

    def __init__(
        self,
        capacitance: Parameter,
        tolerance: Parameter,
        rated_voltage: Parameter,
        temperature_coefficient: Parameter,
        case_size: Parameter = Constant(2),
    ):
        super().__init__()

        self._setup_interfaces()
        self.set_capacitance(capacitance)
        self.set_rated_voltage(rated_voltage)
        self.set_temperature_coefficient(temperature_coefficient)
        self.set_tolerance(tolerance)
        self.set_case_size(case_size)

    def _setup_traits(self):
        pass

    def _setup_interfaces(self):
        class _IFs(Component.InterfacesCls()):
            unnamed = times(2, Electrical)

        self.IFs = _IFs(self)
        self.add_trait(can_bridge_defined(*self.IFs.unnamed))

    def set_capacitance(self, capacitance: Parameter):
        self.capacitance = capacitance

        if type(capacitance) is not Constant:
            return
        _capacitance: Constant = capacitance

        class _has_type_description(has_type_description.impl()):
            @staticmethod
            def get_type_description():
                capacitance = self.capacitance
                return unit_map(
                    _capacitance.value, ["µF", "mF", "F", "KF", "MF", "GF"], start="F"
                )

        self.add_trait(_has_type_description())

    def set_rated_voltage(self, rated_voltage: Parameter):
        self.rated_voltage = rated_voltage

    def set_tolerance(self, percentage: Parameter):
        """
        Set tolerance in percent

        E.g.: set_tolerance(10) results in ±10%.
        """
        self.tolerance = percentage

    def set_temperature_coefficient(self, temperature_coefficient: Parameter):
        self.temperature_coefficient = temperature_coefficient

    def set_case_size(self, case_size: Parameter):
        self.case_size = case_size

    def set_auto_case_size(self):
        if type(self.capacitance) is Constant:
            capacitance = self.capacitance.value
        elif type(self.capacitance) is Range:
            capacitance = self.capacitance.max
        else:
            raise NotImplementedError

        if capacitance < 1e-6:
            self.case_size = self.CaseSize.C0402
        elif capacitance < 10e-6:
            self.case_size = self.CaseSize.C0603
        elif capacitance < 100e-6:
            self.case_size = self.CaseSize.C0805
        else:
            self.case_size = self.CaseSize.C1206


class Resistor(Component):
    class CaseSize(IntEnum):
        R01005 = 1
        R0402 = 2
        R0603 = 3
        R0805 = 4
        R1008 = 5
        R1206 = 6
        R1210 = 7
        R1806 = 8
        R1812 = 9
        R1825 = 10
        R2010 = 11
        R2512 = 12

    def _setup_traits(self):
        pass

    def _setup_interfaces(self):
        class _IFs(Component.InterfacesCls()):
            unnamed = times(2, Electrical)

        self.IFs = _IFs(self)

        self.add_trait(can_bridge_defined(*self.IFs.unnamed))

    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls)
        self._setup_traits()
        return self

    def __init__(
        self,
        resistance: Parameter,
        tolerance: Parameter = Constant(1),
        case_size: Parameter = Constant(2),
    ):
        super().__init__()

        self._setup_interfaces()
        self.set_resistance(resistance)
        self.set_tolerance(tolerance)

    def set_tolerance(self, tolerance: Parameter):
        self.tolerance = tolerance

    def set_resistance(self, resistance: Parameter):
        self.resistance = resistance

        if type(resistance) is not Constant:
            # TODO this is a bit ugly
            # it might be that there was another more abstract valid trait
            # but this challenges the whole trait overriding mechanism
            # might have to make a trait stack thats popped or so
            self.del_trait(has_type_description)
            return

        class _has_type_description(has_type_description.impl()):
            @staticmethod
            def get_type_description():
                assert isinstance(self.resistance, Constant)
                resistance: Constant = self.resistance
                return unit_map(
                    resistance.value, ["µΩ", "mΩ", "Ω", "KΩ", "MΩ", "GΩ"], start="Ω"
                )

        self.add_trait(_has_type_description())

    def set_case_size(self, case_size: Parameter):
        self.case_size = case_size


class Faebryk_Logo(Component):
    def __init__(self) -> None:
        super().__init__()

        self.add_trait(has_symmetric_footprint_pinmap())
        self.add_trait(has_defined_type_description("LOGO"))
        self.add_trait(has_defined_footprint(KicadFootprint("logo:faebryk_logo")))


class Mounting_Hole(Component):
    def __init__(self) -> None:
        super().__init__()

        self.add_trait(has_symmetric_footprint_pinmap())
        self.add_trait(has_defined_type_description("H"))
        self.add_trait(
            has_defined_footprint(
                KicadFootprint("MountingHole:MountingHole_3.2mm_M3_ISO7380")
            )
        )


class DifferentialPair(Interface):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        class _IFs(Interface.InterfacesCls()):
            p = Electrical()
            n = Electrical()

        self.IFs = _IFs(self)

    def connect(self, other: Interface) -> Interface:
        assert type(other) is DifferentialPair, "can't connect to different type"
        for s, d in zip(self.IFs.get_all(), other.IFs.get_all()):
            s.connect(d)

        return self


class TPD6S300ARUKR(Component):
    def set_partnumber(self, partnumber: Parameter):
        self.partnumber = partnumber

    def __init__(self) -> None:
        super().__init__()

        class _IFs(Component.InterfacesCls()):
            # Pins names start at 1, so make idx 0 empty
            SBU = [None] + times(2, Electrical)
            C_SBU = [None] + times(2, Electrical)
            CC = [None] + times(2, Electrical)
            C_CC = [None] + times(2, Electrical)
            RPD_G = [None] + times(2, Electrical)
            D = [None] + times(2, Electrical)
            VBIAS = Electrical()
            power = Power()
            n_fault = Electrical()

        self.IFs = _IFs(self)

        class _NC(Component.InterfacesCls()):
            # Make a different NC net for each NC pin, otherwise they are connected
            NC = times(2, Electrical)

        self.add_trait(has_defined_type_description("U"))

        self.set_partnumber(Constant("TPD6S300ARUKR"))
        self.add_trait(is_representable_by_single_value("TPD6S300ARUKR"))

        self.add_trait(
            has_defined_footprint_pinmap(
                {
                    "1": self.IFs.C_SBU[1],
                    "2": self.IFs.C_SBU[2],
                    "3": self.IFs.VBIAS,
                    "4": self.IFs.C_CC[1],
                    "5": self.IFs.C_CC[2],
                    "6": self.IFs.RPD_G[2],
                    "7": self.IFs.RPD_G[1],
                    "8": self.IFs.power.IFs.lv,
                    "9": self.IFs.n_fault,
                    "10": self.IFs.power.IFs.hv,
                    "11": self.IFs.CC[2],
                    "12": self.IFs.CC[1],
                    "13": self.IFs.power.IFs.lv,
                    "14": self.IFs.SBU[2],
                    "15": self.IFs.SBU[1],
                    "16": _NC.NC[0],
                    "17": _NC.NC[1],
                    "18": self.IFs.power.IFs.lv,
                    "19": self.IFs.D[2],
                    "20": self.IFs.D[1],
                    "21": self.IFs.power.IFs.lv,
                }
            )
        )


class TPS54331DR(Component):
    def set_partnumber(self, partnumber: Parameter):
        self.partnumber = partnumber

    def __init__(self) -> None:
        super().__init__()

        class _IFs(Component.InterfacesCls()):
            boot = Electrical()
            Vin = Power()
            enable = Electrical()
            slow_start = Electrical()
            Vsense = Electrical()
            compensation = Electrical()
            PH = Electrical()

        self.IFs = _IFs(self)

        self.add_trait(has_defined_type_description("U"))
        self.set_partnumber(Constant("TPS54331DR"))

        self.add_trait(
            has_defined_footprint_pinmap(
                {
                    "1": self.IFs.boot,
                    "2": self.IFs.Vin.IFs.hv,
                    "3": self.IFs.enable,
                    "4": self.IFs.slow_start,
                    "5": self.IFs.Vsense,
                    "6": self.IFs.compensation,
                    "7": self.IFs.Vin.IFs.lv,
                    "8": self.IFs.PH,
                }
            )
        )
