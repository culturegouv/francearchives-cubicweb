import React from 'react'
import EXAMPLE_QUERIES from './exampleQueries'
import {translate as t} from '../translate'

export function SparnaturalDropdown() {
    const help = "Sélectionner une requête d'exemple"
    const label = t('Examples of queries')
    const [selection, setSelection] = React.useState<{
        label: string
        query: string
    }>(EXAMPLE_QUERIES[0])
    const [doReset, _setDoReset] = React.useState<boolean>(false)

    const doResetRef = React.useRef(doReset)
    const setDoReset = (data) => {
        doResetRef.current = data
        _setDoReset(data)
    }

    const sparnaturalNode = document.querySelector('spar-natural')

    const handleReset = () => {
        if (doResetRef.current) {
            setSelection(EXAMPLE_QUERIES[0])
            setDoReset(true)
        }
    }

    const handleQueryUpdated = () => {
        setDoReset(true)
    }

    React.useEffect(() => {
        window.addEventListener('reset', handleReset)
        return () => {
            window.removeEventListener('reset', handleReset)
        }
    }, [])

    React.useEffect(() => {
        window.addEventListener('queryUpdated', handleQueryUpdated)
        return () => {
            window.removeEventListener('queryUpdated', handleQueryUpdated)
        }
    }, [])

    return (
        <div className="fr-select-group">
            <label htmlFor="sparnatural-select">{label}</label>
            <select
                className="fr-select"
                arial-labelledby="sparnatural-wrapper-label"
                onChange={(ev) => {
                    const query = EXAMPLE_QUERIES.find(
                        (l, q) => l.label === ev.target.value,
                    )
                    if (query === undefined) {
                        return
                    }
                    if (query.label !== selection.label) {
                        setDoReset(false)
                        setSelection(query)
                    }
                    const event = new CustomEvent('loadQuery', {
                        bubbles: true,
                        detail: JSON.parse(query.query),
                    })
                    if (sparnaturalNode) {
                        sparnaturalNode.dispatchEvent(event)
                    }
                }}
            >
                {EXAMPLE_QUERIES.map((query, index) => (
                    <option key={query.label}>{query.label}</option>
                ))}
            </select>
        </div>
    )
}
