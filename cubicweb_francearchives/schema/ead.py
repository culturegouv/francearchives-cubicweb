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
"""cubicweb-francearchives schema"""

from yams.buildobjs import (
    EntityType,
    RelationDefinition,
    SubjectRelation,
    make_type,
    ComputedRelation,
    String,
    RichString,
    Int,
    Boolean,
    Date,
)
from cubicweb import _
from cubicweb.schema import WorkflowableEntityType


Json = make_type("Json")


class Did(EntityType):
    unitid = String(maxsize=256, fulltextindexed=True, indexed=True)
    unittitle = String(required=True, fulltextindexed=True)
    unitdate = String()
    extptr = String(maxsize=2048)
    materialspec = RichString(default_format="text/html")
    note = RichString(default_format="text/html")
    origination = RichString(default_format="text/html")
    physdesc = RichString(default_format="text/html")
    physloc = RichString(default_format="text/html")
    repository = RichString(default_format="text/html")
    startyear = Int()
    stopyear = Int()
    abstract = RichString(default_format="text/html")
    lang_description = RichString(default_format="text/html")
    lang_code = String(maxsize=1024, indexed=True)


class FAHeader(EntityType):
    titlestmt = RichString(default_format="text/html", fulltextindexed=True)
    titleproper = String(fulltextindexed=True)
    publicationstmt = RichString(default_format="text/html", fulltextindexed=True)
    author = RichString(default_format="text/html")
    changes = RichString(default_format="text/html")
    creation = RichString(default_format="text/html")
    descrules = RichString(default_format="text/html")
    lang_description = RichString(default_format="text/html")
    lang_code = String(maxsize=1024, indexed=True)


class FindingAid(EntityType):
    """A descriptive document created to allow retrieval within an archive."""

    name = String(required=True, unique=True, indexed=True)
    eadid = String(required=True, fulltextindexed=True)
    publisher = String(required=True, indexed=True)
    description = RichString(fulltextindexed=True, default_format="text/html")
    # acqinfo = RichString(default_format='text/html')
    accessrestrict = RichString(default_format="text/html")
    userestrict = RichString(default_format="text/html")
    acquisition_info = RichString(default_format="text/html")
    additional_resources = RichString(default_format="text/html")
    bibliography = RichString(default_format="text/html")
    keywords = String(fulltextindexed=True, description=_("comma-separated list of key words"))
    fa_header = SubjectRelation("FAHeader", cardinality="11", inlined=True, composite="subject")
    did = SubjectRelation("Did", cardinality="1*", inlined=True)
    # arrangement = SubjectRelation('Arrangement', cardinality='??',
    #                               inlined=True, composite='subject')
    # biblio_elements = SubjectRelation('BibElement')
    bioghist = RichString(default_format="text/html")
    notes = RichString(default_format="text/html")
    scopecontent = RichString(fulltextindexed=True, default_format="text/html")
    stable_id = String(required=True, unique=True, maxsize=64)
    digitized_versions = SubjectRelation("DigitizedVersion")
    service = SubjectRelation("Service", cardinality="?*", inlined=True)
    website_url = String(maxsize=512, description=_("used as bounce url"))
    oai_id = String(maxsize=512, indexed=True)


class top_components(ComputedRelation):
    rule = "O finding_aid S, NOT EXISTS(O parent_component FAP)"


class child_components(ComputedRelation):
    rule = "O parent_component S"


class findingaid_support(RelationDefinition):
    subject = "FindingAid"
    object = "File"
    cardinality = "??"
    inlined = True
    composite = "subject"
    description = _("support document for a finding aid")


class ape_ead_file(RelationDefinition):
    subject = "FindingAid"
    object = "File"
    cardinality = "??"
    inlined = True
    composite = "subject"
    description = _("APE-EAD XML version of the finding aid")


class FAComponent(EntityType):
    did = SubjectRelation("Did", cardinality="1*", inlined=True)
    description = RichString(fulltextindexed=True, default_format="text/html")
    bibliography = RichString(default_format="text/html")
    accessrestrict = RichString(default_format="text/html")
    userestrict = RichString(default_format="text/html")
    acquisition_info = RichString(default_format="text/html")
    additional_resources = RichString(default_format="text/html")
    # appraisal = String()
    parent_component = SubjectRelation("FAComponent", cardinality="?*", inlined=True)
    finding_aid = SubjectRelation("FindingAid", cardinality="1*", inlined=True)
    digitized_versions = SubjectRelation("DigitizedVersion")
    # arrangement = SubjectRelation('Arrangement', cardinality='??',
    #                               inlined=True, composite='subject')
    # biblio_elements = SubjectRelation('BibElement')
    bioghist = RichString(default_format="text/html")
    notes = RichString(default_format="text/html")
    scopecontent = RichString(fulltextindexed=True, default_format="text/html")
    stable_id = String(required=True, unique=True, maxsize=64)
    component_order = Int(indexed=True)


class EsDocument(EntityType):
    doc = Json()
    entity = SubjectRelation(
        ("FindingAid", "FAComponent"), inlined=True, composite="object", cardinality="1?"
    )


class DigitizedVersion(EntityType):
    url = String(maxsize=512)
    illustration_url = String(maxsize=512)
    role = String(maxsize=128, indexed=True)


class OAIRepository(EntityType):
    name = String(maxsize=128, description=_("human-readable name for the repository"))
    service = SubjectRelation("Service", cardinality="1*", inlined=True)
    url = String(required=True, maxsize=512, description=_("OAI-PMH ListRecords url"))
    # "Index policy: normalize indexes labels"
    should_normalize = Boolean(default=True)
    # "Index policy: consider indexes within the service
    context_service = Boolean(default=True)
    # Is concerned by automatical delta oai import
    periodical_import = Boolean(default=False)
    last_successful_import = Date()


class OAIImportTask(WorkflowableEntityType):
    oai_repository = SubjectRelation(
        "OAIRepository", cardinality="1*", inlined=True, composite="object"
    )


class fatask_oaiharvest_file(RelationDefinition):
    subject = "OAIImportTask"
    object = "File"
    cardinality = "*?"
    # quick fix to resolve incompatibilities with jsonchema.
    # fatask_oaiharvest_file files deletions is handled in a hook
    # composite = "subject"


class fa_referenced_files(RelationDefinition):
    subject = ("FindingAid", "FAComponent")
    object = "File"
    composite = "subject"
    description = _(
        "files referenced in '[otherfindaid|relatedmaterial|separatedmateri]//..//archref'"
    )  # noqa
