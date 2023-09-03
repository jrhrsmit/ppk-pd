from enum import Enum, IntEnum
from functools import total_ordering
import logging

# library imports
from faebryk.core.core import Module, Parameter, Footprint
from faebryk.core.util import unit_map
from faebryk.library.Electrical import Electrical
from faebryk.library.ElectricPower import ElectricPower
from faebryk.library.Constant import Constant
from faebryk.library.Range import Range
from faebryk.library.TBD import TBD
from faebryk.library.has_footprint import has_footprint
from faebryk.library.has_defined_type_description import has_defined_type_description
from faebryk.library.has_type_description import has_type_description
from faebryk.library.can_attach_to_footprint_symmetrically import (
    can_attach_to_footprint_symmetrically,
)
from faebryk.library.has_defined_resistance import has_defined_resistance
from faebryk.library.has_resistance import has_resistance
from faebryk.library.KicadFootprint import KicadFootprint
from faebryk.library.can_attach_to_footprint import can_attach_to_footprint
from faebryk.library.can_attach_via_pinmap import can_attach_via_pinmap
from faebryk.library.can_bridge_defined import can_bridge_defined
from faebryk.library.has_defined_kicad_ref import has_defined_kicad_ref
from faebryk.library.has_defined_footprint import has_defined_footprint
from faebryk.library.can_attach_to_footprint_via_pinmap import (
    can_attach_to_footprint_via_pinmap,
)
from faebryk.libs.util import times
from faebryk.core.util import (
    connect_all_interfaces,
    connect_interfaces_via_chain,
    connect_to_all_interfaces,
)

logger = logging.getLogger("local_library")

from typing import List


from library.jlcpcb.util import (
    float_to_si,
)


class MOSFET(Module):
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
        self.add_trait(has_defined_kicad_ref("Q"))

    def _setup_interfaces(self):
        class _IFs(super().IFS()):
            source = Electrical()
            gate = Electrical()
            drain = Electrical()

        self.IFs = _IFs(self)
        self.add_trait(can_bridge_defined(self.IFs.source, self.IFs.drain))

    def set_channel_type(self, channel_type: Parameter):
        self.channel_type = channel_type

    def set_saturation_type(self, saturation_type: Parameter):
        self.saturation_type = saturation_type


class Diode(Module):
    def set_partnumber(self, partnumber: Parameter):
        self.partnumber = partnumber

    def _setup_interfaces(self):
        # interfaces
        class _IFs(super().IFS()):
            anode = Electrical()
            cathode = Electrical()

        self.IFs = _IFs(self)

    def _setup_traits(self):
        self.add_trait(can_bridge_defined(self.IFs.anode, self.IFs.cathode))
        self.add_trait(has_defined_kicad_ref("D"))
        self.add_trait(has_defined_type_description("Diode"))

    def __init__(self, partnumber=None):
        super().__init__()
        self._setup_interfaces()
        self._setup_traits()

        if partnumber is not None:
            self.set_partnumber(partnumber)


class TVS(Diode):
    def set_reverse_working_voltage(self, reverse_working_voltage: Parameter):
        self.reverse_working_voltage = reverse_working_voltage

    def __init__(self, reverse_working_voltage: Parameter):
        super().__init__()
        self.set_reverse_working_voltage(reverse_working_voltage)


class TVS_Array_Common_Anode(Module):
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
        self.add_trait(has_defined_kicad_ref("D"))

        class _IFs(super().IFS()):
            anode = Electrical()
            cathodes = times(self.num_channels.value, Electrical)

        self.IFs = _IFs(self)

        class _NODEs(Module.NODES()):
            tvs = times(
                self.num_channels.value, lambda: TVS(self.reverse_working_voltage)
            )

        self.NODEs = _NODEs(self)

        # workaround
        for tvs in self.NODEs.tvs:
            tvs.add_trait(can_attach_to_footprint_symmetrically())

        # connect all anodes
        connect_all_interfaces(
            [self.IFs.anode] + [tvs.IFs.anode for tvs in self.NODEs.tvs]
        )

        # connect corresponding cathode pairs
        for tvs, cathode in zip(self.NODEs.tvs, self.IFs.cathodes):
            cathode.connect(tvs.IFs.cathode)


class TVS_Array_Common_Anode_Power(Module):
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
        self.add_trait(has_defined_kicad_ref("D"))

        class _IFs(super().IFS()):
            power = ElectricPower()
            channels = times(self.num_channels.value, Electrical)

        self.IFs = _IFs(self)

        class _NODEs(Module.NODES()):
            tvs = TVS(self.reverse_working_voltage)
            diodes_pos = times(self.num_channels.value, Diode)
            diodes_neg = times(self.num_channels.value, Diode)

        self.NODEs = _NODEs(self)

        # workaround
        for cmp in [self.NODEs.tvs] + self.NODEs.diodes_pos + self.NODEs.diodes_neg:
            cmp.add_trait(can_attach_to_footprint_symmetrically())
        for cmp in self.NODEs.diodes_pos:
            cmp.add_trait(can_attach_to_footprint_symmetrically())
        for cmp in self.NODEs.diodes_neg:
            cmp.add_trait(can_attach_to_footprint_symmetrically())
        self.NODEs.tvs.add_trait(can_attach_to_footprint_symmetrically())

        # connect TVS
        self.NODEs.tvs.IFs.anode.connect(self.IFs.power.IFs.lv)
        self.NODEs.tvs.IFs.cathode.connect(self.IFs.power.IFs.hv)

        # connect all diodes_pos cathodes to power hv
        connect_all_interfaces(
            [self.IFs.power.IFs.hv] + [d.IFs.cathode for d in self.NODEs.diodes_pos]
        )

        # connect all diodes_neg anodes to power lv
        connect_all_interfaces(
            [self.IFs.power.IFs.lv] + [d.IFs.anode for d in self.NODEs.diodes_neg]
        )

        # connect all diodes_neg cathodes to diodes_pos anodes and to the channel
        for channel, diode_pos, diode_neg in zip(
            self.IFs.channels, self.NODEs.diodes_pos, self.NODEs.diodes_neg
        ):
            connect_all_interfaces(
                [channel, diode_neg.IFs.cathode, diode_pos.IFs.anode]
            )


class Fuse(Module):
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
        class _IFs(super().IFS()):
            unnamed = times(2, Electrical)

        self.IFs = _IFs(self)

        self.add_trait(can_attach_to_footprint_symmetrically())
        self.add_trait(can_bridge_defined(self.IFs.unnamed[0], self.IFs.unnamed[1]))
        self.add_trait(has_defined_kicad_ref("F"))


class Capacitor(Module):
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
        C0201 = 2
        C0402 = 3
        C0603 = 4
        C0805 = 5
        C1008 = 6
        C1206 = 7
        C1210 = 8
        C1806 = 9
        C1812 = 10
        C1825 = 11
        C2010 = 12
        C2512 = 13

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
        case_size: Parameter = Range(CaseSize.C0402, CaseSize.C1206),
    ):
        super().__init__()

        self._setup_interfaces()
        self.set_capacitance(capacitance)
        self.set_rated_voltage(rated_voltage)
        self.set_temperature_coefficient(temperature_coefficient)
        self.set_tolerance(tolerance)
        self.set_case_size(case_size)
        self.add_trait(can_attach_to_footprint_symmetrically())

    def _setup_traits(self):
        pass

    def _setup_interfaces(self):
        class _IFs(super().IFS()):
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
            self.case_size = Constant(self.CaseSize.C0402)
        elif capacitance < 10e-6:
            self.case_size = Constant(self.CaseSize.C0603)
        elif capacitance < 100e-6:
            self.case_size = Constant(self.CaseSize.C0805)
        else:
            self.case_size = Constant(self.CaseSize.C1206)


class Inductor(Module):
    class CaseSize(IntEnum):
        R01005 = 1
        R0201 = 2
        R0402 = 3
        R0603 = 4
        R0805 = 5
        R1008 = 6
        R1206 = 7
        R1210 = 8
        R1806 = 9
        R1812 = 10
        R1825 = 11
        R2010 = 12
        R2512 = 13

    class InductorType(Enum):
        Normal = 1
        Power = 2

    def _setup_interfaces(self):
        class _IFs(super().IFS()):
            unnamed = times(2, Electrical)

        self.IFs = _IFs(self)

        self.add_trait(can_bridge_defined(*self.IFs.unnamed))

    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls)
        self.add_trait(can_attach_to_footprint_symmetrically())
        return self

    def __init__(
        self,
        inductance: Parameter,
        self_resonant_frequency: Parameter,
        rated_current: Parameter,
        tolerance: Parameter,
        case_size: Parameter = TBD,
        dc_resistance: Parameter = TBD,
        inductor_type: Parameter = Constant(InductorType.Normal),
    ):
        super().__init__()

        self._setup_interfaces()
        self.set_inductance(inductance)
        self.set_tolerance(tolerance)
        self.set_self_resonant_frequency(self_resonant_frequency)
        self.set_rated_current(rated_current)
        self.set_inductor_type(inductor_type)
        if dc_resistance is not TBD:
            self.set_dc_resistance(dc_resistance)
        if case_size is not TBD:
            self.set_case_size(case_size)

    def set_inductor_type(self, inductor_type: Parameter):
        self.inductor_type = inductor_type

    def set_dc_resistance(self, dc_resistance: Parameter):
        self.dc_resistance = dc_resistance

    def set_rated_current(self, rated_current: Parameter):
        self.rated_current = rated_current

    def set_self_resonant_frequency(self, self_resonant_frequency: Parameter):
        self.self_resonant_frequency = self_resonant_frequency

    def set_tolerance(self, tolerance: Parameter):
        self.tolerance = tolerance

    def set_inductance(self, inductance: Parameter):
        self.inductance = inductance

        if type(inductance) is not Constant:
            # TODO this is a bit ugly
            # it might be that there was another more abstract valid trait
            # but this challenges the whole trait overriding mechanism
            # might have to make a trait stack thats popped or so
            self.del_trait(has_type_description)
            return

        class _has_type_description(has_type_description.impl()):
            @staticmethod
            def get_type_description():
                assert isinstance(self.inductance, Constant)
                _inductance: Constant = self.inductance
                return f"{float_to_si(_inductance.value)}H"

        self.add_trait(_has_type_description())

    def set_case_size(self, case_size: Parameter):
        self.case_size = case_size


class Resistor(Module):
    class CaseSize(IntEnum):
        R01005 = 1
        R0201 = 2
        R0402 = 3
        R0603 = 4
        R0805 = 5
        R1008 = 6
        R1206 = 7
        R1210 = 8
        R1806 = 9
        R1812 = 10
        R1825 = 11
        R2010 = 12
        R2512 = 13

    def _setup_traits(self):
        pass

    def _setup_interfaces(self):
        class _IFs(super().IFS()):
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
        case_size: Parameter = Constant(CaseSize.R0402),
    ):
        super().__init__()

        self._setup_interfaces()
        self.set_resistance(resistance)
        self.set_tolerance(tolerance)
        self.set_case_size(case_size)
        self.add_trait(can_attach_to_footprint_symmetrically())

    def set_tolerance(self, tolerance: Parameter):
        self.tolerance = tolerance

    def set_resistance(self, resistance: Parameter):
        self.resistance = resistance
        self.add_trait(has_defined_resistance(resistance))

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
                assert isinstance(
                    self.get_trait(has_resistance).get_resistance(), Constant
                )
                resistance = self.get_trait(has_resistance).get_resistance()
                assert isinstance(resistance, Constant)
                return unit_map(
                    resistance.value, ["µΩ", "mΩ", "Ω", "KΩ", "MΩ", "GΩ"], start="Ω"
                )

        self.add_trait(_has_type_description())

    def set_case_size(self, case_size: Parameter):
        self.case_size = case_size


class Faebryk_Logo(Module):
    def __init__(self) -> None:
        super().__init__()

        self.add_trait(can_attach_to_footprint_symmetrically())
        self.add_trait(has_defined_kicad_ref("LOGO"))
        self.add_trait(has_defined_type_description("Faebryk logo"))
        self.add_trait(has_defined_footprint(KicadFootprint("logo:faebryk_logo", [])))


class Mounting_Hole(Module):
    def __init__(self) -> None:
        super().__init__()

        self.add_trait(can_attach_to_footprint_symmetrically())
        self.add_trait(has_defined_kicad_ref("H"))
        self.add_trait(has_defined_type_description("Mounting hole 3.2mm M3"))
        self.add_trait(
            has_defined_footprint(
                KicadFootprint("MountingHole:MountingHole_3.2mm_M3_ISO7380", [])
            )
        )


class Pin_Header(Module):
    def __init__(self, rows: int = 1, columns: int = 1, pitch_mm=2.54) -> None:
        super().__init__()

        class _IFs(super().IFS()):
            unnamed = times(rows * columns, Electrical)

        self.IFs = _IFs(self)

        self.add_trait(has_defined_kicad_ref("J"))
        self.add_trait(
            has_defined_type_description(f"Pin header {rows}x{columns} {pitch_mm}mm")
        )
        self.add_trait(
            has_defined_footprint(
                KicadFootprint(
                    f"Connector_PinHeader_{pitch_mm:.02f}mm:PinHeader_{rows}x{columns:02d}_P{pitch_mm:.02f}mm_Vertical",
                    [str(i) for i in range(1, rows * columns + 1)],
                )
            )
        )

        pinout = {}
        for i in range(1, rows * columns + 1):
            pinout[str(i)] = self.IFs.unnamed[i - 1]

        self.add_trait(can_attach_to_footprint_via_pinmap(pinout))


class TPD6S300ARUKR(Module):
    def set_partnumber(self, partnumber: Parameter):
        self.partnumber = partnumber

    def __init__(self) -> None:
        super().__init__()

        class _IFs(super().IFS()):
            # Pins names start at 1 so make idx 0 empty
            SBU = times(2, Electrical)
            C_SBU = times(2, Electrical)
            CC = times(2, Electrical)
            C_CC = times(2, Electrical)
            RPD_G = times(2, Electrical)
            D = times(2, Electrical)
            VBIAS = Electrical()
            power = ElectricPower()
            n_fault = Electrical()

        self.IFs = _IFs(self)

        class NC(super().IFS()):
            # Make a different NC net for each NC pin, otherwise they are connected
            NC = times(2, Electrical)

        self.add_trait(has_defined_kicad_ref("U"))

        self.set_partnumber(Constant("TPD6S300ARUKR"))
        self.add_trait(has_defined_type_description("TPD6S300ARUKR"))

        self.add_trait(
            can_attach_to_footprint_via_pinmap(
                {
                    "1": self.IFs.C_SBU[1],
                    "2": self.IFs.C_SBU[2],
                    "3": self.IFs.VBIAS,
                    "4": self.IFs.C_CC[1],
                    "5": self.IFs.C_CC[2],
                    "6": self.IFs.RPD_G[2],
                    "7": self.IFs.RPD_G[1],
                    "8": self.IFs.power.NODEs.lv,
                    "9": self.IFs.n_fault,
                    "10": self.IFs.power.NODEs.hv,
                    "11": self.IFs.CC[2],
                    "12": self.IFs.CC[1],
                    "13": self.IFs.power.NODEs.lv,
                    "14": self.IFs.SBU[2],
                    "15": self.IFs.SBU[1],
                    "16": NC.NC[0],
                    "17": NC.NC[1],
                    "18": self.IFs.power.NODEs.lv,
                    "19": self.IFs.D[2],
                    "20": self.IFs.D[1],
                    "21": self.IFs.power.NODEs.lv,
                }
            )
        )


class TPS54331DR(Module):
    def set_partnumber(self, partnumber: Parameter):
        self.partnumber = partnumber

    def __init__(self) -> None:
        super().__init__()

        class _IFs(super().IFS()):
            boot = Electrical()
            Vin = ElectricPower()
            enable = Electrical()
            slow_start = Electrical()
            Vsense = Electrical()
            compensation = Electrical()
            PH = Electrical()

        self.IFs = _IFs(self)

        self.add_trait(has_defined_kicad_ref("U"))
        self.add_trait(has_defined_type_description("Buck converter"))
        self.set_partnumber(Constant("TPS54331DR"))

        self.add_trait(
            can_attach_to_footprint_via_pinmap(
                {
                    "1": self.IFs.boot,
                    "2": self.IFs.Vin.NODEs.hv,
                    "3": self.IFs.enable,
                    "4": self.IFs.slow_start,
                    "5": self.IFs.Vsense,
                    "6": self.IFs.compensation,
                    "7": self.IFs.Vin.NODEs.lv,
                    "8": self.IFs.PH,
                }
            )
        )
