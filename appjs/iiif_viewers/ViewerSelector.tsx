/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2023
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

import {UniversalViewer} from './UniversalViewer'
import {Mirador} from './Mirador'
import {translate as t} from '../translate'

import './index.css'

type ViewerSelectorProps = {
    viewer: 'uv' | 'm'
    manifest: string
    language: string
}

export function ViewerSelector({
    viewer,
    manifest,
    language,
}: ViewerSelectorProps) {
    const [currentViewer, setCurrentViewer] = useState(viewer)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        setLoading(false)
    }, [])

    function getViewer() {
        if (currentViewer === 'uv') {
            return (
                <div className="uv-viewer">
                    <UniversalViewer
                        manifest={manifest}
                        language={language}
                        style={{height: 800}}
                    />
                </div>
            )
        }
        return (
            <div className="mirador-viewer">
                <Mirador manifest={manifest} language={language} />
            </div>
        )
    }

    function onClick(v: 'uv' | 'm') {
        window.location.href = `${window.location.pathname}?viewer=${v}`
    }
    function disabled() {
        return 'disabled'
    }
    if (loading) {
        return <span>Loading....</span>
    }
    return (
        <>
            {getViewer()}
            <fieldset className="fr-segmented fr-my-8v viewers-wrapper">
                <legend className="fr-segmented__legend fr-segmented__legend--inline">
                    {t('See with the viewer:')}&nbsp;
                </legend>
                <div className="fr-segmented__elements" role="group">
                    <div className="fr-segmented__element">
                        <input
                            id="mirador-viewer"
                            value="m"
                            onClick={() => onClick('m')}
                            type="radio"
                            checked={currentViewer === 'm'}
                            role="button"
                            aria-pressed={currentViewer === 'm' ? true : false}
                            aria-label={t('See with Mirador viewer')}
                        />
                        <label className="fr-label" htmlFor="mirador-viewer">
                            {t('Mirador')}
                        </label>
                    </div>
                    <div className="fr-segmented__element">
                        <input
                            id="uv-viewer"
                            value="uv"
                            type="radio"
                            onClick={() => onClick('uv')}
                            aria-label={t('See with UniversalViewer')}
                            role="button"
                            aria-pressed={currentViewer === 'uv' ? true : false}
                            checked={currentViewer === 'uv'}
                        />
                        <label className="fr-label" htmlFor="uv-viewer">
                            {t('UniversalViewer')}
                        </label>
                    </div>
                </div>
            </fieldset>
        </>
    )
}
