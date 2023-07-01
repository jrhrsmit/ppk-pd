import logging

logger = logging.getLogger(__name__)

import sqlite3
from library.library.components import Capacitor
from faebryk.library.core import Parameter
from faebryk.library.library.parameters import Range, Constant
from faebryk.library.traits.parameter import (
    is_representable_by_single_value,
)
from library.jlcpcb.util import float_to_si, sort_by_basic_price
from library.e_series import e_series_in_range


def build_capacitor_temperature_coefficient_query(
    temperature_coefficient: Parameter,
):
    if type(temperature_coefficient) is Constant:
        value_min = temperature_coefficient.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
        value_max = Capacitor.TemperatureCoefficient.C0G
    elif type(temperature_coefficient) is Range:
        value_min = temperature_coefficient.min
        value_max = temperature_coefficient.max
    else:
        raise NotImplementedError

    query = "("
    add_or = False
    for tc in Capacitor.TemperatureCoefficient:
        if tc >= value_min and tc <= value_max:
            if add_or:
                query += " OR "
            else:
                add_or = True
            query += "description LIKE '%" + tc.name + "%'"

    query += ")"
    return query


def build_capacitor_tolerance_query(capacitance: Parameter, tolerance: Constant):
    if type(tolerance) is not Constant:
        raise NotImplementedError

    max_tolerance_percent = tolerance.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()

    if type(capacitance) is Constant:
        value = capacitance.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
    elif type(capacitance) is Range:
        value = capacitance.min
    else:
        raise NotImplementedError

    tolerances = {
        "0.1pF": 0.1e-12,
        "0.25pF": 0.25e-12,
        "0.5pF": 0.5e-12,
        "1%": 0.01 * value,
        "2%": 0.02 * value,
        "2.5%": 0.025 * value,
        "5%": 0.05 * value,
        "10%": 0.10 * value,
        "15%": 0.15 * value,
        "20%": 0.20 * value,
    }
    plusminus = "±"
    query = "("
    add_or = False
    for tolerance_str, tolerance_abs in tolerances.items():
        if tolerance_abs <= max_tolerance_percent / 100 * value:
            if add_or:
                query += " OR "
            else:
                add_or = True
            tolerance_str_escape = tolerance_str.replace("%", "\%")
            query += "description LIKE '%" + plusminus + tolerance_str_escape + "%'"
            query += " ESCAPE '\\'"

    query += ")"
    return query


def build_capacitor_value_query(capacitance: Parameter):
    if type(capacitance) is Constant:
        value = capacitance.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
        value_str = float_to_si(value) + "F"
        query = (
            f"(description LIKE '% {value_str}%' OR description LIKE '{value_str}%')"
        )
        return query
    elif type(capacitance) is Range:
        e_values = e_series_in_range(capacitance)
        query = "("
        add_or = False
        for value in e_values:
            if add_or:
                query += " OR "
            else:
                add_or = True
            value_str = float_to_si(value) + "F"
            query += (
                f"description LIKE '% {value_str}%' OR description LIKE '{value_str}%'"
            )

            # JLCPCB uses both nF and uF for caps in the >=10nF,<1uF range
            if (
                "nF" in value_str
                and not "." in value_str
                and len(value_str.rstrip("nF")) >= 2
            ):
                value_uf_str = f"0.{value_str.rstrip('nF'):03}".rstrip("0") + "uF"
                query += f" OR description LIKE '% {value_uf_str}%' OR description LIKE '{value_uf_str}%'"

        query += ")"
        return query
    else:
        raise NotImplementedError(
            f"Can't build query for capacitance value of type {type(capacitance)}"
        )


def build_capacitor_rated_voltage_query(rated_voltage: Parameter):
    if type(rated_voltage) is not Constant:
        raise NotImplementedError

    # TODO: not all voltages are included here. Should actually be fetched from the DB
    voltages = [2.5, 4, 6.3, 10, 16, 25, 35, 50, 63, 80, 100, 150]
    allowed_voltages = [
        voltage for voltage in voltages if voltage >= rated_voltage.value
    ]
    query = "("
    add_or = False
    for value in allowed_voltages:
        if add_or:
            query += " OR "
        else:
            add_or = True
        value_str = float_to_si(value) + "V"
        query += f"description LIKE '% {value_str}%' OR description LIKE '{value_str}%'"
    query += ")"
    return query


def build_capacitor_case_size_query(case_size: Parameter):
    if type(case_size) is Constant:
        value_min = case_size.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
        value_max = value_min
    elif type(case_size) is Range:
        value_min = case_size.min
        value_max = case_size.max
    else:
        raise NotImplementedError

    query = "("
    add_or = False
    for cs in Capacitor.CaseSize:
        if cs >= value_min and cs <= value_max:
            if add_or:
                query += " OR "
            else:
                add_or = True
            query += "package LIKE '%" + cs.name.strip("C") + "'"

    query += ")"
    return query


def log_result(lcsc_pn: str, cmp: Capacitor):
    tolerance = cmp.tolerance.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()

    if type(cmp.capacitance) is Range:
        capacitance_str = (
            f"{float_to_si(cmp.capacitance.min)}F - {float_to_si(cmp.capacitance.max)}F"
        )
    else:
        capacitance = cmp.capacitance.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
        capacitance_str = f"{float_to_si(capacitance)}F"

    logger.info(
        f"Picked {lcsc_pn: <8} for component {cmp} (value: {capacitance_str}, {tolerance}%)"
    )


def find_capacitor(
    cmp: Capacitor,
    quantity: int = 1,
    moq: int = 50,
):
    """
    Find the LCSC part number of a capacitor which is in stock at JLCPCB.

    """

    case_size_query = build_capacitor_case_size_query(cmp.case_size)
    capacitance_query = build_capacitor_value_query(cmp.capacitance)
    tolerance_query = build_capacitor_tolerance_query(cmp.capacitance, cmp.tolerance)
    temperature_coefficient_query = build_capacitor_temperature_coefficient_query(
        cmp.temperature_coefficient
    )
    rated_voltage_query = build_capacitor_rated_voltage_query(cmp.rated_voltage)

    con = sqlite3.connect("jlcpcb_part_database/cache.sqlite3")
    cur = con.cursor()
    query = f"""
        SELECT lcsc, basic, price
        FROM "main"."components" 
        WHERE (category_id LIKE '%27%' OR category_id LIKE '%29%')
        AND {case_size_query}
        AND stock > {moq}
        AND {temperature_coefficient_query}
        AND {capacitance_query}
        AND {tolerance_query}
        AND {rated_voltage_query}
        """
    res = cur.execute(query).fetchall()
    if res is None:
        raise LookupError(f"Could not find capacitor for query: {query}")

    res = sort_by_basic_price(res, quantity)

    lcsc_pn = "C" + str(res[0][0])
    log_result(lcsc_pn, cmp)

    return lcsc_pn
