/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2024
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

import {createRoot} from 'react-dom/client'
import {createPortal} from 'react-dom'
import React, {useEffect, useState} from 'react'
import {ButtonsGroup} from '@codegouvfr/react-dsfr/ButtonsGroup'
import {translate as t} from './translate'
import {createModal} from '@codegouvfr/react-dsfr/Modal'
import {startReactDsfr} from '@codegouvfr/react-dsfr/spa'
import {fr} from '@codegouvfr/react-dsfr'
startReactDsfr({defaultColorScheme: 'light'})

const faContextModal = createModal({
    isOpenedByDefault: false,
    id: 'fa-context-modal',
})

interface ContextTreeNode {
    type: 'FAComponent' | 'FindingAid'
    stableId: string
    title: string
    children: ContextTreeNode[]
}

interface ContextTreeProps {
    nodes: ContextTreeNode[]
    selectedId: string
    level: number
    lang: string | undefined
}

declare global {
    interface Window {
        BASE_URL: string
    }
}

function nodeUrl(node: ContextTreeNode): string {
    if (node.type === 'FindingAid') {
        return `${window.BASE_URL}/findingaid/${node.stableId}`
    }
    return `${window.BASE_URL}/facomponent/${node.stableId}`
}

function ContextTree({nodes, selectedId, level, lang}: ContextTreeProps) {
    function childrenTree(node: ContextTreeNode) {
        const childrenCount = node.children.length
        if (childrenCount === 0) {
            return null
        }
        level = level + 1
        return (
            <li>
                <ContextTree
                    nodes={node.children}
                    selectedId={selectedId}
                    level={level}
                    lang={lang}
                />
            </li>
        )
    }

    function title(node: ContextTreeNode) {
        if (node.stableId === selectedId) {
            return (
                <span className="detailed-path-list-item-active" lang={lang}>
                    {node.title}
                </span>
            )
        }
        return (
            <a href={nodeUrl(node)}>
                <span lang={lang}>{node.title}</span>
            </a>
        )
    }
    function isLast(idx: number) {
        return idx === nodes.length - 1
    }

    return (
        <ul className={`detailed-path-list${level != 1 ? '' : '-root'}`}>
            {nodes.map((node, idx) => (
                <>
                    <li>
                        <p
                            className={`detailed-path-list-item${
                                isLast(idx) ? '-last' : ''
                            }`}
                        >
                            {title(node)}
                        </p>
                    </li>
                    {childrenTree(node)}
                </>
            ))}
        </ul>
    )
}

function loadContextTree(
    entityType: 'FindingAid' | 'FAComponent',
    stableId: string,
    lang: string | undefined,
): Promise<ContextTreeNode[]> {
    return fetch(`/facontext-data/${entityType}/${stableId}`, {
        credentials: 'same-origin',
    })
        .then((response) => response.json())
        .then((tree) => {
            return Promise.resolve([tree])
        })
}

interface FAContextProps {
    entityType: 'FindingAid' | 'FAComponent'
    stableId: string
    elementCount: string
    lang: string | undefined
}

const FAContextTitle = () => (
    <>
        <span
            aria-hidden="true"
            className={fr.cx('fr-icon-arrow-right-line', 'fr-icon--lg')}
        ></span>
        {t('Description context:')}
    </>
)

function FAContext({
    entityType: type,
    stableId,
    elementCount,
    lang,
}: FAContextProps) {
    const [tree, setTree] = useState<ContextTreeNode[] | null>(null)
    useEffect(() => {
        loadContextTree(type, stableId, lang).then(setTree)
    }, [type, stableId, elementCount])
    return (
        <>
            {createPortal(
                <faContextModal.Component
                    className="fa-context-modal"
                    title={<FAContextTitle />}
                >
                    {tree && (
                        <nav className="detailed-path-inner-levels">
                            <ContextTree
                                nodes={tree}
                                selectedId={stableId}
                                level={1}
                                lang={lang}
                            />
                        </nav>
                    )}
                </faContextModal.Component>,
                document.body,
            )}
            <div className="detailed-path-list-item">
                {' '}
                <p className="detailed-path-list-item--button">
                    <span>...</span>
                    <ButtonsGroup
                        buttonsSize="small"
                        buttons={[
                            {
                                onClick: () => faContextModal.open(),
                                disabled: tree === null,
                                iconId:
                                    tree === null
                                        ? 'fr-icon-refresh-line'
                                        : undefined,
                                children: t(
                                    'Display the context with all {0} elements',
                                    elementCount,
                                ),
                            },
                        ]}
                    />
                </p>
            </div>
        </>
    )
}

const contextContainer = document.getElementById('fa-context-container')
if (contextContainer !== null) {
    const stableId = contextContainer.dataset.faContextStableId
    const entityType = contextContainer.dataset.faContextEntityType
    const elementCount = contextContainer.dataset.faContextElementCount
    const lang = contextContainer.dataset.lang
    const root = createRoot(contextContainer)
    if (
        stableId != null &&
        elementCount != null &&
        entityType != null &&
        ['FAComponent', 'FindingAid'].includes(entityType)
    ) {
        root.render(
            <FAContext
                entityType={entityType as 'FAComponent' | 'FindingAid'}
                stableId={stableId}
                elementCount={elementCount}
                lang={lang}
            />,
        )
    }
} else {
    console.error("Document 'fa-context-container' not found")
}
