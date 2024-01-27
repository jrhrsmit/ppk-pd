import logging

from faebryk.core.core import Parameter
from faebryk.library.Constant import Constant
from faebryk.library.has_designator_prefix_defined import has_designator_prefix_defined
from faebryk.library.has_simple_value_representation_defined import (
    has_simple_value_representation_defined,
)
from faebryk.library.Range import Range
from faebryk.library.TBD import TBD
from library.jlcpcb.util import (
    float_to_si,
    jlcpcb_db,
)
from library.library.components import MOSFET

logger = logging.getLogger(__name__)


def build_mosfet_package_query(package: Parameter) -> str:
    if package is TBD:
        return ""
    elif type(package) is Constant:
        return f"AND package = {package.value}"
    else:
        raise NotImplementedError


def parameter_to_string(parameter: Parameter, unit: str) -> str:
    if type(parameter) is Constant:
        return f"{float_to_si(parameter.value)}{unit}"
    elif type(parameter) is Range:
        return (
            f"{float_to_si(parameter.min)}{unit} - {float_to_si(parameter.max)}{unit}"
        )
    else:
        raise NotImplementedError


def log_result(lcsc_pn: str, cmp: MOSFET):
    if type(cmp.channel_type) is Constant:
        channel_type_str = cmp.channel_type.value.name
    else:
        raise NotImplementedError

    if type(cmp.package) is Constant:
        package_str = f"{float_to_si(cmp.package.value)}"
    else:
        package_str = "None specified"

    drain_source_resistance_str = parameter_to_string(cmp.drain_source_resistance, "Ω")
    gate_source_threshold_voltage_str = parameter_to_string(
        cmp.gate_source_threshold_voltage, "V"
    )
    drain_source_voltage_str = parameter_to_string(cmp.drain_source_voltage, "V")
    power_dissipation_str = parameter_to_string(cmp.power_dissipation, "W")
    continuous_drain_current_str = parameter_to_string(
        cmp.continuous_drain_current, "A"
    )

    cmp_name = ".".join([pname for parent, pname in cmp.get_hierarchy()])
    logger.info(
        f"Picked {lcsc_pn: <8} for component {cmp_name} (Channel type: {channel_type_str}, Package: {package_str}, Drain-source resistance: {drain_source_resistance_str}, Gate-source threshold voltage: {gate_source_threshold_voltage_str}, Drain-source voltage: {drain_source_voltage_str}, Power dissipation: {power_dissipation_str}, Continuous drain current: {continuous_drain_current_str})"
    )


def compare_float_against_parameter(value: float, parameter: Parameter):
    if type(parameter) is Constant:
        if value != parameter.value:
            return False
    elif type(parameter) is Range:
        if value < parameter.min:
            return False
        if value > parameter.max:
            return False
    else:
        raise NotImplementedError
    return True


def find_mosfet(
    db: jlcpcb_db,
    cmp: MOSFET,
    quantity: int = 1,
    moq: int = 50,
):
    """
    Find the LCSC part number of a MOSFET which is in stock at JLCPCB.
    """

    package_query = build_mosfet_package_query(cmp.package)

    query = f"""
        {package_query}
        AND stock > {moq}
        ORDER BY basic DESC, price ASC
        """

    categories = db.get_category_id(category="Transistor", subcategory="MOSFET")

    db.query_category(categories, query)

    if isinstance(cmp.channel_type, Constant):
        if cmp.channel_type.value == MOSFET.ChannelType.N_CHANNEL:
            db.filter_results_by_extra_json_attributes("Type", Constant("N Channel"))
        else:
            db.filter_results_by_extra_json_attributes("Type", Constant("P Channel"))

    db.filter_results_by_extra_json_attributes(
        "Continuous Drain Current (Id)", cmp.continuous_drain_current
    )
    db.filter_results_by_extra_json_attributes(
        "Drain Source Voltage (Vdss)", cmp.drain_source_voltage
    )
    db.filter_results_by_extra_json_attributes(
        "Power Dissipation (Pd)", cmp.power_dissipation
    )
    db.filter_results_by_extra_json_attributes(
        "Gate Threshold Voltage (Vgs(th)@Id)",
        cmp.gate_source_threshold_voltage,
        lambda x: x.split("@")[0],
    )
    db.filter_results_by_extra_json_attributes(
        "Drain Source On Resistance (RDS(on)@Vgs,Id)",
        cmp.drain_source_resistance,
        lambda x: x.split("@")[0],
    )

    part = db.sort_by_basic_price(quantity)

    lcsc_pn = "C" + str(part["lcsc_pn"])
    cmp.add_trait(has_simple_value_representation_defined(part["manufacturer_pn"]))
    log_result(lcsc_pn, cmp)

    return lcsc_pn
