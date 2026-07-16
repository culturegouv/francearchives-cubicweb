import Button from '@codegouvfr/react-dsfr/Button'
import Input from '@codegouvfr/react-dsfr/Input'
import Tag from '@codegouvfr/react-dsfr/Tag'
import {Autocomplete, AutocompleteValue} from '@mui/material'
import _ from 'lodash'
import React, {useState, useEffect, useMemo} from 'react'

type Value = {value: string; label: string}

export function FaAutocomplete<Multiple extends boolean>({
    id,
    label,
    value,
    freeSolo,
    loadOptions,
    onChange,
    onInputChange,
    multiple,
    disabled,
    readonly,
    error,
    loading,
    placeholder,
}: {
    id?: string
    value?: AutocompleteValue<Value, Multiple, false, false>
    label: string
    freeSolo?: boolean
    onChange: (
        newValue: AutocompleteValue<Value, Multiple, false, false>,
    ) => void
    onInputChange?: (event: any, value: any) => void
    loadOptions: (input: string) => Promise<Value[]>
    multiple?: Multiple
    disabled?: boolean
    readonly?: boolean
    error?: string
    loading?: boolean
    placeholder?: string
}) {
    const [options, setOptions] = useState<Value[]>([])
    const [loadingSuggestions, setLoadingSuggestions] = useState(false)
    const [inputValue, setInputValue] = useState('')

    const loadOptionsThrottled = useMemo(() => {
        async function _loadOptions(input: string) {
            setLoadingSuggestions(true)
            const result = await loadOptions(input)
            setLoadingSuggestions(false)
            return result
        }
        return _.throttle(_loadOptions, 300)
    }, [])

    useEffect(() => {
        async function load() {
            const newResults = (await loadOptionsThrottled(
                inputValue,
            )) as Value[]
            setOptions(newResults)
        }
        if (inputValue.length >= 3) {
            load()
        } else {
            setOptions([])
        }
    }, [inputValue])

    return (
        <Autocomplete
            id={id}
            // @ts-ignore TODO fix typing
            value={value === undefined ? null : value}
            freeSolo
            disabled={disabled}
            readOnly={readonly}
            multiple={multiple}
            options={options}
            noOptionsText="Aucun résultat trouvé"
            getOptionLabel={(option) =>
                typeof option === 'string' ? option : option.label
            }
            // Filtering is done on the server
            filterOptions={(x) => x}
            onChange={(e, v) => onChange(v)}
            onInputChange={(event, newInputValue) => {
                if (onInputChange) {
                    onInputChange(event, newInputValue)
                }
                setInputValue(newInputValue)
            }}
            loading={loadingSuggestions || loading}
            disablePortal={true}
            isOptionEqualToValue={(option, value) =>
                option.value === value.value
            }
            renderTags={(value, getTagProps) =>
                value.map((option, index) => {
                    const {key, onDelete} = getTagProps({index})
                    return (
                        <Tag
                            key={key}
                            nativeButtonProps={{
                                onClick: onDelete,
                            }}
                            className="fr-btn--icon-right fr-icon-close-line"
                        >
                            {option.label}
                        </Tag>
                    )
                })
            }
            renderInput={(params) => {
                const selectedEntries = params.InputProps.startAdornment
                return (
                    <>
                        <Input
                            id={params.id}
                            ref={params.InputProps.ref}
                            label={label}
                            nativeInputProps={{
                                ...params.inputProps,
                                placeholder,
                            }}
                            disabled={disabled}
                            state={error ? 'error' : 'default'}
                            stateRelatedMessage={error ? error : undefined}
                            addon={
                                // Only show clear button when single value is present
                                !multiple &&
                                value !== null &&
                                value !== undefined &&
                                // @ts-ignore TODO fix typing
                                value?.value !== '' ? (
                                    <Button
                                        type={'button'}
                                        priority="secondary"
                                        iconId="fr-icon-close-line"
                                        title="Clear search"
                                        onClick={() => {
                                            const c = params.inputProps.onChange
                                            if (c) {
                                                // @ts-ignore TODO fix typing
                                                c({target: {value: ''}})
                                            }
                                        }}
                                    />
                                ) : (
                                    <></>
                                )
                            }
                        />
                        <div
                            style={{
                                display: 'flex',
                                flexWrap: 'wrap',
                                gap: '0.5rem',
                            }}
                        >
                            {selectedEntries}
                        </div>
                    </>
                )
            }}
        />
    )
}
