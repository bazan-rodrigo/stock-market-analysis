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

        // dcc.DatePickerSingle — react-dates/Aphrodite inyecta background: white !important
        // CSS no puede ganarle; aplicamos inline con 'important' desde JS
        document.querySelectorAll('[class*="DateInput_input"]').forEach(function (inp) {
            inp.style.setProperty('background-color', '#2c2c2c', 'important');
            inp.style.setProperty('color',            '#dee2e6', 'important');
        });
        document.querySelectorAll('[class*="SingleDatePickerInput_"], [class*="DateInput_"]:not(input)').forEach(function (d) {
            d.style.setProperty('background-color', '#2c2c2c', 'important');
            d.style.setProperty('border-color',     '#555',    'important');
        });
    }

    var timer;
    new MutationObserver(function () {
        clearTimeout(timer);
        timer = setTimeout(patch, 40);
    }).observe(document.documentElement, { childList: true, subtree: true });

    patch();
}());
