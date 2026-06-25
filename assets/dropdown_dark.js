(function () {
    function patch() {
        document.querySelectorAll('div.dash-dropdown-wrapper').forEach(function (w) {
            w.style.setProperty('background-color', '#2c2c2c', 'important');
            w.style.setProperty('border',           '1px solid #555', 'important');
            w.style.setProperty('border-radius',    '4px', 'important');
            w.style.setProperty('color',            '#dee2e6', 'important');
        });
        document.querySelectorAll('input.dash-dropdown-focus-target').forEach(function (inp) {
            inp.style.setProperty('background',   'transparent', 'important');
            inp.style.setProperty('border',       'none', 'important');
            inp.style.setProperty('outline',      'none', 'important');
            inp.style.setProperty('box-shadow',   'none', 'important');
        });

        // dcc.DatePickerSingle — por ID (wrapper + input)
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

        // Popup del calendario — barrido global (cubre portal y renderizado inline)
        // Inline !important gana sobre CSS !important de react-dates
        [
            '[class*="SingleDatePicker_picker"]',
            '[class*="DayPicker_transitionContainer"]',
            '[class*="CalendarMonthGrid"]',
            '[class*="CalendarMonth"]:not([class*="CalendarMonthGrid"])',
        ].forEach(function (sel) {
            document.querySelectorAll(sel).forEach(function (el) {
                el.style.setProperty('background-color', '#1f2937', 'important');
            });
        });
    }

    var timer;
    new MutationObserver(function () {
        clearTimeout(timer);
        timer = setTimeout(patch, 40);
    }).observe(document.documentElement, { childList: true, subtree: true });

    patch();
}());
