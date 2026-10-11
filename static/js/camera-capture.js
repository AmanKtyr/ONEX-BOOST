/**
 * Camera Capture Logic
 * Handles square photo capture, camera switching, and modal integration.
 */

let cameraModalInstance = null;
let currentTargetInputId = null;
let cameraStream = null;
let currentFacingMode = 'environment';

function stopCameraStream() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
        cameraStream = null;
    }
}

async function startCameraStream() {
    stopCameraStream(); // Stop existing if any
    
    const video = document.getElementById('video');
    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({ 
            video: { 
                facingMode: currentFacingMode,
                width: { ideal: 1280 },
                height: { ideal: 1280 }
            } 
        });
        video.srcObject = cameraStream;
        return true;
    } catch (err) {
        console.error("Error accessing camera: ", err);
        Swal.fire({
            icon: 'error',
            title: 'Camera Error',
            text: 'Could not access the camera. Please check permissions.'
        });
        return false;
    }
}

function initCameraCapture() {
    const modalEl = document.getElementById('cameraModal');
    if (!modalEl) return;

    cameraModalInstance = new bootstrap.Modal(modalEl);
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const takePhotoBtn = document.getElementById('take-photo-btn');
    const switchCameraBtn = document.getElementById('switch-camera-btn');
    const cancelCameraBtn = document.getElementById('cancel-camera-btn');

    // Handle all capture buttons on the page
    document.addEventListener('click', function(e) {
        const btn = e.target.closest('.capture-btn');
        if (btn) {
            currentTargetInputId = btn.getAttribute('data-target');
            // For mobile, default to the rear camera, for desktop, the user camera
            const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
            currentFacingMode = isMobile ? 'environment' : 'user';
            
            startCameraStream().then(success => {
                if (success) cameraModalInstance.show();
            });
        }
    });

    if (switchCameraBtn) {
        switchCameraBtn.addEventListener('click', function() {
            currentFacingMode = currentFacingMode === 'user' ? 'environment' : 'user';
            startCameraStream();
        });
    }

    if (takePhotoBtn) {
        takePhotoBtn.addEventListener('click', function() {
            if (!currentTargetInputId) return;

            // Calculate center square crop
            const size = Math.min(video.videoWidth, video.videoHeight);
            canvas.width = size;
            canvas.height = size;
            
            const sx = (video.videoWidth - size) / 2;
            const sy = (video.videoHeight - size) / 2;

            const context = canvas.getContext('2d');
            context.drawImage(video, sx, sy, size, size, 0, 0, size, size);

            canvas.toBlob(function(blob) {
                const file = new File([blob], "captured_image.jpg", { type: "image/jpeg" });
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(file);
                
                const input = document.getElementById(currentTargetInputId);
                if (input) {
                    // Validation
                    const maxSizeMB = 2;
                    if (file.size > maxSizeMB * 1024 * 1024) {
                        Swal.fire({ 
                            icon: 'error', 
                            title: 'File Too Large', 
                            text: `The image size must be no more than ${maxSizeMB} MB.` 
                        });
                        input.value = '';
                        return;
                    }

                    input.files = dataTransfer.files;

                    // Show local preview
                    const previewContainer = document.getElementById('preview_' + currentTargetInputId);
                    if (previewContainer) {
                        const previewImg = previewContainer.querySelector('img');
                        if (previewImg) {
                            previewImg.src = URL.createObjectURL(blob);
                            previewContainer.style.display = 'block';
                        }
                    }

                    // Trigger change for validation scripts
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }

                cameraModalInstance.hide();
            }, 'image/jpeg', 0.85);
        });
    }

    // Direct fix for cancel buttons not working
    if (cancelCameraBtn) {
        cancelCameraBtn.addEventListener('click', function() {
            cameraModalInstance.hide();
        });
    }

    modalEl.addEventListener('hidden.bs.modal', stopCameraStream);
    
    // Add file preview for manual selection as well
    document.addEventListener('change', function(e) {
        const input = e.target;
        if (input.type === 'file' && input.id) {
            const previewContainer = document.getElementById('preview_' + input.id);
            if (previewContainer && input.files && input.files[0]) {
                const file = input.files[0];
                // Validation
                const maxSizeMB = 2;
                const isIdentityDoc = input.id === 'id_identity_document_image';
                const allowedTypes = isIdentityDoc ? 
                    ['image/jpeg', 'image/png', 'image/jpg', 'application/pdf'] : 
                    ['image/jpeg', 'image/png', 'image/jpg'];

                if (file.size > maxSizeMB * 1024 * 1024) {
                    Swal.fire({ 
                        icon: 'error', 
                        title: 'File Too Large', 
                        text: `The file size must be no more than ${maxSizeMB} MB.` 
                    });
                    input.value = '';
                    if (previewContainer) previewContainer.style.display = 'none';
                    return;
                }

                if (!allowedTypes.includes(file.type)) {
                    Swal.fire({ 
                        icon: 'error', 
                        title: 'Invalid File Type', 
                        text: `Only ${allowedTypes.join(', ')} files are allowed.` 
                    });
                    input.value = '';
                    if (previewContainer) previewContainer.style.display = 'none';
                    return;
                }

                // Only show preview if it's an image
                if (file.type.startsWith('image/')) {
                    const reader = new FileReader();
                    reader.onload = function(ev) {
                        const img = previewContainer.querySelector('img');
                        if (img) {
                            img.src = ev.target.result;
                            previewContainer.style.display = 'block';
                        }
                    }
                    reader.readAsDataURL(file);
                } else {
                    // For PDF, we could show an icon or just hide preview
                    if (previewContainer) previewContainer.style.display = 'none';
                }
            }
        }
    });
}



document.addEventListener('DOMContentLoaded', initCameraCapture);