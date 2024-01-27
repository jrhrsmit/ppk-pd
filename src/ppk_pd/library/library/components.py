import logging
from enum import Enum, IntEnum
from functools import total_ordering
from typing import List

# library imports
from faebryk.core.core import Module, Parameter
from faebryk.core.util import (
    as_unit,
    as_unit_with_tolerance,
    connect_all_interfaces,
    unit_map,
)
from faebryk.library.can_attach_to_footprint_symmetrically import (
    can_attach_to_footprint_symmetrically,
)
from faebryk.library.can_attach_to_footprint_via_pinmap import (
    can_attach_to_footprint_via_pinmap,
)
from faebryk.library.can_bridge_defined import can_bridge_defined
from faebryk.library.Constant import Constant
from faebryk.library.Electrical import Electrical
from faebryk.library.ElectricPower import ElectricPower
from faebryk.library.has_defined_footprint import has_defined_footprint
from faebryk.library.has_defined_kicad_ref import has_defined_kicad_ref
from faebryk.library.has_defined_resistance import has_defined_resistance
from faebryk.library.has_designator_prefix_defined import has_designator_prefix_defined
from faebryk.library.has_resistance import has_resistance
from faebryk.library.has_simple_value_representation_based_on_params import (
    has_simple_value_representation_based_on_params,
)
from faebryk.library.has_simple_value_representation_defined import (
    has_simple_value_representation_defined,
)
from faebryk.library.KicadFootprint import KicadFootprint
from faebryk.library.Range import Range
from faebryk.library.TBD import TBD
from faebryk.libs.util import times
from library.jlcpcb.util import (
    float_to_si,
)

logger = logging.getLogger("local_library")


# from library.jlcpcb.inductor_search import find_inductor


class MOSFET(Module):
    class ChannelType(Enum):
        N_CHANNEL = 1
        P_CHANNEL = 2

    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls)
        self._setup_traits()
        return self

    def __init__(
        self,
        channel_type: Parameter,
        drain_source_voltage: Parameter,
        continuous_drain_current: Parameter,
        drain_source_resistance: Parameter,
        gate_source_threshold_voltage: Parameter,
        power_dissipation: Parameter,
        package: Parameter,
    ) -> None:
        super().__init__()
        self._setup_interfaces()
        self.set_channel_type(channel_type)
        self.set_drain_source_voltage(drain_source_voltage)
        self.set_continuous_drain_current(continuous_drain_current)
        self.set_drain_source_resistance(drain_source_resistance)
        self.set_gate_source_threshold_voltage(gate_source_threshold_voltage)
        self.set_power_dissipation(power_dissipation)
        self.set_package(package)

    def _setup_traits(self):
        self.add_trait(has_defined_kicad_ref("Q"))

    def _setup_interfaces(self):
        class _IFs(Module().IFS()):
            source = Electrical()
            gate = Electrical()
            drain = Electrical()

        self.IFs = _IFs(self)
        self.add_trait(can_bridge_defined(self.IFs.source, self.IFs.drain))

    def map_string_to_pin(self, pin: str):
        pin = pin.upper()
        if pin == "S" or pin == "SOURCE":
            return self.IFs.source
        elif pin == "G" or pin == "GATE":
            return self.IFs.gate
        elif pin == "D" or pin == "DRAIN":
            return self.IFs.drain
        else:
            raise ValueError(f"Unknown pin name: {pin}")

    def set_package(self, package: Parameter):
        self.package = package

    def set_channel_type(self, channel_type: Parameter):
        self.channel_type = channel_type

    def set_drain_source_voltage(self, drain_source_voltage: Parameter):
        self.drain_source_voltage = drain_source_voltage

    def set_continuous_drain_current(self, continuous_drain_current: Parameter):
        self.continuous_drain_current = continuous_drain_current

    def set_drain_source_resistance(self, drain_source_resistance: Parameter):
        self.drain_source_resistance = drain_source_resistance

    def set_gate_source_threshold_voltage(
        self, gate_source_threshold_voltage: Parameter
    ):
        self.gate_source_threshold_voltage = gate_source_threshold_voltage

    def set_power_dissipation(self, power_dissipation: Parameter):
        self.power_dissipation = power_dissipation


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
        class _IFs(Module().IFS()):
            unnamed = times(2, Electrical)

        self.IFs = _IFs(self)

        self.add_trait(can_attach_to_footprint_symmetrically())
        self.add_trait(can_bridge_defined(self.IFs.unnamed[0], self.IFs.unnamed[1]))
        self.add_trait(has_defined_kicad_ref("F"))


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

        class _IFs(super().IFS()):
            unnamed = times(2, Electrical)

        self.IFs = _IFs(self)
        self.add_trait(can_bridge_defined(*self.IFs.unnamed))

        class _PARAMs(super().PARAMS()):
            inductance = TBD[float]()
            self_resonant_frequency = TBD[float]()
            rated_current = TBD[float]()
            case_size = TBD[Inductor.CaseSize]()
            dc_resistance = TBD[float]()
            inductor_type = TBD[Inductor.InductorType]()
            partnumber = TBD[str]()

        self.PARAMs = _PARAMs(self)

        self.add_trait(can_attach_to_footprint_symmetrically())
        self.add_trait(
            has_simple_value_representation_based_on_params(
                (
                    self.PARAMs.inductance,
                    self.PARAMs.self_resonant_frequency,
                    self.PARAMs.rated_current,
                    self.PARAMs.dc_resistance,
                ),
                lambda ps: f"{as_unit_with_tolerance(ps[0], 'H')}, "
                f"{as_unit(ps[2].max, 'A')}, "
                f"SRF {as_unit(ps[1].max, 'Hz')}, "
                f"DCR {as_unit(ps[3].max, 'Ω')}",
            )
        )
        self.add_trait(has_designator_prefix_defined("R"))


class Faebryk_Logo(Module):
    def __init__(self) -> None:
        super().__init__()

        self.add_trait(can_attach_to_footprint_symmetrically())
        self.add_trait(has_defined_kicad_ref("LOGO"))
        self.add_trait(has_defined_footprint(KicadFootprint("logo:faebryk_logo", [])))


class Mounting_Hole(Module):
    def __init__(self) -> None:
        super().__init__()

        self.add_trait(can_attach_to_footprint_symmetrically())
        self.add_trait(has_defined_kicad_ref("H"))
        self.add_trait(
            has_defined_footprint(
                KicadFootprint("MountingHole:MountingHole_3.2mm_M3_ISO7380", [])
            )
        )


class Pin_Header(Module):
    def __init__(self, rows: int = 1, columns: int = 1, pitch_mm=2.54) -> None:
        super().__init__()

        class _IFs(Module().IFS()):
            unnamed = times(rows * columns, Electrical)

        self.IFs = _IFs(self)

        self.add_trait(has_defined_kicad_ref("J"))
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

        class _IFs(Module().IFS()):
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

        class NC(Module().IFS()):
            # Make a different NC net for each NC pin, otherwise they are connected
            NC = times(2, Electrical)

        self.add_trait(has_defined_kicad_ref("U"))

        self.set_partnumber(Constant("TPD6S300ARUKR"))

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
                    "8": self.IFs.power.IFs.lv,
                    "9": self.IFs.n_fault,
                    "10": self.IFs.power.IFs.hv,
                    "11": self.IFs.CC[2],
                    "12": self.IFs.CC[1],
                    "13": self.IFs.power.IFs.lv,
                    "14": self.IFs.SBU[2],
                    "15": self.IFs.SBU[1],
                    "16": NC.NC[0],
                    "17": NC.NC[1],
                    "18": self.IFs.power.IFs.lv,
                    "19": self.IFs.D[2],
                    "20": self.IFs.D[1],
                    "21": self.IFs.power.IFs.lv,
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

        self.add_trait(has_designator_prefix_defined("U"))
        self.add_trait(has_simple_value_representation_defined("TPS54331DR"))
        # TODO: fix this:
        self.set_partnumber(Constant("TPS54331DR"))

        self.add_trait(
            can_attach_to_footprint_via_pinmap(
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


class TPS543x(Module):
    def set_partnumber(self, partnumber: Parameter):
        self.partnumber = partnumber

    def __init__(self) -> None:
        class _IFs(Module().IFS()):
            Vin = ElectricPower()
            enable = Electrical()
            boot = Electrical()
            Vsense = Electrical()
            PH = Electrical()

        self.IFs = _IFs(self)

        self.add_trait(has_defined_kicad_ref("U"))
        self.set_partnumber(Constant("TPS5430DDAR"))

        class NC(Module().IFS()):
            # Make a different NC net for each NC pin, otherwise they are connected
            NC = times(2, Electrical)

        self.add_trait(
            can_attach_to_footprint_via_pinmap(
                {
                    "1": self.IFs.boot,
                    "2": NC.NC[0],
                    "3": NC.NC[1],
                    "4": self.IFs.Vsense,
                    "5": self.IFs.enable,
                    "6": self.IFs.Vin.IFs.lv,
                    "7": self.IFs.Vin.IFs.hv,
                    "8": self.IFs.PH,
                }
            )
        )


class TL072CDT(Module):
    """
    Dual JFET-Input Operational Amplifier, SOIC-8 package
    """

    def set_partnumber(self, partnumber: Parameter):
        self.partnumber = partnumber

    def __init__(self) -> None:
        super().__init__()

        class _IFs(super().IFS()):
            power_input = ElectricPower()
            output = times(2, Electrical)
            inverting_input = times(2, Electrical)
            non_inverting_input = times(2, Electrical)

        self.IFs = _IFs(self)

        self.set_partnumber(Constant("TL072CDT"))
        self.add_trait(has_defined_kicad_ref("U"))

        self.add_trait(
            can_attach_to_footprint_via_pinmap(
                {
                    "1": self.IFs.output[1],
                    "2": self.IFs.inverting_input[1],
                    "3": self.IFs.non_inverting_input[1],
                    "4": self.IFs.power_input.IFs.lv,
                    "5": self.IFs.non_inverting_input[2],
                    "6": self.IFs.inverting_input[2],
                    "7": self.IFs.output[2],
                    "8": self.IFs.power_input.IFs.hv,
                }
            )
        )
