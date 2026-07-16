/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2019
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

/* global $, L, BASE_URL */

import {GestureHandling} from 'leaflet-gesture-handling'

import 'leaflet-gesture-handling/dist/leaflet-gesture-handling.css'
L.Map.addInitHook('addHandler', 'gestureHandling', GestureHandling)

const goldenIcon = L.divIcon({
    iconAnchor: [0, 24],
    labelAnchor: [-6, 0],
    popupAnchor: [0, -36],
    html: `<span class="golden-marker" />`,
})

const blueIcon = L.divIcon({
    iconAnchor: [0, 24],
    labelAnchor: [-6, 0],
    popupAnchor: [0, -36],
    html: `<span class="blue-marker" />`,
})

let markerInfo

let servicesData

let servicesOverlays = {}

let selectedService
let serviceEid // PrimaryView service eid

let sidebarControl

let servicesCount = {}

L.Control.Layers.include({
    _layerControlInputsMap: {},

    buildServicesControlInputsMap: function () {
        const inputs = this._layerControlInputs
        for (let i = 0; i < inputs.length; i++) {
            this._layerControlInputsMap[
                L.Util.trim(inputs[i].nextSibling.textContent)
            ] = inputs[i]
        }
    },

    getOverlays: function (visibility) {
        let layers = {}
        const control = this
        this._layers.forEach(function (obj) {
            // check if layer is an overlay
            if (obj.overlay) {
                if (
                    visibility === undefined ||
                    control._map.hasLayer(obj.layer) === visibility
                )
                    return (layers[obj.name] = obj.layer)
            }
        })
        return layers
    },

    toggleLayoutDisabled: function (title, disabled) {
        const input = this._layerControlInputsMap[title]
        if (input === undefined) {
            console.error(
                'toggleLayoutDisabled: input not found for "' + title + '"',
            )
            return
        }
        if (input.disabled !== disabled) {
            input.disabled = disabled
            if (disabled) L.DomUtil.setOpacity(input.nextSibling, 0.5)
            else L.DomUtil.setOpacity(input.nextSibling, 1)
        }
    },

    updateServiceCount: function (title, counts) {
        var input = this._layerControlInputsMap[title]
        if (input === undefined) {
            console.error(
                'updateServiceCount: input not found for "' + title + '"',
            )
            return
        }
        const span = input.nextSibling
        const count = counts['0'] + counts['1']
        title = ' ' + title
        if (count > 0) {
            title += ' (' + count + ')'
        }
        span.innerHTML = title
    },

    updateServicesCount: function (servicesCount) {
        for (const [title, counts] of Object.entries(servicesCount)) {
            this.updateServiceCount(title, counts)
        }
    },
})

L.Control.AllServices = L.Control.extend({
    options: {
        collapsed: false,
        position: 'topleft',
    },

    initialize: function (options /*{ data: {...}  }*/) {
        // constructor
        L.Util.setOptions(this, options)
    },

    _labels: {},
    setLabels: function (labels) {
        this._labels = labels
    },

    _input: null,
    getAllServicesCheckbox: function () {
        return this._input
    },

    onAdd: function () {
        this._initLayout()

        return this._container
    },

    _initLayout: function () {
        let container = (this._container = L.DomUtil.create(
            'div',
            'leaflet-control-layers leaflet-control-layers-expanded leaflet-control leaflet-all-services-control',
        ))
        const overlays = L.DomUtil.create(
            'div',
            'leaflet-control-layers-overlays',
            container,
        )
        let input = (this._input = L.DomUtil.create(
            'input',
            'leaflet-control-layers-selector',
            overlays,
        ))
        input.type = 'checkbox'
        input.id = 'all-services'
        input.checked = true
        const span = L.DomUtil.create('label', '', overlays)
        span.innerHTML += ' ' + this._labels.allTitle
        span.setAttribute('for', input.id)
        L.DomEvent.disableClickPropagation(container)
        return container
    },
})

L.control.allServices = function (id, options) {
    return new L.Control.AllServices(id, options)
}

L.Control.Partners = L.Control.extend({
    options: {
        collapsed: false,
        position: 'topleft',
    },

    initialize: function (options /*{ data: {...}  }*/) {
        // constructor
        L.Util.setOptions(this, options)
    },

    onAdd: function () {
        this._initLayout()

        return this._container
    },

    _layerControlInputsMap: {},

    _labels: {},
    setLabels: function (labels) {
        this._labels = labels
    },

    _partnersFilter: '01',
    getPartnersFilter: function () {
        return this._partnersFilter
    },

    _availableOptions: new Set(), // all available options for a particular dataset
    addAvailablePartnersOption: function (option) {
        if (!'01'.includes(option)) {
            console.error(
                'addAvailablePartnersOption: try to add an invalid option ' +
                    option +
                    ' to partners',
            )
        } else {
            this._availableOptions.add(option)
        }
    },

    arePartnersAvailable: function () {
        return this._availableOptions.has('1')
    },

    _selectedServices: {0: new Set(), 1: new Set([])},
    updateSelectedServices: function (option, title, action) {
        if (!'01'.includes(option)) {
            console.error(
                'addAvailablePartnersOption: try to add an invalid option ' +
                    option +
                    ' to partners',
            )
            return
        }
        let layers = this._selectedServices[option]
        if (layers.has(title)) {
            if (action === 'remove') layers.delete(title)
        } else {
            if (action === 'add') layers.add(title)
        }
        this._selectedServices[option] = layers
    },

    toggleLayoutDisabled: function (title, action, options) {
        const control = this
        var updated = ''
        options.forEach(function (option) {
            control.updateSelectedServices(option, title, action)
            updated += option
        })
        const data = this._selectedServices
        for (const input of Object.values(this._layerControlInputsMap)) {
            if (updated.includes(input.value)) {
                const values = data[input.value]
                let disabled
                if (action === 'remove') {
                    disabled = values.size === 0
                }
                if (action === 'add') {
                    disabled = false
                }
                input.disabled = disabled
                if (disabled) L.DomUtil.setOpacity(input.nextSibling, 0.5)
                else L.DomUtil.setOpacity(input.nextSibling, 1)
            }
        }
    },

    updateServicesCount: function (servicesCount) {
        var values = {0: 0, 1: 0}
        for (const counts of Object.values(servicesCount)) {
            for (const [option, count] of Object.entries(counts)) {
                values[option] += count
            }
        }
        for (const [title, input] of Object.entries(
            this._layerControlInputsMap,
        )) {
            const span = input.nextSibling
            const count = values[input.value]
            span.innerHTML = ' ' + title
            if (count > 0) span.innerHTML += ' (' + count + ')'
        }
    },

    _reloadServices: null,
    initReloadServices: function (func) {
        this._reloadServices = func
    },

    reloadServices: function () {
        if (this._reloadServices !== null) {
            this._reloadServices()
        }
    },

    _initLayout: function () {
        let container = (this._container = L.DomUtil.create(
            'div',
            'leaflet-control-layers leaflet-control-layers-expanded leaflet-control leaflet-partners-control ',
        ))
        // ADD partners as argument fo populate
        L.DomEvent.disableClickPropagation(container)
        this._addInput(container, 'partners', this._labels.partners, '1')
        //this._addInput(container, 'nopartners', this._labels.nopartners, '0')
        return container
    },

    _addInput: function (container, id, label, value) {
        const overlays = L.DomUtil.create(
            'div',
            'leaflet-control-layers-overlays',
            container,
        )
        const input = L.DomUtil.create(
            'input',
            'leaflet-control-layers-selector',
            overlays,
        )
        input.type = 'checkbox'
        input.id = id
        input.value = value
        //input.checked = this._selectedServices[value].size > 0
        L.DomEvent.on(input, 'change', this.inputSelected, this)
        this._layerControlInputsMap[label] = input
        const span = L.DomUtil.create('label', '', overlays)
        span.innerHTML += ' ' + label
        span.setAttribute('for', input.id)
        if (!this._availableOptions.has(value)) {
            input.disabled = true
            L.DomUtil.setOpacity(input.nextSibling, 0.5)
        }
    },

    inputSelected: function (ev) {
        L.DomEvent.preventDefault(ev)
        const elem = ev.target
        elem.checked
            ? (this._partnersFilter = elem.value)
            : (this._partnersFilter = '01')
        this.reloadServices()
    },

    onRemove: function () {
        for (const input of Object.values(this._layerControlInputsMap)) {
            L.DomEvent.off(input)
        }
    },
})

L.control.partners = function (id, options) {
    return new L.Control.Partners(id, options)
}

L.Control.Sidebar.include({
    prepareServicesTabContent: function () {
        const $sidebar = $(this.getContainer())
        if (selectedService) {
            $sidebar.find('.leaflet-sidebar-empty-data').addClass('fr-hidden')
            $sidebar
                .find('.leaflet-sidebar-pane-services')
                .removeClass('fr-hidden')
        } else {
            $sidebar
                .find('.leaflet-sidebar-empty-data')
                .removeClass('fr-hidden')
            $sidebar
                .find('.leaflet-sidebar-pane-services')
                .addClass('fr-hidden')
        }
    },
})

function getZoom(dpt) {
    if (dpt === undefined || dpt === null) return 2.5
    return dpt < 900 ? 7 : dpt === 93 ? 10 : dpt === 973 ? 8 : 9
}

function buildMap() {
    const mapElement = document.querySelector('#services-dpt-map')
    if (mapElement === null) {
        return
    }
    // build map
    serviceEid = mapElement.dataset.zoom

    const selectedDepartment = (function () {
        var m = /annuaire\/departements\/(\d+[AB]?)/.exec(
            document.location.pathname,
        )
        if (m !== null) {
            return m[1]
        }
        m = /\?dpt=(\d+[AB]?)/.exec(document.location.search)
        if (m !== null) {
            return m[1]
        }
        return null
    })()

    $('select[name="dpt"]').change(function () {
        let dpt = $(this).val()
        let dptUrl = BASE_URL + 'annuaire/departements'
        if (dpt !== '00') dptUrl += '?dpt=' + $(this).val()
        document.location.href = dptUrl
    })

    const map = createMap('services-dpt-map')

    map.on({
        dblclick: function (e) {
            map.fitBounds(e.target.getBounds())
            map.setView(e.target.getBounds().getCenter())
            return false
        },
    })

    function createMap(divId) {
        const dptLines = {
                fillColor: '#efefef',
                weight: 2,
                opacity: 1,
                color: '#ccc',
                dashArray: '3',
                fillOpacity: 0.25,
            },
            selectedDepartmentLines = {
                color: 'white',
                weight: 3,
                fill: true,
                opacity: 1,
                fillColor: '#999',
            }

        let center = null,
            zoom = null,
            latitude = null,
            longitude = null

        const $elt = $('#selector-geo-dpt').children(':selected')
        if (selectedDepartment && $elt.val() === selectedDepartment) {
            zoom = getZoom(selectedDepartment)
            latitude = $elt.data('lat')
            longitude = $elt.data('long')
            if (latitude !== 'None' && longitude !== 'None') {
                center = new L.LatLng(latitude, longitude)
            }
        }
        if (center === null) {
            center = new L.LatLng(45.070312, 7.6868565) // world
            zoom = 2
        }
        const map = L.map(divId, {
            center: center,
            zoom: zoom,
            maxZoom: 18,
            tileSize: 512,
            zoomOffset: -1,
            zoomControl: false,
            cluster: false,
            gestureHandling: true,
        })

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution:
                '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(map)

        function highlightFeature(e) {
            const layer = e.target
            layer.setStyle(selectedDepartmentLines)
            if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
                layer.bringToFront()
            }
        }

        let geojson

        function resetHighlightFeature(e) {
            geojson.resetStyle(e.target)
        }

        function clickFeature(e) {
            document.location.href =
                BASE_URL +
                'annuaire/departements?dpt=' +
                e.target.feature.properties.code
        }

        function onEachFeature(feature, layer) {
            // does this feature have a property named popupContent

            layer.on({
                mouseover: highlightFeature,
                mouseout: resetHighlightFeature,
                click: clickFeature,
            })
            layer.bindTooltip(
                '<p>' +
                    feature.properties.nom +
                    ' - ' +
                    feature.properties.code +
                    '</p>',
                {opacity: 1},
            )
            if (selectedDepartment === feature.properties.code) {
                layer.setStyle(selectedDepartmentLines)
            }
        }
        $.getJSON(mapElement.dataset.jsondata, function (data) {
            // add GeoJSON layer to the map once the file is loaded
            geojson = L.geoJson(data.features, {
                style: dptLines,
                onEachFeature: onEachFeature,
            }).addTo(map)
        })
        return map
    }

    // initialize controls
    L.Control.zoomHome().addTo(map)

    const allServicesControl = L.control.allServices()

    const servicesControl = L.control.layers(null, [], {
        collapsed: false,
        position: 'topleft',
    })

    const partnersControl = L.control.partners()

    sidebarControl = L.control
        .sidebar({
            container: 'services-dpt-sidebar',
            position: 'right',
            closeButton: true,
        })
        .addTo(map)

    sidebarControl.on('content', function (ev) {
        switch (ev.id) {
            case 'services':
                this.prepareServicesTabContent()
                break
        }
    })

    function updateSidebarServiceTab(feature) {
        const $sidebar = $(sidebarControl.getContainer())
        $sidebar.find('.service').html(feature.properties.name)
        if (feature.properties.contact_name === null) {
            $sidebar.find('li.contact').addClass('fr-hidden')
        } else {
            $sidebar
                .find('li.contact .contact-label')
                .html(feature.properties.contact_label)
            $sidebar
                .find('li.contact span')
                .html(feature.properties.contact_name)
            $sidebar.find('li.contact').removeClass('fr-hidden')
        }
        if (feature.properties.phone_number === null) {
            $sidebar.find('li.phone').addClass('fr-hidden')
        } else {
            $sidebar.find('li.phone span').html(feature.properties.phone_number)
            $sidebar.find('li.phone').removeClass('fr-hidden')
        }
        if (feature.properties.opening_period === null) {
            $sidebar.find('li.opening_period').addClass('fr-hidden')
        } else {
            $sidebar
                .find('li.opening_period span')
                .html(feature.properties.opening_period)
            $sidebar.find('li.opening_period').removeClass('fr-hidden')
        }
        if (feature.properties.address === null) {
            $sidebar.find('li.address').addClass('fr-hidden')
        } else {
            $sidebar.find('li.address span').html(feature.properties.address)
            $sidebar.find('li.address').removeClass('fr-hidden')
        }
        if (feature.properties.mailing_address === null) {
            $sidebar.find('li.mailing_address').addClass('fr-hidden')
        } else {
            $sidebar
                .find('li.mailing_address span')
                .html(feature.properties.mailing_address)
            $sidebar.find('li.mailing_address').removeClass('fr-hidden')
        }
        if (feature.properties.email === null) {
            $sidebar.find('li.email').addClass('fr-hidden')
        } else {
            $sidebar
                .find('li.email span')
                .html(
                    '<a href="mailto:' +
                        feature.properties.email +
                        '"  target="_blank" rel="nofollow noopener noreferrer">' +
                        feature.properties.email +
                        '</a>',
                )
            $sidebar.find('li.email').removeClass('fr-hidden')
        }
        if (feature.properties.annual_closure === null) {
            $sidebar.find('li.annual_closure').addClass('fr-hidden')
        } else {
            $sidebar
                .find('li.annual_closure span')
                .html(feature.properties.annual_closure)
            $sidebar.find('li.annual_closure').removeClass('fr-hidden')
        }
        const website = feature.properties.website
        if (website === null) {
            $sidebar.find('li.website').addClass('fr-hidden')
        } else {
            $sidebar
                .find('li.website span')
                .html(
                    '<a href="' +
                        website +
                        '" target="_blank" rel="nofollow noopener noreferrer">' +
                        website +
                        '</a><i class="fa fa-external-link"></i>',
                )
            $sidebar.find('li.website').removeClass('fr-hidden')
        }
        if (feature.properties.code_insee === null) {
            $sidebar.find('li.code_insee').addClass('fr-hidden')
        } else {
            $sidebar
                .find('li.code_insee span')
                .html(feature.properties.code_insee)
            $sidebar.find('li.code_insee').removeClass('fr-hidden')
        }
        $sidebar
            .find('li.gps span')
            .html(
                feature.properties.latitude +
                    ', ' +
                    feature.properties.longitude,
            )
        const sn = feature.properties.service_social_network
        if (sn.length > 0) {
            let network = []
            sn.forEach(function (data) {
                network.push(
                    '<span class="text-nowrap"><a href="' +
                        data[1] +
                        '" target="_blank" rel="nofollow noopener noreferrer">' +
                        data[0] +
                        '</a><i class="fa fa-external-link"></i></span>',
                )
            })
            $sidebar.find('li.social_network span').html(network.join(', '))
            $sidebar.find('li.social_network').removeClass('fr-hidden')
        } else {
            $sidebar.find('li.social_network').addClass('fr-hidden')
        }
        if (feature.properties.ead === '1') {
            $sidebar
                .find('.fi-link a')
                .prop(
                    'href',
                    BASE_URL + 'inventaires/' + feature.properties.code,
                )
                .removeClass('fr-hidden')
        } else {
            $sidebar.find('.fi-link').addClass('fr-hidden')
        }
        if (feature.properties.nomina === '1') {
            $sidebar
                .find('.nomina-link a')
                .prop(
                    'href',
                    BASE_URL + 'basedenoms/service/' + feature.properties.code,
                )
                .removeClass('fr-hidden')
        } else {
            $sidebar.find('.nomina-link').addClass('fr-hidden')
        }
        sidebarControl.open('services')
    }

    function initServiceLayout(feature, layer) {
        layer.bindPopup(
            '<p><b>' +
                feature.properties.name +
                '</b><p><i>' +
                markerInfo +
                '</i></p></p>',
        )
        layer.on('mouseover', function () {
            this.openPopup()
        })
        layer.on('mouseout', function () {
            this.closePopup()
        })
        layer.on('dblclick', function (e) {
            map.setView(e.latlng, 19)
            selectedService = feature.properties.eid
            updateSidebarServiceTab(feature)
        })
        layer.on('click', function () {
            sidebarControl.close()
        })
    }

    function updateService(data, title, category, cluster) {
        let partnersOptions = new Set()
        // partnersOptions hold values for partnersControl checkboxes
        data = data[category] !== undefined ? data[category] : []
        if (data.length === 0) {
            return {cluster: cluster, add: false, options: partnersOptions}
        }
        let serviceCount = {0: 0, 1: 0}
        const partnersFilter = partnersControl.getPartnersFilter()
        const icon = category === 'D' ? blueIcon : goldenIcon
        const service = L.geoJson(null, {
            pointToLayer: function (feature, latlng) {
                if (
                    feature.properties.category === category &&
                    partnersFilter.includes(feature.properties.partner)
                ) {
                    if (map.hasLayer(cluster)) {
                        serviceCount[feature.properties.partner] += 1
                    }
                    partnersOptions.add(feature.properties.partner)
                    return L.marker(latlng, {icon: icon}, {opacity: 1})
                }
            },

            onEachFeature: function (feature, layer) {
                initServiceLayout(feature, layer)
            },
        })
        cluster.clearLayers()
        service.addData(data)
        cluster.addLayer(service)
        servicesCount[title] = serviceCount

        return {
            cluster: cluster,
            add: true,
            options: partnersOptions,
        }
    }

    function addService(data, title, category) {
        data = data[category] !== undefined ? data[category] : []
        if (data.length === 0) {
            return
        }
        let serviceCount = {0: 0, 1: 0}
        const icon = category === 'D' ? blueIcon : goldenIcon
        const service = L.geoJson(null, {
            pointToLayer: function (feature, latlng) {
                if (feature.properties.category === category) {
                    serviceCount[feature.properties.partner] += 1
                    if (
                        !selectedService &&
                        serviceEid &&
                        feature.properties.eid === serviceEid
                    ) {
                        // display service information
                        selectedService = serviceEid
                        updateSidebarServiceTab(feature)
                        // zoom to it
                        map.setView(latlng, 19)
                    }
                    return L.marker(latlng, {icon: icon}, {opacity: 1})
                }
            },

            onEachFeature: function (feature, layer) {
                initServiceLayout(feature, layer)
            },
        })
        const cluster = new L.MarkerClusterGroup({
            polygonOptions: {
                color: '#ffffff',
                opacity: 0.4,
                stroke: false,
            },
        })
        service.addData(data)
        cluster.addLayer(service)
        cluster.addTo(map)

        servicesCount[title] = serviceCount
        for (const [option, count] of Object.entries(serviceCount)) {
            if (count > 0) {
                // create a partners checkbox for each options
                partnersControl.addAvailablePartnersOption(option)
                partnersControl.updateSelectedServices(option, title, 'add')
            }
        }
        servicesControl.addOverlay(cluster, title)
    }

    fetch(mapElement.dataset.markerurl, {credentials: 'same-origin'})
        .then((response) => response.json())
        .then((data) => {
            servicesData = data.data
            markerInfo = data.i18n.markerInfo
            if (servicesData.length === 0) {
                console.error('Fetch: no data found', servicesData)
                return
            }
            addAllServicesControlToMap(data.i18n.services)
            servicesOverlays = data.overlays
            for (const [title, category] of Object.entries(servicesOverlays)) {
                addService(servicesData, title, category)
            }
            if (serviceEid && !selectedService) {
                console.error('Requested service %s is not found', serviceEid)
                // sidebarControl.open('services')
            }
            addServicesControlToMap()
            addPartnersControlToMap(data.i18n.partners)
            handleServicesOverlaysSelection()
            // display the sidebar
            sidebarControl.getContainer().classList.remove('fr-hidden')
        })

    function resetLocation() {
        if (selectedDepartment) {
            map.setZoom(getZoom(selectedDepartment))
        }
        selectedService = null
        sidebarControl.close()
    }

    function reloadService(layerTitle, action) {
        const layer = servicesControl.getOverlays()[layerTitle]
        const result = updateService(
            servicesData,
            layerTitle,
            servicesOverlays[layerTitle],
            layer,
        )
        if (result.add) {
            // change partnersControl options
            partnersControl.toggleLayoutDisabled(
                layerTitle,
                action,
                result.options,
            )
        }
        var counts = servicesCount[layerTitle]
        servicesControl.updateServiceCount(layerTitle, counts)
        partnersControl.updateServicesCount(servicesCount)
        resetLocation()
    }

    function reloadServices() {
        for (const [layerTitle, layer] of Object.entries(
            servicesControl.getOverlays(),
        )) {
            const result = updateService(
                servicesData,
                layerTitle,
                servicesOverlays[layerTitle],
                layer,
            )
            if (result.add) {
                let disable = false
                const partnersFilter = partnersControl.getPartnersFilter()
                if (partnersFilter.length === 0 || result.options.size === 0)
                    disable = true
                else if (
                    partnersFilter.length === 1 &&
                    !result.options.has(partnersFilter)
                )
                    disable = true
                servicesControl.toggleLayoutDisabled(layerTitle, disable)
            }
        }
        servicesControl.updateServicesCount(servicesCount)
        partnersControl.updateServicesCount(servicesCount)
    }

    function addServicesControlToMap() {
        servicesControl.addTo(map)
        servicesControl.buildServicesControlInputsMap()
        servicesControl.updateServicesCount(servicesCount)
        L.DomUtil.addClass(
            servicesControl.getContainer(),
            ' leaflet-services-control',
        )
    }

    function addPartnersControlToMap(labels) {
        // don't display partners filer if no "parters" available
        if (partnersControl.arePartnersAvailable()) {
            partnersControl.setLabels(labels)
            partnersControl.initReloadServices(reloadServices)
            partnersControl.addTo(map)
            partnersControl.updateServicesCount(servicesCount)
        }
    }

    function addAllServicesControlToMap(labels) {
        allServicesControl.setLabels(labels)
        allServicesControl.addTo(map)

        // add a listner to allServicesControl checkbox
        L.DomEvent.addListener(
            allServicesControl.getAllServicesCheckbox(),
            'click',
            function (ev) {
                if ($(this).prop('checked') === true) {
                    for (const layer of Object.values(
                        servicesControl.getOverlays(),
                    )) {
                        map.addLayer(layer)
                    }
                } else {
                    for (const layer of Object.values(
                        servicesControl.getOverlays(),
                    )) {
                        map.removeLayer(layer)
                    }
                }
                servicesControl.buildServicesControlInputsMap()
                servicesControl.updateServicesCount(servicesCount)
                partnersControl.updateServicesCount(servicesCount)
                reloadServices()
                L.DomEvent.stopPropagation(ev)
            },
        )
    }

    function handleServicesOverlaysSelection() {
        // add listners to layoutControl overlays
        const allServicesCheckbox = allServicesControl.getAllServicesCheckbox()
        map.on('overlayadd', function (eo) {
            if (Object.keys(servicesControl.getOverlays(false)).length === 0) {
                if (!$(allServicesCheckbox).is(':checked')) {
                    $(allServicesCheckbox).prop('checked', true)
                }
            }
            reloadService(eo.name, 'add')
        })

        map.on('overlayremove', function (eo) {
            if ($(allServicesCheckbox).is(':checked')) {
                $(allServicesCheckbox).prop('checked', false)
            }
            reloadService(eo.name, 'remove')
        })

        map.on('click', function () {
            // deselect the selected service and close the sidebarControl
            if (selectedService !== null) {
                selectedService = null
            }
            sidebarControl.close()
        })
    }

    const homeLink = document.querySelectorAll('.leaflet-control-zoomhome-home')
    // set a dfsr icon on zoomhome button instead of awesome icon
    if (homeLink !== undefined) {
        homeLink[0].firstChild.classList.remove('fa')
        homeLink[0].firstChild.classList.remove('fa-home')
        homeLink[0].firstChild.classList.add('fr-icon-home-4-line')
    }
}

document.addEventListener('DOMContentLoaded', () => buildMap())
