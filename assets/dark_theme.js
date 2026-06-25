(function () {

    function patchDropdowns() {
        document.querySelectorAll('div.dash-dropdown-wrapper').forEach(function (w) {
            w.style.setProperty('background-color', '#2c2c2c', 'important');
            w.style.setProperty('border',           '1px solid #555', 'important');
            w.style.setProperty('border-radius',    '4px', 'important');
            w.style.setProperty('color',            '#dee2e6', 'important');
        });
        document.querySelectorAll('input.dash-dropdown-focus-target').forEach(function (inp) {
            inp.style.setProperty('background',  'transparent', 'important');
            inp.style.setProperty('border',      'none', 'important');
            inp.style.setProperty('outline',     'none', 'important');
            inp.style.setProperty('box-shadow',  'none', 'important');
        });
    }

    function patchDatePickerInputs() {
        document.querySelectorAll('.dash-datepicker-input-wrapper').forEach(function (el) {
            el.style.setProperty('background-color', '#2c2c2c', 'important');
            el.style.setProperty('border',           '1px solid #555', 'important');
            el.style.setProperty('border-radius',    '4px', 'important');
            el.style.setProperty('color',            '#dee2e6', 'important');
            el.querySelectorAll('svg').forEach(function (svg) {
                svg.style.setProperty('fill',  '#dee2e6', 'important');
                svg.style.setProperty('color', '#dee2e6', 'important');
            });
        });
    }

    function patchCalendarPopup() {
        [
            '.dash-datepicker-content',
            '.dash-datepicker-calendar-wrapper',
            '.dash-datepicker-controls',
            '.dash-datepicker-calendar-container',
            'table.dash-datepicker-calendar',
        ].forEach(function (sel) {
            document.querySelectorAll(sel).forEach(function (el) {
                el.style.setProperty('background-color', '#1f2937', 'important');
            });
        });
        document.querySelectorAll('td.dash-datepicker-calendar-date-inside').forEach(function (td) {
            if (td.getAttribute('aria-disabled') === 'true') return;
            td.style.setProperty('background-color', '#1f2937', 'important');
            td.style.setProperty('color',            '#d1d5db', 'important');
        });
    }

    function patch() {
        patchDropdowns();
        patchDatePickerInputs();
        patchCalendarPopup();
    }

    var timer, timer2;
    new MutationObserver(function () {
        clearTimeout(timer);
        clearTimeout(timer2);
        timer  = setTimeout(patch, 0);
        timer2 = setTimeout(patchCalendarPopup, 300);
    }).observe(document.documentElement, { childList: true, subtree: true });

    patch();
}());
