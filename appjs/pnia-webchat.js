/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2023
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

/* global wrapWebchat */

function loadWebchat() {
    wrapWebchat({
        color: '#243469', // La couleur d'arrière plan du bouton de chat et du bandeau en haut de la fenêtre.
        webchatParams: {
            // Ces paramètres permettront d'identifier l'utilisateur.
            userId: 'anonymous', // <-- À DÉFINIR DYNAMIQUEMENT PAR L'APPLICATION APPELANTE
            userIdType: 'login', // <-- À POSITIONNER : login OU email
            userFirstName: '', // <-- À DÉFINIR DYNAMIQUEMENT PAR L'APPLICATION APPELANTE (OU LAISSER VIDE)
            userLastName: '', // <-- À DÉFINIR DYNAMIQUEMENT PAR L'APPLICATION APPELANTE (OU LAISSER VIDE)
            webChatToken:
                'MmFhMDI0ZTktODBjYS00ZTJhLTk5OWUtNjc5MmUzMTVmMzhiLTE2ODUwMDM4NDE2Mzg=',
            originId: '', // Indique l'endroit où est intégré le webchat (Information qui peut être retrouvée dans l'entraînement),
            customParams: {}, // Des paramètres personnalisés à ajouter dans l'url du chatbot,
            persona: null, // Le nom du persona à utiliser (optionnel)
        },
        height: '80%', // La hauteur de la fenêtre.
        width: '30%', // La largeur de la fenêtre.
        chatButtonIcon: {
            // Paramétrage du bouton de chat.
            url: 'https://files.wikit.ai/mcl-rh/1708006053384-Noria_Piste-2_1.png', // Ajouter une image en arrière plan du bouton de chat.
            altText: 'Bouton du chatbot', // Text alternatif pour l'image (accessibilité).
            height: '100px', // Hauteur du bouton de chat.
            width: '100px', // Largeur du bouton de chat.
            borderRadius: '50%', // Rayon de la bordure du bouton de chat.
        },
        chatButtonTooltip: {
            // Afficher une bulle de texte à côté du bouton de chat.
            text: "NORIA : besoin d'aide ?", // Le texte du message
            backgroundColor: null, // La couleur d'arrière plan.
            textColor: null, // La couleur du texte.
            visibility: 'visible', // La visibilité de la bulle au passage de la souris ('hidden') ou tout le temps ('visible').
        },
        chatButtonAnimation: {
            // Animation du bouton de chat
            delay: '2000', // Délais en millisecondes après lequel le bouton s'anime
            enabled: true, // Active l'animation
            openTooltip: true, // Ouvre l'info-bulle après l'animation
        },
        headerButtons: {
            // Le texte d'accessibilité des boutons au haut de la fenêtre du webchat.
            color: '#fff',
            closeIconDescription: 'Fermer la fenêtre',
            launchIconDescription: 'Ouvrir dans un nouvel onglet',
            maximizeIconDescription: 'Agrandir la fenêtre',
            minimizeIconDescription: 'Rétrécir la fenêtre',
        },
        opening: {
            // L'état (ouvert / fermé) du webchat en arrivant sur la page. Noter qu'une ouverture automatique n`'est pas possible sur mobile.
            mode: 'close', // 3 modes possibles, ouvert ('open'), fermé ('close') ou ouvert après un délais ('delay').
            delay: null, // Le délais en millisecondes pour l'ouverture du webchat.
            memorize: true, // Mémoriser l'état d'ouverture du webchat.
        },
        position: {
            // La position du bouton de chat et du webchat dans le navigateur.
            right: '1rem',
            bottom: '5rem',
        },
    })
}

document.addEventListener('DOMContentLoaded', () => loadWebchat())
