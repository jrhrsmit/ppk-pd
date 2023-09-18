# library imports
from faebryk.core.core import Parameter
from faebryk.core.core import Module
from faebryk.library.Electrical import Electrical
from faebryk.library.ElectricPower import ElectricPower
from faebryk.library.Constant import Constant
from faebryk.library.Range import Range
from faebryk.library.TBD import TBD
from faebryk.library.has_footprint import has_footprint
from faebryk.library.can_attach_via_pinmap import can_attach_via_pinmap
from faebryk.library.can_attach_to_footprint_symmetrically import (
    can_attach_to_footprint_symmetrically,
)
from faebryk.library.can_attach_to_footprint_via_pinmap import (
    can_attach_to_footprint_via_pinmap,
)

# function imports
from faebryk.libs.util import times
from faebryk.core.util import get_all_nodes

import logging

log = logging.getLogger(__name__)

# Project library imports
from library.library.components import (
    TPS54331DR,
    Capacitor,
    Resistor,
    Diode,
    Inductor,
    Mounting_Hole,
    Faebryk_Logo,
    Pin_Header,
)

from library.jlcpcb.part_picker import pick_part

from library.e_series import e_series_ratio, E24, E48
from library.jlcpcb.util import float_to_si

from math import sqrt, pi, log10, tan, atan, degrees, radians, exp


class Boost_Converter_TPS61040DBVR(Module):
    pass


class Buck_Converter_TPS54331DR(Module):
    """
    Buck converter based on TPS54331.

    See https://www.ti.com/lit/ds/symlink/tps54331.pdf for design details,
    especially figure 13 for component names and the step by step design
    procedure for the calculations.
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
        self.NODEs.C5.set_capacitance(capacitance=Range(Css_min, Css_max))
        self.NODEs.C5.set_auto_case_size()

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

        self.NODEs.R1.set_resistance(
            Range(Ren1_value * (1 - resistor_range), Ren1_value * (1 + resistor_range))
        )
        self.NODEs.R2.set_resistance(
            Range(Ren2_value * (1 - resistor_range), Ren2_value * (1 + resistor_range))
        )

        log.debug(
            f"Ren1: {float_to_si(Ren1_value)}Ohm: {float_to_si(Ren1_value * (1 - resistor_range))}Ohm - {float_to_si(Ren1_value * (1 + resistor_range))}Ohm"
        )
        log.debug(
            f"Ren2: {float_to_si(Ren2_value)}Ohm: {float_to_si(Ren2_value * (1 - resistor_range))}Ohm - {float_to_si(Ren2_value * (1 + resistor_range))}Ohm"
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

        self.NODEs.R5.set_resistance(Constant(R5))
        self.NODEs.R6.set_resistance(Constant(R6))
        log.debug(f"R5: {R5}")
        log.debug(f"R6: {R6}")

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
        self.NODEs.C1.set_capacitance(Range(Cbulk, 4 * Cbulk))
        self.NODEs.C2.set_capacitance(Range(Cbulk, 4 * Cbulk))
        self.NODEs.C1.set_case_size(
            Range(Capacitor.CaseSize.C0402, Capacitor.CaseSize.C1206)
        )
        self.NODEs.C2.set_case_size(
            Range(Capacitor.CaseSize.C0402, Capacitor.CaseSize.C1206)
        )

        # plus 50% safety margin against voltage transients
        self.NODEs.C1.set_rated_voltage(Constant(input_voltage.max * 1.5))
        self.NODEs.C2.set_rated_voltage(Constant(input_voltage.max * 1.5))

    def calc_output_capacitors(
        self,
        input_voltage: Range,
        output_voltage: Constant,
        output_current: Constant,
        output_ripple_voltage: Constant,
    ):
        R_out = output_voltage.value / output_current.value
        # With high switching frequencies such as the 570-kHz frequency of this design, internal circuit
        # limitations of the TPS54331 limit the practical maximum crossover frequency to about 25 kHz.
        F_crossover_max = 25e3
        # minimum output capacitance needed to gain loop stability
        C_out_min_stable = 1 / (2 * pi * R_out * F_crossover_max)
        # approximate efficiency
        efficiency = 0.8
        # calculate actual ripple voltage
        duty_cycle = output_voltage.value / (input_voltage.max * efficiency)
        # estimate capacitor ESR to be 10mOhm for X7R caps
        R_esr = 10e-3
        # peak to peak inductor current
        if type(self.NODEs.L1.inductance) is Constant:
            L = self.NODEs.L1.inductance.value
        elif type(self.NODEs.L1.inductance) is Range:
            L = self.NODEs.L1.inductance.min
        else:
            raise NotImplementedError("No way to determine maximum inductance of L1")

        I_L_ripple = (
            output_voltage.value
            * (input_voltage.max - output_voltage.value)
            / (input_voltage.max * L * self.switching_frequency * 0.8)
        )
        # minimum output capacitance needed to satisfy the ripple requirement
        C_out_min_ripple = (duty_cycle - 0.5) / (
            (output_ripple_voltage.value / I_L_ripple - R_esr)
            * 4
            * self.switching_frequency
        )

        # minimum output capacitance
        log.debug(f"min rip: {C_out_min_ripple}, stab: {C_out_min_stable}")
        C_out_min = max(C_out_min_ripple, C_out_min_stable)

        # multiply by 5, as the capacitance at the DC bias can be 5 times as low as specified
        # for more info see https://www.analog.com/en/technical-articles/how-to-measure-capacity-versus-bias-voltage-on-mlccs.html
        # Even though this might be worst case, the cheapest capacitor will likely have a voltage
        # rating just above the specified minimum voltage rating. If this is not the case, the capacitor
        # will likely be of a low value so that the voltage rating doesn't matter, and thus increasing the
        # capacitance will not have any effect on the choice of component.
        # C_out_min *= 2

        log.debug(f"output capacitance C_out_min: {float_to_si(C_out_min)}F")
        self.NODEs.C8.set_capacitance(Range(C_out_min / 2, C_out_min))
        self.NODEs.C9.set_capacitance(Range(C_out_min / 2, C_out_min))
        self.NODEs.C8.set_case_size(
            Range(Capacitor.CaseSize.C0402, Capacitor.CaseSize.C1206)
        )
        self.NODEs.C9.set_case_size(
            Range(Capacitor.CaseSize.C0402, Capacitor.CaseSize.C1206)
        )
        # 100% margin for output ripple voltage against transients + increase the DC capacitance
        self.NODEs.C8.set_rated_voltage(
            Constant((output_voltage.value + output_ripple_voltage.value) * 2)
        )
        self.NODEs.C9.set_rated_voltage(
            Constant((output_voltage.value + output_ripple_voltage.value) * 2)
        )

    def calc_inductor_value(
        self, input_voltage: Range, output_voltage: Constant, output_current: Constant
    ):
        # using low-ESR output caps, K_{ind} can be 0.3.
        K_ind = 0.3
        L_min = (
            output_voltage.value
            * (input_voltage.max - output_voltage.value)
            / (
                input_voltage.max
                * K_ind
                * output_current.value
                * self.switching_frequency
            )
        )

        # take lowest inductance for the highest I values
        L = L_min
        I_rms = sqrt(
            output_current.value**2
            + 1
            / 12
            * (
                output_voltage.value
                * (input_voltage.max - output_voltage.value)
                / (input_voltage.max * L * self.switching_frequency * 0.8)
            )
            ** 2
        )
        I_peak = output_current.value + output_voltage.value * (
            input_voltage.max - output_voltage.value
        ) / (1.6 * input_voltage.max * L * self.switching_frequency)
        log.debug(
            f"L_min: {float_to_si(L_min)}H, L: {float_to_si(L)}H, I_rms: {float_to_si(I_rms)}A, I_peak: {float_to_si(I_peak)}A"
        )
        # I_peak and I_rms are calculated based on L_range max
        self.NODEs.L1.set_inductance(Range(L_min, L_min * 1.5))
        # Max DC resistance of 100mOhm
        self.NODEs.L1.set_dc_resistance(Range(0, 0.3))
        self.NODEs.L1.set_rated_current(Constant(I_rms))
        self.NODEs.L1.set_tolerance(Constant(20))

    def calc_compensation_filter(
        self, output_voltage: Constant, output_current: Constant
    ):
        V_ggm = 800
        # the datasheet mentions their 2x47uF caps can have a DC capacitance as low as 54uF, so account for that error
        C_out_actual = (
            self.NODEs.C8.capacitance.min
            * 2
            * min(
                1,
                exp(
                    -(
                        (output_voltage.value - 0.5)
                        / (self.NODEs.C8.rated_voltage.value / 2)
                    )
                ),
            )
        )
        C_o = C_out_actual
        log.debug(f"Co: {C_o}")
        R_esr = 1e-3
        F_co = 25e3
        R_sense = 1 / 12
        R_o = output_voltage.value / output_current.value

        phase_loss = degrees(
            atan(2 * pi * F_co * R_esr * C_o) - atan(2 * pi * F_co * R_o * C_o)
        )
        phase_margin = 70
        phase_boost = (phase_margin - 90) - phase_loss

        k = tan(radians(phase_boost / 2 + 45))

        F_z1 = F_co / k
        F_p1 = F_co * k

        R_oa = 8e6
        GM_comp = 12

        # low frequency pole
        gain = -20 * log10(2 * pi * R_sense * F_co * C_o)
        R_z = (
            2
            * pi
            * F_co
            * output_voltage.value
            * C_o
            * R_oa
            / (GM_comp * V_ggm * self.reference_voltage)
        )
        C_z = 1 / (2 * pi * F_z1 * R_z)
        C_p = 1 / (2 * pi * F_p1 * R_z)

        log.debug(f"C_o = {float_to_si(C_o)}F")
        log.debug(f"Gain = {gain:.2f}dB")
        log.debug(f"PL = {phase_loss:.2f}deg")
        log.debug(f"F_z1 = {float_to_si(F_z1)}Hz")
        log.debug(f"F_p1 = {float_to_si(F_p1)}Hz")
        log.debug(f"R_z = {float_to_si(R_z)}Ohm")
        log.debug(f"C_z = {float_to_si(C_z)}F")
        log.debug(f"C_p = {float_to_si(C_p)}F")

        error_range = 0.12
        self.NODEs.R3.set_resistance(
            Range(R_z * (1 - error_range), R_z * (1 + error_range))
        )
        self.NODEs.C6.set_capacitance(
            Range(C_z * (1 - error_range), C_z * (1 + error_range))
        )
        self.NODEs.C7.set_capacitance(
            Range(C_p * (1 - error_range), C_p * (1 + error_range))
        )

    def check_input_output_voltage_range(
        self, input_voltage: Range, output_voltage: Constant, output_current: Constant
    ):
        # catch diode D1 forward voltage
        V_D = 0.55
        # output inductor series resistance
        R_L = 0.3
        # minimum output current
        I_o_min = 0
        #
        R_ds_on_min = 80e-3
        R_ds_on_max = 200e-3
        V_o_min = (
            0.089 * ((input_voltage.max - I_o_min * R_ds_on_min) + V_D)
            - (I_o_min * R_L)
            - V_D
        )
        if output_voltage.value < V_o_min:
            raise ValueError(
                f"Output voltage of {float_to_si(output_voltage.value)}V is lower than minimum output voltage of {float_to_si(V_o_min)}V"
            )
        V_o_max = (
            0.91 * ((input_voltage.min - output_current.value * R_ds_on_max) + V_D)
            - (output_current.value * R_L)
            - V_D
        )
        if output_voltage.value > V_o_max:
            raise ValueError(
                f"Output voltage of {float_to_si(output_voltage.value)}V is higher than maximum output voltage of {float_to_si(V_o_max)}V"
            )

    def calc_component_values(
        self,
        input_voltage: Range,
        output_voltage: Constant,
        input_ripple_voltage: Constant = Constant(0.25),
        output_ripple_voltage: Constant = Constant(0.05),
        output_current: Constant = Constant(0.5),
        output_voltage_accuracy: Constant = Constant(0.02),
    ):
        self.check_input_output_voltage_range(
            input_voltage, output_voltage, output_current
        )
        self.calc_slowstart_capacitor()
        if type(input_voltage) is Constant or type(input_voltage) is Range:
            self.calc_enable_resistors(input_voltage=input_voltage)

        self.calc_output_voltage_divider(output_voltage, output_voltage_accuracy)
        self.calc_input_capacitors(input_voltage, input_ripple_voltage, output_current)
        self.calc_inductor_value(input_voltage, output_voltage, output_current)
        self.calc_output_capacitors(
            input_voltage, output_voltage, output_current, output_ripple_voltage
        )
        self.calc_compensation_filter(output_voltage, output_current)

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

        class _IFs(super().IFS()):
            input = ElectricPower()
            output = ElectricPower()

        self.IFs = _IFs(self)

        class _NODEs(Module.NODES()):
            U1 = TPS54331DR()
            # divider for UVLO mechanism in enable pin
            R1 = Resistor(TBD, tolerance=Constant(1))
            R2 = Resistor(TBD, tolerance=Constant(1))
            # compensation resistor
            R3 = Resistor(TBD, tolerance=Constant(1))
            # R4 is omitted, not necessary in most designs
            # Divider for Vsense
            R5 = Resistor(TBD, tolerance=Constant(1))
            R6 = Resistor(TBD, tolerance=Constant(1))
            # input bulk caps
            C1 = Capacitor(
                capacitance=TBD,
                tolerance=Constant(20),
                rated_voltage=Constant(10),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X5R),
            )
            C2 = Capacitor(
                capacitance=TBD,
                tolerance=Constant(20),
                rated_voltage=Constant(10),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X5R),
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
                rated_voltage=Constant(25),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X7R),
            )
            # slow-start capacitor, abs. max voltage on SS pin is 3V
            C5 = Capacitor(
                capacitance=TBD,
                tolerance=Constant(10),
                rated_voltage=Constant(25),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X7R),
            )
            # Compensation capacitors, abs. max voltage on comp pin is 3V
            C6 = Capacitor(
                capacitance=TBD,
                tolerance=Constant(10),
                rated_voltage=Constant(16),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X7R),
            )
            C7 = Capacitor(
                capacitance=TBD,
                tolerance=Constant(10),
                rated_voltage=Constant(25),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X7R),
            )
            # output capacitors
            C8 = Capacitor(
                capacitance=TBD,
                tolerance=Constant(20),
                rated_voltage=TBD,
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X5R),
            )
            C9 = Capacitor(
                capacitance=TBD,
                tolerance=Constant(20),
                rated_voltage=TBD,
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X5R),
            )
            # Catch diode
            D1 = Diode(partnumber=Constant("B340A-13-F"))
            # Inductor
            L1 = Inductor(
                inductance=TBD,
                self_resonant_frequency=Range(0, self.switching_frequency * 1.2),
                rated_current=TBD,
                tolerance=Constant(20),
            )

        self.NODEs = _NODEs(self)

        self.NODEs.D1.add_trait(
            can_attach_to_footprint_via_pinmap(
                {
                    "1": self.NODEs.D1.IFs.cathode,
                    "2": self.NODEs.D1.IFs.anode,
                }
            )
        )

        # connect power and grounds
        gnd = self.IFs.input.NODEs.lv
        gnd.connect(self.IFs.output.NODEs.lv)
        self.IFs.input.connect(self.NODEs.U1.IFs.Vin)

        # input bulk and filter caps
        for cap in [self.NODEs.C1, self.NODEs.C2, self.NODEs.C3]:
            self.IFs.input.NODEs.hv.connect_via(cap, gnd)

        # enable UVLO divider
        self.IFs.input.NODEs.hv.connect_via(self.NODEs.R1, self.NODEs.U1.IFs.enable)
        self.NODEs.U1.IFs.enable.connect_via(self.NODEs.R2, gnd)

        # slow-start cap
        self.NODEs.U1.IFs.slow_start.connect_via(self.NODEs.C5, gnd)

        # boot capacitor
        self.NODEs.U1.IFs.boot.connect_via(self.NODEs.C4, self.NODEs.U1.IFs.PH)

        # catch diode
        self.NODEs.D1.IFs.anode.connect(gnd)
        self.NODEs.D1.IFs.cathode.connect(self.NODEs.U1.IFs.PH)

        # compensation filter
        self.NODEs.U1.IFs.compensation.connect_via(self.NODEs.C7, gnd)
        self.NODEs.U1.IFs.compensation.connect_via(
            self.NODEs.C6, self.NODEs.R3.IFs.unnamed[0]
        )
        self.NODEs.R3.IFs.unnamed[1].connect(gnd)

        # inductor
        self.NODEs.U1.IFs.PH.connect_via(self.NODEs.L1, self.IFs.output.NODEs.hv)

        # output caps
        self.IFs.output.NODEs.hv.connect_via(self.NODEs.C8, gnd)
        self.IFs.output.NODEs.hv.connect_via(self.NODEs.C9, gnd)

        # vsense divider
        self.IFs.output.NODEs.hv.connect_via(self.NODEs.R5, self.NODEs.U1.IFs.Vsense)
        self.NODEs.U1.IFs.Vsense.connect_via(self.NODEs.R6, gnd)

        self.calc_component_values(
            input_voltage,
            output_voltage,
            input_ripple_voltage,
            output_ripple_voltage,
            output_current,
            output_voltage_accuracy,
        )


class USB_C_PD_PSU(Module):
    pass


class STM32G473VET6(Module):
    """
    ST-Microelectronics MCU with 512kB flash, 128kB RAM, Cortex M4 core.
    """

    pass


class MCU(Module):
    pass


class Limiter(Module):
    pass


class Sensing(Module):
    pass


class Power_Frontend(Module):
    pass


class Logic_Analyzer_Frontend(Module):
    pass


class Display(Module):
    pass


class PPK_PD(Module):
    def __init__(self) -> None:
        super().__init__()

        class _NODEs(Module.NODES()):
            # power_supply = USB_C_PD_PSU()
            # mcu = MCU()
            # power_frontend = Power_Frontend()
            # logic_analyzer_frontend = Logic_Analyzer_Frontend()
            buck = Buck_Converter_TPS54331DR(
                input_voltage=Range(5, 22),
                output_voltage=Constant(4),
                output_current=Constant(0.5),
                output_ripple_voltage=Constant(0.001),
                input_ripple_voltage=Constant(0.1),
            )
            mounting_hole = times(4, Mounting_Hole)
            faebryk_logo = Faebryk_Logo()
            input_header = Pin_Header(1, 2, 2.54)
            output_header = Pin_Header(1, 2, 2.54)

        self.NODEs = _NODEs(self)

        self.NODEs.input_header.IFs.unnamed[0].connect(
            self.NODEs.buck.IFs.input.NODEs.lv
        )
        self.NODEs.input_header.IFs.unnamed[1].connect(
            self.NODEs.buck.IFs.input.NODEs.hv
        )
        self.NODEs.output_header.IFs.unnamed[0].connect(
            self.NODEs.buck.IFs.output.NODEs.lv
        )
        self.NODEs.output_header.IFs.unnamed[1].connect(
            self.NODEs.buck.IFs.output.NODEs.hv
        )

        pick_part(self)

        #         log.debug(
        #             f"R1 (UVLO div Ren1):     {float_to_si(self.NODEs.buck.NODEs.R1.resistance.value)}Ohm"
        #         )
        #         log.debug(
        #             f"R2 (UVLO div Ren2):     {float_to_si(self.NODEs.buck.NODEs.R2.resistance.value)}Ohm"
        #         )
        #         log.debug(
        #             f"R3 (comp R_z):          {float_to_si(self.NODEs.buck.NODEs.R3.resistance.value)}Ohm"
        #         )
        #         log.debug(
        #             f"R5 (Vout div1):         {float_to_si(self.NODEs.buck.NODEs.R5.resistance.value)}Ohm"
        #         )
        #         log.debug(
        #             f"R6 (Vout div2):         {float_to_si(self.NODEs.buck.NODEs.R6.resistance.value)}Ohm"
        #         )
        #         log.debug(
        #             f"C1 (input bulk 1):      {float_to_si(self.NODEs.buck.NODEs.C1.capacitance.value)}F"
        #         )
        #         log.debug(
        #             f"C2 (input bulk 2):      {float_to_si(self.NODEs.buck.NODEs.C2.capacitance.value)}F"
        #         )
        #         log.debug(
        #             f"C3 (hf input):          {float_to_si(self.NODEs.buck.NODEs.C3.capacitance.value)}F"
        #         )
        #         log.debug(
        #             f"C4 (boot):              {float_to_si(self.NODEs.buck.NODEs.C4.capacitance.value)}F"
        #         )
        #         log.debug(
        #             f"C5 (slow-start):        {float_to_si(self.NODEs.buck.NODEs.C5.capacitance.value)}F"
        #         )
        #         log.debug(
        #             f"C6 (comp C_z):          {float_to_si(self.NODEs.buck.NODEs.C6.capacitance.value)}F"
        #         )
        #         log.debug(
        #             f"C7 (comp C_p):          {float_to_si(self.NODEs.buck.NODEs.C7.capacitance.value)}F"
        #         )
        #         log.debug(
        #             f"C8 (output bulk 1):     {float_to_si(self.NODEs.buck.NODEs.C8.capacitance.value)}F"
        #         )
        #         log.debug(
        #             f"C9 (output bulk 2):     {float_to_si(self.NODEs.buck.NODEs.C9.capacitance.value)}F"
        #         )
        #         log.debug(
        #             f"L1 (ind):               {float_to_si(self.NODEs.buck.NODEs.L1.inductance.value)}H"
        #         )

        # hack footprints
        for r in get_all_nodes(self) + [self]:
            if not r.has_trait(has_footprint):
                assert type(r) in [
                    Buck_Converter_TPS54331DR,
                    PPK_PD,
                ], f"{r}"
            if not r.has_trait(can_attach_via_pinmap):
                r.add_trait(can_attach_to_footprint_symmetrically())