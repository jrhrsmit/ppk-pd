import logging

logger = logging.getLogger(__name__)

import sqlite3
from library.library.components import MOSFET
from faebryk.library.has_defined_type_description import has_defined_type_description
from library.jlcpcb.util import (
    float_to_si,
    si_to_float,
    get_value_from_pn,
    sort_by_basic_price,
    connect_to_db,
    jlcpcb_query,
)
from library.e_series import e_series_in_range
from faebryk.core.core import Module, Parameter, Footprint
import json
import re
from faebryk.library.Constant import Constant
from faebryk.library.Range import Range
from faebryk.library.TBD import TBD


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


def mosfet_filter(
    query: jlcpcb_query,
    cmp: MOSFET,
):
    filtered_resuls = []
    if type(cmp.channel_type) is Constant:
        for r in query.results:
            try:
                extra_json = json.loads(r["extra"])
            except:
                logger.debug(f"Could not parse extra JSON for {r['extra']}")
                continue

            try:
                attributes = extra_json["attributes"]
            except:
                logger.debug(
                    f"Could not extract attributes from extra JSON for {extra_json}"
                )
                continue

            try:
                Id = si_to_float(attributes["Continuous Drain Current (Id)"])
                Type = attributes["Type"]
                Vds = si_to_float(attributes["Drain Source Voltage (Vdss)"])
                Pd = si_to_float(attributes["Power Dissipation (Pd)"])
                Vgs_th = si_to_float(
                    attributes["Gate Threshold Voltage (Vgs(th)@Id)"].split("@")[0]
                )
                rds_on = si_to_float(
                    attributes["Drain Source On Resistance (RDS(on)@Vgs,Id)"].split(
                        "@"
                    )[0]
                )
            except:
                logger.debug(
                    f"Could not extract parameters from extra JSON for {attributes}"
                )
                continue

            if type(cmp.channel_type) != Constant:
                raise NotImplementedError
            if (
                cmp.channel_type.value == MOSFET.ChannelType.N_CHANNEL
                and Type != "N Channel"
            ) or (
                cmp.channel_type == cmp.ChannelType.P_CHANNEL and Type != "P Channel"
            ):
                continue

            if (
                compare_float_against_parameter(Id, cmp.continuous_drain_current)
                == False
            ):
                logger.debug(f"Id {Id} does not match {cmp.continuous_drain_current}")
                continue
            if compare_float_against_parameter(Vds, cmp.drain_source_voltage) == False:
                logger.debug(f"Vds {Vds} does not match {cmp.drain_source_voltage}")
                continue
            if compare_float_against_parameter(Pd, cmp.power_dissipation) == False:
                logger.debug(f"Pd {Pd} does not match {cmp.power_dissipation}")
                continue
            if (
                compare_float_against_parameter(
                    Vgs_th, cmp.gate_source_threshold_voltage
                )
                == False
            ):
                logger.debug(
                    f"Vgs_th {Vgs_th} does not match {cmp.gate_source_threshold_voltage}"
                )
                continue
            if (
                compare_float_against_parameter(rds_on, cmp.drain_source_resistance)
                == False
            ):
                logger.debug(
                    f"rds_on {rds_on} does not match {cmp.drain_source_resistance}"
                )
                continue

            filtered_resuls.append(r)

    query.results = filtered_resuls


def find_mosfet(
    cmp: MOSFET,
    quantity: int = 1,
    moq: int = 50,
):
    """
    Find the LCSC part number of a MOSFET which is in stock at JLCPCB.
    """

    package_query = build_mosfet_package_query(cmp.package)

    query = f"""
        SELECT lcsc, mfr, basic, price, extra, description
        FROM "main"."components" 
        WHERE (category_id = 97 or category_id = 98)
        {package_query}
        AND stock > {moq}
        ORDER BY basic DESC, price ASC
        """

    q = jlcpcb_query(query)

    mosfet_filter(q, cmp)

    logger.info(f"Found {len(q.results)} results after filtering")

    sorted_res = q.sort_by_basic_price()

    lcsc_pn = "C" + str(q.results[0]["lcsc"])
    cmp.add_trait(has_defined_type_description(q.results[0]["manufacturer_pn"]))
    log_result(lcsc_pn, cmp)

    return lcsc_pn
