# library imports
import logging
import math

# Project library imports
from math import atan, degrees, exp, log10, pi, radians, sqrt, tan  # noqa: E402

from faebryk.core.core import Module, Parameter
from faebryk.core.util import get_all_nodes
from faebryk.library.can_attach_to_footprint_symmetrically import (
    can_attach_to_footprint_symmetrically,
)
from faebryk.library.can_attach_to_footprint_via_pinmap import (
    can_attach_to_footprint_via_pinmap,
)
from faebryk.library.can_attach_via_pinmap import can_attach_via_pinmap
from faebryk.library.Capacitor import Capacitor
from faebryk.library.Constant import Constant
from faebryk.library.Diode import Diode
from faebryk.library.Electrical import Electrical
from faebryk.library.ElectricLogic import ElectricLogic
from faebryk.library.ElectricPower import ElectricPower
from faebryk.library.has_footprint import has_footprint
from faebryk.library.Range import Range
from faebryk.library.Resistor import Resistor
from faebryk.library.TBD import TBD

# function imports
from faebryk.libs.util import times
from library.e_series import (
    E12,
    E24,
    E48,
    e_series_in_range,
    e_series_ratio,
)
from library.jlcpcb.part_picker import pick_part
from library.jlcpcb.util import float_to_si
from library.library.components import (
    MOSFET,
    TL072CDT,
    TPS54331DR,
    Faebryk_Logo,
    Inductor,
    Mounting_Hole,
    Pin_Header,
)
from faebryk.core.util import (
    as_unit,
    as_unit_with_tolerance,
)

log = logging.getLogger(__name__)


class Boost_Converter_TPS61040DBVR(Module):
    pass


class Instrumentation_Amplifier_TL072CP(Module):
    """
    Dual Instrumentation amplifier based on 3x TL072CP.

    For schematic, see https://en.wikipedia.org/wiki/Instrumentation_amplifier
    """

    def set_gain(self, gain: list[Parameter]):
        if len(gain) != 2:
            raise ValueError("Gain must be a list of two parameters")
        self.gain = gain
        if isinstance(gain, Constant):
            # Assume R2 = R3
            for rg, r1s in self.NODEs.rgs, self.NODEs.r1s:
                assert r1s[0].resistance == r1s[1].resistance
                rg.set_resistance(
                    Constant(2 * r1s[0].resistance.value / gain.value - 1)
                )
        elif isinstance(gain, Range):
            # Assume R2 = R3
            for rg, r1s in self.NODEs.rgs, self.NODEs.r1s:
                assert r1s[0].resistance == r1s[1].resistance
                rg.set_resistance(
                    Range(
                        2 * r1s[0].resistance.value / gain.max - 1,
                        2 * r1s[0].resistance.value / gain.min - 1,
                    )
                )

    def __init__(self, gain: list[Parameter]) -> None:
        super().__init__()

        class _IFs(super().IFS()):
            power_input = ElectricPower()
            outputs = times(2, Electrical)
            inverting_inputs = times(2, Electrical)
            non_inverting_inputs = times(2, Electrical)
            offsets = times(2, Electrical)

        class _NODEs(super().NODES()):
            buffers = times(2, lambda: times(2, TL072CDT))
            differential_opamps = times(2, TL072CDT)
            r1s = times(
                2, lambda: times(2, lambda: Resistor(resistance=Constant(100e3)))
            )
            r2s = times(
                2, lambda: times(2, lambda: Resistor(resistance=Constant(100e3)))
            )
            r3s = times(
                2, lambda: times(2, lambda: Resistor(resistance=Constant(100e3)))
            )
            rgs = times(2, lambda: Resistor(resistance=TBD))

        self.IFs = _IFs(self)
        self.NODEs = _NODEs(self)

        for (
            inverting_input,
            non_inverting_input,
            output,
            offset,
            buffer,
            diff_opamp,
            r1,
            r2,
            r3,
            rg,
        ) in zip(
            self.IFs.inverting_inputs,
            self.IFs.non_inverting_inputs,
            self.IFs.outputs,
            self.IFs.offsets,
            self.NODEs.buffers,
            self.NODEs.differential_opamps,
            self.NODEs.r1s,
            self.NODEs.r2s,
            self.NODEs.r2s,
            self.NODEs.rgs,
        ):
            # Connect the buffers to the inputs
            inverting_input.connect(buffer[0].IFs.non_inverting_input)
            non_inverting_input.connect(buffer[1].IFs.non_inverting_input)
            # connect R1
            for (
                b,
                r,
            ) in zip(buffer, r1):
                b.IFs.output.connect_via(r, b.IFs.inverting_input)
            # connect Rg
            buffer[0].connect_via(rg, buffer[1])
            # connect R2
            buffer[0].IFs.output.connect_via(r2[0], diff_opamp.IFs.inverting_input)
            buffer[1].IFs.output.connect_via(r2[1], diff_opamp.IFs.non_inverting_input)
            # connect R3
            diff_opamp.IFs.output.connect_via(r3[0], diff_opamp.IFs.inverting_input)
            diff_opamp.IFs.non_inverting_input.connect_via(r3[1], offset)
            # connect output
            diff_opamp.IFs.output.connect(output)


class Automatic_Sensing_Resistor_Switching(Module):
    """
    Automatic sensing resistor switching circuit.

    This circuit automatically switches between sensing resistors to
    match the current range. It uses a MOSFET to switch between the
    resistors, and an instrumentation amplifier to amplify the voltage
    drop across the resistor to the ADC range.

    The power_input_logic should have a 3V margin on the negative rail
    and a 5V margin on the positive rail of the power input.
    power_input_logic.IFs.hv >= power_input.IFs.hv + 5V
    power_input_logic.IFs.lv <= power_input.IFs.lv - 3V

    power_input has a maximum voltage of 22V.

    """

    def set_current_range(self, current_range: Parameter):
        assert type(current_range) == Range
        self.current_range = current_range

    def set_voltage_range(self, voltage_range: Parameter):
        assert type(voltage_range) == Range
        self.voltage_range = voltage_range

    def set_hysteresis(self, hysteresis: Parameter):
        assert type(hysteresis) == Constant
        self.hysteresis = hysteresis

    def set_sense_voltage_range(self, sense_voltage_range: Parameter):
        assert type(sense_voltage_range) == Range
        self.sense_voltage_range = sense_voltage_range

    def set_adc_voltage_range(self, adc_voltage_range: Parameter):
        assert type(adc_voltage_range) == Range
        self.adc_voltage_range = adc_voltage_range

    def construct_sense_resistors(self) -> list[Resistor]:
        sense_resistor_values = []
        r_sense = Range(
            self.sense_voltage_range.max / self.current_range.max,
            self.sense_voltage_range.min / self.current_range.min,
        )

        # select first (highest) sensing resistor in E series
        sense_resistor_values.append(
            e_series_in_range(Range(r_sense.max, r_sense.max * 10), E12)[0]
        )

        while True:
            r = sense_resistor_values[-1]
            r_max_current = self.sense_voltage_range.max / r
            if r_max_current >= self.current_range.max:
                break
            r_next_min = (
                r
                / (1 - self.hysteresis.value)
                / (self.sense_voltage_range.max / self.sense_voltage_range.min)
            )
            if r_next_min < r_sense.min:
                sense_resistor_values.append(
                    e_series_in_range(Range(r_next_min / 10, r_sense.min), E12)[-1]
                )
                break
            sense_resistor_values.append(
                e_series_in_range(Range(r_next_min, r_next_min * 10), E12)[0]
            )

        sense_resistors = []
        # set case sizes according to max power
        for r in sense_resistor_values:
            i_max = min(self.sense_voltage_range.max / r, self.current_range.max)
            p_max = i_max**2 * r
            sense_resistors.append(
                Resistor(
                    resistance=Constant(r),
                    tolerance=Range(0, 1),
                    rated_power=Constant(p_max),
                    case_size=Range(Resistor.CaseSize.R0402, Resistor.CaseSize.R2512),
                ),
            )
            # sense_resistors[-1].set_case_size_by_power(Constant(p_max))

        return sense_resistors

    def __init__(
        self,
        voltage_range: Parameter,
        sense_voltage_range: Parameter,
        adc_voltage_range: Parameter,
        current_range: Parameter,
        hysteresis: Parameter,
    ) -> None:
        super().__init__()

        self.set_voltage_range(voltage_range)
        self.set_current_range(current_range)
        self.set_sense_voltage_range(sense_voltage_range)
        self.set_hysteresis(hysteresis)
        self.set_adc_voltage_range(adc_voltage_range)

        sense_resistor_list = self.construct_sense_resistors()

        class _IFs(Module.IFS()):
            power_input = ElectricPower()
            power_output = ElectricPower()
            power_input_logic = ElectricPower()
            power_input_adc = ElectricPower()
            adc_output = times(len(sense_resistor_list), Electrical)
            resistor_status = times(len(sense_resistor_list), ElectricLogic)

        class _NODEs(Module.NODES()):
            sensing_resistors = sense_resistor_list
            nmoses = times(
                len(sense_resistor_list),
                lambda: MOSFET(
                    channel_type=Constant(MOSFET.ChannelType.N_CHANNEL),
                    drain_source_voltage=Range(25, float("inf")),
                    continuous_drain_current=Range(5.5, float("inf")),
                    drain_source_resistance=TBD,
                    gate_source_threshold_voltage=Range(0.5, 8),
                    power_dissipation=TBD,
                    package=TBD,
                ),
            )
            dual_instrumentation_amplifiers = times(
                math.ceil(len(sense_resistor_list) / 2),
                lambda: Instrumentation_Amplifier_TL072CP(gain=TBD),
            )
            output_voltage_limiting_diodes = times(len(sense_resistor_list) * 2, Diode)
            output_current_limiting_resitors = times(
                len(sense_resistor_list), lambda: Resistor(Constant(1.8e3))
            )

        self.IFs = _IFs(self)
        self.NODEs = _NODEs(self)

        gain_max = self.adc_voltage_range.max / self.sense_voltage_range.max
        amp_offset_voltage = 3e-3
        offset_error_max = (gain_max + 1) * amp_offset_voltage * 2
        gain_max = (
            self.adc_voltage_range.max - offset_error_max
        ) / self.sense_voltage_range.max
        gain = Range(0.9 * gain_max, gain_max)
        # Set amplifier gain
        for amp in self.NODEs.dual_instrumentation_amplifiers:
            amp.set_gain([gain, gain])

        # Set parameters for NMOSes
        for nmos, rs in zip(self.NODEs.nmoses, self.NODEs.sensing_resistors):
            max_rds_on = 30e-3
            assert isinstance(rs.resistance, Constant)
            nmos.set_drain_source_resistance(Range(0, max_rds_on))
            # Set the maximum power dissipation
            max_current = self.sense_voltage_range.max / rs.resistance.value
            max_power = max_current**2 * max_rds_on
            nmos.set_power_dissipation(Range(max_power, float("inf")))

        # connect components
        for (
            i,
            [nmos, rs],
        ) in enumerate(
            zip(
                self.NODEs.nmoses,
                self.NODEs.sensing_resistors,
            )
        ):
            self.IFs.power_input.IFs.hv.connect(nmos.IFs.drain)
            nmos.IFs.source.connect_via(rs, self.IFs.power_output.IFs.hv)
            dual_amp_i = math.floor(i / 2)
            amp_i = i % 2
            nmos.IFs.source.connect(
                self.NODEs.dual_instrumentation_amplifiers[
                    dual_amp_i
                ].IFs.non_inverting_inputs[amp_i]
            )
            self.IFs.power_output.IFs.hv.connect(
                self.NODEs.dual_instrumentation_amplifiers[
                    dual_amp_i
                ].IFs.inverting_inputs[amp_i]
            )

        # connect amplifiers to sensing resistors and output
        for i, amp in enumerate(self.NODEs.dual_instrumentation_amplifiers):
            self.IFs.power_input_logic.connect(amp.IFs.power_input)
            amp.IFs.outputs[0].connect_via(
                self.NODEs.output_current_limiting_resitors[i * 2],
                self.IFs.adc_output[i * 2],
            )
            if i * 2 + 1 < len(self.NODEs.sensing_resistors):
                break
            amp.IFs.outputs[1].connect_via(
                self.NODEs.output_current_limiting_resitors[i * 2 + 1],
                self.IFs.adc_output[i * 2 + 1],
            )

        # Connect voltage limiting diodes
        for i, output in enumerate(self.IFs.adc_output):
            output.connect_via(
                self.NODEs.output_voltage_limiting_diodes[2 * i],
                self.IFs.power_input_adc.IFs.hv,
            )
            self.IFs.power_input_adc.IFs.lv.connect_via(
                self.NODEs.output_voltage_limiting_diodes[2 * i + 1], output
            )

        self.IFs.power_input.IFs.lv.connect(self.IFs.power_output.IFs.lv)

        # set partnumbers for voltage limiting diodes
        for diode in self.NODEs.output_voltage_limiting_diodes:
            diode.set_partnumber(Constant("1N5819WS"))


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
        self.NODEs.L1.set_rated_current(Range(I_rms, float("inf")))
        self.NODEs.L1.set_tolerance(Range(0, 20))

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
        self,
        input_voltage: Parameter,
        output_voltage: Parameter,
        output_current: Parameter,
    ):
        # catch diode D1 forward voltage
        V_D = Constant(0.55)
        # output inductor series resistance
        R_L = Constant(0.3)
        # Drain to source on resistance of internal MOSFET
        R_ds_on = Range(80e-3, 200e-3)

        if type(input_voltage) is Range:
            V_i = input_voltage
        elif type(input_voltage) is Constant:
            V_i = Range(input_voltage, input_voltage)

        if type(output_current) is Range:
            I_o = output_current
        elif type(output_current) is Constant:
            I_o = Range(output_current, output_current)

        if type(output_voltage) is Range:
            V_o = output_voltage
        elif type(output_voltage) is Constant:
            V_o = Range(output_voltage, output_voltage)

        V_o_costraint = Range(
            Constant(0.089) * (Constant(V_i.min - I_o.min * R_ds_on.min) + V_D)
            - (I_o.min * R_L)
            - V_D,
            Constant(0.91) * (Constant(input_voltage.min - I_o.max * R_ds_on.max) + V_D)
            - (I_o.max * R_L)
            - V_D,
        )

        if V_o_costraint.min > V_o.min:
            raise ValueError(
                f"Output voltage of {as_unit_with_tolerance(output_voltage, 'V')} "
                "is lower than minimum output voltage of "
                f"{as_unit_with_tolerance(V_o, 'V')}"
            )
        if V_o_costraint.max < V_o.max:
            raise ValueError(
                f"Output voltage of {as_unit_with_tolerance(output_voltage,'V')} "
                " is higher than maximum output voltage of "
                f"{as_unit_with_tolerance(V_o, 'V')}"
            )

    def calc_component_values(
        self,
        input_voltage: Parameter,
        output_voltage: Parameter,
        input_ripple_voltage: Parameter,
        output_ripple_voltage: Parameter,
        output_current: Parameter,
        output_voltage_accuracy: Parameter,
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

        class PARAMS(super().PARAMS()):
            # Switching frequency is fixed at 570kHz
            switching_frequency = Constant(570e3)
            # reference voltage is at 800mV
            reference_voltage = Constant(800e-3)

            input_voltage = TBD()
            output_voltage = TBD()
            input_ripple_voltage = Constant(0.25)
            output_ripple_voltage = Constant(0.05)
            output_current = Constant(0.5)
            output_voltage_accuracy = Constant(0.02)

        self.PARAMs = PARAMS(self)

        class _IFs(super().IFS()):
            input = ElectricPower()
            output = ElectricPower()

        self.IFs = _IFs(self)

        class _NODEs(Module.NODES()):
            U1 = TPS54331DR()
            # divider for UVLO mechanism in enable pin
            R1 = Resistor()
            R2 = Resistor()
            # compensation resistor
            R3 = Resistor()
            # R4 is omitted, not necessary in most designs
            # Divider for Vsense
            R5 = Resistor()
            R6 = Resistor()
            # input bulk caps
            C1 = Capacitor().builder(
                lambda c: (
                    c.PARAMs.rated_voltage.merge(Range.lower_bound(10)),
                    c.PARAMs.temperature_coefficient.merge(
                        Range.lower_bound(
                            Capacitor.TemperatureCoefficient.X5R,
                        )
                    ),
                )
            )
            C2 = Capacitor().builder(
                lambda c: (
                    c.PARAMs.rated_voltage.merge(Range.lower_bound(10)),
                    c.PARAMs.temperature_coefficient.merge(
                        Range.lower_bound(
                            Capacitor.TemperatureCoefficient.X5R,
                        )
                    ),
                )
            )
            # input HF filter cap of 10nF
            C3 = Capacitor().builder(
                lambda c: (
                    c.PARAMs.capacitance.merge(Range.from_center(10e-9, 2e-9)),
                    c.PARAMs.rated_voltage.merge(Range.lower_bound(50)),
                    c.PARAMs.temperature_coefficient.merge(
                        Range.lower_bound(Capacitor.TemperatureCoefficient.X7R)
                    ),
                )
            )
            # boot capacitor, always 100nF
            C4 = Capacitor().builder(
                lambda c: (
                    c.PARAMs.capacitance.merge(Range.from_center(100e-9, 10e-9)),
                    c.PARAMs.rated_voltage.merge(Range.lower_bound(25)),
                    c.PARAMs.temperature_coefficient.merge(
                        Range.lower_bound(Capacitor.TemperatureCoefficient.X7R)
                    ),
                )
            )
            # slow-start capacitor, abs. max voltage on SS pin is 3V
            C5 = Capacitor().builder(
                lambda c: (
                    c.PARAMs.capacitance.merge(TBD()),
                    c.PARAMs.rated_voltage.merge(Range.lower_bound(25)),
                    c.PARAMs.temperature_coefficient.merge(
                        Range.lower_bound(Capacitor.TemperatureCoefficient.X7R)
                    ),
                )
            )
            # Compensation capacitors, abs. max voltage on comp pin is 3V
            C6 = Capacitor().builder(
                lambda c: (
                    c.PARAMs.rated_voltage.merge(Range.lower_bound(16)),
                    c.PARAMs.temperature_coefficient.merge(
                        Range.lower_bound(Capacitor.TemperatureCoefficient.X7R)
                    ),
                )
            )
            C7 = Capacitor().builder(
                lambda c: (
                    c.PARAMs.rated_voltage.merge(Range.lower_bound(25)),
                    c.PARAMs.temperature_coefficient.merge(
                        Range.lower_bound(Capacitor.TemperatureCoefficient.X7R)
                    ),
                )
            )
            # output capacitors
            C8 = Capacitor().builder(
                lambda c: (
                    c.PARAMs.temperature_coefficient.merge(
                        Range.lower_bound(Capacitor.TemperatureCoefficient.X5R)
                    ),
                )
            )
            C9 = Capacitor().builder(
                lambda c: (
                    c.PARAMs.temperature_coefficient.merge(
                        Range.lower_bound(Capacitor.TemperatureCoefficient.X5R)
                    ),
                )
            )
            # Catch diode
            # TODO: partnumber=Constant("B340A-13-F"))
            D1 = Diode()

            # Inductor
            L1 = Inductor(
                inductance=TBD,
                self_resonant_frequency=TBD,  # Constant(self.switching_frequency * 1.2),
                rated_current=TBD,
                tolerance=Range(0, 0.2),
                inductor_type=Constant(Inductor.InductorType.Power),
            )

        self.NODEs = _NODEs(self)

        # TODO: check if this is necessary, is it for LCSC footprint compatibility?
        self.NODEs.D1.add_trait(
            can_attach_to_footprint_via_pinmap(
                {
                    "1": self.NODEs.D1.IFs.cathode,
                    "2": self.NODEs.D1.IFs.anode,
                }
            )
        )

        # connect power and grounds
        gnd = self.IFs.input.IFs.lv
        gnd.connect(self.IFs.output.IFs.lv)
        self.IFs.input.connect(self.NODEs.U1.IFs.Vin)

        # input bulk and filter caps
        for cap in [self.NODEs.C1, self.NODEs.C2, self.NODEs.C3]:
            self.IFs.input.IFs.hv.connect_via(cap, gnd)

        # enable UVLO divider
        self.IFs.input.IFs.hv.connect_via(self.NODEs.R1, self.NODEs.U1.IFs.enable)
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
        self.NODEs.U1.IFs.PH.connect_via(self.NODEs.L1, self.IFs.output.IFs.hv)

        # output caps
        self.IFs.output.IFs.hv.connect_via(self.NODEs.C8, gnd)
        self.IFs.output.IFs.hv.connect_via(self.NODEs.C9, gnd)

        # vsense divider
        self.IFs.output.IFs.hv.connect_via(self.NODEs.R5, self.NODEs.U1.IFs.Vsense)
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
            buck = Buck_Converter_TPS54331DR().builder(
                lambda b: (
                    b.PARAMs.input_voltage.merge(Range(5, 22)),
                    b.PARAMs.output_voltage.merge(Range.from_center(4, 0.01)),
                    b.PARAMs.output_current.merge(Range.lower_bound(0.5)),
                    b.PARAMs.output_ripple_voltage.merge(Range.upper_bound(0.001)),
                    b.PARAMs.input_ripple_voltage.merge(Range.upper_bound(0.1)),
                )
            )
            mounting_hole = times(4, Mounting_Hole)
            faebryk_logo = Faebryk_Logo()
            input_header = Pin_Header(1, 2, 2.54)
            output_header = Pin_Header(1, 2, 2.54)
            # auto_sense_resistors = Automatic_Sensing_Resistor_Switching(
            #     voltage_range=Range(0, 22),
            #     sense_voltage_range=Range(100e-6, 100e-3),
            #     current_range=Range(1e-9, 5),
            #     hysteresis=Constant(0.2),
            # )

        self.NODEs = _NODEs(self)

        self.NODEs.input_header.IFs.unnamed[0].connect(self.NODEs.buck.IFs.input.IFs.lv)
        self.NODEs.input_header.IFs.unnamed[1].connect(self.NODEs.buck.IFs.input.IFs.hv)
        self.NODEs.output_header.IFs.unnamed[0].connect(
            self.NODEs.buck.IFs.output.IFs.lv
        )
        self.NODEs.output_header.IFs.unnamed[1].connect(
            self.NODEs.buck.IFs.output.IFs.hv
        )

        # # list sense resistors and their minimum and maximum currents, and case size
        # for r in self.NODEs.auto_sense_resistors.NODEs.sensing_resistors:
        #     log.info(
        #         # f"{float_to_si(r.resistance.value)}Ohm : {float_to_si(self.NODEs.auto_sense_resistors.sense_voltage_range.min / r.resistance.value)}A - {float_to_si(self.NODEs.auto_sense_resistors.sense_voltage_range.max / r.resistance.value)}A : {r.case_size.value.name}"
        #         f"{float_to_si(r.resistance.value)}Ohm : {float_to_si(self.NODEs.auto_sense_resistors.sense_voltage_range.min / r.resistance.value)}A - {float_to_si(self.NODEs.auto_sense_resistors.sense_voltage_range.max / r.resistance.value)}A"
        #     )

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
                    Automatic_Sensing_Resistor_Switching,
                ], f"{r}"
            if not r.has_trait(can_attach_via_pinmap):
                r.add_trait(can_attach_to_footprint_symmetrically())
