
function confirmDelete(itemId, itemName, deleteUrl, redirectUrl) {
    Swal.fire({
        title: 'Are you sure?',
        text: `You are about to delete ${itemName}. This action cannot be undone.`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#ff3ca6',
        cancelButtonColor: '#6c7293',
        confirmButtonText: 'Yes, delete it!',
        cancelButtonText: 'Cancel',
        background: '#fff',
        customClass: {
            popup: 'border-radius-12',
            title: 'text-dark font-weight-bold',
            content: 'text-muted'
        }
    }).then((result) => {
        if (result.isConfirmed) {
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

            fetch(deleteUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken
                }
            })
            .then(response => {
                if (response.ok) {
                    return response.json();
                }
                throw new Error('Network response was not ok.');
            })
            .then(data => {
                if (data.status === 'success') {
                    Swal.fire({
                        title: 'Deleted!',
                        text: `${itemName} has been successfully deleted.`,
                        icon: 'success',
                        confirmButtonColor: '#4599cd'
                    }).then(() => {
                        if (redirectUrl) {
                            window.location.href = redirectUrl;
                        } else {
                            window.location.reload();
                        }
                    });
                } else {
                    Swal.fire({
                        title: 'Error!',
                        text: data.message || 'An unexpected error occurred.',
                        icon: 'error',
                        confirmButtonColor: '#4599cd'
                    });
                }
            })
            .catch(error => {
                console.error('Fetch error:', error);
                Swal.fire({
                    title: 'Error!',
                    text: 'An error occurred while deleting the item. Please try again.',
                    icon: 'error',
                    confirmButtonColor: '#4599cd'
                });
            });
        }
    });
}