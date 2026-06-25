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
        ['evol-date-from', 'evol-date-to',
         'pair-date-from', 'pair-date-to',
         'sig-recalc-date', 'str-calc-date'].forEach(function (pid) {
            var el = document.getElementById(pid);
            if (!el) return;
            el.style.setProperty('background-color', '#2c2c2c', 'important');
            el.style.setProperty('border',           '1px solid #555', 'important');
            el.style.setProperty('border-radius',    '4px', 'important');
            el.querySelectorAll('input, [role="textbox"]').forEach(function (inp) {
                inp.style.setProperty('background-color', '#2c2c2c', 'important');
                inp.style.setProperty('color',            '#dee2e6', 'important');
            });
        });
    }

    function patchCalendarPopup() {
        [
            '[class*="SingleDatePicker_picker"]',
            '[class*="DayPicker"]',
            '[class*="DayPicker_transitionContainer"]',
            '[class*="CalendarMonthGrid"]',
            '[class*="CalendarMonth"]:not([class*="CalendarMonthGrid"])',
            'table[class*="CalendarMonth_table"]',
        ].forEach(function (sel) {
            document.querySelectorAll(sel).forEach(function (el) {
                el.style.setProperty('background',       '#1f2937', 'important');
                el.style.setProperty('background-color', '#1f2937', 'important');
            });
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
