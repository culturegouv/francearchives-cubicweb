import React, {useState} from 'react'

import {YearInput} from './widgets'
import {translate as t} from '../translate'

export interface IDatesBox {
    minDate: number | null
    setMinDate: (value: number | null) => void
    maxDate: number | null
    setMaxDate: (value: number | null) => void
    onStateChange: (value: boolean) => void
    setCanReset: (value: boolean) => void
}

export function DatesBox({
    minDate,
    setMinDate,
    maxDate,
    setMaxDate,
    onStateChange,
    setCanReset,
}: IDatesBox) {
    const [periodInput, setPeriodInput] = useState(minDate !== maxDate)

    return (
        <fieldset className="fr-fieldset">
            <legend className="fr-fieldset__legend">
                <h2 className="fr-h5">{t('Dates')}</h2>
            </legend>
            <div className="fr-col-8 fr-fieldset__element">
                <p className="fr-hidden fr-unhidden-sm fr-hint-text">
                    {t('as_dates_info')}
                </p>
            </div>
            <div className="as-dates">
                <fieldset className="fr-segmented">
                    <legend className="fr-segmented__legend">
                        {t('Year')}/{t('Period')}
                    </legend>
                    <div className="fr-segmented__elements" role="group">
                        <div className="fr-segmented__element">
                            <input
                                id="segmented-date-year"
                                value="1"
                                type="radio"
                                checked={!periodInput}
                                name="segmented-date"
                                aria-label={t('Year')}
                                role="button"
                                aria-pressed={!periodInput ? true : false}
                                onClick={() => {
                                    setPeriodInput(false)
                                    setMaxDate(minDate)
                                    setCanReset(true)
                                }}
                            />
                            <label
                                className="fr-label"
                                htmlFor="segmented-date-year"
                            >
                                {t('Year')}
                            </label>
                        </div>
                        <div className="fr-segmented__element">
                            <input
                                id="segmented-date-period"
                                value="2"
                                checked={periodInput}
                                type="radio"
                                name="segmented-date"
                                aria-label={t('Period')}
                                role="button"
                                aria-pressed={periodInput ? true : false}
                                onClick={() => {
                                    setPeriodInput(true)
                                    setCanReset(true)
                                }}
                            />
                            <label
                                className="fr-label"
                                htmlFor="segmented-date-period"
                            >
                                {t('Period')}
                            </label>
                        </div>
                    </div>
                </fieldset>
                {!periodInput ? (
                    <YearInput
                        id="as-exact-date"
                        label={t('Exact year')}
                        value={minDate}
                        placeholder={t('ex.: 1968')}
                        setValue={(value) => {
                            setMinDate(value)
                            setMaxDate(value)
                            setCanReset(true)
                        }}
                        minValue={null}
                        onStateChange={onStateChange}
                    />
                ) : (
                    <>
                        <YearInput
                            id="as-min-date"
                            label={t('Start year')}
                            value={minDate}
                            setValue={setMinDate}
                            minValue={null}
                            placeholder={t('ex.: 1453')}
                            onStateChange={onStateChange}
                        />
                        <YearInput
                            id="as-max-date"
                            label={t('Stop year')}
                            value={maxDate}
                            setValue={setMaxDate}
                            minValue={minDate}
                            placeholder={t('ex.: 1648')}
                            onStateChange={onStateChange}
                        />
                    </>
                )}
            </div>
        </fieldset>
    )
}
