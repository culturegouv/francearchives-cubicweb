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
 * requirements in conditions enabling the security of their systems and/or
 * data to be ensured and, more generally, to use and operate it in the
 * same conditions as regards security.
 *
 * The fact that you are presently reading this means that you have had
 * knowledge of the CeCILL-C license and that you accept its terms.
 */

import React, {useState} from 'react'
import {AuthorityTypeAhead} from './authoritySearchBar'
import {DropDown, PlusButton, RemoveRowButton} from './widgets'
import {translate as t} from '../translate'
import {Input} from '@codegouvfr/react-dsfr/Input'

const TYPE_OPTIONS = [
    {value: 't', label: t('Tout le texte')},
    {value: 'l', label: t('Location')},
    {value: 'a', label: t('Person or institution')},
    {value: 's', label: t('Topic')},
]

const PLACEHOLDERS = {
    l: t('as_location_placeholder'),
    a: t('as_person_placeholder'),
    s: t('as_subject_placeholder'),
}

export function TextOrAuthorityInput({
    archivesRef,
    ressourcesSite,
    value,
    type,
    label,
    update,
    updateType,
    endpoint,
    index,
    operators,
    updateOperator,
    addSearch,
    removeSearch,
    setCanReset,
}) {
    const [clearNow, setClearNow] = useState(false)
    const divClass = index == 0 ? 'as-criterion' : 'as-criterion__next'
    return (
        <div
            className={`fr-grid-row fr-grid-row--gutters fr-grid-row--bottom ${divClass}`}
        >
            <div className="fr-col-12 fr-col-lg-3">
                <DropDown
                    value={type}
                    label={t('Select a criterion')}
                    options={TYPE_OPTIONS}
                    onChange={(e) => {
                        update({value: '', label: ''})
                        updateType(e.target.value)
                        setClearNow(true)
                    }}
                />
            </div>
            <div className="fr-col-12 fr-col-lg-7">
                {type === 't' ? (
                    <Input
                        label={t('Tout le texte : recherche libre')}
                        nativeInputProps={{
                            value: value,
                            onChange: (e) =>
                                update({value: e.target.value, label: ''}),
                            type: 'text',
                            placeholder: t('ex.: cartes postales Dieppe'),
                        }}
                    />
                ) : (
                    <AuthorityTypeAhead
                        archivesRef={archivesRef}
                        ressourcesSite={ressourcesSite}
                        endpoint={endpoint}
                        selectedMemory={
                            typeof value === 'number'
                                ? [{value: value, label: label}]
                                : []
                        }
                        update={update}
                        index={index}
                        type={type}
                        clearNow={clearNow}
                        setClearNow={setClearNow}
                        label={
                            TYPE_OPTIONS.find((o) => o.value === type)?.label
                        }
                        placeholder={PLACEHOLDERS[type]}
                        setCanReset={setCanReset}
                    />
                )}
            </div>
            <div className="fr-col-12 fr-col-lg-2 as-operators">
                {operators.length > index ? (
                    <DropDown
                        value={operators[index]}
                        label={t('Operator')}
                        options={[
                            {value: 'ET', label: t('AND')},
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
                {index > 0 ? <RemoveRowButton onClick={removeSearch} /> : <></>}
            </div>
        </div>
    )
}

export function TextOrAuthoritySearchBox({
    archivesRef,
    ressourcesSite,
    searches,
    addSearch,
    updateSearch,
    operators,
    updateOperator,
    searchTypes,
    updateSearchType,
    labels,
    endpoint,
    removeSearch,
    setCanReset,
}) {
    return (
        <fieldset className="fr-fieldset">
            <legend className="fr-fieldset__legend">
                <h2 className="fr-h5">{t('Dans le texte')}</h2>
            </legend>
            <div className="fr-col-8">
                <p className="fr-hidden fr-unhidden-sm fr-hint-text">
                    {t('as_text_info')}
                </p>
            </div>
            {searches.map((element, index) => (
                <div
                    key={`search${index}`}
                    id={`as-toasb-${index}`}
                    className="fr-fieldset__element"
                >
                    <TextOrAuthorityInput
                        archivesRef={archivesRef}
                        ressourcesSite={ressourcesSite}
                        value={element}
                        type={searchTypes[index]}
                        label={labels[index]}
                        update={(value) => {
                            updateSearch(value, index)
                        }}
                        updateType={(value) => {
                            updateSearchType(value, index)
                        }}
                        endpoint={endpoint}
                        index={index}
                        operators={operators}
                        updateOperator={updateOperator}
                        addSearch={addSearch}
                        removeSearch={() => {
                            removeSearch(index)
                        }}
                        setCanReset={setCanReset}
                    />
                </div>
            ))}
        </fieldset>
    )
}
