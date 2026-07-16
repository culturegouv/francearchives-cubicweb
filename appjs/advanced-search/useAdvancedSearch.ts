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

import {useState} from 'react'

function useToggle(
    defaultValue: boolean = true,
): [boolean, () => void, (value: boolean) => void] {
    const [toggleValue, setToggleValue] = useState(defaultValue)
    const toggleFunction = () => {
        setToggleValue(!toggleValue)
    }
    return [toggleValue, toggleFunction, setToggleValue]
}

function useStringArray(
    initialValue: string[],
    defaultElement: string,
): [
    string[],
    () => void,
    (value: string, index: number) => void,
    (value: string[]) => void,
    (index: number) => void,
] {
    const [array, setArray] = useState<string[]>(initialValue)
    const addValue = () => {
        setArray((array) => [...array, defaultElement])
    }
    const updateElement = (value: string, index: number) => {
        setArray((array) => [
            ...array.slice(0, index),
            value,
            ...array.slice(index + 1),
        ])
    }
    const removeElement = (index: number) => {
        setArray((array) => [
            ...array.slice(0, index),
            ...array.slice(index + 1),
        ])
    }
    return [array, addValue, updateElement, setArray, removeElement]
}

/** Remove last empty value from array only if array has more than 1 element*/
function trimLastEmptyValue(values, operators, array1, array2) {
    let lastIndex = values.length - 1
    let result = [values, operators]
    if (array1) {
        result = [...result, array1]
    }
    if (array2) {
        result = [...result, array2]
    }
    while (lastIndex >= 1 && result[0][lastIndex] === '') {
        result = [
            values.slice(0, lastIndex),
            operators.slice(0, operators.length - 1),
        ]
        if (array1) {
            result = [...result, array1.slice(0, lastIndex)]
        }
        if (array2) {
            result = [...result, array2.slice(0, lastIndex)]
        }
        lastIndex = result[0].length - 1
    }
    return result
}

function urlFragment(parameterName, valuesOperatorsTypes) {
    const [values, operators, types] = valuesOperatorsTypes
    if (values.length < 2 && values[0] === '') {
        return ''
    }
    const result = `&${parameterName}=${encodeURIComponent(
        JSON.stringify(values),
    )}&${parameterName}_op=${encodeURIComponent(JSON.stringify(operators))}`
    if (!types) {
        return result
    }
    return `${result}&${parameterName}_t=${encodeURIComponent(
        JSON.stringify(types),
    )}`
}

export function useAdvancedSearch() {
    const [archivesRef, toggleArchivesRef, setArchivesRef] = useToggle()
    const [ressourcesSite, toggleRessourcesSite, setRessourcesSite] =
        useToggle()
    const [canReset, setCanReset] = useState(false)
    const [
        searches,
        addSearchValue,
        updateSearchValue,
        setSearches,
        removeSearchValue,
    ] = useStringArray([''], '')

    const [
        operators,
        addOperator,
        updateOperator,
        setOperators,
        removeOperator,
    ] = useStringArray([], 'ET')
    const [
        authoritiesLabels,
        addAuthorityLabel,
        updateAuthorityLabel,
        setAuthoritiesLabels,
        removeAuthoritiesLabel,
    ] = useStringArray([''], '')
    // values must be in "t", "s", "l", "a" for text, subject, location, agent
    const [
        searchTypes,
        addSearchType,
        updateSearchType,
        setSearchTypes,
        removeSearchType,
    ] = useStringArray(['t'], 't')

    const [
        services,
        addServiceValue,
        updateServiceValue,
        setServices,
        removeServiceValue,
    ] = useStringArray([''], 'ET')
    const [serviceOperator, setServiceOperator] = useState<string>('OU')
    const [
        servicesLabels,
        addServiceLabel,
        updateServiceLabel,
        setServicesLabels,
        removeServiceLabel,
    ] = useStringArray([''], '')

    const [
        producers,
        addProducerValue,
        updateProducer,
        setProducers,
        removeProducerValue,
    ] = useStringArray([''], '')
    const [
        producerOperators,
        addProducerOperator,
        updateProducerOperator,
        setProducerOperators,
        removeProducerOperator,
    ] = useStringArray([], 'ET')
    const [
        producerTypes,
        addProducerType,
        updateProducerType,
        setProducerTypes,
        removeProducerType,
    ] = useStringArray(['t'], 't') // values must be "t" for text or "k" for keyword search

    const [minDate, setMinDate] = useState<number | null>(null)
    const [maxDate, setMaxDate] = useState<number | null>(null)

    const [clearServicesNow, setClearServicesNow] = useState(false)
    const [clearProducersNow, setClearProducersNow] = useState(false)

    const addSearch = () => {
        addSearchValue()
        addAuthorityLabel()
        addOperator()
        addSearchType()
        setCanReset(true)
    }

    const updateSearch = ({value, label}, index: number) => {
        updateSearchValue(value, index)
        updateAuthorityLabel(label, index)
        setCanReset(true)
    }

    const removeSearch = (index: number) => {
        removeSearchValue(index)
        removeAuthoritiesLabel(index)
        removeOperator(index - 1)
        removeSearchType(index)
    }

    const addService = () => {
        addServiceValue()
        addServiceLabel()
        setCanReset(true)
    }

    const updateService = ({value, label}, index: number) => {
        updateServiceValue(value, index)
        updateServiceLabel(label, index)
        setCanReset(true)
    }

    const removeService = (index: number) => {
        removeServiceValue(index)
        removeServiceLabel(index)
    }

    const addProducer = () => {
        addProducerValue()
        addProducerType()
        addProducerOperator()
        setCanReset(true)
    }

    const removeProducer = (index: number) => {
        removeProducerValue(index)
        removeProducerOperator(index - 1)
        removeProducerType(index)
    }

    // Read and load values from session storage
    const loadSessionStorage = () => {
        const previousData = sessionStorage.getItem('faAdvancedSearch')
        if (previousData !== null && previousData.length) {
            const data = JSON.parse(previousData)
            setArchivesRef(data['archivesRef'])
            setRessourcesSite(data['ressourcesSite'])
            setSearches(data['searches'][0])
            setCanReset(true)
            setOperators(data['searches'][1])
            setAuthoritiesLabels(data['searches'][2])
            setSearchTypes(data['searches'][3])
            setServices(data['services'][0])
            setServiceOperator(data['services'][1])
            setServicesLabels(data['services'][2])
            setProducers(data['producers'][0])
            setProducerOperators(data['producers'][1])
            setProducerTypes(data['producers'][2])
            setMinDate(data['minDate'])
            setMaxDate(data['maxDate'])
        }
    }

    const resetValues = (resetTypes: boolean = true) => {
        if (resetTypes) {
            setArchivesRef(true)
            setRessourcesSite(true)
            setCanReset(false)
        } else {
            setCanReset(true)
        }
        setSearches([''])
        setOperators([])
        setAuthoritiesLabels([''])
        setSearchTypes(['t'])
        setServices([''])
        setServiceOperator('OU')
        setServicesLabels([''])
        setProducers([''])
        setProducerOperators([])
        setProducerTypes(['t'])
        setMinDate(null)
        setMaxDate(null)
        setClearServicesNow(true)
        setClearProducersNow(true)
        sessionStorage.removeItem('faAdvancedSearch')
    }

    const launchSearch = () => {
        let url = `/search?q=&advanced=true`
        if (archivesRef && !ressourcesSite) {
            url += '&es_escategory=archives'
        }
        if (!archivesRef && ressourcesSite) {
            url += '&es_escategory=siteres'
        }

        url += urlFragment(
            'searches',
            trimLastEmptyValue(searches, operators, searchTypes, false),
        )
        url += urlFragment('services', [
            trimLastEmptyValue(services, [], false, false)[0],
            serviceOperator,
            false,
        ])
        url += urlFragment(
            'producers',
            trimLastEmptyValue(
                producers,
                producerOperators,
                producerTypes,
                false,
            ),
        )

        if (minDate !== null) {
            url += `&es_date_min=${minDate}`
        }
        if (maxDate !== null) {
            url += `&es_date_max=${maxDate}`
        }
        const [trimmedServices, _, trimmedServicesLabels] = trimLastEmptyValue(
            services,
            [],
            servicesLabels,
            false,
        )

        const searchMemory = {
            archivesRef: archivesRef,
            ressourcesSite: ressourcesSite,
            searches: trimLastEmptyValue(
                searches,
                operators,
                authoritiesLabels,
                searchTypes,
            ),
            services: [trimmedServices, serviceOperator, trimmedServicesLabels],
            producers: trimLastEmptyValue(
                producers,
                producerOperators,
                producerTypes,
                false,
            ),
            minDate: minDate,
            maxDate: maxDate,
        }

        sessionStorage.setItem('faAdvancedSearch', JSON.stringify(searchMemory))
        window.location.href = url
    }

    return {
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
    }
}
