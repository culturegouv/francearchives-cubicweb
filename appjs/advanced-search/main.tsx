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
import {createRoot} from 'react-dom/client'

import {Checkbox} from '@codegouvfr/react-dsfr/Checkbox'

import {TextOrAuthoritySearchBox} from './textOrAuthorityBox'
import {useAdvancedSearch} from './useAdvancedSearch'
import {ServicesBox} from './servicesBox'
import {ProducerBox} from './producerBox'
import {DatesBox} from './datesBox'
import {FormButtons} from './formButtons'
import {translate as t} from '../translate'
import {startReactDsfr} from '@codegouvfr/react-dsfr/spa'
startReactDsfr({defaultColorScheme: 'light'})

function AdvancedSearch() {
    const [loading, setLoading] = useState(true)
    const [canSubmit, setCanSubmit] = useState(true)
    const {
        archivesRef,
        toggleArchivesRef,
        ressourcesSite,
        toggleRessourcesSite,
        searches,
        addSearch,
        updateSearch,
        removeSearch,
        operators,
        updateOperator,
        authoritiesLabels,
        searchTypes,
        updateSearchType,
        services,
        addService,
        updateService,
        removeService,
        serviceOperator,
        setServiceOperator,
        servicesLabels,
        producers,
        addProducer,
        updateProducer,
        removeProducer,
        producerOperators,
        updateProducerOperator,
        updateProducerType,
        minDate,
        setMinDate,
        maxDate,
        setMaxDate,
        launchSearch,
        loadSessionStorage,
        resetValues,
        clearServicesNow,
        setClearServicesNow,
        clearProducersNow,
        setClearProducersNow,
        canReset,
        setCanReset,
    } = useAdvancedSearch()

    useEffect(() => {
        loadSessionStorage()
        setLoading(false)
    }, [])

    if (loading) {
        return <span>Loading....</span>
    }
    return (
        <div className="fr-container">
            <h1>{t('Advanced search')}</h1>
            <div className="fr-mb-5w">
                <FormButtons
                    canSubmit={canSubmit}
                    canReset={canReset}
                    launchSearch={launchSearch}
                    resetValues={resetValues}
                />
            </div>
            <div className="as-field as-field--sources">
                <Checkbox
                    legend={<h2 className="fr-h5">{t('Type of resources')}</h2>}
                    orientation="horizontal"
                    options={[
                        {
                            hintText: t('archives_search_info'),
                            label: t('Referenced archives'),
                            nativeInputProps: {
                                name: 'as-scop',
                                checked: archivesRef,
                                onChange: () => {
                                    toggleArchivesRef()
                                    resetValues(false)
                                },
                            },
                        },
                        {
                            hintText: t('siteres_search_info'),
                            label: t('Site contents'),
                            nativeInputProps: {
                                name: 'as-scop',
                                checked: ressourcesSite,
                                onChange: () => {
                                    toggleRessourcesSite()
                                    resetValues(false)
                                },
                            },
                        },
                    ]}
                />
            </div>
            <div className="as-field text-or-authority">
                <TextOrAuthoritySearchBox
                    archivesRef={archivesRef}
                    ressourcesSite={ressourcesSite}
                    searches={searches}
                    addSearch={addSearch}
                    updateSearch={updateSearch}
                    operators={operators}
                    updateOperator={updateOperator}
                    searchTypes={searchTypes}
                    updateSearchType={updateSearchType}
                    labels={authoritiesLabels}
                    endpoint={'advanced_search/suggest'}
                    removeSearch={removeSearch}
                    setCanReset={setCanReset}
                />
            </div>
            <div className="as-field">
                <ServicesBox
                    searches={services}
                    labels={servicesLabels}
                    addSearch={addService}
                    updateSearch={updateService}
                    operator={serviceOperator}
                    setOperator={setServiceOperator}
                    endpoint={'advanced_search/services'}
                    clearNow={clearServicesNow}
                    setClearNow={setClearServicesNow}
                    removeService={removeService}
                    archivesRef={archivesRef}
                    ressourcesSite={ressourcesSite}
                    setCanReset={setCanReset}
                />
            </div>
            {archivesRef ? (
                <div className="as-field">
                    <ProducerBox
                        searches={producers}
                        addSearch={addProducer}
                        updateSearch={updateProducer}
                        operators={producerOperators}
                        updateOperator={updateProducerOperator}
                        updateType={updateProducerType}
                        endpoint={'advanced_search/all'}
                        clearNow={clearProducersNow}
                        setClearNow={setClearProducersNow}
                        removeSearch={removeProducer}
                        setCanReset={setCanReset}
                    />
                </div>
            ) : (
                <></>
            )}
            <div className="as-field">
                <DatesBox
                    minDate={minDate}
                    setMinDate={setMinDate}
                    maxDate={maxDate}
                    setMaxDate={setMaxDate}
                    setCanReset={setCanReset}
                    onStateChange={(valid) => {
                        setCanSubmit(valid)
                    }}
                />
            </div>
            <div className="fr-mt-5w">
                <FormButtons
                    canSubmit={canSubmit}
                    canReset={canReset}
                    launchSearch={launchSearch}
                    resetValues={resetValues}
                />
            </div>
        </div>
    )
}
const root = createRoot(document.getElementById('advanced-search'))
root.render(<AdvancedSearch />)
