/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2020
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

/* global BASE_URL */

import {each} from 'lodash/collection'

function revealGlossary() {
    const regex = new RegExp(/glossaire#(\d+)/)
    const links = Array.prototype.slice
        .call(document.querySelectorAll('main a'))
        .filter((e) => e.href.includes('/glossaire#'))
    if (links.length) {
        fetch(BASE_URL + '_glossaryterms', {credentials: 'same-origin'})
            .then(function (res) {
                return res.json()
            })
            .then(function (glossary) {
                each(links, (link) => {
                    var match = link.href.match(regex)
                    if (match !== null) {
                        if (glossary[match[1]] !== undefined) {
                            link.id = 'link-' + match[1]
                            link.target = '_blank'
                            link.classList.add('fr-link')
                            link.setAttribute(
                                'aria-describedby',
                                'tooltip-' + match[1],
                            )
                            const span =
                                '<span class="fr-tooltip fr-placement" id="tooltip-' +
                                match[1] +
                                '" role="tooltip" aria-hidden="true">' +
                                glossary[match[1]] +
                                '</span>'
                            link.insertAdjacentHTML('afterend', span)
                        } else {
                            // dead link
                            link.href = '#'
                            link.classList.add('dead-link')
                        }
                    }
                })
            })
    }
}

document.addEventListener('DOMContentLoaded', () => revealGlossary())
