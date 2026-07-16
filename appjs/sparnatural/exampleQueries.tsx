import {translate as t} from '../translate'

const queries = [
    {
        label: t("Sélectionner une requête d'exemple"),
        query: `{}`,
    },
    {
        label: t("Inventaires d'archives produits par Georges Clemenceau"),
        query: `{
            "distinct": true,
            "variables": [
              "Inventaire_1"
            ],
            "order": null,
            "branches": [
              {
                "line": {
                  "s": "?Inventaire_1",
                  "p": "https://francearchives.gouv.fr/sparnatural#provenance",
                  "o": "?Personne_2",
                  "sType": "https://francearchives.gouv.fr/sparnatural#Inventaire",
                  "oType": "https://francearchives.gouv.fr/sparnatural#Personne",
                  "values": []
                },
                "children": [
                  {
                    "line": {
                      "s": "?Personne_2",
                      "p": "https://francearchives.gouv.fr/sparnatural#aRicoName",
                      "o": "?Nom_4",
                      "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                      "oType": "https://francearchives.gouv.fr/sparnatural#Nom",
                      "values": [
                        {
                          "label": "georges clemenceau",
                          "regex": "georges clemenceau"
                        }
                      ]
                    },
                    "children": []
                  }
                ]
              }
            ]
          }`,
    },
    {
        label: t(
            'Archives produites par Jean Petit qui a pour activité « notaire à Paris »',
        ),
        query: `{
                "distinct": true,
                "variables": [
                  "Archives_1"
                ],
                "order": null,
                "branches": [
                  {
                    "line": {
                      "s": "?Archives_1",
                      "p": "https://francearchives.gouv.fr/sparnatural#provenance",
                      "o": "?Personne_2",
                      "sType": "https://francearchives.gouv.fr/sparnatural#Archives",
                      "oType": "https://francearchives.gouv.fr/sparnatural#Personne",
                      "values": []
                    },
                    "children": [
                      {
                        "line": {
                          "s": "?Personne_2",
                          "p": "https://francearchives.gouv.fr/sparnatural#aRicoName",
                          "o": "?Nom_4",
                          "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                          "oType": "https://francearchives.gouv.fr/sparnatural#Nom",
                          "values": [
                            {
                              "label": "jean petit",
                              "regex": "jean petit"
                            }
                          ]
                        },
                        "children": []
                      },
                      {
                        "line": {
                          "s": "?Personne_2",
                          "p": "https://francearchives.gouv.fr/sparnatural#aPourActivite",
                          "o": "?Activite_6",
                          "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                          "oType": "https://francearchives.gouv.fr/sparnatural#Activite",
                          "values": [
                            {
                              "label": "notaire à Paris",
                              "rdfTerm": {
                                "type": "uri",
                                "value": "https://francearchives.gouv.fr/externaluri/d3nyui3o8w--11y7jgy8q3wnt"
                              }
                            }
                          ]
                        },
                        "children": []
                      }
                    ]
                  }
                ]
              }`,
    },
    {
        label: t('Archives antérieures à 1715 concernant Pamiers'),
        query: `{
            "distinct": true,
            "variables": [
              "Archives_1",
              "Date_2"
            ],
            "order": null,
            "branches": [
              {
                "line": {
                  "s": "?Archives_1",
                  "p": "https://francearchives.gouv.fr/sparnatural#dateFinArchives",
                  "o": "?Date_2",
                  "sType": "https://francearchives.gouv.fr/sparnatural#Archives",
                  "oType": "https://francearchives.gouv.fr/sparnatural#Date",
                  "values": [
                    {
                      "label": "Jusqu'à 1715",
                      "start": null,
                      "stop": "1715-12-31T23:50:38.000Z"
                    }
                  ]
                },
                "children": []
              },
              {
                "line": {
                  "s": "?Archives_1",
                  "p": "https://francearchives.gouv.fr/sparnatural#concerne",
                  "o": "?Lieu_4",
                  "sType": "https://francearchives.gouv.fr/sparnatural#Archives",
                  "oType": "https://francearchives.gouv.fr/sparnatural#Lieu",
                  "values": []
                },
                "children": [
                  {
                    "line": {
                      "s": "?Lieu_4",
                      "p": "https://francearchives.gouv.fr/sparnatural#aRicoName",
                      "o": "?Nom_6",
                      "sType": "https://francearchives.gouv.fr/sparnatural#Lieu",
                      "oType": "https://francearchives.gouv.fr/sparnatural#Nom",
                      "values": [
                        {
                          "label": "Pamiers",
                          "regex": "Pamiers"
                        }
                      ]
                    },
                    "children": []
                  }
                ]
              }
            ]
          }`,
    },
    {
        label: t(
            "Personne qui a pour activité « notaire » et est le producteur d'archives",
        ),
        query: `{
            "distinct": true,
            "variables": [
              "Personne_1"
            ],
            "order": null,
            "branches": [
              {
                "line": {
                  "s": "?Personne_1",
                  "p": "https://francearchives.gouv.fr/sparnatural#aPourActivite",
                  "o": "?Activite_2",
                  "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                  "oType": "https://francearchives.gouv.fr/sparnatural#Activite",
                  "values": [
                    {
                      "label": "notaire",
                      "rdfTerm": {
                        "type": "uri",
                        "value": "https://francearchives.gouv.fr/externaluri/d3nyu9x713-9kcjiv44l4wh"
                      }
                    }
                  ]
                },
                "children": []
              },
              {
                "line": {
                  "s": "?Personne_1",
                  "p": "https://francearchives.gouv.fr/sparnatural#estProvenanceDe",
                  "o": "?Archives_4",
                  "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                  "oType": "https://francearchives.gouv.fr/sparnatural#Archives",
                  "values": []
                },
                "children": []
              }
            ]
          }`,
    },
    {
        label: t(
            'Personne qui fait partie de la famille qui a pour nom « Bonaparte »',
        ),
        query: `{
            "distinct": true,
            "variables": [
                "Personne_1"
            ],
            "order": null,
            "branches": [
                {
                    "line": {
                        "s": "?Personne_1",
                        "p": "https://francearchives.gouv.fr/sparnatural#estMembreDeFamille",
                        "o": "?Family_2",
                        "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                        "oType": "https://francearchives.gouv.fr/sparnatural#Family",
                        "values": []
                    },
                    "children": [
                        {
                            "line": {
                                "s": "?Family_2",
                                "p": "https://francearchives.gouv.fr/sparnatural#aRicoName",
                                "o": "?Nom_4",
                                "sType": "https://francearchives.gouv.fr/sparnatural#Family",
                                "oType": "https://francearchives.gouv.fr/sparnatural#Nom",
                                "values": [
                                    {
                                        "label": "Bonaparte",
                                        "regex": "Bonaparte"
                                    }
                                ]
                            },
                            "children": []
                        }
                    ]
                }
            ]
        }`,
    },
    {
        label: t('Personnes qui sont nées entre 1850 et 1950'),
        query: `{
            "distinct": true,
            "variables": [
              "Personne_1",
              "Date_2"
            ],
            "order": null,
            "branches": [
              {
                "line": {
                  "s": "?Personne_1",
                  "p": "https://francearchives.gouv.fr/sparnatural#personneDate1Naissance",
                  "o": "?Date_2",
                  "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                  "oType": "https://francearchives.gouv.fr/sparnatural#Date",
                  "values": [
                    {
                      "label": "de 1850 à 1950",
                      "start": "1849-12-31T23:50:40.000Z",
                      "stop": "1950-12-31T22:59:59.000Z"
                    }
                  ]
                },
                "children": []
              }
            ]
          }`,
    },
    {
        label: t(
            'Archives concernant Poitiers et qui ne sont pas conservées par les Archives de la Vienne',
        ),
        query: `{
            "distinct": true,
            "variables": [
              "Archives_1"
            ],
            "order": null,
            "branches": [
              {
                "line": {
                  "s": "?Archives_1",
                  "p": "https://francearchives.gouv.fr/sparnatural#concerne",
                  "o": "?Lieu_2",
                  "sType": "https://francearchives.gouv.fr/sparnatural#Archives",
                  "oType": "https://francearchives.gouv.fr/sparnatural#Lieu",
                  "values": []
                },
                "children": [
                  {
                    "line": {
                      "s": "?Lieu_2",
                      "p": "https://francearchives.gouv.fr/sparnatural#aRicoName",
                      "o": "?Nom_4",
                      "sType": "https://francearchives.gouv.fr/sparnatural#Lieu",
                      "oType": "https://francearchives.gouv.fr/sparnatural#Nom",
                      "values": [
                        {
                          "label": "Poitiers",
                          "regex": "Poitiers"
                        }
                      ]
                    },
                    "children": []
                  }
                ]
              },
              {
                "line": {
                  "s": "?Archives_1",
                  "p": "https://francearchives.gouv.fr/sparnatural#aPourLieuDeConservation",
                  "o": "?Organization_6",
                  "sType": "https://francearchives.gouv.fr/sparnatural#Archives",
                  "oType": "https://francearchives.gouv.fr/sparnatural#Organization",
                  "values": [
                    {
                      "label": "Archives départementales de la Vienne",
                      "rdfTerm": {
                        "type": "uri",
                        "value": "https://francearchives.gouv.fr/service/34295"
                      }
                    }
                  ]
                },
                "children": [],
                "notExists": true
              }
            ]
          }`,
    },
    {
        label: t(
            'Lieux qui sont le sujet des archives reliées au fonds « Fabrique de berlingot Eysséric »',
        ),
        query: `{
            "distinct": true,
            "variables": [
                "Lieu_1"
            ],
            "order": null,
            "branches": [
                {
                    "line": {
                        "s": "?Lieu_1",
                        "p": "https://francearchives.gouv.fr/sparnatural#estConcernePar",
                        "o": "?Archives_2",
                        "sType": "https://francearchives.gouv.fr/sparnatural#Lieu",
                        "oType": "https://francearchives.gouv.fr/sparnatural#Archives",
                        "values": []
                    },
                    "children": [
                        {
                            "line": {
                                "s": "?Archives_2",
                                "p": "https://francearchives.gouv.fr/sparnatural#contenuDansInventaire",
                                "o": "?Inventaire_4",
                                "sType": "https://francearchives.gouv.fr/sparnatural#Archives",
                                "oType": "https://francearchives.gouv.fr/sparnatural#Inventaire",
                                "values": []
                            },
                            "children": [
                                {
                                    "line": {
                                        "s": "?Inventaire_4",
                                        "p": "https://francearchives.gouv.fr/sparnatural#aPourIntitule",
                                        "o": "?Intitule_6",
                                        "sType": "https://francearchives.gouv.fr/sparnatural#Inventaire",
                                        "oType": "https://francearchives.gouv.fr/sparnatural#Intitule",
                                        "values": [
                                            {
                                                "label": "Fabrique de berlingots",
                                                "regex": "Fabrique de berlingots"
                                            }
                                        ]
                                    },
                                    "children": []
                                }
                            ]
                        }
                    ]
                }
            ]
        }`,
    },
    {
        label: t(
            'Lieu de conservation qui conserve des archives concernant « Charles de Gaulle »',
        ),
        query: `{
            "distinct": true,
            "variables": [
              "Organization_1"
            ],
            "order": null,
            "branches": [
              {
                "line": {
                  "s": "?Organization_1",
                  "p": "https://francearchives.gouv.fr/sparnatural#conserveArchive",
                  "o": "?Archives_2",
                  "sType": "https://francearchives.gouv.fr/sparnatural#Organization",
                  "oType": "https://francearchives.gouv.fr/sparnatural#Archives",
                  "values": []
                },
                "children": [
                  {
                    "line": {
                      "s": "?Archives_2",
                      "p": "https://francearchives.gouv.fr/sparnatural#concerne",
                      "o": "?Personne_4",
                      "sType": "https://francearchives.gouv.fr/sparnatural#Archives",
                      "oType": "https://francearchives.gouv.fr/sparnatural#Personne",
                      "values": []
                    },
                    "children": [
                      {
                        "line": {
                          "s": "?Personne_4",
                          "p": "https://francearchives.gouv.fr/sparnatural#aRicoName",
                          "o": "?Nom_6",
                          "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                          "oType": "https://francearchives.gouv.fr/sparnatural#Nom",
                          "values": [
                            {
                              "label": "Charles de Gaulle",
                              "regex": "Charles de Gaulle"
                            }
                          ]
                        },
                        "children": []
                      }
                    ]
                  }
                ]
              }
            ]
          }`,
    },
    {
        label: t(
            'Institution qui a pour type « ministère » ET est le sujet d’archives',
        ),
        query: `{
          "distinct": true,
          "variables": [
            "Organization_1"
          ],
          "order": null,
          "branches": [
            {
              "line": {
                "s": "?Organization_1",
                "p": "https://francearchives.gouv.fr/sparnatural#aPourTypeDOrganisation",
                "o": "?TypeDOrganisation_2",
                "sType": "https://francearchives.gouv.fr/sparnatural#Organization",
                "oType": "https://francearchives.gouv.fr/sparnatural#TypeDOrganisation",
                "values": [
                  {
                    "label": "ministère",
                    "rdfTerm": {
                      "type": "uri",
                      "value": "https://francearchives.gouv.fr/externaluri/d5bloo2gwk-sgl3fc00gzgl"
                    }
                  }
                ]
              },
              "children": []
            },
            {
              "line": {
                "s": "?Organization_1",
                "p": "https://francearchives.gouv.fr/sparnatural#estConcernePar",
                "o": "?Archives_4",
                "sType": "https://francearchives.gouv.fr/sparnatural#Organization",
                "oType": "https://francearchives.gouv.fr/sparnatural#Archives",
                "values": []
              },
              "children": []
            }
          ]
        }`,
    },
    {
        label: t('Personne a pour date de naissance'),
        query: `{
            "distinct": true,
            "variables": [
              "Personne_1",
              "Date_2"
            ],
            "order": null,
            "branches": [
              {
                "line": {
                  "s": "?Personne_1",
                  "p": "https://francearchives.gouv.fr/sparnatural#personneDate1Naissance",
                  "o": "?Date_2",
                  "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                  "oType": "https://francearchives.gouv.fr/sparnatural#Date",
                  "values": []
                },
                "children": []
              }
            ]
          }`,
    },
    {
        label: t('Personne a pour date de mort'),
        query: `{
            "distinct": true,
            "variables": [
              "Personne_1",
              "Date_2"
            ],
            "order": null,
            "branches": [
              {
                "line": {
                  "s": "?Personne_1",
                  "p": "https://francearchives.gouv.fr/sparnatural#personneDate2Mort",
                  "o": "?Date_2",
                  "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                  "oType": "https://francearchives.gouv.fr/sparnatural#Date",
                  "values": []
                },
                "children": []
              }
            ]
          }`,
    },
    {
        label: t('Personne a pour parent Personne'),
        query: `{
            "distinct": true,
            "variables": [
                "Personne_1",
                "Personne_2"
            ],
            "order": null,
            "branches": [
                {
                    "line": {
                        "s": "?Personne_1",
                        "p": "https://francearchives.gouv.fr/sparnatural#aPourParent",
                        "o": "?Personne_2",
                        "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                        "oType": "https://francearchives.gouv.fr/sparnatural#Personne",
                        "values": []
                    },
                    "children": []
                }
            ]
        }`,
    },
    {
        label: t('Personne a pour enfant Personne'),
        query: `{
            "distinct": true,
            "variables": [
                "Personne_1",
                "Personne_2"
            ],
            "order": null,
            "branches": [
                {
                    "line": {
                        "s": "?Personne_1",
                        "p": "https://francearchives.gouv.fr/sparnatural#aPourEnfant",
                        "o": "?Personne_2",
                        "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                        "oType": "https://francearchives.gouv.fr/sparnatural#Personne",
                        "values": []
                    },
                    "children": []
                }
            ]
        }`,
    },
    {
        label: t('Personne a pour époux/épouse Personne'),
        query: `{
            "distinct": true,
            "variables": [
                "Personne_1",
                "Personne_2"
            ],
            "order": null,
            "branches": [
                {
                    "line": {
                        "s": "?Personne_1",
                        "p": "https://francearchives.gouv.fr/sparnatural#aPourEpouse",
                        "o": "?Personne_2",
                        "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                        "oType": "https://francearchives.gouv.fr/sparnatural#Personne",
                        "values": []
                    },
                    "children": []
                }
            ]
        }`,
    },
    {
        label: t('Personne a pour frère/soeur Personne'),
        query: `{
            "distinct": true,
            "variables": [
                "Personne_1",
                "Personne_2"
            ],
            "order": null,
            "branches": [
                {
                    "line": {
                        "s": "?Personne_1",
                        "p": "https://francearchives.gouv.fr/sparnatural#aPourAdelphe",
                        "o": "?Personne_2",
                        "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                        "oType": "https://francearchives.gouv.fr/sparnatural#Personne",
                        "values": []
                    },
                    "children": []
                }
            ]
        }`,
    },
    {
        label: t('Personne est membre de Institution'),
        query: `{
            "distinct": true,
            "variables": [
                "Personne_1",
                "Organization_2"
            ],
            "order": null,
            "branches": [
                {
                    "line": {
                        "s": "?Personne_1",
                        "p": "https://francearchives.gouv.fr/sparnatural#estMembreDe",
                        "o": "?Organization_2",
                        "sType": "https://francearchives.gouv.fr/sparnatural#Personne",
                        "oType": "https://francearchives.gouv.fr/sparnatural#Organization",
                        "values": []
                    },
                    "children": []
                }
            ]
        }`,
    },
    {
        label: t('Institution a pour membre Personne'),
        query: `{
            "distinct": true,
            "variables": [
                "Organization_1",
                "Personne_2"
            ],
            "order": null,
            "branches": [
                {
                    "line": {
                        "s": "?Organization_1",
                        "p": "https://francearchives.gouv.fr/sparnatural#aPourMembre",
                        "o": "?Personne_2",
                        "sType": "https://francearchives.gouv.fr/sparnatural#Organization",
                        "oType": "https://francearchives.gouv.fr/sparnatural#Personne",
                        "values": []
                    },
                    "children": []
                }
            ]
        }`,
    },
]

export default queries
