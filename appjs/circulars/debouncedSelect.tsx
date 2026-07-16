/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2024
 * Contact http://www.logilab.fr -- mailto:contact@logilab.fr
 *
 * This software is governed by the CeCILL-C license under French law and
 * abiding by the rules of distribution of free software. You can use,
 * modify and/ or redistribute the software under the terms of the CeCILL-C
 * license as circulated by CEA, CNRS and INRIA at the following URL
 * "http://www.cecill.info
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
import React from 'react'

import {ChangeEventHandler} from 'react'
import {useState} from 'react'
import {Select} from '@codegouvfr/react-dsfr/SelectNext'
import {translate as t} from '../translate'

export function DebouncedSelect({
    id,
    label,
    value: initialValue,
    placeholder,
    onChange,
    options,
    debounce = 500,
}: {
    id: string
    label: string
    value: string
    placeholder: string
    onChange: (value: string | number) => void
    options: Array<{label: string; value: string}>
    debounce?: number
} & Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'onChange'>) {
    const [value, setValue] = React.useState(initialValue)

    React.useEffect(() => {
        setValue(initialValue)
    }, [initialValue])

    React.useEffect(() => {
        const timeout = setTimeout(() => {
            onChange(value)
        }, debounce)

        return () => clearTimeout(timeout)
    }, [value])
    const messageId = id + '-message'
    return (
        <div className="fr-select-group">
            <label className="fr-label" htmlFor={id}>
                {label}
            </label>
            <select
                id={id}
                className="fr-select"
                placeholder={placeholder}
                aria-describedby={messageId}
                onChange={(event) => setValue(event.target.value)}
                defaultValue={value}
                value={value}
            >
                <option selected disabled>
                    {placeholder}
                </option>
                {options.map((option, idx) => {
                    return (
                        <option value={option.value} key={idx}>
                            {option.label}
                        </option>
                    )
                })}
            </select>
            <div
                className="fr-messages-group"
                id={messageId}
                aria-live="polite"
            ></div>
        </div>
    )
}
