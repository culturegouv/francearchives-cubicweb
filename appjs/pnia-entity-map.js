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

/* global L, PruneClusterForLeaflet, PruneCluster*/
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

function buildMap() {
    const mapElement = document.querySelectorAll('.fa-entity-map')

    if (mapElement === null) {
        console.error('Could not create the map: .fa-entity-map not found')
        return
    }

    mapElement.forEach(function (mapElement) {
        let map = L.map('service-map-' + mapElement.dataset.index, {
            gestureHandling: true,
        })

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution:
                '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(map)

        let bounds = new L.LatLngBounds()

        fetch(mapElement.dataset.markerurl, {credentials: 'same-origin'})
            .then((response) => response.json())
            .then((markers) => {
                const pruneCluster = new PruneClusterForLeaflet()
                for (let marker of markers) {
                    const mapMarker = new PruneCluster.Marker(
                        marker.lat,
                        marker.lng,
                    )
                    bounds.extend(L.latLng(marker.lat, marker.lng))
                    if (marker.level === 'level-D') {
                        mapMarker.data.icon = blueIcon
                    } else {
                        mapMarker.data.icon = goldenIcon
                    }
                    mapMarker.data.popup = `<p><b>${marker.name}</b></p>`
                    pruneCluster.RegisterMarker(mapMarker)
                }
                map.addLayer(pruneCluster)
                map.fitBounds(bounds)
            })
        const mapid = mapElement.getAttribute('id')
        const toggle = document.querySelector('#toggle-' + mapid)
        toggle.addEventListener('click', function () {
            if (mapElement.classList.contains('fr-hidden')) {
                setTimeout(function () {
                    map.invalidateSize()
                }, 2)
            }
            mapElement.classList.toggle('fr-hidden')
        })
    })
}

document.addEventListener('DOMContentLoaded', () => buildMap())
