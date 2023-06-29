import logging

logger = logging.getLogger(__name__)

import sqlite3
from library.library.components import Resistor
from library.jlcpcb.util import (
    float_to_si,
    si_to_float,
    e_values_in_range,
    get_value_from_pn,
)
from faebryk.library.core import Parameter
from faebryk.library.library.parameters import Range, Constant

from faebryk.library.traits.parameter import (
    is_representable_by_single_value,
)
import re


def build_resistor_tolerance_query(resistance: Parameter, max_tolerance_percent: float):
    if type(resistance) is Constant:
        resistance = resistance.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
    elif type(resistance) is Range:
        resistance = resistance.min
    else:
        raise NotImplementedError

    tolerances = {
        "0.01%": 0.0001 * resistance,
        "0.02%": 0.0002 * resistance,
        "0.05%": 0.0005 * resistance,
        "0.1%": 0.001 * resistance,
        "0.2%": 0.002 * resistance,
        "0.25%": 0.0025 * resistance,
        "0.5%": 0.005 * resistance,
        "1%": 0.01 * resistance,
        "2%": 0.02 * resistance,
        "3%": 0.03 * resistance,
        "5%": 0.05 * resistance,
        "7.5%": 0.075 * resistance,
        "10%": 0.10 * resistance,
        "15%": 0.15 * resistance,
        "20%": 0.20 * resistance,
        "30%": 0.30 * resistance,
    }
    plusminus = "±"
    query = "("
    add_or = False
    for tolerance_str, tolerance_abs in tolerances.items():
        if tolerance_abs <= max_tolerance_percent / 100 * resistance:
            if add_or:
                query += " OR "
            else:
                add_or = True
            tolerance_str_escape = tolerance_str.replace("%", "\%")
            query += "description LIKE '%" + plusminus + tolerance_str_escape + "%'"
            query += " ESCAPE '\\'"

    query += ")"
    return query


def build_resistor_value_query(resistance: Parameter):
    if type(resistance) is Constant:
        value = resistance.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
        value_str = float_to_si(value) + "Ω"
        query = (
            f"(description LIKE '% {value_str}%' OR description LIKE '{value_str}%')"
        )
        return query
    elif type(resistance) is Range:
        e_values = e_values_in_range(resistance)
        query = "("
        add_or = False
        for value in e_values:
            if add_or:
                query += " OR "
            else:
                add_or = True
            value_str = float_to_si(value) + "Ω"
            query += (
                f"description LIKE '% {value_str}%' OR description LIKE '{value_str}%'"
            )
        query += ")"
        return query
    else:
        raise NotImplementedError


def log_result(lcsc_pn: str, cmp: Resistor):
    tolerance = cmp.tolerance.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()

    if type(cmp.resistance) is Range:
        resistance_str = (
            f"{float_to_si(cmp.resistance.min)}Ω - {float_to_si(cmp.resistance.max)}Ω"
        )
    else:
        resistance = cmp.resistance.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
        resistance_str = f"{float_to_si(resistance)}Ω"

    logger.info(
        f"Picked {lcsc_pn: <8} for component {cmp} (value: {resistance_str}, {tolerance}%)"
    )


def find_resistor(
    cmp: Resistor,
    case: str = "0402",
    moq: int = 50,
):
    """
    Find the LCSC part number of a resistor which is in stock at JLCPCB.

    TODO: Does not find 'better' tolerance components, only exactly the tolerance specified.
    """

    tolerance = cmp.tolerance.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()

    resistance_query = build_resistor_value_query(cmp.resistance)
    tolerance_query = build_resistor_tolerance_query(cmp.resistance, tolerance)

    con = sqlite3.connect("jlcpcb_part_database/cache.sqlite3")
    cur = con.cursor()
    query = f"""
        SELECT lcsc 
        FROM "main"."components" 
        WHERE (category_id LIKE '%46%' or category_id LIKE '%52%')
        AND package LIKE '%{case}'
        AND stock > {moq}
        AND {resistance_query}
        AND {tolerance_query}
        ORDER BY basic DESC, price ASC
        """
    res = cur.execute(query).fetchone()
    if res is None:
        raise LookupError(f"Could not find resistor for query: {query}")

    lcsc_pn = "C" + str(res[0])
    log_result(lcsc_pn, cmp)

    return lcsc_pn
