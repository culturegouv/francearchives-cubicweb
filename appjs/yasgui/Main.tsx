/* global SPARQL_ENDPOINT */

import React from 'react'
import {Select} from '@codegouvfr/react-dsfr/SelectNext'

import Yasgui from '@triply/yasgui'
import '@triply/yasgui/build/yasgui.min.css'

import PREFIXES from './prefixes.js'
import {SAMPLE_QUERIES} from './sample-queries.js'
import {translate as t} from '../translate'

const Yasqe = Yasgui.Yasqe
const ENDPOINT = (window as any).SPARQL_ENDPOINT

Yasqe.defaults.autocompleters.splice(
    Yasqe.defaults.autocompleters.indexOf('prefixes'),
    1,
)
Yasqe.forkAutocompleter('prefixes', {
    name: 'prefixes-fa',
    get: () => {
        return new Promise((resolve) => {
            setTimeout(() => {
                resolve(
                    Object.keys(PREFIXES).map(
                        (prefix) => `${prefix}: <${PREFIXES[prefix]}>`,
                    ),
                )
            })
        })
    },
})

Yasqe.defaults.value = `SELECT DISTINCT ?Concept
WHERE {
  [] a ?Concept
} LIMIT 100`
Yasgui.defaults.requestConfig.endpoint = ENDPOINT
Yasgui.defaults.endpointCatalogueOptions.getData = () => {
    return [
        {
            endpoint: ENDPOINT,
        },
    ]
}
Yasgui.defaults.yasr.prefixes = PREFIXES

const ResultsPermalink = ({yasqe}) => {
    const [query, setQuery] = React.useState('')
    const [endPointUrl, setEndPointUrl] = React.useState('')
    const [contentType, setContentType] = React.useState('')
    const contentTypeMapping = {
        'application/sparql-results+json': 'application/json',
    } // this will allow to render the result directly in the webbrowser

    React.useEffect(() => {
        if (!yasqe) {
            return
        }
        yasqe.on('queryResponse', (instance, req, duration) => {
            setQuery(
                encodeURI(instance.getValueWithoutComments()).replace(
                    /#/g,
                    '%23',
                ),
            )
            setEndPointUrl(req.req.url)
            const contentType = req.header['content-type']
            if (contentType in contentTypeMapping) {
                setContentType(contentTypeMapping[contentType])
            } else {
                setContentType(contentType)
            }
        })
    }, [yasqe, contentTypeMapping])

    const resultsUrl = `${endPointUrl}?query=${query}&format=${contentType}`
    return query ? (
        <div className="permalink">
            <a href={resultsUrl}>Permalien vers les résultats</a>
        </div>
    ) : null
}

export default function Main() {
    const [yasgui, setYasgui] = React.useState<Yasgui | null>(null)

    React.useEffect(() => {
        const yasguiAnchor = document.getElementById('yasgui')
        if (yasguiAnchor !== null) {
            setYasgui(new Yasgui(yasguiAnchor, {}))
        }
    }, [])

    const prefixes = Object.keys(PREFIXES).map((prefix) => {
        return {
            value: prefix,
            label: `${prefix}: ${PREFIXES[prefix]}`,
        }
    })

    const sampleQueries = SAMPLE_QUERIES.map((query, index) => {
        return {
            value: index,
            label: query.title,
            query: query.query,
        }
    })

    const updateSampleQuery = (option) => {
        const tab = yasgui!.getTab()
        if (tab !== undefined) {
            tab.setQuery(sampleQueries[option.value].query)
        }
    }

    const addNewPrefix = (option) => {
        const prefixes = {}
        prefixes[option.value] = PREFIXES[option.value]
        const tab = yasgui!.getTab()
        if (tab !== undefined) {
            tab.getYasqe().addPrefixes(prefixes)
        }
    }
    return (
        <div className="fr-container">
            <div className="fr-grid-row fr-grid-row--gutters fr-grid-row--center">
                <div className="fr-col-md-6">
                    <Select
                        label={t('Query examples')}
                        nativeSelectProps={{
                            onChange: (e) => updateSampleQuery(e.target),
                        }}
                        options={sampleQueries}
                    />
                </div>
                <div className="fr-col-md-6">
                    <Select
                        label={t('Namespace')}
                        nativeSelectProps={{
                            onChange: (e) => addNewPrefix(e.target),
                        }}
                        options={prefixes}
                    />
                </div>
            </div>
            <div>
                <div id="yasgui" />
            </div>
            <ResultsPermalink
                yasqe={yasgui ? yasgui.getTab()!.getYasqe() : null}
            />
        </div>
    )
}
