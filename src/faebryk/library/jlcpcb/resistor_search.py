import logging

logger = logging.getLogger(__name__)

import sqlite3
from library.library.components import Resistor
from library.jlcpcb.util import (
    float_to_si,
    si_to_float,
    get_value_from_pn,
    sort_by_basic_price,
    connect_to_db,
)
from library.e_series import e_series_in_range
from faebryk.core.core import Module, Parameter, Footprint
import json
import re
from faebryk.library.Constant import Constant
from faebryk.library.Range import Range
from faebryk.library.TBD import TBD


def build_resistor_tolerance_query(resistance: Parameter, tolerance: Parameter):
    if type(tolerance) is not Constant:
        raise NotImplementedError

    # assert type(max_tolerance_percent) is Constant
    max_tolerance_percent = tolerance.value

    if type(resistance) is Constant:
        r = resistance.value
    elif type(resistance) is Range:
        r = resistance.min
    else:
        raise NotImplementedError

    tolerances = {
        "0.01%": 0.0001 * r,
        "0.02%": 0.0002 * r,
        "0.05%": 0.0005 * r,
        "0.1%": 0.001 * r,
        "0.2%": 0.002 * r,
        "0.25%": 0.0025 * r,
        "0.5%": 0.005 * r,
        "1%": 0.01 * r,
        "2%": 0.02 * r,
        "3%": 0.03 * r,
        "5%": 0.05 * r,
        "7.5%": 0.075 * r,
        "10%": 0.10 * r,
        "15%": 0.15 * r,
        "20%": 0.20 * r,
        "30%": 0.30 * r,
    }
    plusminus = "±"
    query = "("
    add_or = False
    for tolerance_str, tolerance_abs in tolerances.items():
        if tolerance_abs <= max_tolerance_percent / 100 * r:
            if add_or:
                query += " OR "
            else:
                add_or = True
            tolerance_str_escape = tolerance_str.replace("%", "\\%")
            query += "description LIKE '%" + plusminus + tolerance_str_escape + "%'"
            query += " ESCAPE '\\'"

    query += ")"
    return query


def build_resistor_value_query(resistance: Parameter):
    if type(resistance) is Constant:
        value = resistance.value
        value_str = float_to_si(value) + "Ω"
        query = f"(description COLLATE Latin1_General_BIN LIKE '% {value_str}%' OR description COLLATE Latin1_General_BIN LIKE '{value_str}%')"
        return query
    elif type(resistance) is Range:
        e_values = e_series_in_range(resistance)
        query = "("
        add_or = False
        for value in e_values:
            if add_or:
                query += " OR "
            else:
                add_or = True
            value_str = float_to_si(value) + "Ω"
            query += f"(description COLLATE Latin1_General_BIN LIKE '% {value_str}%' OR description COLLATE Latin1_General_BIN LIKE '{value_str}%')"
        query += ")"
        return query
    else:
        raise NotImplementedError


def build_resistor_case_size_query(case_size: Parameter):
    if type(case_size) is Constant:
        value_min = case_size.value
        value_max = value_min
    elif type(case_size) is Range:
        value_min = case_size.min
        value_max = case_size.max
    else:
        raise NotImplementedError

    query = "("
    add_or = False
    for cs in Resistor.CaseSize:
        if cs >= value_min and cs <= value_max:
            if add_or:
                query += " OR "
            else:
                add_or = True
            query += "package LIKE '%" + cs.name.strip("R") + "'"

    query += ")"
    return query


def log_result(lcsc_pn: str, cmp: Resistor):
    assert type(cmp.tolerance) is Constant
    tolerance = cmp.tolerance.value

    if type(cmp.case_size) is Constant:
        case_size_str = f"{cmp.case_size.value.name}"
    elif type(cmp.case_size) is Range:
        case_size_str = f"{cmp.case_size.min.name} - {cmp.case_size.max.name}"
    else:
        case_size_str = "<unknown case size>"

    if type(cmp.rated_power) is Constant:
        rated_power_str = f"{float_to_si(cmp.rated_power.value)}W"
    elif type(cmp.rated_power) is Range:
        rated_power_str = (
            f"{float_to_si(cmp.rated_power.min)}W - {float_to_si(cmp.rated_power.max)}W"
        )
    else:
        rated_power_str = "<unknown rated power>"

    if type(cmp.resistance) is Range:
        resistance_str = (
            f"{float_to_si(cmp.resistance.min)}Ω - {float_to_si(cmp.resistance.max)}Ω"
        )
    elif type(cmp.resistance) is Constant:
        resistance = cmp.resistance.value
        resistance_str = f"{float_to_si(resistance)}Ω"
    else:
        raise NotImplementedError

    cmp_name = ".".join([pname for parent, pname in cmp.get_hierarchy()])
    logger.info(
        f"Picked {lcsc_pn: <8} for component {cmp_name} (value: {resistance_str}, {tolerance}%, {case_size_str}, {rated_power_str})"
    )


def resistor_filter(
    query_result: list[tuple[int, int, str, str]],
    rated_power: Parameter,
) -> list[tuple[int, int, str, str]]:
    filtered_resuls = []
    if type(rated_power) is Constant:
        for _, row in enumerate(query_result):
            try:
                extra = row[3]
                extra_json = json.loads(extra)
                attributes = extra_json["attributes"]
                val = attributes["Power(Watts)"]
                if val != "-" and si_to_float(val) > rated_power.value:
                    filtered_resuls.append(row)
            except:
                pass
    elif type(rated_power) is Range:
        for _, row in enumerate(query_result):
            try:
                extra = row[3]
                extra_json = json.loads(extra)
                attributes = extra_json["attributes"]
                val = attributes["Power(Watts)"]
                if (
                    val != "-"
                    and si_to_float(val) >= rated_power.min
                    and si_to_float(val) <= rated_power.max
                ):
                    filtered_resuls.append(row)
            except:
                pass
    else:
        raise NotImplementedError

    return filtered_resuls


def find_resistor(
    cmp: Resistor,
    quantity: int = 1,
    moq: int = 50,
):
    """
    Find the LCSC part number of a resistor which is in stock at JLCPCB.

    TODO: Does not find 'better' tolerance components, only exactly the tolerance specified.
    """

    case_size_query = build_resistor_case_size_query(cmp.case_size)
    resistance_query = build_resistor_value_query(cmp.resistance)
    tolerance_query = build_resistor_tolerance_query(cmp.resistance, cmp.tolerance)

    con = connect_to_db()
    cur = con.cursor()
    query = f"""
        SELECT lcsc, basic, price, extra
        FROM "main"."components" 
        WHERE (category_id = 46 or category_id = 52)
        AND {case_size_query}
        AND stock > {moq}
        AND {resistance_query}
        AND {tolerance_query}
        ORDER BY basic DESC, price ASC
        """
    res = cur.execute(query).fetchall()
    if not res:
        raise LookupError(f"Could not find resistor for query: {query}")

    res = resistor_filter(res, cmp.rated_power)

    res = [row[0:3] for row in res]
    res = sort_by_basic_price(res, quantity)

    lcsc_pn = "C" + str(res[0][0])
    log_result(lcsc_pn, cmp)

    return lcsc_pn
