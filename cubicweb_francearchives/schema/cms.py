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
    String,
    RichString,
    RelationDefinition,
    Date,
    Int,
    Boolean,
    SubjectRelation,
    Bytes,
    Float,
)
from yams.constraints import SizeConstraint, RegexpConstraint

from cubicweb import _
from cubicweb.schema import ERQLExpression
from cubicweb_link.schema import Link
from cubicweb_file.schema import File
from cubicweb_card.schema import Card


from cubicweb_francearchives import SOCIAL_NETWORK_LIST, CMS_OBJECTS
from cubicweb_francearchives.schema.ead import Json


link_title_sizeconsts = [
    c for c in Link.get_relation("title").constraints if isinstance(c, SizeConstraint)
]
link_title_sizeconsts[0].max = 512


def uuidize(cls):
    cls.add_relation(String(maxsize=32, required=True, unique=True), name="uuid")
    return cls


for etype in (Link, File):
    uuidize(etype)

Card.add_relation(Boolean(default=True), name="do_index")


PNIA_RO_ATTR_PERMS = {"read": ("managers", "guests", "users"), "add": ("managers",), "update": ()}

PNIA_ADMIN_ATTR_PERMS = {
    "read": ("managers", "guests", "users"),
    "add": ("managers",),
    "update": ("managers",),
}


class PreviousInfo(EntityType):
    url = String()


class previous_info(RelationDefinition):
    subject = CMS_OBJECTS
    object = "PreviousInfo"
    cardinality = "?1"
    composite = "subject"


@uuidize
class CmsObject(EntityType):
    __abstract__ = True
    title = String(required=True, fulltextindexed=True)
    content = RichString(fulltextindexed=True, default_format="text/html")
    order = Int(required=True, default=0)
    metadata = SubjectRelation("Metadata", inlined=True, cardinality="??", composite="subject")


@uuidize
class Metadata(EntityType):
    title = String()
    description = String()
    subject = String()
    creator = String()
    type = String()
    keywords = String()


ON_FRONTPAGE_VOC = (
    "",
    _("onhp_hp"),
    _("onhp_nhp"),
    _("onhp_arch"),
)


class Section(CmsObject):
    __permissions__ = {
        "read": ("managers", "users", "guests"),
        "add": ("managers", "users"),
        "update": ("managers", "owners"),
        "delete": (
            ERQLExpression("X name NULL, U in_group G, " 'G name IN ("owners", "managers")'),
        ),
    }
    subtitle = String()
    name = String(
        unique=True, description=_("unique identifier"), __permissions__=PNIA_RO_ATTR_PERMS
    )
    short_description = String(description=_("display on menu"))
    children = SubjectRelation(CMS_OBJECTS, cardinality="*?")
    header = String(maxsize=500, description=_("display on HP, maximum length is 500 characters"))
    on_homepage = String(
        vocabulary=ON_FRONTPAGE_VOC, default=_(""), internationalizable=True, indexed=True
    )
    on_homepage_order = Int()
    display_mode = String(
        vocabulary=(
            _("mode_no_display"),
            _("mode_tree"),
            _("mode_themes"),
        ),
        default=_("mode_tree"),
        internationalizable=True,
    )
    children_sorting_order = String(
        description=_(
            "Sortorder for item order (e.g '-sortdate' for sorting in reverse chronological order or '-sortdate -order'). Multiple values must be separated by a space (e.g '-sortdate -order'). If the field is left empty, the reverse chronological sorting will be applied."  # noqa
        )
    )


@uuidize
class CmsI18nObject(EntityType):
    __abstract__ = True
    title = String(required=True, fulltextindexed=True)
    content = RichString(fulltextindexed=True, default_format="text/html")
    language = String(
        required=True,
        vocabulary=(
            _("en"),
            _("de"),
            _("es"),
        ),
    )


class SectionTranslation(CmsI18nObject):
    __unique_together__ = [("language", "translation_of")]
    subtitle = String(fulltextindexed=True)
    short_description = String(fulltextindexed=True)
    header = String(maxsize=500, description=_("display on HP, maximum length is 500 characters"))


class translation_of_section(RelationDefinition):
    name = "translation_of"
    subject = "SectionTranslation"
    object = "Section"
    cardinality = "1*"
    inlined = True
    composite = "object"


class BaseContent(CmsObject):
    header = String(maxsize=500, description=_("display on HP, maximum length is 500 characters"))
    summary = RichString(default_format="text/html")
    summary_policy = String(
        required=True,
        vocabulary=(
            _("no_summary"),
            _("summary_headers_6"),
            # _("summary_headers_1"),
            _("summary_headers_2"),
            _("summary_headers_3"),
        ),
        default=_("no_summary"),
        internationalizable=True,
    )
    content_type = String(
        vocabulary=(_("Article"), _("Publication"), _("SearchHelp")),
        default="Article",
        internationalizable=True,
        required=True,
    )
    description = String()
    keywords = String()
    on_homepage = String(
        vocabulary=ON_FRONTPAGE_VOC, default=_(""), internationalizable=True, indexed=True
    )
    on_homepage_order = Int()


class BaseContentTranslation(CmsI18nObject):
    __unique_together__ = [("language", "translation_of")]
    header = String(maxsize=500, description=_("display on HP, maximum length is 500 characters"))
    summary = RichString(default_format="text/html")


class translation_of_basecontent(RelationDefinition):
    name = "translation_of"
    subject = "BaseContentTranslation"
    object = "BaseContent"
    cardinality = "1*"
    inlined = True
    composite = "object"


class NewsContent(CmsObject):
    header = String(maxsize=500, description=_("display on HP, maximum length is 500 characters"))
    start_date = Date()
    stop_date = Date()
    on_homepage = String(
        vocabulary=ON_FRONTPAGE_VOC, default=_(""), internationalizable=True, indexed=True
    )
    on_homepage_order = Int()


@uuidize
class CommemoDate(EntityType):
    type = String(maxsize=256)  # TODO: use a vocabulary later ?
    date = Date(required=True)
    date_is_precise = Boolean(indexed=True)


class CommemorationItem(CmsObject):
    header = String(maxsize=500, description=_("display on HP, maximum length is 500 characters"))
    summary = RichString(default_format="text/html")
    summary_policy = String(
        required=True,
        vocabulary=(
            _("no_summary"),
            _("summary_headers_6"),
            # _("summary_headers_1"),
            _("summary_headers_2"),
            _("summary_headers_3"),
        ),
        default=_("no_summary"),
        internationalizable=True,
    )
    subtitle = String(fulltextindexed=True)
    alphatitle = String(indexed=True)
    start_year = Int()
    stop_year = Int()
    commemoration_year = Int()
    commemo_dates = SubjectRelation("CommemoDate")
    on_homepage = String(
        vocabulary=ON_FRONTPAGE_VOC, default=_(""), internationalizable=True, indexed=True
    )
    on_homepage_order = Int()


class CommemorationItemTranslation(CmsI18nObject):
    __unique_together__ = [("language", "translation_of")]
    subtitle = String(fulltextindexed=True)
    header = String(maxsize=500, description=_("display on HP, maximum length is 500 characters"))
    summary = RichString(default_format="text/html")


class translation_of_commemorationitem(RelationDefinition):
    name = "translation_of"
    subject = "CommemorationItemTranslation"
    object = "CommemorationItem"
    cardinality = "1*"
    inlined = True
    composite = "object"


@uuidize
class Image(EntityType):
    caption = RichString(default_format="text/html")
    description = RichString(
        default_format="text/html",
        description=_("this field will be displayed as image alt in HTML"),
    )
    copyright = String()
    image_file = SubjectRelation("File", cardinality="1*", inlined=True, composite="subject")
    uri = String(description=_("Url for an internal link"))


class commemoration_image(RelationDefinition):
    subject = "CommemorationItem"
    object = "Image"
    cardinality = "*?"
    composite = "subject"


class news_image(RelationDefinition):
    subject = "NewsContent"
    object = "Image"
    cardinality = "*?"
    composite = "subject"


class basecontent_image(RelationDefinition):
    subject = "BaseContent"
    object = "Image"
    cardinality = "*?"
    composite = "subject"


class section_image(RelationDefinition):
    # XXX only one relation `image` should be sufficient
    subject = ("Section",)
    object = "Image"
    cardinality = "*?"
    composite = "subject"


class OrderedSubjectAuthority(EntityType):
    """Ternary relation describing the order of a subject in a section"""

    subject_entity = SubjectRelation(
        "SubjectAuthority", cardinality="1*", composite="object", inlined=True
    )
    order = Int(required=True)


class subject_image(RelationDefinition):
    # XXX only one relation `image` should be sufficient
    subject = "SubjectAuthority"
    object = "Image"
    cardinality = "*?"
    composite = "subject"


class section_themes(RelationDefinition):
    subject = "Section"
    object = "OrderedSubjectAuthority"


class service_image(RelationDefinition):
    subject = "Service"
    object = "Image"
    cardinality = "??"
    composite = "subject"


class externref_image(RelationDefinition):
    subject = "ExternRef"
    object = "Image"
    cardinality = "*?"
    composite = "subject"


@uuidize
class CssImage(EntityType):
    __persmissions_ = {
        "read": ("managers", "users", "guests"),
        "add": ("managers", "users"),
        "update": ("managers", "users"),
        "delete": (),
    }

    cssid = String(required=True, maxsize=64, unique=True, indexed=True)
    caption = RichString(default_format="text/html")
    description = RichString(default_format="text/html")
    copyright = String()
    image_file = SubjectRelation("File", cardinality="1*", inlined=True, composite="subject")
    order = Int(required=True, unique=True)


class cssimage_of(RelationDefinition):
    subject = "CssImage"
    object = "Section"
    cardinality = "??"


@uuidize
class Category(EntityType):
    name = String(required=True, fulltextindexed=True)


class commemoration_category(RelationDefinition):
    subject = "CommemorationItem"
    object = "Category"
    cardinality = "*?"


@uuidize
class Circular(EntityType):
    circ_id = String(
        indexed=True,
        required=True,
        unique=True,
        constraints=[
            RegexpConstraint(r"^[^/:?&\s]+$"),
        ],
    )
    siaf_daf_code = String(
        fulltextindexed=True, description=_("Text identification code (SIAF or DAF)")
    )
    nor = String(description=_("Normalized interministerial system for official tests numbering"))
    code = String(
        fulltextindexed=True, description=_("Text identification code (other than SIAF or DAF)")
    )
    title = String(fulltextindexed=True, required=True, description=_("Text title"))
    kind = String(fulltextindexed=True, description=_("Text kind (other than SIAF or DAF)"))
    siaf_daf_kind = String(fulltextindexed=True, description=_("Text kind (SIAF or DAF)"))
    status = String(
        required=True,
        fulltextindexed=True,
        vocabulary=(
            _("in-effect"),
            _("revoked"),
            _("in-effect-partially"),
            _("punctual"),
            _("obsolete"),
        ),
    )
    signing_date = Date(description=_("Signing or publication date (other than DAF or SIAF)"))
    siaf_daf_signing_date = Date(description=_("Signing or publication date"))
    circular_modification_date = Date()
    abrogation_date = Date()
    link = String(description=_("Hypertext link to the circular"))
    order = Int(required=True, default=0)
    producer = String(description=_("producers name"))
    producer_acronym = String()
    abrogation_text = String()
    archival_field = String()
    json_values = Json(__permissions__=PNIA_RO_ATTR_PERMS)


class attachment(RelationDefinition):
    """internal file link"""

    subject = "Circular"
    object = "File"
    cardinality = "*?"
    composite = "subject"
    fulltext_container = "subject"


class additional_attachment(RelationDefinition):
    """additional internal file link"""

    subject = "Circular"
    object = "File"
    cardinality = "**"
    composite = "subject"
    fulltext_container = "subject"


class additional_link(RelationDefinition):
    subject = "Circular"
    object = "Link"
    cardinality = "**"


class historical_context(RelationDefinition):
    subject = "Circular"
    object = "Concept"
    cardinality = "?*"


class business_field(RelationDefinition):
    subject = "Circular"
    object = "Concept"
    cardinality = "**"


class document_type(RelationDefinition):
    subject = "Circular"
    object = "Concept"
    cardinality = "?*"


class action(RelationDefinition):
    subject = "Circular"
    object = "Concept"
    cardinality = "?*"


class modified_text(RelationDefinition):
    subject = "Circular"
    object = "OfficialText"
    cardinality = "**"


class modifying_text(RelationDefinition):
    subject = "Circular"
    object = "OfficialText"
    cardinality = "**"


class revoked_text(RelationDefinition):
    subject = "Circular"
    object = "OfficialText"
    cardinality = "**"


@uuidize
class OfficialText(EntityType):
    code = String(required=True)
    name = String()
    circular = SubjectRelation("Circular", inlined=True, cardinality="?*")


@uuidize
class Service(EntityType):
    category = String(required=True, fulltextindexed=True)
    name = String(fulltextindexed=True)
    name2 = String(fulltextindexed=True, description=_("long name"))
    short_name = String(maxsize=64, fulltextindexed=True, indexed=True, description=_("short name"))
    phone_number = String()
    code_insee_commune = String(maxsize=20)
    email = String()
    address = String(fulltextindexed=True)
    mailing_address = String(fulltextindexed=True)
    zip_code = String(maxsize=10)
    city = String(fulltextindexed=True)
    website_url = String()
    search_form_url = String(
        description=_("Use {eadid}, {unitid} or {unittitle} substitution pattern")
    )
    thumbnail_url = String(description=_("Use {url} substitution pattern"))
    thumbnail_dest = String(description=_("Use {url} substitution pattern"))
    annual_closure = String()
    opening_period = String()
    contact_name = String(fulltextindexed=True)
    level = String(
        vocabulary=(
            _("level-R"),
            _("level-D"),
            _("level-C"),
            _("level-Y"),
            _("level-M"),
            _("level-P"),
            _("level-H"),
            _("level-U"),
            _("level-I"),
            _("level-E"),
            _("level-N"),
            _("level-F"),
        ),
        fulltextindexed=True,
        internationalizable=True,
    )
    code = String(maxsize=64, fulltextindexed=True)
    longitude = Float()
    latitude = Float()
    dpt_code = String(maxsize=3, indexed=True)
    other = RichString(default_format="text/html", fulltextindexed=True)
    iiif_extptr = Boolean(
        default=False,
        description=_("Service has a IIIF server"),
    )
    iiif_ead_policy = String(
        vocabulary=(
            _("iiif_role"),  # role == IIIF_MANIFEST_ROLE
            _("iiif_ligeo_extptr"),  # LIGEO
            _("iiif_bnf"),  # Pattern standard IIIF (BNF, Mnesys, etc.)
            _("iiif_ajlsm"),  # "FRAD053", "FRCDF"
        ),
        internationalizable=True,
    )


class annex_of(RelationDefinition):
    subject = "Service"
    object = "Service"
    cardinality = "?*"


class maintainer(RelationDefinition):
    subject = "AuthorityRecord"
    object = "Service"
    cardinality = "?*"
    inlined = True


@uuidize
class SocialNetwork(EntityType):
    name = String(required=True, fulltextindexed=True, vocabulary=SOCIAL_NETWORK_LIST)
    url = String(required=True)


class service_social_network(RelationDefinition):
    subject = "Service"
    object = "SocialNetwork"
    cardinality = "**"
    composite = "subject"


class ExternRef(CmsObject):
    url = String()
    # turn reftype into an entity?
    reftype = String(
        required=True,
        vocabulary=(_("Blog"), _("Virtual_exhibit"), _("Other")),
        internationalizable=True,
    )
    start_year = Int()
    stop_year = Int()
    header = String(maxsize=500, description=_("display on HP, maximum length is 500 characters"))
    on_homepage = String(
        vocabulary=ON_FRONTPAGE_VOC, default=_(""), internationalizable=True, indexed=True
    )
    on_homepage_order = Int()


class exref_service(RelationDefinition):
    subject = "ExternRef"
    object = "Service"


class basecontent_service(RelationDefinition):
    subject = "BaseContent"
    object = "Service"


class related_content_suggestion(RelationDefinition):
    subject = ("BaseContent", "ExternRef", "CommemorationItem")
    object = ("BaseContent", "ExternRef", "CommemorationItem")


@uuidize
class Map(EntityType):
    title = String(required=True, fulltextindexed=True)
    map_title = String(fulltextindexed=True)
    top_content = RichString(
        fulltextindexed=True, default_format="text/html", description=_("appears before the map")
    )
    bottom_content = RichString(
        fulltextindexed=True, default_format="text/html", description=_("appears after the map")
    )

    map_file = Bytes(
        required=True,
        description=_(
            'CSV file containing "Code_insee", "URL", '
            '"Couleur" and "Legende"'
            'columns separated by ","'
        ),
    )
    metadata = SubjectRelation("Metadata", inlined=True, cardinality="??")
    order = Int(required=True, default=0)


class map_image(RelationDefinition):
    subject = "Map"
    object = "Image"
    cardinality = "??"
    composite = "subject"


class NewsLetterSubscriber(EntityType):
    email = String(required=True, unique=True, maxsize=256)


class Caches(EntityType):
    __unique_together__ = [("name", "instance_type")]
    name = String(required=True, maxsize=32, indexed=True)
    values = Json(__permissions__=PNIA_ADMIN_ATTR_PERMS)
    instance_type = String(required=True, vocabulary=("cms", "consultation"))


class GlossaryTerm(EntityType):
    term = String(unique=True, required=True)
    term_plural = String(unique=True, description=_("Usefull only for labels and filters"))
    short_description = String(
        required=True, description=_("Glossary term description for the popup")
    )
    description = String(required=True, description=_("Full glossary term description"))
    sort_letter = String(required=True, maxsize=1)
    anchor = String(unique=True)


class FaqItem(EntityType):
    question = RichString(required=True, default_format="text/html")
    answer = RichString(required=True, default_format="text/html")
    category = String(
        required=True,
        vocabulary=(
            _("01_faq_basecontent_public"),
            _("02_faq_search"),
            _("03_faq_ir"),
            _("04_faq_circular"),
            _("05_faq_basecontent_pro"),
            _("06_faq_eac"),
            _("07_faq_nomina"),
        ),
        default=_("03_faq_ir"),
        internationalizable=True,
    )
    order = Int()


class FaqItemTranslation(EntityType):
    __unique_together__ = [("language", "translation_of")]
    question = RichString(required=True, default_format="text/html")
    answer = RichString(required=True, default_format="text/html")
    language = String(
        required=True,
        vocabulary=(
            _("en"),
            _("de"),
            _("es"),
        ),
    )


class translation_of_faq(RelationDefinition):
    name = "translation_of"
    subject = "FaqItemTranslation"
    object = "FaqItem"
    cardinality = "1*"
    inlined = True
    composite = "object"


class SiteLink(EntityType):
    __permissions__ = {
        "read": ("managers", "users", "guests"),
        "add": ("managers",),
        "update": ("managers",),
        "delete": ("managers",),
    }
    label_fr = String(maxsize=512, required=True)
    label_en = String(maxsize=512)
    label_es = String(maxsize=512)
    label_de = String(maxsize=512)
    description_fr = String(maxsize=350)
    description_en = String(maxsize=350)
    description_es = String(maxsize=350)
    description_de = String(maxsize=350)
    link = String(maxsize=512, required=True)
    context = String(
        required=True,
        vocabulary=(
            _("main_menu_links"),
            _("archiviste_hp_links"),
            _("footer_ministries"),
            _("footer_public_sites"),
            _("footer_archives_sites"),
            _("footer_search_notebooks"),
            _("footer_usefull_links"),
            _("footer_links_directories"),
            _("footer_links"),
            _("foundout_link"),
        ),
        internationalizable=True,
    )
    order = Int(required=True)
