export const SAMPLE_QUERIES = [
    {
        query: 'SELECT ?s ?p ?o\nWHERE { ?s ?p ?o . }\nLIMIT 100',
        title: 'Explorer les donn\u00e9es',
    },
    {
        query: 'SELECT DISTINCT ?class\nWHERE {\n ?x a ?class .\n}',
        title: 'Liste des classes',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT * WHERE {\n  ?x  a rico:RecordResource.\n  ?x rico:hasProvenance <https://francearchives.gouv.fr/agent/18939034>.\n} ',
        title: 'Archives produites par Georges Clemenceau (autorité personne)',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nSELECT DISTINCT ?x WHERE {\n  ?x  a rico:RecordResource.\n  ?x rico:hasProvenance ?originator.\n  ?originator rico:name "Petit, Jean".\n  ?originator rico:performsOrPerformed ?performance.\n  ?performance rico:hasActivityType ?activity.\n  ?activity rdfs:label "notaire à paris".\n} ',
        title: 'Archives produites par Jean Petit (autorité personne) qui a pour activité « notaire à Paris »',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\nSELECT DISTINCT * WHERE {\n  ?x  a rico:RecordResource.\n  ?x rico:hasOrHadSubject <https://francearchives.gouv.fr/location/131515519>.\n  ?x rico:beginningDate ?dateDeb.\n  FILTER(?dateDeb < "1715"^^xsd:gYear)\n} ',
        title: 'Archives antérieures à 1715 concernant Pamiers (autorité)',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nSELECT DISTINCT ?x WHERE {  \n  ?x a rico:Person.\n  ?x rico:performsOrPerformed ?performance.\n  ?performance rico:hasActivityType ?activity.\n  ?activity rdfs:label "notaire".\n  ?archive rico:hasProvenance ?x.\n  ?archive a rico:RecordResource.\n} ',
        title: "Personne qui a pour activité « notaire » et est le producteur d'archives",
    },
    {
        query: 'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nPREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT ?x ?nom WHERE {\n  ?x a rico:Person.\n  ?x rico:isOrWasMemberOf ?family.\n  ?family rico:name "Bonaparte (famille)".\n} ',
        title: 'Personne qui fait partie de la famille qui a pour nom « Bonaparte »',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> \nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n\nSELECT DISTINCT ?x ?bDate WHERE {\n  ?x  a rico:Person.\n  ?x rico:birthDate ?bDate .\n  FILTER(YEAR(?bDate) > 1850).\n  FILTER(YEAR(?bDate) < 1950).\n}\nLIMIT 100',
        title: 'Personnes qui sont nées entre 1850 et 1950',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT ?x  WHERE {\n  ?x a rico:RecordResource.\n  ?x rico:hasOrHadSubject <https://francearchives.gouv.fr/location/18294577>.\n  MINUS { ?x rico:hasOrHadManager <https://francearchives.gouv.fr/service/34295> }\n} \nLIMIT 100',
        title: 'Archives concernant Poitiers (autorité) et qui ne sont pas conservées par les Archives de la Vienne',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT ?x ?dateFin WHERE {\n  ?x  a rico:RecordResource.\n  <https://francearchives.gouv.fr/findingaid/dfbd0c734816bbdd0d26c5ff7021686d373a0bca> rico:includesOrIncluded+ ?x.\n  ?x rico:endDate ?dateFin.\n} ',
        title: 'Dates de fin qui sont reliées aux archives reliées au fonds « Fabrique de berlingots Eysséric »',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n\nSELECT DISTINCT ?x WHERE {\n  ?x  a rico:RecordResource.\n  ?FARecord rico:describesOrDescribed ?x.\n  ?FARecord rico:hasDocumentaryFormType <https://www.ica.org/standards/RiC/vocabularies/documentaryFormTypes#FindingAid>.\n  {?x rico:hasOrHadSubject <https://francearchives.gouv.fr/subject/131518563>.}\n  UNION {\n    ?x rico:hasOrHadSubject <https://francearchives.gouv.fr/subject/212809359>.\n  } \n  UNION{   \n    ?x rico:hasProvenance ?person.  \n    ?person rico:performsOrPerformed ?perf.   \n    ?perf rico:hasActivityType ?activity.   \n    ?activity rdfs:label "photographe".  \n  } \n} ',
        title: 'Fonds d’archives reliés aux thèmes « photographie » OU « document photographique » (autorités thème) OU qui a pour producteur une personne (autorité) qui a pour activité « photographe »',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#> \nSELECT DISTINCT ?place ?nom WHERE { \n  ?x  a rico:RecordResource. \n  ?x rico:hasOrHadSubject ?place. \n  ?place a rico:Place.\n  ?place rico:name ?nom.\n  <https://francearchives.gouv.fr/findingaid/dfbd0c734816bbdd0d26c5ff7021686d373a0bca> rico:includesOrIncluded+ ?x.\n}  ',
        title: 'Lieux sujets d’archives qui sont reliées au fonds « Fabrique de berlingots Eysséric »',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#> \nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> \nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>  \nSELECT DISTINCT ?service WHERE {   \n  ?x  a rico:RecordResource. \n  ?x rico:hasOrHadSubject <https://francearchives.gouv.fr/agent/130851666>. \n  ?x rico:hasOrHadManager ?service.\n}',
        title: 'Lieu de conservation qui conserve des archives concernant « Charles de Gaulle » (autorité personne)',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> \nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>  \nSELECT DISTINCT ?x ?name WHERE { \n  ?x  a rico:CorporateBody.\n  ?x rico:name ?name. \n  ?z ?rel ?x.\n  ?z a rico:RecordResource.\n  FILTER(regex(?name,"marine","i")).\n}  ',
        title: 'Institution dont le nom contient « marine » et relié à un fonds OU à des archives',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>   \nSELECT DISTINCT ?personne ?nomPersonne ?org ?nomInstitution WHERE { \n  ?personne a rico:Person. \n  ?personne rico:name ?nomPersonne. \n  ?org rico:name ?nomInstitution.\n  ?org a rico:CorporateBody. \n  ?personne rico:isAgentAssociatedWithAgent ?org. \n} \nLIMIT 100',
        title: 'Personne qui a une relation avec une institution',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#> \nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> \nSELECT DISTINCT ?x ?nom WHERE { \n  ?x a rico:CorporateBody. \n  ?x rico:hasOrHadLegalStatus ?status.  \n  ?status rdfs:label "ministère". \n  ?record a rico:RecordResource. \n  ?record rico:hasOrHadSubject ?x. \n  ?x rico:name ?nom.\n} ',
        title: 'Institution qui a pour type « ministère » ET est le sujet d’archives',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> \nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#> \nSELECT DISTINCT * WHERE { \n  ?x  a rico:RecordResource.  \n  {\n    ?x rico:hasOrHadSubject <https://francearchives.gouv.fr/subject/130952779>.\n  } \n  UNION {   \n    ?x rico:hasOrHadSubject <https://francearchives.gouv.fr/subject/18257132>. \n  } \n  ?x rico:hasOrHadSubject ?place.  \n  ?place a rico:Place. \n  ?x rico:endDate ?dateFin.    \n  FILTER(?dateFin > "1800"^^xsd:gYear) \n} \nLIMIT 100 ',
        title: 'Pour isoler les les descriptions relatives à des moulins localisés : Thème « moulin » OU « moulin à eau » relié à des archives qui comportent un lieu ET postérieures à 1800',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT ?pers ?date\nWHERE {\n  ?pers a rico:Person.\n  ?pers rico:birthDate ?date.\n}\nLIMIT 1000',
        title: 'Personne a pour date de naissance "date"',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT ?pers ?date\nWHERE {\n  ?pers a rico:Person.\n  ?pers rico:deathDate ?date.\n}\nLIMIT 1000',
        title: 'Personne a pour date de mort "date"',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT ?pers1 ?pers2\nWHERE {\n  ?pers1 a rico:Person.\n  ?pers2 a rico:Person.\n  ?pers1 rico:isChildOf ?pers2.\n}\nLIMIT 100',
        title: 'Personne a pour parent Personne',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT ?pers1 ?pers2\nWHERE {\n  ?pers1 a rico:Person.\n  ?pers2 a rico:Person.\n  ?pers1 rico:hasChild ?pers2.\n}\nLIMIT 1000',
        title: 'Personne a pour enfant Personne',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT ?pers1 ?pers2\nWHERE {\n  ?pers1 a rico:Person.\n  ?pers2 a rico:Person.\n  ?pers1 rico:hasOrHadSpouse ?pers2.\n}\nLIMIT 1000',
        title: 'Personne a pour époux/épouse Personne',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT ?pers1 ?pers2\nWHERE {\n  ?pers1 a rico:Person.\n  ?pers2 a rico:Person.\n  ?pers1 rico:hasSibling ?pers2.\n}\nLIMIT 1000',
        title: 'Personne a pour frère/sœur Personne',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT ?pers ?org\nWHERE {\n  ?pers a rico:Person.\n  ?org a rico:CorporateBody.\n  ?pers rico:isAgentAssociatedWithAgent ?org.\n}\nLIMIT 1000',
        title: 'Personne est membre de Institution',
    },
    {
        query: 'PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\nSELECT DISTINCT ?org ?pers\nWHERE {\n  ?pers a rico:Person.\n  ?org a rico:CorporateBody.\n  ?org rico:isAgentAssociatedWithAgent ?pers.\n}\nLIMIT 1000',
        title: 'Institution a pour membre Personne',
    },
]
