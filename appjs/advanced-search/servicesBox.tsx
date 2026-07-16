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

import React, {useState, useEffect} from 'react'
import {
    SearchRequest,
    QueryDslBoolQuery,
} from '@elastic/elasticsearch/lib/api/types'
import {PlusButton, RemoveRowButton, Toggle} from './widgets'
import {translate as t} from '../translate'
import {FaAutocomplete} from './FAAutocomplete'

export function ServiceTypeAhead({
    archivesRef,
    ressourcesSite,
    update,
    selectedMemory,
    typeaheadId,
    index,
    clearNow,
    setClearNow,
    endpoint,
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
        const must: QueryDslBoolQuery['must'] = [
            {
                simple_query_string: {
                    query: `${textSearch}*`,
                    fields: ['short_name^3', 'alltext'],
                    default_operator: 'and',
                },
            },
        ]
        if (archivesRef && !ressourcesSite) {
            must.push({range: {archives: {gte: 1}}})
        } else if (!archivesRef && ressourcesSite) {
            must.push({range: {siteres: {gte: 1}}})
        } else {
            must.push({range: {documents_count: {gte: 1}}})
        }

        const es_query: SearchRequest = {
            query: {
                bool: {
                    must: must,
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
                    console.error(response.error)
                    setSelected([{value: '', label: ''}])
                } else {
                    setErrorMsg(null)
                    const items = response['hits']['hits']
                        .map((element) => {
                            return {
                                value: element['_source']['eid'],
                                label:
                                    element['_source']['short_name'] ||
                                    element['_source']['title'],
                            }
                        })
                        .filter((element) => {
                            return element['label'] !== null
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
    const label = `${t('as_publisher')} ${index + 1}`
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

export function ServicesBox({
    searches,
    labels,
    addSearch,
    updateSearch,
    operator,
    setOperator,
    endpoint,
    clearNow,
    setClearNow,
    removeService,
    ressourcesSite,
    archivesRef,
    setCanReset,
}) {
    return (
        <fieldset className="fr-fieldset">
            <legend className="fr-fieldset__legend">
                <h2 className="fr-h5">{t('as_publishers')}</h2>
            </legend>
            <div className="fr-col-8 fr-fieldset__element">
                <p className="fr-hidden fr-unhidden-sm fr-hint-text">
                    {t('as_publishers_info')}
                </p>
            </div>
            <div className="fr-fieldset__element">
                <div className="fr-mb-2w">
                    <Toggle
                        value={operator}
                        options={[
                            {value: 'OU', label: t('Include')},
                            {value: 'SAUF', label: t('Exclude')},
                        ]}
                        onChange={(value) => {
                            setOperator(value)
                            setCanReset(true)
                        }}
                    />
                </div>
                {searches.map((element, index) => (
                    <div
                        key={`service${index}`}
                        className="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom fr-mb-2w fr-mb-md-2v"
                    >
                        <div className="fr-col-12 fr-col-lg-10">
                            <ServiceTypeAhead
                                update={(value) => updateSearch(value, index)}
                                selectedMemory={
                                    typeof element === 'number'
                                        ? [
                                              {
                                                  value: element,
                                                  label: labels[index],
                                              },
                                          ]
                                        : []
                                }
                                typeaheadId={`service-typeahead-${index}`}
                                index={index}
                                endpoint={endpoint}
                                clearNow={clearNow}
                                setClearNow={setClearNow}
                                placeholder={t('as_search_service_placeholder')}
                                ressourcesSite={ressourcesSite}
                                archivesRef={archivesRef}
                                setCanReset={setCanReset}
                            />
                        </div>
                        <div className="fr-col-12 fr-col-lg-2 as-operators">
                            {index == searches.length - 1 ? (
                                <PlusButton onClick={addSearch} />
                            ) : (
                                <></>
                            )}
                            {index > 0 ? (
                                <RemoveRowButton
                                    onClick={() => {
                                        removeService(index)
                                    }}
                                />
                            ) : (
                                <></>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </fieldset>
    )
}
