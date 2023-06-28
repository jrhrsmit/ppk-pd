import logging

logger = logging.getLogger(__name__)

from si_prefix import SI_PREFIX_UNITS, si_format
import sqlite3
from library.library.components import Capacitor
from faebryk.library.core import Parameter
from faebryk.library.library.parameters import Range, Constant
from faebryk.library.traits.parameter import (
    is_representable_by_single_value,
)
from math import log10, ceil, floor


def resistor_value_to_si(value: float) -> str:
    value_str = si_format(
        value,
        precision=2,
        format_str="{value}",
    )
    prefix_str = si_format(
        value,
        precision=2,
        format_str="{prefix}",
    )
    return value_str.rstrip("0").rstrip(".") + prefix_str


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


def e_values_in_range(value_range: Range):
    e192 = [
        1.00,
        1.01,
        1.02,
        1.04,
        1.05,
        1.06,
        1.07,
        1.09,
        1.10,
        1.11,
        1.13,
        1.14,
        1.15,
        1.17,
        1.18,
        1.20,
        1.21,
        1.23,
        1.24,
        1.26,
        1.27,
        1.29,
        1.30,
        1.32,
        1.33,
        1.35,
        1.37,
        1.38,
        1.40,
        1.42,
        1.43,
        1.45,
        1.47,
        1.49,
        1.50,
        1.52,
        1.54,
        1.56,
        1.58,
        1.60,
        1.62,
        1.64,
        1.65,
        1.67,
        1.69,
        1.72,
        1.74,
        1.76,
        1.78,
        1.80,
        1.82,
        1.84,
        1.87,
        1.89,
        1.91,
        1.93,
        1.96,
        1.98,
        2.00,
        2.03,
        2.05,
        2.08,
        2.10,
        2.13,
        2.15,
        2.18,
        2.21,
        2.23,
        2.26,
        2.29,
        2.32,
        2.34,
        2.37,
        2.40,
        2.43,
        2.46,
        2.49,
        2.52,
        2.55,
        2.58,
        2.61,
        2.64,
        2.67,
        2.71,
        2.74,
        2.77,
        2.80,
        2.84,
        2.87,
        2.91,
        2.94,
        2.98,
        3.01,
        3.05,
        3.09,
        3.12,
        3.16,
        3.20,
        3.24,
        3.28,
        3.32,
        3.36,
        3.40,
        3.44,
        3.48,
        3.52,
        3.57,
        3.61,
        3.65,
        3.70,
        3.74,
        3.79,
        3.83,
        3.88,
        3.92,
        3.97,
        4.02,
        4.07,
        4.12,
        4.17,
        4.22,
        4.27,
        4.32,
        4.37,
        4.42,
        4.48,
        4.53,
        4.59,
        4.64,
        4.70,
        4.75,
        4.81,
        4.87,
        4.93,
        4.99,
        5.05,
        5.11,
        5.17,
        5.23,
        5.30,
        5.36,
        5.42,
        5.49,
        5.56,
        5.62,
        5.69,
        5.76,
        5.83,
        5.90,
        5.97,
        6.04,
        6.12,
        6.19,
        6.26,
        6.34,
        6.42,
        6.49,
        6.57,
        6.65,
        6.73,
        6.81,
        6.90,
        6.98,
        7.06,
        7.15,
        7.23,
        7.32,
        7.41,
        7.50,
        7.59,
        7.68,
        7.77,
        7.87,
        7.96,
        8.06,
        8.16,
        8.25,
        8.35,
        8.45,
        8.56,
        8.66,
        8.76,
        8.87,
        8.98,
        9.09,
        9.20,
        9.31,
        9.42,
        9.53,
        9.65,
        9.76,
        9.88,
    ]
    e96 = [
        1.00,
        1.02,
        1.05,
        1.07,
        1.10,
        1.13,
        1.15,
        1.18,
        1.21,
        1.24,
        1.27,
        1.30,
        1.33,
        1.37,
        1.40,
        1.43,
        1.47,
        1.50,
        1.54,
        1.58,
        1.62,
        1.65,
        1.69,
        1.74,
        1.78,
        1.82,
        1.87,
        1.91,
        1.96,
        2.00,
        2.05,
        2.10,
        2.15,
        2.21,
        2.26,
        2.32,
        2.37,
        2.43,
        2.49,
        2.55,
        2.61,
        2.67,
        2.74,
        2.80,
        2.87,
        2.94,
        3.01,
        3.09,
        3.16,
        3.24,
        3.32,
        3.40,
        3.48,
        3.57,
        3.65,
        3.74,
        3.83,
        3.92,
        4.02,
        4.12,
        4.22,
        4.32,
        4.42,
        4.53,
        4.64,
        4.75,
        4.87,
        4.99,
        5.11,
        5.23,
        5.36,
        5.49,
        5.62,
        5.76,
        5.90,
        6.04,
        6.19,
        6.34,
        6.49,
        6.65,
        6.81,
        6.98,
        7.15,
        7.32,
        7.50,
        7.68,
        7.87,
        8.06,
        8.25,
        8.45,
        8.66,
        8.87,
        9.09,
        9.31,
        9.53,
        9.76,
    ]
    e48 = [
        1.00,
        1.05,
        1.10,
        1.15,
        1.21,
        1.27,
        1.33,
        1.40,
        1.47,
        1.54,
        1.62,
        1.69,
        1.78,
        1.87,
        1.96,
        2.05,
        2.15,
        2.26,
        2.37,
        2.49,
        2.61,
        2.74,
        2.87,
        3.01,
        3.16,
        3.32,
        3.48,
        3.65,
        3.83,
        4.02,
        4.22,
        4.42,
        4.64,
        4.87,
        5.11,
        5.36,
        5.62,
        5.90,
        6.19,
        6.49,
        6.81,
        7.15,
        7.50,
        7.87,
        8.25,
        8.66,
        9.09,
        9.53,
    ]
    e24 = [
        1.0,
        1.1,
        1.2,
        1.3,
        1.5,
        1.6,
        1.8,
        2.0,
        2.2,
        2.4,
        2.7,
        3.0,
        3.3,
        3.6,
        3.9,
        4.3,
        4.7,
        5.1,
        5.6,
        6.2,
        6.8,
        7.5,
        8.2,
        9.1,
    ]
    e_values = set(e24 + e48 + e96 + e192)
    result = []
    lower_exp = int(floor(log10(value_range.min)))
    upper_exp = int(ceil(log10(value_range.max)))
    for exp in range(lower_exp, upper_exp):
        for e in e_values:
            val = e * 10**exp
            if val >= value_range.min and val <= value_range.max:
                result.append(val)
    return result


def build_capacitor_value_query(capacitance: Parameter):
    if type(capacitance) is Constant:
        value = capacitance.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
        value_str = resistor_value_to_si(value) + "F"
        query = (
            f"(description LIKE '% {value_str}%' OR description LIKE '{value_str}%')"
        )
        return query
    elif type(capacitance) is Range:
        e_values = e_values_in_range(capacitance)
        query = "("
        add_or = False
        for value in e_values:
            if add_or:
                query += " OR "
            else:
                add_or = True
            value_str = resistor_value_to_si(value) + "F"
            query += (
                f"description LIKE '% {value_str}%' OR description LIKE '{value_str}%'"
            )
        query += ")"
        return query
    else:
        raise NotImplementedError


def find_capacitor(
    capacitance: Parameter,
    tolerance_percent: float = 20,
    temperature_coefficient: Capacitor.TemperatureCoefficient = Capacitor.TemperatureCoefficient.X7R,
    voltage: float = 16,
    case: str = "0402",
    moq: int = 50,
):
    """
    Find the LCSC part number of a capacitor which is in stock at JLCPCB.

    """
    capacitance_query = build_capacitor_value_query(capacitance)
    tolerance_query = build_capacitor_tolerance_query(capacitance, tolerance_percent)
    temperature_coefficient_query = build_capacitor_temperature_coefficient_query(
        temperature_coefficient
    )

    con = sqlite3.connect("jlcpcb_part_database/cache.sqlite3")
    cur = con.cursor()
    query = f"""
        SELECT lcsc 
        FROM "main"."components" 
        WHERE (category_id LIKE '%27%' OR category_id LIKE '%29%')
        AND package LIKE '%{case}'
        AND stock > {moq}
        AND {temperature_coefficient_query}
        AND {capacitance_query}
        AND {tolerance_query}
        ORDER BY basic DESC, price ASC
        """
    res = cur.execute(query).fetchone()
    if res is None:
        raise LookupError(f"Could not find capacitor for query: {query}")
    return "C" + str(res[0])
