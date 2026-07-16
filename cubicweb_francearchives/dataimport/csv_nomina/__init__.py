# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2026
# Contact http://www.logilab.fr -- mailto:contact@logilab.fr
#
# This software is governed by the CeCILL-C license under French law and
# abiding by the rules of distribution of free software. You can use,
# modify and/ or redistribute the software under the terms of the CeCILL-C
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty and the software's author, the holder of the
# economic rights, and the successive licensors have only limited liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading, using, modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean that it is complicated to manipulate, and that also
# therefore means that it is reserved for developers and experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systemsand/or
# data to be ensured and, more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL-C license and that you accept its terms.
#

from collections import defaultdict, OrderedDict

import logging

from logilab.common.textutils import unormalize

from cubicweb_francearchives.utils import remove_html_tags
from cubicweb_francearchives.dataimport import (
    load_services_map,
)
from cubicweb_francearchives.dataimport.oai_nomina import compute_nomina_stable_id

from cubicweb_francearchives.entities.nomina import (
    NominaActCodeTypes,
    NominaESActCodeTypes,
    normalized_doctype_code,
)

NOMINA_ACT_TYPES = list(NominaActCodeTypes.keys()) + list(NominaESActCodeTypes.keys())


def invalid_doc_type(doctype):
    if not doctype:
        return True
    if doctype in ("SOCFACE",):
        return False
    if doctype != "OAI" and normalized_doctype_code(doctype) not in NOMINA_ACT_TYPES:
        return True
    return False


COMMON_FIELDS = OrderedDict(
    (
        ("Cote du registre", "C_c"),  # "cote",
        ("Classe", "D_RM_y"),  # "event_year",  # XXX
        ("Bureau de recrutement", "L_RM_p"),  # "event_commune",
        ("Code département de recrutement", "L_RM_dc"),  # ignore
        ("Département de recrutement", "L_RM_d"),  # "event_department"
        ("Code pays ou territoire de recrutement", "L_RM_cc"),  # ignore
        ("Pays ou territoire de recrutement", "L_RM_c"),  # "event_country"
        ("Nom", "P_n"),  # "names
        ("Prénoms", "P_f"),  # "forenames"
        ("Année de naissance", "D_N_y"),  # "birth_year"
        ("Date de naissance", "D_N_d"),  # "birth_date"
        ("Commune de naissance", "L_N_p"),  # "birth_commune"
        ("Code département naissance", "L_N_dc"),  # ignore
        ("Département de naissance", "L_N_d"),  # "birth_department"
        ("Code pays ou territoire de naissance", "L_N_cc"),  # ignore
        ("Pays ou territoire de naissance", "L_N_c"),  # "birth_country"
        ("Profession", "C_o"),  # "occupations"
        ("Instruction générale", "C_e"),  # "instruction"
        ("Commune de résidence", "L_R_p"),  # "residence_commune"
        ("Code département de résidence", "L_R_dc"),  # ignore
        ("Département de résidence", "L_R_d"),  # "residence_department"
        ("Code pays ou territoire de résidence", "L_R_cc"),  # ignore
        ("Pays ou territoire de résidence", "L_R_c"),  # "residence_country"
        ("Année de décès", "D_D_y"),  # "death_year"
        ("Date de décès", "D_D_d"),  # "death_date"
        ("Commune de décès", "L_D_p"),  # "death_commune"
        ("code département de décès", "L_D_dc"),  # ignore
        ("Département décès", "L_D_d"),  # "death_department
        ("Code pays ou territoire de décès", "L_D_cc"),  # ignore
        ("Pays ou territoire de décès", "L_D_c"),  # "death_country"
        ("URI", "U"),  # "source_url
        ("Matricule", "C_n"),  # "act_number"
        ("Mention", "C_m"),  # "mention_mpf"),
        ("identifiant", "notice_id"),
        ("numerise", "C_d"),  # ignore
        ("delete", "delete"),  # optional
    )
)

MARIAGE_FIELDS = OrderedDict(
    (
        ("Cote_Registre", "C_c"),  # "cote"
        ("Type_Acte", "t_a"),  # "act_type"
        ("Annee_Acte", "D_acte_y"),  # "act_date"
        ("Nom", "P_n_m"),  # "names"
        ("Prenoms", "P_f_m"),  # "forenames"
        ("Nom_epouxe", "P_n_f"),  # "spouse_names"
        ("Prenoms_epouxe", "P_f_f"),  # "spouse_fornames"
        ("Date_evenement", "D_XXX_d"),
        ("Lieu_evenement", "L_XXX_p"),
        ("code_dpt_evenement", "L_XXX_dc"),
        ("departement_evenement", "L_XXX_d"),
        ("date_acte", "D_acte_d"),
        ("Numero_acte", "C_n"),  # "act_number"
        ("id_acte", "notice_id"),  # "notice_id"
        ("Infos_Complementaires", "C_a"),  #
        ("URI", "U"),
        ("delete", "delete"),  # optional
    )
)

IGNORE_KEY = "III"

BIRTH_DEATH_FIELDS = OrderedDict(
    (
        ("Cote_Registre", "C_c"),
        ("Type_Acte", "t_a"),
        ("Annee_Acte", "D_acte_y"),
        ("Nom", "P_n"),
        ("Prenoms", "P_f"),
        ("Nom_epouxe", IGNORE_KEY),
        ("Prenoms_epouxe", IGNORE_KEY),
        ("Date_evenement", "D_XXX_d"),
        ("Lieu_evenement", "L_XXX_p"),
        ("code_dpt_evenement", "L_XXX_dc"),
        ("departement_evenement", "L_XXX_d"),
        ("date_acte", "D_acte_d"),
        ("Numero_acte", "C_n"),  # nro
        ("id_acte", "notice_id"),  # notice_id
        ("Infos_Complementaires", "C_a"),  # autres
        ("URI", "U"),
        ("delete", "delete"),  # optional
    )
)

CIVIL_STATUS_CODES = {"M": "mariage", "B": "naissance", "D": "deces"}

SOCFACE_FIELDS = OrderedDict(
    [
        ("Identifiant unique de notice (service)", "notice_id"),
        ("Identifiant Arkindex", "id_arkindex"),
        ("Nom de famille (orig)", None),
        ("Nom de famille", "names"),
        ("Prénoms", "forenames"),
        ("Âge", "age"),
        ("Date de naissance", "birth_date"),
        ("Lieu de naissance", "birth_place"),  # commune (?)
        ("Lien avec le chef de ménage", "household_role"),
        ("Profession (source)", "occupations"),
        ("Profession (index SIAF)", "occupations_index"),
        ("Genre", "gender"),
        ("État civil", "civil_status"),
        ("Employeur", "employer"),
        ("Nationalité", "nationality"),
        ("Observations", "additional_info"),
        ("Identifiant du service d'archives", "service_code"),  # or None ?
        ("Chemin d'image", "teklia_url"),  # XXX ?
        ("Hauteur du rectangle de l'image", None),
        ("Largeur du rectangle de l'image", None),
        ("Position horizontale du rectangle", None),
        ("Position verticale du rectangle", None),
        ("Année du recensement", "event_date"),
        ("URL de la visionneuse", "source_url"),
        ("Année du recensement", "event_date"),
        ("Département", "event_department"),  # XXX est un nombre (?)
        ("Numéro INSEE de la commune", None),
        ("Identifiant Cassini de la commune", None),
        ("Commune de recensement", "event_commune"),  # event place
        ("Commune (normalisée)", "event_place"),  # event commune, department, country
        ("Cote", "cote"),
        ("Page et position de la ligne sur la page", "doc_page_line_id"),
        ("Numéro Arkindex du ménage", "household_id"),
        ("Thème", "act_type"),  # XXX shell we index as it is ?
        ("Typologie documentaire", None),  # valeur unique "liste nominative"
        ("delete", "delete"),  # optionnel
    ]
)

# ============================================================================
# SOCFACE UPDATE CONSTANTS
# ============================================================================

SOCFACE_UPDATE_REQUIRED_COLUMNS = ("Identifiant Arkindex",)

SOCFACE_UPDATE_ALLOWED_COLUMNS = frozenset(
    [
        "Identifiant Arkindex",  # required
        "Nom de famille",
        "Prénoms",
        "Âge",
        "Date de naissance",
        "Lieu de naissance",
        "Lien avec le chef de ménage",
        "Profession (source)",
        "Profession (index SIAF)",
        "Genre",
        "État civil",
        "Employeur",
        "Nationalité",
        "Observations",
        "Année du recensement",
        "URL de la visionneuse",
        "Département",
        "Commune de recensement",
        "Commune (normalisée)",
        "Cote",
        "Page et position de la ligne sur la page",
        "Numéro Arkindex du ménage",
    ]
)


def check_socface_update_fieldnames(cnx, fieldnames):
    """Validate CSV columns for SOCFACE update.

    :param cnx: CubicWeb connection
    :param fieldnames: List of CSV column names
    :return: List of errors (empty if valid)
    """
    errors = []

    # 1. Check required column
    for col in SOCFACE_UPDATE_REQUIRED_COLUMNS:
        if col not in fieldnames:
            errors.append(f"Required column '{col}' is missing")

    # 2. Check at least one update column is present
    update_columns = set(fieldnames) - set(SOCFACE_UPDATE_REQUIRED_COLUMNS)
    allowed_update = SOCFACE_UPDATE_ALLOWED_COLUMNS - set(SOCFACE_UPDATE_REQUIRED_COLUMNS)
    valid_update_columns = update_columns.intersection(allowed_update)

    if not valid_update_columns:
        errors.append(
            f"At least one update column must be present: " f"{', '.join(sorted(allowed_update))}"
        )

    # 3. Check for forbidden columns
    invalid_columns = update_columns - allowed_update
    if invalid_columns:
        errors.append(
            f"Invalid columns found: {', '.join(sorted(invalid_columns))}. "
            f"Only the following columns are allowed:"
            f" {', '.join(sorted(SOCFACE_UPDATE_ALLOWED_COLUMNS))}"
        )

    return errors


class CSVNominaFieldnames:
    fieldnames = {
        "OAI": OrderedDict(
            (
                ("stable_id", "stable_id"),
                ("oai_id", "oai_id"),
                ("json_data", "json_data"),
                ("service", "service"),
                ("delete", "delete"),
                ("harvested_url", "harvested_url"),
            )
        ),
        "M": MARIAGE_FIELDS,  # mariages
        "B": BIRTH_DEATH_FIELDS,  # baptêmes et naissances
        "S": BIRTH_DEATH_FIELDS,  # décès
        "SOCFACE": SOCFACE_FIELDS,  # format SOCFACE
    }


def readerconfig(cwconfig, **kwargs):
    config = {
        "nomina-index-name": cwconfig["nomina-index-name"],
    }
    config.update(kwargs)
    return config


def check_document_fieldnames(cnx, doctype, fieldnames, update_mode=False):
    """
    :param Connection cnx: CubicWeb database connection
    :param String doctype   : CSV file data type
    :param List fieldnames : CSV file  fieldnames
    :param bool update_mode : True if this is a partial update (SOCFACE), False for initial import
    """
    errors = []
    if invalid_doc_type(doctype):
        errors.append(cnx._("The document type '%s' is not handeled") % doctype)
        return errors

    # For SOCFACE update mode, delegate to specialized validation
    if doctype == "SOCFACE" and update_mode:
        return check_socface_update_fieldnames(cnx, fieldnames)

    expected_fieldnames = CSVNominaFieldnames.fieldnames.get(doctype, COMMON_FIELDS)
    invalid_fieldnames = set(fieldnames).difference(expected_fieldnames.keys())
    if invalid_fieldnames:
        errors.append(
            cnx._('The document contains invalid fieldnames: "%s".') % ", ".join(invalid_fieldnames)
        )

    # optional fields
    if doctype != "OAI" and "delete" not in fieldnames:
        fieldnames.append("delete")

    if list(fieldnames) != list(expected_fieldnames.keys()):
        errors.append(
            cnx._(
                'The document fieldnames are different or are in different order from expected ones: "%s".'  # noqa
            )
            % ", ".join(fieldnames)
        )
    if errors:
        errors.append(cnx._('Expected fieldnames are "%s"') % ", ".join(expected_fieldnames))
    return errors


def check_doctype(values, doctype, logger):
    if doctype in CIVIL_STATUS_CODES:
        dtype = values.get("t_a")
        if dtype and not (CIVIL_STATUS_CODES[doctype] == unormalize(dtype).lower()):
            logger.error(
                "Ignore notice %s with document type %s" % (values["notice_id"], values["t_a"])
            )
            return False
    return True


def clean_value(value):
    """Strip separator and leading/trailing whitespaces from value.

    :param str value: value to clean

    :returns: cleaned value
    :rtype: str
    """
    if value and isinstance(value, str):
        value = remove_html_tags(value).strip()
    return value


class AbstractCSVNominaReader(object):
    def __init__(self, config, cnx, service_code, log=None):
        """Initialize CSVNominaReader.

        :param dict config : reader configuration
        :param onnection cnx: cw connection
        :param String service: service code
        :param Logger log: logger
        """
        self.config = config
        if log is None:
            log = logging.getLogger("rq.task")
        self.log = log
        self.cnx = cnx
        self.service = load_services_map(self.cnx)[service_code]
        self.processed_records = 0
        self.nomina_records_to_delete = []
        self.nomina_duplicated_records = defaultdict(list)
        # keep tack of same_as relaitons
        self.linked_authorities = defaultdict(list)
        self.init_authorities_for_service()

    def get_doctype_fieldnames(self, doctype):
        return CSVNominaFieldnames.fieldnames.get(doctype, COMMON_FIELDS)

    def get_doctype_required_columns(self, doctype):
        return ("oai_id",) if doctype == "OAI" else ("notice_id",)

    def get_record_identifier(self, data):
        raise NotImplementedError

    def init_authorities_for_service(self):
        rset = self.cnx.execute(
            """Any XS, A, L WHERE X is ExternalUri, X extid XS,
               A same_as X, A is AgentAuthority, A label L
            """,  # , X source "nomina"
            {"code": self.service.code},
        )
        for nomina_stable_id, auth_eid, label in rset:
            self.linked_authorities[nomina_stable_id].append((auth_eid, label))

    def add_records_to_delete(self, line, values, act_type):
        identifier, column = self.get_record_identifier(values)
        if not identifier:
            self.log.error(
                "line %s: could not find identifier for deletion in column '%s': %s",
                line,
                column,
                values,
            )
            return
        stable_id = compute_nomina_stable_id(self.service.code, identifier)
        self.nomina_records_to_delete.append((stable_id, act_type))

    def check_duplicated_records(self, line, values):
        identifier, column = self.get_record_identifier(values)
        duplicated = self.nomina_duplicated_records.get(identifier)
        if duplicated:
            self.log.error(
                "line %s: duplicated identifier '%s' (column '%s') "
                "found in line(s): %s. Skip data.",
                line,
                identifier,
                column,
                ", ".join(duplicated),
            )
        self.nomina_duplicated_records[identifier].append(str(line))
        return duplicated

    def check_missing_required_columns(self, doctype, values, line):
        missing_required = False
        for attr in self.get_doctype_required_columns(doctype):
            if not values.get(attr):
                missing_required = True
                colname = [
                    col
                    for col, _attr in self.get_doctype_fieldnames(doctype).items()
                    if _attr == attr
                ][0]
                self.log.warning('line %s: skip the record: no "%s" found', line, colname)
        return missing_required

    def import_records(self, storage, filepath, doctype, delimiter=";", chunksize=1000):
        """index NominaRecords

        :param String filepath  : Filepath to proc.[]ess
        :param String doctype   : CSV file data type
        :param String delimiter : CSV delimiter
        """
        raise NotImplementedError
