document.addEventListener("DOMContentLoaded", function() {
    /*Integration Eulerian / TarteAuCitron*/
    tarteaucitron.services['eulerian-analytics'] = {
        "key": "eulerian-analytics",
        "type": "analytic",
        "name": "Eulerian Analytics",
        "needConsent": true,
        "cookies": ["etuix"],
        "uri" : "https://eulerian.com/vie-privee",
        "js": function () {
            "use strict";
            (function(x,w){ if (!x._ld){ x._ld = 1;
              let ff = function() { if(x._f){x._f('tac',tarteaucitron,1)} };
              w.__eaGenericCmpApi = function(f) { x._f = f; ff(); };
              w.addEventListener("tac.close_alert", ff);
              w.addEventListener("tac.close_panel", ff);
             }})(this,window);
        },
        "fallback": function () { this.js(); },
    };

    (tarteaucitron.job = tarteaucitron.job || []).push('eulerian-analytics');
});
