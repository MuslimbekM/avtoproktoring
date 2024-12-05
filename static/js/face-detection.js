


let video = document.getElementById('camera');
let capturedImage = document.getElementById('capturedImage');
let capturedPhotoInput = document.getElementById('captured_photo');
let faceInfo = document.getElementById('faceInfo');
let stream;

async function toggleLoginMethod() {
    const method = document.getElementById('loginMethod').value;
    if (method === 'password') {
        document.getElementById('passwordLogin').style.display = 'block';
        document.getElementById('faceLogin').style.display = 'none';
    } else if (method === 'face') {
        document.getElementById('passwordLogin').style.display = 'none';
        document.getElementById('faceLogin').style.display = 'block';
    }
}

async function startCamera() {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        stream = await navigator.mediaDevices.getUserMedia({video: true});
        video.srcObject = stream;
    } else {
        alert("Brauzer kamerani qo'llab-quvvatlamaydi.");
    }
}

async function capturePhoto() {
    let canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    let context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    // Rasmni Base64 formatida olish
    let dataURL = canvas.toDataURL('image/png');
    capturedPhotoInput.value = dataURL;

    // Rasmni ko'rsatish
    capturedImage.src = dataURL;
    capturedImage.style.display = 'block';

    // Kamerani o'chirish
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
    }

    // Yuzni aniqlash
    await loadModels();
    await detectFaces(canvas);
}

async function loadModels() {

    await faceapi.nets.tinyFaceDetector.loadFromUri('/static/models/tiny_face_detector_model-weights_manifest.json\n');
    await faceapi.nets.faceLandmark68Net.loadFromUri('/static/models/face_landmark_68_model-weights_manifest.json\n');
    await faceapi.nets.faceRecognitionNet.loadFromUri('/static/models/face_recognition_model-weights_manifest.json');
}

async function detectFaces(canvas) {
    const options = new faceapi.TinyFaceDetectorOptions({
        inputSize: 512,
        scoreThreshold: 0.5
    });

    const detections = await faceapi.detectAllFaces(canvas, options).withFaceLandmarks();

    if (detections.length > 0) {
        const displaySize = {width: canvas.width, height: canvas.height};
        const resizedDetections = faceapi.resizeResults(detections, displaySize);

        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height); // Canvasni tozalash

        resizedDetections.forEach(detection => {
            const box = detection.detection.box;
            ctx.strokeStyle = 'blue';
            ctx.lineWidth = 2;
            ctx.strokeRect(box.x, box.y, box.width, box.height);

            // Yuz yonida ism-familiyani ko'rsatish
            ctx.font = "16px Arial";
            ctx.fillStyle = "blue";
            ctx.fillText("Aniqlangan Yuz", box.x, box.y - 10);
        });
        faceInfo.style.display = "block";
    } else {
        alert("Yuz aniqlanmadi. Qayta urinib ko'ring.");
    }
}
