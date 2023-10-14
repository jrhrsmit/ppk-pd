import logging

from library.library.components import Capacitor
from library.jlcpcb.util import jlcpcb_db, float_to_si
from library.e_series import e_series_in_range
from faebryk.core.core import Parameter
from faebryk.library.Constant import Constant
from faebryk.library.Range import Range

logger = logging.getLogger(__name__)


def build_capacitor_temperature_coefficient_query(
    temperature_coefficient: Parameter,
):
    if type(temperature_coefficient) is Constant:
        value_min = temperature_coefficient.value
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
    if isinstance(tolerance, Constant):
        max_tolerance_percent = tolerance.value
        min_tolerance_percent = tolerance.value
    elif isinstance(tolerance, Range):
        max_tolerance_percent = tolerance.max
        min_tolerance_percent = tolerance.min
    else:
        raise NotImplementedError

    if type(capacitance) is Constant:
        value = capacitance.value
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
        if (
            tolerance_abs <= max_tolerance_percent / 100 * value
            and tolerance_abs > min_tolerance_percent / 100 * value
        ):
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
        value = capacitance.value
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
        value_min = case_size.value
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
    if isinstance(cmp.tolerance, Constant):
        tolerance = cmp.tolerance.value
    elif isinstance(cmp.tolerance, Range):
        tolerance = cmp.tolerance.max
    else:
        raise NotImplementedError

    if type(cmp.capacitance) is Range:
        capacitance_str = (
            f"{float_to_si(cmp.capacitance.min)}F - {float_to_si(cmp.capacitance.max)}F"
        )
    elif type(cmp.capacitance) is Constant:
        capacitance = cmp.capacitance.value
        capacitance_str = f"{float_to_si(capacitance)}F"
    else:
        raise NotImplementedError

    cmp_name = ".".join([pname for parent, pname in cmp.get_hierarchy()])
    logger.info(
        f"Picked {lcsc_pn: <8} for component {cmp_name} (value: {capacitance_str}, {tolerance}%)"
    )


def find_capacitor(
    db: jlcpcb_db,
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

    categories = db.get_category_id(
        "Capacitors", "Multilayer Ceramic Capacitors MLCC - SMD/SMT"
    )

    query = f"""
        {case_size_query}
        AND stock > {moq}
        AND {temperature_coefficient_query}
        AND {capacitance_query}
        AND {tolerance_query}
        AND {rated_voltage_query}
        """
    db.query_category(categories, query)

    part = db.sort_by_basic_price(quantity)

    lcsc_pn = "C" + str(part["lcsc_pn"])
    log_result(lcsc_pn, cmp)

    return lcsc_pn
