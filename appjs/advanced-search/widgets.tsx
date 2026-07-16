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
import {ChangeEventHandler} from 'react'

import React, {useEffect, useState} from 'react'
import {Button} from '@codegouvfr/react-dsfr/Button'
import SelectNext from '@codegouvfr/react-dsfr/SelectNext'
import {Input, InputProps} from '@codegouvfr/react-dsfr/Input'
import {translate as t} from '../translate'

export interface IPlusButton {
    onClick: () => void
}

export function PlusButton({onClick}: IPlusButton) {
    return (
        <>
            <div className="fr-hidden fr-unhidden-lg">
                <Button
                    title={t('Add a criterion')}
                    iconId="fr-icon-add-line"
                    priority="secondary"
                    nativeButtonProps={{
                        onClick: onClick,
                    }}
                />
            </div>
            <div className="fr-hidden-lg">
                <Button
                    title={t('Add a criterion')}
                    iconId="fr-icon-add-line"
                    // @ts-ignore: react-dsfr bug adding an unwanted fr-btn--icon-left class by default

                    iconPosition=""
                    priority="secondary"
                    nativeButtonProps={{
                        onClick: onClick,
                    }}
                >
                    {t('Add')}
                </Button>
            </div>
        </>
    )
}

export interface IRemoveRowButton {
    onClick: () => void
}

export function RemoveRowButton({onClick}: IRemoveRowButton) {
    return (
        <>
            <div className="fr-hidden fr-unhidden-lg">
                <Button
                    title={t('Remove the criterion')}
                    iconId="fr-icon-subtract-line"
                    priority="secondary"
                    nativeButtonProps={{
                        onClick: onClick,
                        'aria-label': t('Remove the criterion'),
                    }}
                    onClick={onClick}
                />
            </div>
            <div className="fr-hidden-lg">
                <Button
                    title={t('Remove the criterion')}
                    iconId="fr-icon-subtract-line"
                    priority="secondary"
                    nativeButtonProps={{
                        onClick: onClick,
                    }}
                    onClick={onClick}
                >
                    {t('Remove')}
                </Button>
            </div>
        </>
    )
}

export interface IDropDown {
    value: string
    label: string | null
    options: Array<{label: string; value: string}>
    help?: string
    onChange?: ChangeEventHandler<HTMLSelectElement>
}

export function DropDown({value, label, options, help, onChange}: IDropDown) {
    return (
        <SelectNext
            label={label}
            nativeSelectProps={{
                onChange,
                value,
                //@ts-expect-error is actually works
                'arial-label': help,
            }}
            options={options}
            placeholder={help}
        />
    )
}

export interface IToggle {
    value: string
    options: Array<{label: string; value: string}>
    onChange: any
}

export function Toggle({value, options, onChange}: IToggle) {
    const option1 = options[0]
    const option2 = options[1]
    return (
        <fieldset className="fr-segmented">
            <legend className="fr-segmented__legend fr-segmented__legend--inline">
                {t('Filter')}
            </legend>
            <div className="fr-segmented__elements" role="group">
                <div className="fr-segmented__element">
                    <input
                        id="segmented-toggle-1"
                        value={option1.value}
                        checked={option1.value == value}
                        type="radio"
                        name="segmented-toggle"
                        role="button"
                        aria-label={option1.label}
                        aria-pressed={option1.value == value ? true : false}
                        onClick={() => {
                            onChange(option1.value)
                        }}
                    />
                    <label className="fr-label" htmlFor="segmented-toggle-1">
                        {option1.label}
                    </label>
                </div>
                <div className="fr-segmented__element">
                    <input
                        id="segmented-toggle-2"
                        value={option2.value}
                        checked={option2.value == value}
                        type="radio"
                        name="segmented-toggle"
                        aria-label={option2.label}
                        role="button"
                        aria-pressed={option2.value == value ? true : false}
                        onClick={() => {
                            onChange(option2.value)
                        }}
                    />
                    <label className="fr-label" htmlFor="segmented-toggle-2">
                        {option2.label}
                    </label>
                </div>
            </div>
        </fieldset>
    )
}

export interface IYearInput {
    id: string
    label: string
    value: number | null
    setValue: (value: number | null) => void
    minValue: number | null
    placeholder: string
    onStateChange: (value: boolean) => void
}

export function YearInput({
    id,
    label,
    value,
    setValue,
    minValue,
    placeholder,
    onStateChange,
}: IYearInput) {
    const [state, setState] = useState<InputProps['state']>('default')
    const [stateRelatedMessage, setStateRelatedMessage] = useState('')

    useEffect(() => {
        onStateChange(state === 'default')
    }, [state])

    useEffect(() => {
        if (minValue && value && value < minValue) {
            setState('error')
            setStateRelatedMessage(
                t('The end date must be greater than the start date'),
            )
        } else {
            setState('default')
            setStateRelatedMessage('')
        }
    }, [minValue, value])

    const checkNumberOrNull = (input) => {
        if (!isNaN(parseInt(input))) {
            setValue(parseInt(input))
            setState('default')
            setStateRelatedMessage('')
        } else if (input === '') {
            setValue(null)
            setState('default')
            setStateRelatedMessage('')
        } else {
            setValue(null)
            setState('error')
            setStateRelatedMessage(t('The value entered must be a number'))
        }
    }
    return (
        <Input
            label={label}
            state={state}
            stateRelatedMessage={stateRelatedMessage}
            hintText={placeholder}
            nativeInputProps={{
                id: id,
                value: value ?? '',
                onChange: (e) => checkNumberOrNull(e.target.value),
                placeholder: placeholder,
            }}
        />
    )
}
