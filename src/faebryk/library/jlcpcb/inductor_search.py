import logging

logger = logging.getLogger(__name__)

import sqlite3
from library.library.components import Inductor
from library.jlcpcb.util import (
    float_to_si,
    sort_by_basic_price,
    si_to_float,
    connect_to_db,
)
from library.e_series import e_series_in_range
import json
import re
from faebryk.core.core import Module, Parameter, Footprint
from faebryk.library.Constant import Constant
from faebryk.library.Range import Range
from faebryk.library.TBD import TBD


def build_inductor_tolerance_query(inductance: Parameter, tolerance: Constant):
    if type(tolerance) is not Constant:
        raise NotImplementedError

    max_tolerance_percent = tolerance.value

    if type(inductance) is Constant:
        value = inductance.value
    elif type(inductance) is Range:
        value = inductance.min
    else:
        raise NotImplementedError

    tolerances = {
        "1%": 0.01 * value,
        "2%": 0.02 * value,
        "3%": 0.03 * value,
        "5%": 0.05 * value,
        "7%": 0.07 * value,
        "10%": 0.10 * value,
        "12%": 0.12 * value,
        "15%": 0.15 * value,
        "18%": 0.18 * value,
        "20%": 0.20 * value,
        "22%": 0.22 * value,
        "23%": 0.23 * value,
        "25%": 0.25 * value,
        "30%": 0.30 * value,
        "35%": 0.35 * value,
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
            tolerance_str_escape = tolerance_str.replace("%", "\\%")
            query += "description LIKE '%" + plusminus + tolerance_str_escape + "%'"
            query += " ESCAPE '\\'"

    query += ")"
    return query


def build_inductor_value_query(inductance: Parameter):
    if type(inductance) is Constant:
        value = inductance.value
        value_str = float_to_si(value) + "H"
        query = (
            f"(description LIKE '% {value_str}%' OR description LIKE '{value_str}%')"
        )
        return query
    elif type(inductance) is Range:
        e_values = e_series_in_range(inductance)
        query = "("
        add_or = False
        for value in e_values:
            if add_or:
                query += " OR "
            else:
                add_or = True
            value_str = float_to_si(value) + "H"
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
            f"Can't build query for inductance value of type {type(inductance)}"
        )


def build_inductor_rated_voltage_query(rated_voltage: Parameter):
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


def build_inductor_case_size_query(case_size: Parameter):
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
    for cs in Inductor.CaseSize:
        if cs >= value_min and cs <= value_max:
            if add_or:
                query += " OR "
            else:
                add_or = True
            query += "package LIKE '%" + cs.name.strip("L") + "'"

    query += ")"
    return query


def log_result(lcsc_pn: str, cmp: Inductor):
    tolerance = cmp.tolerance.value

    if type(cmp.inductance) is Range:
        inductance_str = (
            f"{float_to_si(cmp.inductance.min)}H - {float_to_si(cmp.inductance.max)}H"
        )
    elif type(cmp.inductance) is Constant:
        inductance = cmp.inductance.value
        inductance_str = f"{float_to_si(inductance)}H"
    else:
        raise NotImplementedError

    cmp_name = ".".join([pname for parent, pname in cmp.get_hierarchy()])
    logger.info(
        f"Picked {lcsc_pn: <8} for component {cmp_name} (value: {inductance_str}, {tolerance}%)"
    )


def inductor_filter(
    query_result: list[tuple[int, int, str, str, str]],
    inductance: Parameter,
    rated_current: Parameter,
    dc_resistance: Parameter,
    self_resonant_frequency: Parameter,
    inductor_type: Parameter,
):
    filtered_result = []

    logger.info(f"Starting out with {len(query_result)} results")
    if type(inductance) is Constant:
        for _, row in enumerate(query_result):
            desc = row[4]
            val = re.search("[0-9.]+ ?[pnuµmkMG]?H", desc)
            if not val:
                continue
            try:
                val = val.group()
                if val != "-" and si_to_float(val) == inductance.value:
                    filtered_result.append(row)
            except:
                pass
    elif type(inductance) is Range:
        for _, row in enumerate(query_result):
            desc = row[4]
            val = re.search("[0-9.]+ ?[pnuµmkMG]?H", desc)
            if not val:
                continue
            val = val.group()
            try:
                #  logger.info(f"Regex result: '{val}', float: {si_to_float(val)}H, min: {inductance.min}, max: {inductance.max}")
                #  logger.info(f"Regex result: '{val}', min: {si_to_float(inductance.min)}, max: {si_to_float(inductance.max)}")
                if (
                    si_to_float(val) >= inductance.min
                    and si_to_float(val) <= inductance.max
                ):
                    filtered_result.append(row)
            except:
                pass
    else:
        raise NotImplementedError

    query_result = filtered_result
    filtered_result = []
    logger.info(f"After inductance filtering {len(query_result)} results left")

    if type(rated_current) is Constant:
        for _, row in enumerate(query_result):
            try:
                extra = row[3]
                extra_json = json.loads(extra)
                attributes = extra_json["attributes"]
                val = attributes["Rated Current"]
                if val != "-" and si_to_float(val) > rated_current.value:
                    filtered_result.append(row)
            except:
                pass
    elif type(rated_current) is Range:
        for _, row in enumerate(query_result):
            try:
                extra = row[3]
                extra_json = json.loads(extra)
                attributes = extra_json["attributes"]
                val = si_to_float(attributes["Rated Current"])
                if val != "-" and (val > rated_current.min and val < rated_current.max):
                    filtered_result.append(row)
            except:
                pass
    else:
        raise NotImplementedError

    query_result = filtered_result
    filtered_result = []

    logger.info(f"After rated current filtering {len(query_result)} results left")

    if type(dc_resistance) is Constant:
        for _, row in enumerate(query_result):
            try:
                extra = row[3]
                extra_json = json.loads(extra)
                attributes = extra_json["attributes"]
                val = si_to_float(attributes["DC Resistance (DCR)"])
                if val != "-" and si_to_float(val) < dc_resistance.value:
                    filtered_result.append(row)
            except:
                pass
    elif type(dc_resistance) is Range:
        for _, row in enumerate(query_result):
            try:
                extra = row[3]
                extra_json = json.loads(extra)
                attributes = extra_json["attributes"]
                val = si_to_float(attributes["DC Resistance (DCR)"])
                if val != "-" and (val > dc_resistance.min and val < dc_resistance.max):
                    filtered_result.append(row)
            except:
                pass
    else:
        raise NotImplementedError

    query_result = filtered_result
    filtered_result = []

    logger.info(f"After DC resistance filtering {len(query_result)} results left")

    if type(inductor_type) is Constant:
        if inductor_type.value == Inductor.InductorType.Power:
            logger.warn(
                f"Self resonant frequency filtering not supported for power inductors"
            )
            return query_result

    if type(self_resonant_frequency) is Constant:
        for _, row in enumerate(query_result):
            try:
                extra = row[3]
                logger.info(f"json:  {extra}")
                extra_json = json.loads(extra)
                attributes = extra_json["attributes"]
                val = attributes["Frequency - Self Resonant"]
                if si_to_float(val) > self_resonant_frequency.value:
                    filtered_result.append(row)
            except:
                pass
    elif type(self_resonant_frequency) is Range:
        for _, row in enumerate(query_result):
            try:
                extra = row[3]
                extra_json = json.loads(extra)
                attributes = extra_json["attributes"]
                val = si_to_float(attributes["Frequency - Self Resonant"])
                if (
                    val > self_resonant_frequency.min
                    and val < self_resonant_frequency.max
                ):
                    filtered_result.append(row)
            except:
                pass
    else:
        raise NotImplementedError

    logger.info(
        f"After self resonant frequency filtering {len(filtered_result)} results left"
    )

    return filtered_result


def find_inductor(
    cmp: Inductor,
    quantity: int = 1,
    moq: int = 50,
):
    """
    Find the LCSC part number of a inductor which is in stock at JLCPCB.

    """

    if type(cmp.inductor_type) != Constant:
        raise NotImplementedError

    if cmp.inductor_type.value == Inductor.InductorType.Normal:
        category = 12  # SMD inductors
    elif cmp.inductor_type.value == Inductor.InductorType.Power:
        category = 13  # Power inductors
    else:
        raise NotImplementedError

    if hasattr(cmp, "case_size"):
        case_size_query = build_inductor_case_size_query(cmp.case_size)
    else:
        case_size_query = "1"
    tolerance_query = build_inductor_tolerance_query(cmp.inductance, cmp.tolerance)

    con = connect_to_db()
    cur = con.cursor()
    query = f"""
        SELECT lcsc, basic, price, extra, description
        FROM "main"."components" 
        WHERE category_id = {category}
        AND {case_size_query}
        AND stock > {moq}
        AND {tolerance_query}
        """
    res = cur.execute(query).fetchall()

    if not res:
        raise LookupError(f"Could not find inductor for query: {query}")
    res = inductor_filter(
        res,
        inductance=cmp.inductance,
        rated_current=cmp.rated_current,
        dc_resistance=cmp.dc_resistance,
        self_resonant_frequency=cmp.self_resonant_frequency,
        inductor_type=cmp.inductor_type,
    )
    res = [row[0:3] for row in res]
    res = sort_by_basic_price(res, quantity)

    lcsc_pn = "C" + str(res[0][0])
    log_result(lcsc_pn, cmp)

    return lcsc_pn