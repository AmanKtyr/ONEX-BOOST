document.addEventListener('DOMContentLoaded', function () {
    const pincodeInputs = document.querySelectorAll('input[name$="pincode"]');

    pincodeInputs.forEach(pincodeInput => {
        pincodeInput.addEventListener('blur', function () {
            const pincode = this.value;
            const form = this.closest('form');

            if (pincode.length === 6 && /^[0-9]+$/.test(pincode)) {
                fetch(`https://api.postalpincode.in/pincode/${pincode}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data && data[0].Status === 'Success') {
                            const postOffice = data[0].PostOffice[0];
                            const stateInput = form.querySelector('input[name$="state"]');
                            const cityInput = form.querySelector('input[name$="city"]');
                            const areaInput = form.querySelector('input[name$="area"]');

                            if (stateInput) {
                                stateInput.value = postOffice.State;
                            }
                            if (cityInput) {
                                cityInput.value = postOffice.District;
                            }
                            if (areaInput) {
                                // If multiple areas, you might want to create a dropdown.
                                // For now, just using the first one.
                                areaInput.value = postOffice.Name;
                            }
                        }
                    })
                    .catch(error => console.error('Error fetching pincode data:', error));
            }
        });
    });
});