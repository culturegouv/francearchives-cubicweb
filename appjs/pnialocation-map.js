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

function buildMap() {
    const mapElement = document.querySelector('#fa-map'),
        map = L.map('fa-map', {gestureHandling: true}),
        settings = {
            tileProvider:
                'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
            tileAttribution:
                'Esri &mdash; Sources: Esri, HERE, Garmin, Intermap, increment P Corp., GEBCO, USGS, FAO, NPS, NRCAN, GeoBase, IGN, Kadaster NL, Ordnance Survey, Esri Japan, METI, Esri China (Hong Kong), (c) OpenStreetMap contributors, and the GIS User Community',
        }
    const bounds = new L.LatLngBounds()
    L.tileLayer(settings.tileProvider, {
        attribution: settings.tileAttribution,
        minZoom: 3,
        scrollWheelZoom: false,
    }).addTo(map)

    function createDashIcon() {
        return L.icon({
            iconUrl: mapElement.dataset.iconUrl,
        })
    }
    fetch(mapElement.dataset.markerurl, {credentials: 'same-origin'})
        .then((response) => response.json())
        .then((markers) => {
            if (!markers.length) {
                return
            }
            const pruneCluster = new PruneClusterForLeaflet()
            for (let marker of markers) {
                const mapMarker = new PruneCluster.Marker(
                    marker.lat,
                    marker.lng,
                )
                let docLabel = 'documents'
                bounds.extend(L.latLng(marker.lat, marker.lng))
                if (marker.count === 1) {
                    docLabel = 'document'
                }
                if (marker.dashLabel) {
                    mapMarker.data.icon = createDashIcon
                }
                mapMarker.data.popup = `<div class="map-authority">
                 <a class="map-authority__title" href="${marker.url}">${marker.label}</a>
                 <span class="map-authority__desc">${marker.count} ${docLabel}</span>
                </div>`
                pruneCluster.RegisterMarker(mapMarker)
            }
            map.addLayer(pruneCluster)
            map.fitBounds(bounds)
        })
}

document.addEventListener('DOMContentLoaded', () => buildMap())
