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

/* global $ BASE_URL $ */

const choiceKey = 'FASiteSearchCategory'
const hideAlertKey = 'hFAa'

function setupTypeAhead() {
    typeof $.typeahead === 'function' &&
        $.typeahead({
            input: '#norql',
            minLength: 1,
            maxItem: 30,
            hint: true,
            cache: false,
            matcher: true,
            group: 'etype',
            filter: false, // data is already filtered by elasticsearch
            accent: {
                from: 'ãàáäâẽèéëêìíïîõòóöôùúüûñç',
                to: 'aaaaaeeeeeiiiiooooouuuunc',
            },
            display: ['text', 'etype'],
            resultContainer: 'div.typeahead__result',
            template:
                "<span class='link'>{{text}}</span> - <small>{{countlabel}}</small>",
            dynamic: true,
            source: {
                ajax: {
                    type: 'GET',
                    url: BASE_URL + '_suggest',
                    data: {
                        q: '{{query}}',
                        escategory: window.localStorage[choiceKey],
                    },
                },
            },
            callback: {
                // Redirect to url after clicking or pressing enter
                onClickAfter: function (node, a, item) {
                    window.location.href = item.url // Set window location to site url
                },
            },
        })
}

function toggleCategoryChoice(category) {
    const currentChoice = window.localStorage[choiceKey]
    if (currentChoice.includes(category)) {
        window.localStorage[choiceKey] = currentChoice.replace(category, '')
    } else {
        window.localStorage[choiceKey] += category
    }
    setupTypeAhead()
}

function setupAlert() {
    const container = document.querySelector('#fa-alert-container')
    if (container === null) {
        return
    }
    let hash = container.dataset['alertid']
    if (hash === null && hash === 'unknown') {
        return
    }
    if (
        hideAlertKey in window.localStorage &&
        window.localStorage[hideAlertKey] === hash
    ) {
        return
    }
    container.classList.remove('fr-hidden')
    const alertBtn = document.querySelector('#alert-close-button')
    alertBtn.onclick = function () {
        container.parentNode.removeChild(container)
        window.localStorage[hideAlertKey] = hash
    }
}

function setupSearchBarForm() {
    const searchBarForm = document.querySelector('#header-search-bar-form')
    if (searchBarForm === null) {
        return
    }

    // Initialize localStorage values
    if (!(choiceKey in window.localStorage)) {
        window.localStorage[choiceKey] = 'archivessiteres'
    }

    // Check values from localStorage state
    if (window.localStorage[choiceKey].includes('archives')) {
        searchBarForm.rb1.checked = true
    }
    if (window.localStorage[choiceKey].includes('siteres')) {
        searchBarForm.rb2.checked = true
    }
    // Change localStorage onClik
    searchBarForm.rb1.onclick = function () {
        toggleCategoryChoice('archives')
    }

    searchBarForm.rb2.onclick = function () {
        toggleCategoryChoice('siteres')
    }

    searchBarForm.rb1.addEventListener('focus', function () {
        $('#rbm1').addClass('focused')
    })

    searchBarForm.rb1.addEventListener('blur', function () {
        $('#rbm1').removeClass('focused')
    })

    searchBarForm.rb2.addEventListener('focus', function () {
        $('#rbm2').addClass('focused')
    })

    searchBarForm.rb2.addEventListener('blur', function () {
        $('#rbm2').removeClass('focused')
    })
}

function setupDropDown() {
    $('.fa-dropdown').change(function () {
        if (this.value) {
            window.location.href = this.value
        }
    })
}

function setupDownloadDropDown() {
    $('.fa-download-dropdown').change(function () {
        if (this.value) {
            let link = document.querySelector('#' + this.value)
            if (link === null) {
                console.error('Could not find "' + this.value + '" link')
            }
            link.click()
        }
    })
}

function loadSearchfunctions() {
    setupTypeAhead()
    setupSearchBarForm()
    setupDropDown()
    setupDownloadDropDown()
    setupAlert()
}

document.addEventListener('DOMContentLoaded', () => loadSearchfunctions())
