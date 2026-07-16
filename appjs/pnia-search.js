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

/* global $ */

function checkPageInput(suffix) {
    var $form = $('#page-number-input-form' + suffix)
    var $input = $form.find('#page-number-input' + suffix)
    var value = parseInt($input.val())
    var pageNumber = $input.attr('max')
    var $pagegroup = $form.find('#page-number-error-group' + suffix)
    var $error = $form.find('#page-number-message' + suffix)
    $pagegroup.removeClass('fr-input-group--error')
    $error.addClass('fr-hidden').attr('aria-hidden', 'true')
    if (isNaN(value) || value > parseInt(pageNumber)) {
        $pagegroup.addClass('fr-input-group--error')
        $error.removeClass('fr-hidden').attr('aria-hidden', 'false')
        $input.attr('aria-describedby', $error)
        return false
    }
    $form.submit()
}

function setUpPageNumberInput(suffix) {
    var form = document.querySelector('#page-number-input-form' + suffix)
    if (form !== null) {
        form.addEventListener('submit', function (e) {
            if (!checkPageInput(suffix)) {
                e = e || window.event
                if (e.preventDefault) {
                    e.preventDefault()
                } else {
                    e.returnValue = false
                }
                return false
            }
        })
        $('#page-number-input' + suffix).bind('blur', function () {
            $('#page-number-error-group' + suffix).removeClass(
                'fr-input-group--error',
            )
            $('#page-number-message' + suffix)
                .addClass('fr-hidden')
                .attr('aria-hidden', 'true')
        })
    }
}

function checkDateRange() {
    var $form = $('#date-facet')
    var $mininput = $form.find('#date-min-input')
    var minvalue = parseInt($mininput.val())
    var $maxinput = $form.find('#date-max-input')
    var maxvalue = parseInt($maxinput.val())
    var $maxinputgroup = $form.find('#date-facet-fieldset')
    var $error = $form.find('#date-facet-message')
    $maxinputgroup.removeClass('fr-fieldset--error')

    if (minvalue && maxvalue) {
        if (minvalue > maxvalue) {
            $maxinputgroup.addClass('fr-fieldset--error')
            $error.removeClass('fr-hidden').attr('aria-hidden', 'false')
            $maxinput.attr('aria-describedby', 'date-facet-message-error')
            return false
        }
    }
    $form.submit()
}

function setUpDateMaxInput() {
    const form = document.querySelector('#date-facet')
    if (form !== null) {
        form.addEventListener('submit', function (e) {
            if (!checkDateRange()) {
                e = e || window.event
                if (e.preventDefault) {
                    e.preventDefault()
                } else {
                    e.returnValue = false
                }
                return false
            }
        })
        const $fieldset = $('#date-facet-fieldset')
        var $error = $('#date-facet-message')
        $('#date-max-input').bind('focus', function () {
            $fieldset.removeClass('fr-fieldset--error')
            $error.addClass('fr-hidden').attr('aria-hidden', 'true')
        })
        $('#date-min-input').bind('focus', function () {
            $fieldset.removeClass('fr-fieldset--error')
            $error.addClass('fr-hidden').attr('aria-hidden', 'true')
        })
    }
}

function setupFacetsOptions() {
    $('.fr-facet-values').ready(function () {
        const facets = $('.fr-facet-values')
        for (const elem of facets) {
            const searchBar = $(elem).find('.facet-search-bar')[0]
            const input = $(searchBar).find('input')[0]
            const noResultElement = $(elem).find('.fr-facet-empty')[0]
            const listElements = $(elem).find('li')

            // Search fields are hidden by default and only shown if necessary
            if (listElements.length > 10) {
                $(searchBar).css('display', 'flex')
            }
            // Listen to input change and filter elements
            $(input).on('input', function (e) {
                const value = e.target.value
                filterFacets(listElements, noResultElement, value)
            })

            // Focus the first visible search result for keyboard navigation
            $(searchBar).on('submit', function (e) {
                e.preventDefault()
                const visibleItems = $(listElements).filter(function () {
                    return $(this).css('display') !== 'none'
                })
                if (visibleItems[0]) {
                    $(visibleItems[0]).find('a')[0].focus()
                }
            })
            // Filter on load
            filterFacets(listElements, noResultElement, input.value)
        }
    })

    function cleanUpText(original) {
        // Clean up accents
        return original
            .toLocaleLowerCase()
            .normalize('NFD')
            .replace(/\p{Diacritic}/gu, '')
    }

    function filterFacets(listElements, noResultElement, value) {
        let hasResults = false
        for (const li of listElements) {
            const link = $(li).find('a')[0]
            const text = $(link).text()
            if (cleanUpText(text).includes(cleanUpText(value))) {
                hasResults = true
                $(li).css('display', 'flex')
            } else {
                $(li).css('display', 'none')
            }
        }
        if (!hasResults) {
            $(noResultElement).css('display', 'block')
        } else {
            $(noResultElement).css('display', 'none')
        }
    }
}

function setupCSVExportLoading() {
    const csvExportBtn = document.querySelector('#csv-export-btn')

    if (csvExportBtn) {
        csvExportBtn.addEventListener('click', async function (e) {
            e.preventDefault()

            // Check if button is disabled (too many results)
            if (this.hasAttribute('disabled')) {
                return false
            }

            const isLoading = this.getAttribute('data-loading') === 'true'
            if (isLoading) {
                return false
            }

            const url = this.getAttribute('data-csv-url')
            const filename = this.getAttribute('data-csv-filename')

            if (!url || !filename) {
                console.error('CSV export: missing url or filename')
                return false
            }

            setLoadingState(this, true)

            try {
                const response = await fetch(url)

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`)
                }

                const blob = await response.blob()
                const downloadUrl = window.URL.createObjectURL(blob)

                const a = document.createElement('a')
                a.href = downloadUrl
                a.download = filename
                a.style.display = 'none'
                document.body.appendChild(a)
                a.click()

                document.body.removeChild(a)
                window.URL.revokeObjectURL(downloadUrl)

                setLoadingState(this, false)
            } catch (error) {
                console.error('CSV export error:', error)
                setLoadingState(this, false)
            }
        })
    }

    function setLoadingState(btn, isLoading) {
        btn.setAttribute('data-loading', isLoading.toString())
        btn.setAttribute('aria-busy', isLoading.toString())

        const contentSpan = btn.querySelector('.csv-export-content')
        const loaderSpan = btn.querySelector('.csv-export-loader')

        if (contentSpan && loaderSpan) {
            if (isLoading) {
                contentSpan.classList.add('fr-hidden')
                loaderSpan.classList.remove('fr-hidden')
            } else {
                contentSpan.classList.remove('fr-hidden')
                loaderSpan.classList.add('fr-hidden')
            }
        }
    }
}

function loadSearchfunctions() {
    setupFacetsOptions()
    setUpDateMaxInput()
    setUpPageNumberInput('-full')
    setUpPageNumberInput('')
    setupCSVExportLoading()
}

document.addEventListener('DOMContentLoaded', () => loadSearchfunctions())
