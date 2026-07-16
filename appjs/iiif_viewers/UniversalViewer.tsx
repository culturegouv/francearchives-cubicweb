/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2019
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

// Adapted from
// https://github.com/UniversalViewer/universalviewer/wiki/UV-Examples
// https://codesandbox.io/s/uv-nextjs-example-uh9zi

import React, {
    useEffect,
    useMemo,
    useLayoutEffect,
    useRef,
    useState,
} from 'react'
import {IIIFEvents as BaseEvents, init, Viewer} from 'universalviewer'
import 'universalviewer/dist/esm/index.css'

export function useEvent(
    viewer: Viewer | undefined,
    name: string,
    cb: (...args: any[]) => void,
) {
    useLayoutEffect(() => {
        if (viewer) {
            return viewer.on(name, cb)
        }
    }, [viewer])
}

var config1 = {modules: {footerPanel: {options: {downloadEnabled: false}}}}
var config = {options: {footerPanelEnabled: false}}

export function useUniversalViewer(
    ref: React.RefObject<HTMLDivElement>,
    options: any,
    language: string,
) {
    const [uv, setUv] = useState<Viewer>()

    useEffect(() => {
        if (ref.current) {
            const currentUv = init(ref.current, options)

            // this is loading an complete config file for reference
            // to increase loading speed, just use the specific settings you require
            currentUv.on('configure', function ({config, cb}) {
                cb({
                    modules: {footerPanel: {options: {downloadEnabled: false}}},
                })
                if (language === 'fr') {
                    cb(
                        new Promise(function (resolve) {
                            import(
                                'universalviewer/dist/esm/fr-FR-SX32APTS.js'
                            ).then(function (response) {
                                resolve(response)
                            })
                        }),
                    )
                }
            })
            setUv(currentUv)

            return () => {
                currentUv.dispose()
            }
        }
    }, [ref])

    return uv
}

export type UniversalViewerProps = {
    config?: any
    manifest: string
    language: string
    canvasIndex?: number
    onChangeCanvas?: (manifest: string, canvas: string) => void
    onChangeManifest?: (manifest: string) => void
    style?: React.CSSProperties
}

export const UniversalViewer: React.FC<UniversalViewerProps> = React.memo(
    ({manifest, language, canvasIndex, onChangeCanvas, style}) => {
        const ref = useRef<HTMLDivElement>(null)
        const lastIndex = useRef<number>()
        const options = useMemo(
            () => ({
                manifest: manifest,
                canvasIndex: canvasIndex || 0,
            }),
            [],
        )
        const uv = useUniversalViewer(ref, options, language)

        useEffect(() => {
            if (uv && (canvasIndex || canvasIndex === 0)) {
                if (lastIndex.current !== canvasIndex) {
                    //@ts-expect-error TS2341: Property '_assignedContentHandler' is private and only accessible within class 'UniversalViewer'.

                    uv._assignedContentHandler?.publish(
                        BaseEvents.CANVAS_INDEX_CHANGE,
                        canvasIndex,
                    )
                    lastIndex.current = canvasIndex
                }
            }
        }, [canvasIndex, uv])

        useEvent(uv, BaseEvents.CANVAS_INDEX_CHANGE, (i) => {
            if (onChangeCanvas) {
                if (lastIndex.current !== i) {
                    //@ts-expect-error TS2341: Property '_assignedContentHandler' is private and only accessible within class 'UniversalViewer'.
                    const canvas = uv?.extension?.helper.getCanvasByIndex(i)
                    if (canvas) {
                        lastIndex.current = i
                        onChangeCanvas(manifest, canvas.id)
                    }
                }
            }
        })

        return <div className="uv" id="uv" style={style} ref={ref} />
    },
)
