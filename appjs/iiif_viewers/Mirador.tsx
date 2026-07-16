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

import React from 'react'
import miradorDownloadPlugins from '@biblissima/mirador-dl-plugin'
import {miradorImageToolsPlugin} from '@biblissima/mirador-image-tools'

import MiradorViewer from 'mirador'

const miradorId = 'mirador-container'

export function Mirador({
    manifest,
    language,
}: {
    manifest: string
    language?: string
}) {
    React.useLayoutEffect(() => {
        const config = {
            id: miradorId, // id selector where Mirador should be instantiate
            language: language,
            selectedTheme: 'dark',
            themes: {
                dark: {
                    palette: {
                        type: 'dark',
                        primary: {
                            main: '#09669d',
                        },
                        secondary: {
                            main: '#40e014',
                        },
                    },
                },
            },
            workspace: {
                showZoomControls: true, // Configure if zoom controls should be displayed by default
            },
            miradorDownloadPlugin: {
                restrictDownloadOnSizeDefinition: true,
            },
            windows: [
                {
                    allowClose: false,
                    allowFullscreen: true,
                    imageToolsEnabled: true,
                    imageToolsOpen: true,
                    loadedManifest: manifest,
                },
            ],
        }

        let miradorViewer = MiradorViewer.viewer(config, [
            ...miradorImageToolsPlugin,
        ])
    }, [])
    return <div id={miradorId} />
}
