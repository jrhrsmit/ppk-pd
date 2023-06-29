import logging

logger = logging.getLogger(__name__)

import sqlite3
from library.library.components import Capacitor
from faebryk.library.core import Parameter
from faebryk.library.library.parameters import Range, Constant
from faebryk.library.traits.parameter import (
    is_representable_by_single_value,
)
from library.jlcpcb.util import float_to_si
from library.e_series import e_series_in_range


def build_capacitor_temperature_coefficient_query(
    temperature_coefficient: Capacitor.TemperatureCoefficient,
):
    query = "("
    add_or = False
    for tc in Capacitor.TemperatureCoefficient:
        if tc >= temperature_coefficient:
            if add_or:
                query += " OR "
            else:
                add_or = True
            query += "description LIKE '%" + tc.name + "%'"

    query += ")"
    return query


def build_capacitor_tolerance_query(
    capacitance: Parameter, max_tolerance_percent: float
):
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
    allowed_voltages = [voltage for voltage in voltages if voltage >= rated_voltage.value]
    query = "("
    add_or = False
    for value in allowed_voltages:
        if add_or:
            query += " OR "
        else:
            add_or = True
        value_str = float_to_si(value) + "V"
        query += f"description LIKE '% {value_str}' OR description LIKE '{value_str}'"
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
    moq: int = 50,
):
    """
    Find the LCSC part number of a capacitor which is in stock at JLCPCB.

    """
    tolerance = cmp.tolerance.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()
    temperature_coefficient = cmp.temperature_coefficient.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()
    case_size = Capacitor.CaseSize(
        cmp.case_size.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
    )
    case_size_str = case_size.name.strip("C")

    capacitance_query = build_capacitor_value_query(cmp.capacitance)
    tolerance_query = build_capacitor_tolerance_query(cmp.capacitance, tolerance)
    temperature_coefficient_query = build_capacitor_temperature_coefficient_query(
        temperature_coefficient
    )
    rated_voltage_query = build_capacitor_rated_voltage_query(cmp.rated_voltage)

    con = sqlite3.connect("jlcpcb_part_database/cache.sqlite3")
    cur = con.cursor()
    query = f"""
        SELECT lcsc 
        FROM "main"."components" 
        WHERE (category_id LIKE '%27%' OR category_id LIKE '%29%')
        AND package LIKE '%{case_size_str}'
        AND stock > {moq}
        AND {temperature_coefficient_query}
        AND {capacitance_query}
        AND {tolerance_query}
        AND {rated_voltage_query}
        ORDER BY basic DESC, price ASC
        """
    res = cur.execute(query).fetchone()
    if res is None:
        raise LookupError(f"Could not find capacitor for query: {query}")

    lcsc_pn = "C" + str(res[0])
    log_result(lcsc_pn, cmp)

    return "C" + str(res[0])
