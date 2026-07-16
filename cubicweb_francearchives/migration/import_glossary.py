import csv
import os.path as osp

""" import GlossaryTerm """
HERE = osp.join(osp.abspath(osp.dirname(__file__)))


def datapath(relpath):
    return osp.join(HERE, "initialdata", relpath)


def import_glossary(cnx):
    with open(datapath("glossaire.csv")) as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)  # noqa
        for idx, row in enumerate(reader):
            if not any(row):
                continue
            term, term_plural, description, short = row[:4]
            if not all((term, description)):
                print(f"skip line {idx} : {row}")
                continue
            term = term.strip()
            kwargs = {
                "term": term,
            }
            short = short or description
            gt = cnx.find("GlossaryTerm", term=term)
            kwargs.update(
                {
                    "description": description.strip(),
                    "short_description": (
                        short.strip() if short.strip() else description.strip()[:1000]
                    ),
                    "term_plural": term_plural.strip() if term_plural.strip() else None,
                    "sort_letter": term[0].lower(),
                }
            )
            if not gt:
                print(f" => '{term}' created")
                gt = cnx.create_entity("GlossaryTerm", **kwargs)
                gt.cw_set(anchor=str(gt.eid))
                cnx.commit()
            else:
                gt = gt.one()
                print(f" => '{term}' updated")
                kwargs.pop("term")
                gt.cw_set(**kwargs)
            gt.cw_adapt_to("IWorkflowable").fire_transition_if_possible("wft_cmsobject_publish")


if __name__ == "__main__":
    import_glossary(cnx)  # noqa
