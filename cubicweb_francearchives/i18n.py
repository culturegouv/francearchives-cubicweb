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
from babel.messages.frontend import extract_messages
import csv
from itertools import chain
import json
from glob import glob
import logging
import os
import os.path as osp
import re


from cubicweb import cwctl
from cubicweb.cwconfig import CubicWebConfiguration as cwcfg
from cubicweb_web.i18n import WebI18nCubeMessageExtractor

import cubicweb_francearchives as cwfa


PO_DIR = osp.join(osp.abspath(osp.dirname(cwfa.__file__)), "i18n")
NAMED_SUBST_RGX = re.compile(r"%\((.*?)\)s")


def is_application_entry(entry, skip_msgctxt=True):
    """return True if the entry was created from an explicit application message
    (i.e. not an automtically created one by CW from the application schema).

    Since we don't have separate po files in
    (cf. https://www.cubicweb.org/ticket/1631210), we use the best possible
    pessimistic heuristic.
    """
    if entry.msgctxt != "appjs" and skip_msgctxt:
        return False
    # XXX load schema and check for etype instead of this
    #     stupid 2-words heuristic
    if entry.msgid.startswith("New ") and len(entry.msgid.split()) == 2:
        return False
    if entry.msgid.startswith("This ") and len(entry.msgid.split()) == 2:
        return False
    if entry.msgid.startswith("add a ") and len(entry.msgid.split()) == 3:
        return False
    return True


def po_entries(po, skip_msgctxt=True):
    """return all entries in ``po`` sorted by msgids"""
    all_entries = chain(po.translated_entries(), po.untranslated_entries())
    application_entries = (
        entry for entry in all_entries if is_application_entry(entry, skip_msgctxt)
    )
    return sorted(application_entries, key=lambda e: e.msgid)


def all_pofiles():
    """parses ``PO_DIR`` and load all '.po' files found

    return the corresponding 'lang' -> 'pofile' dictionary
    """
    pofiles = {}
    for filepath in glob(osp.join(PO_DIR, "*.po")):
        pofiles[osp.splitext(osp.basename(filepath))[0]] = polib.pofile(filepath)
    return pofiles


def pofiles_as_dicts(po_files, skip_msgctxt=True):
    """convert a mapping 'lang' -> 'pofile' into a mapping
    'lang' -> {(msgctxt, msgid): entry}

    :param po_files: dictionary mapping lang to pofile
    :param skip_msgctxt: whether or not we should distinguish entries
                         with different msgctxts
    """
    po_dicts = {}
    for lang, pofile in po_files.items():
        lang_translations = {}
        for entry in po_entries(pofile, skip_msgctxt):
            lang_translations[(entry.msgctxt or "", entry.msgid)] = entry
        po_dicts[lang] = lang_translations
    return po_dicts


def dump_csv(po_files, output_filename):
    """dump ``po_files`` as CSV in ``output_filename``

    :param po_files: a dictionary mapping 'lang' to a `polib.POFile` object
    :param output_filename: the CSV output filename
    """
    langs = list(cwfa.SUPPORTED_LANGS)
    with open(output_filename, "w") as outf:
        writer = csv.writer(outf)
        headers = ["msgctxt", "msgid"] + langs
        writer.writerow(headers)
        all_po_entries = [po_entries(po_files[lang]) for lang in langs]
        csv_rows = []
        for entries in zip(*all_po_entries):
            csv_row = []
            for lang, entry in zip(langs, entries):
                csv_row.append(entry.msgstr)
                substitutions_consistent(entry.msgid, entry.msgstr)
            csv_row = [entry.msgctxt, entry.msgid] + csv_row
            csv_rows.append(csv_row)
        writer.writerows(csv_rows)


def translations_iterator(reader):
    first_row = next(reader)
    assert first_row[:5] == ["msgctxt", "msgid", "fr", "en", "de"], "invalid header row: %s" % (
        first_row,
    )
    row_length = len(first_row)
    for row in reader:
        values = tuple((cell or "") for cell in row)
        # if current row is shorter than the header one, it means that
        # we don't have translations for all languages, then pad with u''
        if len(values) < row_length:
            values += [""] * (row_length - len(values))
        msgctxt, msgid = values[:2]
        yield (msgctxt, msgid, dict(list(zip(first_row[2:], values[2:]))))


def load_translations_from_csv(filepath):
    with open(filepath) as inputf:
        reader = csv.reader(inputf)
        translations = {}
        for msgctxt, msgid, msg_translations in translations_iterator(reader):
            translations[(msgctxt, msgid)] = msg_translations
        return translations


def substitutions_consistent(msgid, msgstr):
    """
    >>> substitutions_consistent('foo', 'bar')
    True
    >>> substitutions_consistent('foo %s', 'bar')
    False
    >>> substitutions_consistent('foo', 'bar %s')
    False
    >>> substitutions_consistent('%(foo)s bla %(bar)s', '%(foo)s %(bar)s')
    True
    >>> substitutions_consistent('%(foo)s %(bar)s', '%(foo )s %(bar)s')
    False
    >>> substitutions_consistent('%(foo)s %(bar)s', '%(foo)s')
    True
    """
    msgid_substs = set(NAMED_SUBST_RGX.findall(msgid))
    msgstr_substs = set(NAMED_SUBST_RGX.findall(msgstr))
    unknown_substs = msgstr_substs - msgid_substs
    # empty msgstr: testing substs would raise false positives
    if not msgstr:
        return True
    if unknown_substs:
        logging.error(
            "got substs %s in msgid (%r), %s in msgstr (%r)",
            msgid_substs,
            msgid,
            msgstr_substs,
            msgstr,
        )
        return False
    # for unnamed substs, just count number of '%', this should cover most cases
    if not msgid_substs and msgid.count("%") != msgstr.count("%"):
        logging.error(
            "got %s substs in msgid (%r), %s in msgstr (%r)",
            msgid.count("%"),
            msgid,
            msgstr.count("%"),
            msgstr,
        )
        return False
    return True


def update_i18n_catalogs(po_files, csv_filename, autosave=True, skip_msgctxt=True):
    fa_translations = load_translations_from_csv(csv_filename)
    po_dicts = pofiles_as_dicts(po_files, skip_msgctxt)
    for msgid_key, lang_translations in fa_translations.items():
        # make sure we process 'fr' at first
        sorteditems = sorted(
            list(lang_translations.items()), key=lambda k: 0 if k[0] == "fr" else 1
        )
        for lang, label in sorteditems:
            if not lang:
                continue
            if msgid_key in po_dicts[lang]:
                if not substitutions_consistent(msgid_key[1], label):
                    break
                if label:
                    # set translation if not empty
                    po_dicts[lang][msgid_key].msgstr = label
                elif po_dicts["fr"][msgid_key].msgstr:
                    # default to fr translation if not empty
                    po_dicts[lang][msgid_key].msgstr = po_dicts["fr"][msgid_key].msgstr
            else:
                logging.info("skipping %s", (msgid_key,))
                break
    if autosave:
        for pofile in list(po_files.values()):
            pofile.save()
    return po_dicts


HERE = osp.abspath(osp.dirname(__file__))


def add_context_to(context, path):
    po = polib.pofile(path)
    for entry in po:
        if not entry.msgctxt:
            entry.msgctxt = context
    po.save()
    return path


class FranceArchivesMessageExtractor(WebI18nCubeMessageExtractor):
    formats = WebI18nCubeMessageExtractor.formats + ["jinja2", "appjs"]

    def collect_jinja2(self):
        return self.find(".jinja2")

    def collect_appjs(self):
        return (osp.join(HERE, "..", "appjs"),)

    def extract_jinja2(self, files):
        return self._xgettext(files, output="jinja.pot", extraopts="-L python --from-code=utf-8")

    def extract_appjs(self, paths):
        potfile = self._run_babel_cmd(
            "appjs.pot", input_paths=paths, keywords={"t": None, "_": None, "translate": None}
        )
        return add_context_to("appjs", potfile)

    def _run_babel_cmd(self, pot_fname, **options):
        options["output_file"] = osp.join(self.workdir, pot_fname)
        options.setdefault("no_location", True)
        options.setdefault("directory_filter", None)
        options.setdefault("add_comments", ())
        options.setdefault("no_default_keywords", True)
        options.setdefault("mapping_file", osp.join(HERE, "babel.cfg"))
        cmd = extract_messages()
        for attr, value in options.items():
            setattr(cmd, attr, value)
        cmd.run()
        return options["output_file"]


class RecompileInstanceCatalogsCommand(cwctl.InstanceCommand):
    """Recompile i18n catalogs for instances.

    <instance>...
      identifiers of the instances to consider. If no instance is
      given, recompile for all registered instances.
    """

    name = "i18ninstance"

    @staticmethod
    def i18ninstance_instance(appid):
        """recompile instance's messages catalogs"""
        config = cwcfg.config_for(appid)
        config.quick_start = True  # notify this is not a regular start
        repo = config.repository()
        if config._cubes is None:
            # web only config
            config.init_cubes(repo.get_cubes())
        errors = config.i18ncompile()
        if errors:
            print("\n".join(errors))
        else:
            RecompileInstanceCatalogsCommand._generate_js_translations(config)

    @staticmethod
    def _generate_js_translations(config):
        js_content_template = "window.TRANSLATIONS = %s;\n"

        static_i18n = osp.join(config.apphome, "appstatic", "i18n")
        if not osp.exists(static_i18n):
            os.makedirs(static_i18n)
        print("-> compiling message js-specific catalogs to %s" % static_i18n)

        for lang in config.available_languages():
            mo = osp.join(config.apphome, "i18n", lang, "LC_MESSAGES", "cubicweb.mo")

            js = osp.join(static_i18n, lang + ".js")
            with open(js, "w") as f:
                f.write(
                    js_content_template
                    % json.dumps(
                        {e.msgid: e.msgstr for e in polib.mofile(mo) if e.msgctxt == "appjs"},
                        indent=4,
                    )
                )


cwctl.CWCTL.register(RecompileInstanceCatalogsCommand)

try:
    import polib
except ImportError:  # polib is only required in dev mode

    def register_cwctl_commands():
        pass

else:
    from cubicweb.cwctl import CWCTL
    from cubicweb.toolsutils import Command

    class I18nDumpCSV(Command):
        """extract msgids from pofiles and dump a CSV file."""

        arguments = "<output-csv>"
        name = "fa-i18n-dump"
        min_args = max_args = 1

        def run(self, args):
            output_file = args[0]
            po_files = all_pofiles()
            dump_csv(po_files, output_file)

    class I18nLoadCSV(Command):
        """load a CSV file generated by fa-i18n-dump and update po files."""

        arguments = "<input-csv>"
        name = "fa-i18n-load"
        min_args = max_args = 1

        def run(self, args):
            input_file = args[0]
            po_files = all_pofiles()
            update_i18n_catalogs(po_files, input_file)

    def register_cwctl_commands():
        CWCTL.register(I18nDumpCSV)
        CWCTL.register(I18nLoadCSV)
