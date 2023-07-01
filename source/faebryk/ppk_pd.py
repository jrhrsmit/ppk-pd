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
    Diode,
)

from library.lcsc import *

from library.jlcpcb.capacitor_search import find_capacitor
from library.jlcpcb.resistor_search import find_resistor
from library.jlcpcb.partnumber_search import find_partnumber
from library.jlcpcb.part_picker import pick_part

from library.e_series import e_series_ratio, E24, E48, E96


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
        self.CMPs.C5.set_capacitance(capacitance=Range(Css_min, Css_max))
        self.CMPs.C5.set_auto_case_size()

    def calc_enable_resistors(self, input_voltage: Parameter):
        # Resistor value ranges:
        resistor_range = 0.02

        # derive Vstart and Vstop, the input start and input stop threshold voltages.
        if type(input_voltage) is Range:
            Vstart = input_voltage.min * 0.95
            Vstop = input_voltage.min * 0.9
        elif type(input_voltage) is Constant:
            Vstart = input_voltage.value * 0.95
            Vstop = input_voltage.value * 0.9
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

        self.CMPs.R1.set_resistance(
            Range(Ren1_value * (1 - resistor_range), Ren1_value * (1 + resistor_range))
        )
        self.CMPs.R2.set_resistance(
            Range(Ren2_value * (1 - resistor_range), Ren2_value * (1 + resistor_range))
        )

        print(
            f"Ren1: {Ren1_value}: {Ren1_value * (1 - resistor_range)} {Ren1_value * (1 + resistor_range)}"
        )
        print(
            f"Ren2: {Ren2_value}: {Ren2_value * (1 - resistor_range)} {Ren2_value * (1 + resistor_range)}"
        )

    def calc_output_voltage_divider(
        self, output_voltage: Constant, output_voltage_accuracy: Constant
    ):
        # TODO: does not account for resistor tolerance itself
        output_input_ratio = Range(
            value_min=(
                self.reference_voltage
                / output_voltage.value
                * (1 - output_voltage_accuracy.value)
            ),
            value_max=(
                self.reference_voltage
                / output_voltage.value
                * (1 + output_voltage_accuracy.value)
            ),
        )
        (R5, R6) = e_series_ratio(
            R1=Range(9.8e3, 10.2e3),
            output_input_ratio=output_input_ratio,
            e_values=list(set(E24 + E48)),
        )

        self.CMPs.R5.set_resistance(Constant(R5))
        self.CMPs.R6.set_resistance(Constant(R6))
        print(f"R5: {R5}")
        print(f"R6: {R6}")

    def calc_input_capacitors(
        self,
        input_voltage: Range,
        input_ripple_voltage: Constant,
        output_current: Constant,
    ):
        # approximate MLCC bulk capacitor ESR with 10mOhm
        capacitor_esr = 10e-3

        Cbulk = (
            (output_current.value * 0.25)
            / (input_ripple_voltage.value - output_current.value * capacitor_esr)
            / self.switching_frequency
        )
        # spread capacitance over C1 and C2, take a minimum of 2.2uF per cap as we have the footprints there anyway
        Cbulk = max(Cbulk / 2, 2.2e-6)
        self.CMPs.C1.set_capacitance(Range(Cbulk, 4 * Cbulk))
        self.CMPs.C2.set_capacitance(Range(Cbulk, 4 * Cbulk))
        self.CMPs.C1.set_case_size(
            Range(Capacitor.CaseSize.C0402, Capacitor.CaseSize.C1206)
        )
        self.CMPs.C2.set_case_size(
            Range(Capacitor.CaseSize.C0402, Capacitor.CaseSize.C1206)
        )

        # plus 50% safety margin against voltage transients
        self.CMPs.C1.set_rated_voltage(Constant(input_voltage.max * 1.5))
        self.CMPs.C2.set_rated_voltage(Constant(input_voltage.max * 1.5))

    def calc_component_values(
        self,
        input_voltage: Range,
        output_voltage: Constant,
        input_ripple_voltage: Constant = Constant(0.25),
        output_ripple_voltage: Constant = Constant(0.05),
        output_current: Constant = Constant(0.5),
        output_voltage_accuracy: Constant = Constant(0.02),
    ):
        self.calc_slowstart_capacitor()
        if type(input_voltage) is Constant or type(input_voltage) is Range:
            self.calc_enable_resistors(input_voltage=input_voltage)

        self.calc_output_voltage_divider(output_voltage, output_voltage_accuracy)
        self.calc_input_capacitors(input_voltage, input_ripple_voltage, output_current)

    def __init__(
        self,
        input_voltage: Range,
        output_voltage: Constant,
        input_ripple_voltage: Constant = Constant(0.25),
        output_ripple_voltage: Constant = Constant(0.05),
        output_current: Constant = Constant(0.5),
        output_voltage_accuracy: Constant = Constant(0.02),
    ) -> None:
        super().__init__()

        # Switching frequency is fixed at 570kHz
        self.switching_frequency = 570e3

        # reference voltage is at 800mV
        self.reference_voltage = 800e-3

        class _IFs(Component.InterfacesCls()):
            input = Power()
            output = Power()

        self.IFs = _IFs(self)

        class _CMPs(Component.ComponentsCls()):
            ic = TPS54331DR()
            # divider for UVLO mechanism in enable pin
            R1 = Resistor(TBD, tolerance=Constant(1))
            R2 = Resistor(TBD, tolerance=Constant(1))
            # compensation resistor
            # R3 = Resistor(TBD, tolerance=Constant(1))
            # R4 is omitted, not necessary in most designs
            # Divider for Vsense
            R5 = Resistor(TBD, tolerance=Constant(1))
            R6 = Resistor(TBD, tolerance=Constant(1))
            # input bulk caps
            C1 = Capacitor(
                capacitance=TBD,
                tolerance=Constant(20),
                rated_voltage=Constant(10),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X7R),
            )
            C2 = Capacitor(
                capacitance=TBD,
                tolerance=Constant(20),
                rated_voltage=Constant(10),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X7R),
            )
            # input HF filter cap of 10nF
            C3 = Capacitor(
                capacitance=Constant(10e-9),
                tolerance=Constant(20),
                rated_voltage=Constant(50),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X7R),
            )
            # boot capacitor, always 100nF
            C4 = Capacitor(
                capacitance=Constant(100e-9),
                tolerance=Constant(10),
                rated_voltage=Constant(50),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X7R),
            )
            # slow-start capacitor
            C5 = Capacitor(
                capacitance=TBD,
                tolerance=Constant(10),
                rated_voltage=Constant(50),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X7R),
            )
            # Catch diode
            D1 = Diode(partnumber=Constant("B340A-13-F"))
            # Inductor
            # L1 = Inductor()

        self.CMPs = _CMPs(self)

        self.calc_component_values(
            input_voltage,
            output_voltage,
            input_ripple_voltage,
            output_ripple_voltage,
            output_current,
            output_voltage_accuracy,
        )


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
            buck = Buck_Converter_TPS54331DR(
                input_voltage=Range(5, 22),
                output_voltage=Constant(5),
                output_current=Constant(0.1),
                output_ripple_voltage=Constant(0.03),
                input_ripple_voltage=Constant(0.1),
            )

        self.CMPs = _CMPs(self)

        # self.CMPs.buck.calc_component_values(
        #     input_voltage=Range(5, 20),
        #     output_voltage=Constant(5),
        #     output_current=Constant(0.25),
        #     output_ripple_voltage=Constant(0.03),
        #     input_ripple_voltage=Constant(0.1),
        # )

        # print(e_series_ratio(Constant(1e3), Constant(0.5)))
        # print(e_series_ratio(Constant(1e3), Constant(0.99999)))
        # print(e_series_ratio(Constant(1e3), Constant(0.0001)))
        # print(e_series_ratio(Constant(9.8e3), Constant(0.1)))
        # print(e_series_ratio(Constant(1e3), Range(0.4, 0.9)))
        # print(
        #     e_series_ratio(
        #         Range(9.8e3, 10.2e3), Constant(0.8 / 3.3), list(set(E24 + E48 + E96))
        #     )
        # )
        # print(
        #     e_series_ratio(
        #         Range(9.8e3, 10.2e3), Constant(0.8 / 5), list(set(E24 + E48 + E96))
        #     )
        # )
        # print(
        #     e_series_ratio(
        #         Range(9.8e3, 10.2e3),
        #         Range(0.8 / 5 * 0.98, 0.8 / 5 * 1.02),
        #         list(set(E24 + E48)),
        #     )
        # )

        # print(
        #     f"PN of 100nF 16V X7R 10%: {find_capacitor(capacitance=100e-9, tolerance_percent=10)}"
        # )
        # print(
        #     f"PN of 10pF 10% : {find_capacitor(capacitance=10e-12, tolerance_percent=10)}"
        # )
        # print(
        #     f"PN of 2.4pF 15% : {find_capacitor(capacitance=2.4e-12, tolerance_percent=15)}"
        # )
        # print(f"PN of 470k: {find_resistor(resistance=1200)}")
        # lcsc_1k = find_resistor(resistance=1000)
        # print(f"PN of 1k: {lcsc_1k}")
        # print(f"PN of 470k: {find_resistor(resistance=470e3)}")
        # print(f"PN of 1k 0.1%: {find_resistor(resistance=1e3, tolerance_percent=0.1)}")
        # print(f"PN of LMV321: {find_partnumber('LMV321')}")

        pick_part(self)

        # hack footprints
        for r in get_all_components(self) + [self]:
            if not r.has_trait(has_footprint):
                assert type(r) in [
                    Buck_Converter_TPS54331DR,
                    PPK_PD,
                ], f"{r}"
            if not r.has_trait(has_footprint_pinmap):
                r.add_trait(has_symmetric_footprint_pinmap())
