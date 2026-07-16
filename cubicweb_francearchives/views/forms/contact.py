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
from cubicweb import mail, _
from cubicweb_web import ProcessFormError
from cubicweb_web import formfields as ff
from cubicweb_web.views.forms import FieldsForm

from cubicweb_francearchives.views.forms import (
    AbstractPniaStaticFormRenderer,
    AbstractStaticFormView,
    EMAIL_REGEX,
)
from cubicweb_francearchives.views import get_template

ADOCS_OPTION = _("contact_object_5")

SIMPEAD_OPTION = _("contact_object_6")


class ContactFormView(AbstractStaticFormView):
    __regid__ = "contact"
    title = _("Contact")
    eulerian_tag = True
    eulerian_pagegroup = "editorial"

    @property
    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        return [
            (self._cw.build_url(""), _("Home")),
            (None, self._cw._(self.title)),
        ]


class ContactForm(FieldsForm):
    __regid__ = "contact"
    form_renderer_id = "contact"
    domid = "contactForm"
    cssclass = "fr-col-12 fr-col-lg-8"
    needs_css = []
    redirect_path = "contact#contactForm"
    email_content = _(
        """%(message)s


respond to : %(name)s, %(email)s
"""
    )  # noqa
    # fields
    name = ff.StringField(label=_("Name: "), required=True)
    email = ff.StringField(required=True, label=_("Email:"))
    object = ff.StringField(required=True, label=_("Object:"))
    message = ff.StringField(required=True, label=_("Message:"))

    @property
    def action(self):
        return self._cw.build_url(self.redirect_path)

    def publish_form(self):
        """Captcha field is hidden from humans. If captcha is filled
        there is a bug chance that it was done by a robot"""
        logger = logging.getLogger(__name__)
        form = self._cw.vreg["forms"].select("contact", self._cw)
        captcha = self._cw.form.get("captcha")
        if captcha:
            # do not send the email
            return
        data, errors = self.checked_data(form)
        if not errors:
            level = "success"
            email_object = data["object"]
            recipient = self._cw.vreg.config["contact-email"]
            if email_object == ADOCS_OPTION:
                recipient = self._cw.vreg.config["contact-adocs-email"] or recipient
            elif email_object == SIMPEAD_OPTION:
                recipient = self._cw.vreg.config["contact-simplead-email"] or recipient
            msg = self.build_email(recipient, data)
            try:
                logger.info(f"sending e-mail to {recipient}")
                self._cw.vreg.config.sendmails([(msg, (recipient,))])
                msg = self._cw._("Your message has been send.")
                logger.info(f"e-mail has been sent to {recipient}")
            except Exception as exception:
                logging.error(exception)
                level = "error"
                msg = self._cw._("Your message could not be send. Please try again.")
            return {"errors": errors, "msg": msg, "level": level}
        else:
            return {"errors": errors}

    def build_email(self, recipient, data):
        content = self._cw._(self.email_content) % data
        return mail.format_mail(
            {},
            [recipient],
            content=content,
            subject=self._cw._(data["object"]),
            config=self._cw.vreg.config,
        )

    def checked_data(self, form):
        form.formvalues = {}  # init fields value cache
        data, errors = {}, {}
        for field in form.fields:
            try:
                for field, value in field.process_posted(form):
                    if value is not None:
                        data[field.role_name()] = value
                    if field.name == "email" and not EMAIL_REGEX.match(value):
                        msg = _("Please enter a valid email address. For exemple: name@domain.fr")
                        errors["email"] = msg
            except ProcessFormError as exc:
                errors[field.role_name()] = str(exc)
        return data, errors


class ContactFormRenderer(AbstractPniaStaticFormRenderer):
    __regid__ = "contact"
    template = get_template("contact_fields.jinja2")

    @property
    def html_title(self):
        return f'<h3>{self._cw._("Your message")}</h3>'

    def template_attrs(self):
        _ = self._cw._
        selected_object = None
        contact_object = self._cw.form.get("object")
        if contact_object == "adocs":
            selected_object = "contact_object_5"
        elif contact_object == "simplead":
            selected_object = "contact_object_6"
        return {
            "_": _,
            "selected_object": selected_object,
            "submit_value": _("Send your message"),
            "required_info": _("This field is required"),
            "contact_name_label": _("Your name"),
            "contact_email_label": _("Your email address"),
            "contact_email_help": _("Expected format:"),
            "contact_object_label": _("Object of the message"),
            "contact_message_label": _("Your message"),
            "contact_captcha_label": _("Captcha:"),
            "object_select_message": _("Please select the object of your message"),
            "contact_objects": [
                _("contact_object_1"),
                _("contact_object_2"),
                _("contact_object_3"),
                _("contact_object_4"),
                _(ADOCS_OPTION),
                _(SIMPEAD_OPTION),
                _("contact_object_7"),
            ],
        }
