document.addEventListener('DOMContentLoaded', function () {
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        const inputs = Array.from(form.querySelectorAll('input, select, textarea'));

        inputs.forEach((input, index) => {
            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();

                    // Find next focusable element
                    let nextIndex = index + 1;
                    let nextInput = inputs[nextIndex];

                    // Loop to find the next visible and non-disabled element
                    while(nextInput) {
                        if (nextInput.offsetParent !== null && !nextInput.disabled) {
                            nextInput.focus();
                            break;
                        }
                        nextIndex++;
                        nextInput = inputs[nextIndex];
                    }
                }
            });
        });
    });
});