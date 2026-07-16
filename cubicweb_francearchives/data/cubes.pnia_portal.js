/* global $ BASE_URL */

function setupHighresImagesDownloading() {
    var width = $(window).width()

    var hrPropName

    if (width >= 1900) {
        hrPropName = 'highresXl'
    } else if (width >= 1200) {
        hrPropName = 'highresLg'
    } else if (width >= 922) {
        hrPropName = 'highresMd'
    } else if (width >= 768) {
        hrPropName = 'highresSm'
    } else {
        hrPropName = 'highresXs'
    }

    Array.prototype.slice
        .call(document.querySelectorAll('.hero-images--image'))
        .forEach(function (img) {
            var hrImage = new Image()
            hrImage.onload = function () {
                img.src = this.src
                img.classList.remove('hero-images--image__lowres')
            }
            hrImage.src = img.dataset[hrPropName]
        })
}

function resizeHeroImages() {
    if ($(window).width() < 992) {
        return
    }

    var totalHeight = $(window).height()
    var navbarHeight = $('.navtools').outerHeight()
    var heroHeight = $('#hero-images').outerHeight()
    var searchbarHeight = $('#home-search-bar').outerHeight()
    var sectionsHeight = $('#content-headings').outerHeight()

    heroHeight = totalHeight - navbarHeight - searchbarHeight - sectionsHeight

    /* Why 215? Why not?! */
    if (heroHeight > 215) {
        $('#hero-images').css({height: heroHeight + 'px'})
        $('.hero-images--item').css({height: heroHeight + 'px'})
        $('.hero-images--image').css({height: heroHeight + 'px'})
    }
}

function setupSitemap() {
    var container = $('#tree-container')
    if (container.length !== 1) {
        // not on sitemap page
        return
    }
    $('i.fold', container).click(function () {
        var $caret = $(this)
        if ($caret.hasClass('rotate-0')) {
            $caret.removeClass('rotate-0')
            $caret.addClass('rotate-90')
        } else {
            $caret.addClass('rotate-0')
            $caret.removeClass('rotate-90')
        }
        var children = $caret.siblings('ul')
        children.toggleClass('hidden')
    })
}

function setupEscapeButton() {
    $(document).keyup(function (e) {
        // close elements
        var selectors = [
            ['#menu-icon.open', '.menu-item :focus'],
            ['#languageMenu.open', '.languageMenu__menu-item :focus'],
            ['.cwjs-facet-title.unfolded', '.facet__focusable-item:focus'],
        ]
        var $elt, itemSelector, focused
        if (e.key === 'Tab') {
            selectors.forEach(function (selector) {
                var $elt = $(selector[0]),
                    itemSelector = selector[1]
                if (selector[0] === '.cwjs-facet-title.unfolded') {
                    focused = $elt.parent().siblings('.facet__body').find(itemSelector)
                } else {
                    focused = $(itemSelector)
                }
                if ($elt[0] !== undefined) {
                    if (focused.length === 0) {
                        $elt.click()
                    }
                }
            })
        }
        if (e.key === 'Escape') {
            selectors.some(function (selector) {
                var $elt = $(selector[0])
                if ($elt[0] !== undefined) {
                    $elt.click()
                    return true
                }
            })
        }
    })
}

// When the user scrolls down 50px from the top of the document, show the button
window.addEventListener('scroll', scrollFunction)

function scrollFunction() {
    const btn = document.getElementById('toTopBtn')
    if (btn === null) {
        return
    }
    if (
        document.body.scrollTop > 50 ||
        document.documentElement.scrollTop > 50
    ) {
        btn.style.display = 'block'
        btn.style.transition = 'opacity 1s ease-out'
    } else {
        btn.style.display = 'none'
        btn.style.transition = 'opacity 1s ease-out'
    }
}

function initScrollBtn() {
    // When the user clicks on the button, scroll to the top of the document
    $('#toTopBtn').click(function () {
        $('body,html').animate({scrollTop: $('body').offset().top},500);

    })
}

function eurelian_tags(button) {
     let ds = button.dataset;
     if (ds.eulerianActionname === undefined) {
         console.error("eulerian: no dataset found on ", button)
         return
     }
     var action = [];
     action.push('actionname', ds.eulerianActionname);
     action.push('actionlabel', ds.eulerianActionlabel);
     action.push('actionpname', 'component_label');
     action.push('actionpvalue', ds.eulerianComponentlabel);
     if (ds.eulerianComponentvalue !== undefined) {
         action.push('actionpname', 'component_value');
         action.push('actionpvalue', ds.eulerianComponentvalue);
     }
     action.push('actionpname', 'component_hierarchy');
     action.push('actionpvalue', ds.eulerianComponenthierarchy);
     action.push('actionpname', 'heading_hierarchy');
     action.push('actionpvalue', ds.eulerianHeadinghierarchy);
     window.EA_push('action', action);
}


function initEulerianButtons() {
    const buttonSelector = '.eulerian-button'
    $(document).on('click', buttonSelector, function () {
        return eurelian_tags(this)
    })
    $(document).on('keypress', buttonSelector, function (e) {
        if (!/(13)/.test(e.keyCode)) return
        return eurelian_tags(this)
    })
}


$('document').ready(function () {
    setupEscapeButton()
    resizeHeroImages()
    setupHighresImagesDownloading()
    setupSitemap()
    initScrollBtn()
    if (typeof window.EA_push === 'function') {
        // stats are not activated
        initEulerianButtons()
    }
})

window.onresize = function () {
    resizeHeroImages()
}
