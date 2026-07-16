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
 * modify and redistribute granted by the licens, users are provided only
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

import React, {useState, useEffect, useCallback} from 'react'
import {DropDown, PlusButton, RemoveRowButton} from './widgets'
import {translate as t} from '../translate'
import {FaAutocomplete} from './FAAutocomplete'

export function ProducerTypeAhead({
    endpoint,
    selected,
    update,
    updateType,
    typeaheadId,
    index,
    clearNow,
    setClearNow,
    placeholder,
    setCanReset,
}) {
    const [isLoading, setIsLoading] = useState(false)
    const [errorMsg, setErrorMsg] = React.useState<string | null>()
    useEffect(() => {
        if (clearNow) {
            update('')
            setClearNow(false)
        }
    }, [clearNow])

    const handleSearch = useCallback((textSearch: string) => {
        setIsLoading(true)
        // TODO: remove accents

        const es_query = {
            query: {
                simple_query_string: {
                    query: `${textSearch}*`,
                    fields: ['originators.text'],
                    default_operator: 'and',
                },
            },
            size: 0,
            aggs: {
                producer: {
                    terms: {field: 'originators', size: 30},
                },
            },
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
                    update('')
                } else {
                    setErrorMsg(null)
                    const items = response['aggregations']['producer'][
                        'buckets'
                    ].map((element) => ({
                        value: element['key'],
                        label: element['key'],
                    }))
                    options = items
                }
                setIsLoading(false)
                return options
            })
            .catch((error) => {
                setErrorMsg(t('Could not retrieve results'))
                update('')
                console.error(error)
                return []
            })
    }, [])

    const hasError = errorMsg !== undefined && errorMsg !== null
    const label = `${t('as_producer')} ${index + 1}`
    return (
        <FaAutocomplete
            value={
                selected !== '' ? {value: selected, label: selected} : undefined
            }
            label={label}
            freeSolo
            loadOptions={handleSearch}
            multiple={false}
            placeholder={placeholder}
            onInputChange={(event, value) => {
                // do not change the type on the page load
                if (value !== selected) {
                    update(value)
                    updateType('t')
                }
            }}
            onChange={(selectedElement) => {
                if (selectedElement && typeof selectedElement !== 'string') {
                    update(selectedElement.value)
                    updateType('k')
                } else {
                    updateType('t')
                }
                setCanReset(true)
            }}
            loading={isLoading}
            error={hasError ? errorMsg : undefined}
        />
    )
}

export function ProducerBox({
    searches,
    addSearch,
    updateSearch,
    operators,
    updateOperator,
    updateType,
    endpoint,
    clearNow,
    setClearNow,
    removeSearch,
    setCanReset,
}) {
    return (
        <fieldset className="fr-fieldset">
            <legend className="fr-fieldset__legend">
                <h2 className="fr-h5">{t('as_producers')}</h2>
            </legend>
            <div className="fr-col-8 fr-fieldset__element">
                <p className="fr-hidden fr-unhidden-sm fr-hint-text">
                    {t('as_producers_info')}
                </p>
            </div>
            <div className="fr-fieldset__element">
                {searches.map((element, index) => (
                    <div
                        key={`authority${index}`}
                        className="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom fr-mb-4w fr-mb-md-2v as-criterion"
                    >
                        <div className="fr-col-12 fr-col-lg-10">
                            <ProducerTypeAhead
                                endpoint={endpoint}
                                selected={element}
                                update={(value) => updateSearch(value, index)}
                                updateType={(value) => updateType(value, index)}
                                typeaheadId={`producer-typeahead-${index}`}
                                index={index}
                                clearNow={clearNow}
                                setClearNow={setClearNow}
                                placeholder={t(
                                    'as_search_productor_placeholder',
                                )}
                                setCanReset={setCanReset}
                            />
                        </div>
                        <div className="fr-col-12 fr-col-lg-2 as-operators">
                            {operators.length > index ? (
                                <DropDown
                                    value={operators[index]}
                                    label={t('Operator')}
                                    options={[
                                        {
                                            value: 'ET',
                                            label: t('AND'),
                                        },
                                        {value: 'OU', label: t('OR')},
                                        {value: 'SAUF', label: t('EXCEPT')},
                                    ]}
                                    onChange={(e) => {
                                        updateOperator(e.target.value, index)
                                    }}
                                />
                            ) : (
                                <PlusButton onClick={addSearch} />
                            )}
                            {index > 0 ? (
                                <RemoveRowButton
                                    onClick={() => {
                                        removeSearch(index)
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
