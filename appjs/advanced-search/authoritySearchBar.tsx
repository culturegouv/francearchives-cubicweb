/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2022
 * Contact http://www.logilab.fr -- mailto:contact@logilab.fr
 *
 * This software is governed by the CeCILL-C license under French law and
 * abiding by the rules of distribution of free software. You can use,
 * modify and/ or redistribute the software under the terms of the CeCILL-C
 * license as circulated by CEA, CNRS and INRIA at the following URL
 * "http://www.cecill.info".
 *
 * As a counterpart to the access to the source code and rights to copy,
 * modify and redistribute granted by the license, users are provided only
 * with a limited warranty and the software's author, the holder of the
 * economic rights, and the successive licensors have only limited liability.
 *
 * In this respect, the user's attention is drawn to the risks associated
 * with loading, using, modifying and/or developing or reproducing the
 * software by the user in light of its specific status of free software,
 * that may mean that it is complicated to manipulate, and that also
 * therefore means that it is reserved for developers and experienced
 * professionals having in-depth computer knowledge. Users are therefore
 * encouraged to load and test the software's suitability as regards their
 * requirements in conditions enabling the security of their systemsand/or
 * data to be ensured and, more generally, to use and operate it in the
 * same conditions as regards security.
 *
 * The fact that you are presently reading this means that you have had
 * knowledge of the CeCILL-C license and that you accept its terms.
 */

import React, {useEffect, useState} from 'react'
import {
    SearchRequest,
    QueryDslBoolQuery,
} from '@elastic/elasticsearch/lib/api/types'
import {translate as t} from '../translate'
import {FaAutocomplete} from './FAAutocomplete'

const TYPE_ES = {
    a: 'AgentAuthority',
    l: 'LocationAuthority',
    s: 'SubjectAuthority',
}

export function AuthorityTypeAhead({
    archivesRef,
    ressourcesSite,
    endpoint,
    selectedMemory,
    update,
    index,
    label,
    type,
    clearNow,
    setClearNow,
    placeholder,
    setCanReset,
}) {
    const [isLoading, setIsLoading] = useState(false)
    const [selected, setSelected] =
        useState<Array<{value: string; label: string}>>(selectedMemory)
    const [errorMsg, setErrorMsg] = React.useState<string | null>()

    useEffect(() => {
        if (clearNow) {
            setSelected([{value: '', label: ''}])
            setClearNow(false)
        }
    }, [clearNow])

    const handleSearch = (textSearch: string) => {
        setIsLoading(true)
        // TODO: remove accents ?
        const must: QueryDslBoolQuery['must'] = [
            {match: {cw_etype: TYPE_ES[type]}},
            {
                multi_match: {
                    query: textSearch,
                    operator: 'and',
                    type: 'bool_prefix', // look for terms starting by textSearch
                    fields: ['label', 'label._2gram', 'label._3gram'],
                },
            },
        ]
        if (archivesRef && !ressourcesSite) {
            must.push({range: {archives: {gte: 1}}})
        } else if (!archivesRef && ressourcesSite) {
            must.push({range: {siteres: {gte: 1}}})
        } else {
            must.push({range: {count: {gte: 1}}})
        }

        const es_query: SearchRequest = {
            query: {
                bool: {
                    must: must,
                    should: [
                        // give a better score if textSearch strictly matches an authority name
                        {
                            match_phrase: {
                                'text.raw': {
                                    query: textSearch,
                                    boost: 10,
                                    slop: 2,
                                },
                            },
                        },
                        // give a better score if the whole name starts with textSearch
                        {
                            match_bool_prefix: {
                                'text.raw': {query: textSearch},
                            },
                        },
                    ],
                },
            },
            sort: ['_score'],
            from: 0,
            size: 100,
        }
        return fetch(`${endpoint}`, {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(es_query),
        })
            .then((resp) => {
                return resp.json()
            })
            .then((response) => {
                let options = []
                if (response.errors !== undefined) {
                    setErrorMsg(response.errors[0].details)
                    setSelected([{value: '', label: ''}])
                } else {
                    setErrorMsg(null)
                    const items = response['hits']['hits'].map((element) => {
                        return {
                            value: element['_source']['eid'],
                            label: element['_source']['text'],
                        }
                    })
                    options = items
                }
                setIsLoading(false)
                return options
            })
            .catch((error) => {
                setErrorMsg(t('Could not retrieve results'))
                setSelected([{value: '', label: ''}])
                console.error(error)
                return []
            })
    }

    const hasError = errorMsg !== undefined && errorMsg !== null
    return (
        <FaAutocomplete
            value={selected[0]}
            label={label}
            loadOptions={handleSearch}
            multiple={false}
            placeholder={placeholder}
            onChange={(selectedElement) => {
                if (selectedElement) {
                    update(selectedElement)
                    setSelected([selectedElement])
                    setCanReset(true)
                } else {
                    //Nothing is selected
                    update({value: '', label: ''})
                    setSelected([{value: '', label: ''}])
                }
            }}
            loading={isLoading}
            error={hasError ? errorMsg : undefined}
        />
    )
}
