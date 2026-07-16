/* global Yasqe, Yasr, SPARQL_ENDPOINT, SparnaturalYasguiPlugins */

function setUpSparnatural(document) {
    const sparnatural = document.querySelector('spar-natural')

    const yasqe = new Yasqe(document.getElementById('yasqe'), {
        requestConfig: {
            endpoint: SPARQL_ENDPOINT,
        },
        copyEndpointOnNewTab: false,
    })

    Yasr.registerPlugin('table', SparnaturalYasguiPlugins.TableX)

    const yasr = new Yasr(document.getElementById('yasr'), {
        defaultPlugin: 'table',
        pluginOrder: ['table', 'response'],
        //this way, the URLs in the results are prettified using the defined prefixes in the query
        getUsedPrefixes: yasqe.getPrefixesFromQuery,
        // disable persistency
        persistencyExpire: 0,
        maxPersistentResponseSize: 0,
    })

    sparnatural.addEventListener('queryUpdated', (event) => {
        var queryString = sparnatural.expandSparql(event.detail.queryString)
        yasqe.setValue(queryString)
    })

    sparnatural.addEventListener('loadQuery', (event) => {
        var queryString = sparnatural.loadQuery(event.detail)
        yasqe.setValue(queryString)
    })

    sparnatural.addEventListener('submit', () => {
        sparnatural.disablePlayBtn()
        // trigger the query from YasQE
        yasqe.query()
    })

    // link yasqe and yasr
    yasqe.on('queryResponse', function (_yasqe, response, duration) {
        yasr.setResponse(response, duration)
        sparnatural.enablePlayBtn()
    })

    document.getElementById('sparql-toggle').onclick = function () {
        if (document.getElementById('yasqe').style.display == 'none') {
            document.getElementById('yasqe').style.display = 'block'
            yasqe.setValue(yasqe.getValue())
            yasqe.refresh()
            document.getElementById('sparql-toggle-icon').className =
                'fa fa-eye-slash fa-fw'
        } else {
            document.getElementById('yasqe').style.display = 'none'
            document.getElementById('sparql-toggle-icon').className =
                'fa fa-eye fa-fw'
        }
        return false
    }
}

document.addEventListener('DOMContentLoaded', () => setUpSparnatural(document))
