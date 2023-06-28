import logging
from typing import List

logger = logging.getLogger(__name__)

# local imports
import library.lcsc as lcsc

# library imports
from faebryk.library.core import Component, Parameter
from faebryk.library.library.interfaces import Electrical, Power
from faebryk.library.library.parameters import Constant, Range, TBD
from faebryk.library.trait_impl.component import (
    has_defined_footprint_pinmap,
    has_defined_type_description,
    has_symmetric_footprint_pinmap,
)
from faebryk.library.traits.component import has_footprint, has_footprint_pinmap

# function imports
from faebryk.library.util import get_all_components, times

# Project library imports
from library.library.components import (
    MOSFET,
    DifferentialPair,
    TPS54331DR,
    Capacitor,
    Resistor,
)

from library.lcsc import *

from library.jlcpcb.capacitor_search import find_capacitor
from library.jlcpcb.resistor_search import find_resistor
from library.jlcpcb.partnumber_search import find_partnumber
from library.jlcpcb.part_picker import pick_part


class Boost_Converter_TPS61040DBVR(Component):
    pass


class Buck_Converter_TPS54331DR(Component):
    """
    Buck converter based on TPS54331.

    See https://datasheet.lcsc.com/lcsc/1808272040_Texas-Instruments-TPS54331DR_C9865.pdf for design details
    """

    def calc_slowstart_capacitor(self, Tss: Range = Range(3e-3, 8e-3)):
        """
        Calculates the external capacitor value for the slow-start mechanism.

        The slow start capacitor is attached to the SS/slowstart pin.
        Tss is the slow-start time in seconds, and should be between 1 and 10ms.
        """
        assert Tss.min >= 1e-3 and Tss.max < 10e-3

        # Reference voltage
        Vref = 0.8
        # slow-start current
        Iss = 2e-6
        # slow-start capacitor range
        Css_min = 1e-9 * (Tss.min * 1e3 / Vref * (Iss * 1e6))
        Css_max = 1e-9 * (Tss.max * 1e3 / Vref * (Iss * 1e6))
        if Css_max > 27e-9:
            raise ValueError(
                f"Maximum value for Css exceeded. Allowed 27nF, upper limit: {Css_max*1e9}nF"
            )
        self.CMPs.Css.set_capacitance(capacitance=Range(Css_min, Css_max))

    def calc_enable_resistors(self, input_voltage: Parameter):
        # Resistor value ranges:
        resistor_range = 0.02

        # derive Vstart and Vstop, the input start and input stop threshold voltages.
        if type(input_voltage) is Range:
            Vstart = input_voltage.min * 0.95
            Vstop = input_voltage.min * 0.9
        elif type(input_voltage) is Constant:
            Vstart = input_voltage * 0.95
            Vstop = input_voltage * 0.9
        else:
            raise NotImplementedError(
                f"Can't calculate component values with input voltage of type {type(input_voltage)}"
            )

        if Vstop < 3.5:
            raise ValueError(
                f"Vstop is smaller than 3.5V, which is not allowed. Vstop = {Vstop}"
            )

        # Enable threshold voltage
        Ven = 1.25
        # Ren1 and Ren2 form a resistor divider for the enable pin
        Ren1_value = (Vstart - Vstop) / 3e-6
        Ren2_value = Ven / ((Vstart - Ven) / Ren1_value + 1e-6)

        self.CMPs.Ren1.set_resistance(
            Range(Ren1_value * (1 - resistor_range), Ren1_value * (1 + resistor_range))
        )
        self.CMPs.Ren2.set_resistance(
            Range(Ren2_value * (1 - resistor_range), Ren2_value * (1 + resistor_range))
        )

        print(
            f"Ren1: {Ren1_value}: {Ren1_value * (1 - resistor_range)} {Ren1_value * (1 + resistor_range)}"
        )
        print(
            f"Ren2: {Ren2_value}: {Ren2_value * (1 - resistor_range)} {Ren2_value * (1 + resistor_range)}"
        )

    def calc_component_values(
        self,
        input_voltage: Parameter,
        output_voltage: Parameter,
        output_current: Parameter,
    ):
        self.calc_slowstart_capacitor()
        if type(input_voltage) is Constant or type(input_voltage) is Range:
            self.calc_enable_resistors(input_voltage=input_voltage)

    def __init__(self) -> None:
        super().__init__()

        class _IFs(Component.InterfacesCls()):
            input = Power()
            output = Power()

        self.IFs = _IFs(self)

        class _CMPs(Component.ComponentsCls()):
            ic = TPS54331DR()
            Ren1 = Resistor(TBD)
            Ren2 = Resistor(TBD)
            Css = Capacitor(
                capacitance=TBD,
                tolerance=10,
                rated_voltage=Constant(10),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X7R),
            )

        self.CMPs = _CMPs(self)


class USB_C_PD_PSU(Component):
    pass


class STM32G473VET6(Component):
    """
    ST-Microelectronics MCU with 512kB flash, 128kB RAM, Cortex M4 core.
    """

    pass


class MCU(Component):
    pass


class Limiter(Component):
    pass


class Sensing(Component):
    pass


class Power_Frontend(Component):
    pass


class Logic_Analyzer_Frontend(Component):
    pass


class Display(Component):
    pass


class PPK_PD(Component):
    def __init__(self) -> None:
        super().__init__()

        class _CMPs(Component.ComponentsCls()):
            # power_supply = USB_C_PD_PSU()
            # mcu = MCU()
            # power_frontend = Power_Frontend()
            # logic_analyzer_frontend = Logic_Analyzer_Frontend()
            buck = Buck_Converter_TPS54331DR()

        self.CMPs = _CMPs(self)

        self.CMPs.buck.calc_component_values(
            input_voltage=Range(5, 20),
            output_voltage=Constant(5),
            output_current=Constant(0.25),
        )

        print(
            f"PN of 100nF 16V X7R 10%: {find_capacitor(capacitance=100e-9, tolerance_percent=10)}"
        )
        print(
            f"PN of 10pF 10% : {find_capacitor(capacitance=10e-12, tolerance_percent=10)}"
        )
        print(
            f"PN of 2.4pF 15% : {find_capacitor(capacitance=2.4e-12, tolerance_percent=15)}"
        )
        print(f"PN of 470k: {find_resistor(resistance=1200)}")
        lcsc_1k = find_resistor(resistance=1000)
        print(f"PN of 1k: {lcsc_1k}")
        print(f"PN of 470k: {find_resistor(resistance=470e3)}")
        print(f"PN of 1k 0.1%: {find_resistor(resistance=1e3, tolerance_percent=0.1)}")
        print(f"PN of LMV321: {find_partnumber('LMV321')}")

        # hack footprints
        for r in get_all_components(self) + [self]:
            if not r.has_trait(has_footprint):
                assert type(r) in [
                    Buck_Converter_TPS54331DR,
                ], f"{r}"
            if not r.has_trait(has_footprint_pinmap):
                r.add_trait(has_symmetric_footprint_pinmap())
