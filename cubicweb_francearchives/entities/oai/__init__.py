# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2019
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
import logging
import time
from datetime import datetime
from lxml import etree
import urllib.parse

from psycopg2 import OperationalError
from pyramid.response import Response

from logilab.common.decorators import cachedproperty

from cubicweb.predicates import is_instance, one_line_rset
from cubicweb.entities import AnyEntity
from cubicweb_web import httpcache
from cubicweb_web.views import idownloadable

from cubicweb_oaipmh.entities import (
    ETypeOAISetSpec,
    RelatedEntityOAISetSpec,
    NoRecordsMatch,
    OAIPMHRecordAdapter,
)
from cubicweb_oaipmh import MetadataFormat
from cubicweb_oaipmh.views import OAIView, OAIResponse

from logilab.common.decorators import monkeypatch

LOGGER = logging.getLogger("francearchives.oai")


@monkeypatch(OAIView)
def __call__(self):
    """in order to be parsed by Archives Portal Europe Foundation the <ead> must
    have following attributes :

    <ead xsi:schemaLocation="urn:isbn:1-931666-22-9 http://www.loc.gov/ead/ead.xsd"
    audience="external" xmlns="urn:isbn:1-931666-22-9"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xlink="http://www.w3.org/1999/xlink">

    as "xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" is already defined on
    the wrapper (OAI-PMH) lxml remove it from <ead>. We try to keep it by injecting
    the xml record string into wrapper.
    """  # noqa
    start_time = datetime.now()
    LOGGER.info(
        f"OAI-PMH request started: verb={self.oai_request.verb}, "
        f"set={self.oai_request.setspec}, "
        f"from={self.oai_request.from_date}, "
        f"until={self.oai_request.until_date}, "
        f"metadataPrefix={self.oai_request.metadata_prefix}, "
        f"url={self.request.url}"
    )

    encoding = self._cw.encoding
    assert encoding == "UTF-8", "unexpected encoding {0}".format(encoding)
    content = b'<?xml version="1.0" encoding="%s"?>\n' % encoding.encode("utf-8")
    oai_response = OAIResponse(self.oai_request)
    # combine errors coming from view selection with those of request
    # processing.
    errors = self.errors() or {}

    # Retry logic for PostgreSQL connection errors
    max_retries = 2
    retry_delay = 1.0  # seconds
    verb_content = None
    attempt = 0

    while attempt <= max_retries:
        try:
            verb_content = self.verb_content() if not errors else None
            break  # Success, exit retry loop
        except OperationalError as e:
            attempt += 1
            error_msg = str(e)

            if "server closed the connection" in error_msg:
                LOGGER.warning(
                    f"PostgreSQL connection error (attempt {attempt}/{max_retries + 1}): {e}. "
                    f"Reconnecting and retrying..."
                )

                if attempt <= max_retries:
                    # Force reconnection
                    try:
                        self._cw.commit_and_restart()
                        LOGGER.info("Connection restarted successfully")
                    except Exception as restart_error:
                        LOGGER.error(f"Failed to restart connection: {restart_error}")
                        raise

                    # Wait before retry (exponential backoff)
                    time.sleep(retry_delay * attempt)
                    continue
                else:
                    LOGGER.error(
                        f"PostgreSQL connection error after {max_retries + 1} attempts. "
                        f"Total elapsed time: {datetime.now() - start_time}"
                    )
                    raise
            else:
                # Not a connection error, re-raise immediately
                raise

    errors.update(self.oai_request.errors)
    response_elem = oai_response.to_xml(verb_content, errors=errors)
    for ead in response_elem.xpath("..//s:ead", namespaces={"s": "urn:isbn:1-931666-22-9"}):
        ead.attrib["S"] = "#"
    for ead in response_elem.xpath("..//s:ead", namespaces={"s": response_elem.nsmap[None]}):
        ead.attrib["S"] = "#"
    content += etree.tostring(response_elem, encoding="utf-8")
    # realy ugly stuff
    content = content.replace(b'S="#"', b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"')

    elapsed_time = datetime.now() - start_time
    LOGGER.info(
        f"OAI-PMH request completed: status={'error' if errors else 'success'}, "
        f"elapsed_time={elapsed_time}, "
        f"content_size={len(content)} bytes, "
        f"errors={list(errors.keys()) if errors else 'none'}"
    )

    return Response(content, content_type="text/xml")


METADATA_FORMATS = {
    "ape_ead": (
        MetadataFormat("http://www.loc.gov/ead/ead.xsd", "urn:isbn:1-931666-22-9"),
        "oai_ead.export",
    ),
}


class FindingAidStableIdFARecordAdapter(OAIPMHRecordAdapter):
    __select__ = OAIPMHRecordAdapter.__select__ & is_instance("FindingAid")
    metadata_formats = METADATA_FORMATS.copy()
    etype = "FindingAid"

    @classmethod
    def set_definition(cls):
        return FindingAidSetSpec()

    @property
    def identifier(self):
        return self.entity.stable_id


class AbstractOAIDownloadView(idownloadable.DownloadView):
    """oai download view"""

    __select__ = one_line_rset()
    http_cache_manager = httpcache.NoHTTPCacheManager

    def set_request_content_type(self):
        entity = self.cw_rset.get_entity(self.cw_row or 0, self.cw_col or 0)
        adapter = entity.cw_adapt_to(self.adapter_id)
        self._cw.set_content_type(
            adapter.content_type,
            filename=adapter.file_name,
            encoding=adapter.encoding,
            disposition="attachment",
        )

    def call(self):
        entity = self.cw_rset.get_entity(self.cw_row or 0, self.cw_col or 0)
        adapter = entity.cw_adapt_to(self.adapter_id)
        self.w(adapter.dump())


class FindingAidSetSpec(ETypeOAISetSpec):
    """OAI-PMH findinaid set specification

    available sets are:

    - ``findingaid``
    - ``findingaid:service:{service_code}`` (e.g. ``findingaid:service:FRAD005``)
    """

    def __init__(self):
        super(FindingAidSetSpec, self).__init__("FindingAid", "stable_id")

    def setspec_restrictions(self, value=None):
        if value is not None:
            raise NoRecordsMatch("unexpected setspec")
        return "X is FindingAid", {}

    def all_services(self, cnx):
        start_time = datetime.now()
        LOGGER.debug(
            "FindingAidSetSpec.all_services started: "
            "computing services with published FindingAids"
        )

        services = list(
            cnx.execute(
                """Any S,SC,SN,SSN,SN2 WHERE S is Service, S code SC,
                S name SN, S short_name SSN, S name2 SN2,
                NOT S code NULL,
                EXISTS(X is FindingAid, X service S,
                X in_state ST, ST name %(st)s)""",
                {"st": "wfs_cmsobject_published"},
            ).entities()
        )

        elapsed = datetime.now() - start_time
        LOGGER.debug(
            f"FindingAidSetSpec.all_services completed: "
            f"found {len(services)} services in {elapsed}"
        )
        return services

    def setspecs(self, cnx):
        yield "findingaid", cnx._("FindingAid")  # main set
        # + list of all services that have provided some findingaids
        for service in self.all_services(cnx):
            yield ("findingaid:service:{}".format(service.code), service.publisher())

    def __getitem__(self, key):
        assert key == "service", "other relations than 'service' are not tested yet"
        specifier = RelatedEntityOAISetSpec("service", "Service", "code")
        specifier.__parent__ = self
        return specifier


class OAIRepository(AnyEntity):
    __regid__ = "OAIRepository"

    @property
    def tasks(self):
        """return the list of task entities associated to the repository

        The returned tasks are sorted by their creation date.
        """
        return sorted(self.reverse_oai_repository, key=lambda t: t.creation_date)

    @cachedproperty
    def oai_params(self):
        url = urllib.parse.urlparse(self.url)
        return urllib.parse.parse_qs(url.query)
