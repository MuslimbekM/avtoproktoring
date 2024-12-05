import base64
import hashlib
import json
import logging
import os.path
import random
import time

import cv2
import dlib
import face_recognition
import numpy as np
import pdfplumber
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.messages.storage import default_storage
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from face_recognition import face_encodings
from firebase_admin import firestore, storage
from transformers import pipeline  # NLP savol yaratish uchun model

# Firestore obyekti
db = firestore.client()
bucket = storage.bucket()
# Dlib yuz landmarklarini yuklash uchun model
detector = dlib.get_frontal_face_detector()
base_dir = os.path.dirname(os.path.abspath(__file__))
predictor_path = os.path.join(base_dir, "../static/models/shape_predictor_68_face_landmarks.dat")
# Dlib yuklash
predictor = dlib.shape_predictor(predictor_path)


def generate_student_id():
    # 12 xonalik raqamli ID yaratish
    return str(random.randint(10 ** 11, 10 ** 12 - 1))


def generate_username(firstname, lastname):
    """Username generatsiya qilish."""
    random_number = random.randint(100, 999)
    username = f"{firstname.lower()}.{lastname.lower()}{random_number}"
    return username


def check_face_features():
    users_ref = db.collection('stusents').stream()  # Foydalanuvchi kolleksiyasini o'zgartiring
    for user in users_ref:
        user_data = user.to_dict()
        if 'face_features' in user_data:
            face_features = user_data['face_features']
            if len(face_features) != 128:  # 128 o'lcham bo'lishi kerak
                print(f"Noto'g'ri xususiyatlar topildi: {user.id}, Shape: {len(face_features)}")



def extract_face_features(photo_base64):
    """Rasmdan yuz xususiyatlarini ajratib olish."""
    try:
        # Base64 ni dekodlash
        image_data = base64.b64decode(photo_base64.split(',')[1])
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Yuzni aniqlash va xususiyatlarini olish
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_img)
        if len(face_locations) != 1:
            return None  # Bir nechta yuz aniqlansa yoki yuz yo'q bo'lsa

        face_encoding = face_recognition.face_encodings(rgb_img, face_locations)[0]  # 128 o'lchovli vektor
        return face_encoding
    except Exception as e:
        print(f"Xatolik yuz xususiyatlarini olishda: {e}")
        return None


def is_face_registered(face_encoding, collection_name='users'):
    """Yuzning ma'lumotlar bazasida ro'yxatdan o'tganligini tekshirish."""
    users_ref = db.collection(collection_name).stream()
    for user in users_ref:
        user_data = user.to_dict()
        if 'face_features' in user_data:
            registered_features = np.array(user_data['face_features'], dtype=np.float32)
            if len(registered_features) == 128:  # Faqat 128 o'lchovli vektorlarni solishtirish
                matches = face_recognition.compare_faces([registered_features], face_encoding)
                if any(matches):
                    return True
    return False


def clean_invalid_face_features():
    users_ref = db.collection('students').stream()
    for user in users_ref:
        user_data = user.to_dict()
        if 'face_features' in user_data:
            face_features = user_data['face_features']
            if len(face_features) != 128:  # Noto'g'ri o'lchamni tekshirish
                db.collection('users').document(user.id).update({'face_features': firestore.DELETE_FIELD})
                print(f"Tozalandi: {user.id}")

@csrf_exempt
def signup_view(request):
    if request.method == 'POST':
        role = request.POST.get('role')  # 'teacher' yoki 'student'
        firstname = request.POST.get('firstname')
        lastname = request.POST.get('lastname')
        email = request.POST.get('email')
        password = request.POST.get('pass')
        re_password = request.POST.get('re_pass')
        photo_base64 = request.POST.get('captured_photo')

        # Parolni tekshirish
        if password != re_password:
            messages.error(request, "Parollar bir xil bo'lishi kerak.")
            return render(request, 'signup.html')

        # Rasmni tekshirish
        if not photo_base64:
            messages.error(request, "Iltimos, kameradan yuzingizni tasvirga oling.")
            return render(request, 'signup.html')

        # Yuz xususiyatlarini olish
        face_features = extract_face_features(photo_base64)
        if face_features is None:
            messages.error(request, "Yuz aniqlanmadi yoki bir nechta yuz aniqlangan!")
            return render(request, 'signup.html')

        # Yuzni tekshirish
        collection_name = 'students' if role == 'student' else 'teachers'
        if is_face_registered(face_features, collection_name=collection_name):
            messages.error(request, "Ushbu yuz allaqachon ro'yxatdan o'tgan!")
            return render(request, 'signup.html')

        try:
            # Role asosida ID generatsiya
            user_id = f"{role[:2].upper()}{str(int(time.time()))}"  # teacher uchun TE + vaqt, student uchun ST + vaqt
            user_data = {
                'firstname': firstname,
                'lastname': lastname,
                'email': email,
                'password': password,
                'photo': photo_base64,
                'face_features': face_features.tolist(),
            }

            # O'qituvchilar uchun qo'shimcha ma'lumot
            if role == 'teacher':
                user_data['teacher_id'] = user_id

                user_data['subject'] = request.POST.get('subject')  # O'qituvchi predmeti

            # Talabalar uchun qo'shimcha ma'lumot
            if role == 'student':
                user_data['student_id'] = user_id

            # Foydalanuvchini tegishli kolleksiyaga yozish
            db.collection(collection_name).document(user_id).set(user_data)

            # FaceID kolleksiyasiga yozish (faqat talaba uchun)
            if role == 'student':
                face_id = f"FID{str(int(time.time()))}"  # Face ID
                face_data = {
                    'face_id': face_id,
                    'student_id': user_id,
                    'student_face': photo_base64,
                }
                db.collection('faceID').document(face_id).set(face_data)

            messages.success(request, f"{role.title()} sifatida muvaffaqiyatli ro'yxatdan o'tdingiz!")
            return redirect('signin')

        except Exception as e:
            messages.error(request, f"Xatolik yuz berdi: {str(e)}")

    return render(request, 'signup.html')


def generate_face_hash(face_encoding):
    """
    Yuz xususiyatlaridan hash yaratish.
    """
    face_array = np.array(face_encoding)
    face_string = face_array.tostring()
    return hashlib.sha256(face_string).hexdigest()


def check_face(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            image_data = data.get('image', None)

            if not image_data:
                return JsonResponse({'valid': False, 'message': "Rasm yuborilmadi."})

            # Base64 ma'lumotni dekodlash
            header, encoded = image_data.split(",", 1)
            image_bytes = base64.b64decode(encoded)
            np_array = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

            # Yuzni aniqlash
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray_image, scaleFactor=1.1, minNeighbors=5)

            if len(faces) == 0:
                return JsonResponse({'valid': False, 'message': "Yuz topilmadi."})
            elif len(faces) > 1:
                return JsonResponse({'valid': False, 'message': "Bir nechta yuz aniqlanmoqda."})

            # Faqat birinchi yuzni olish
            (x, y, w, h) = faces[0]
            cropped_face = image[y:y+h, x:x+w]

            # RGB formatga o‘tkazish
            rgb_face = cv2.cvtColor(cropped_face, cv2.COLOR_BGR2RGB)

            # Yuz xususiyatlarini olish
            encodings = face_encodings(rgb_face)

            if not encodings:
                return JsonResponse({'valid': False, 'message': "Yuz xususiyatlarini olishda xatolik."})

            new_encoding = encodings[0]  # Olingan yuz xususiyatlari
            new_face_hash = generate_face_hash(new_encoding)  # Yangi yuz uchun hash yaratish

            # Firestore'da mavjud hashlarni tekshirish
            users_ref = db.collection('students')
            all_users = users_ref.stream()

            for user in all_users:
                stored_hash = user.to_dict().get('face_hash', None)
                if stored_hash == new_face_hash:
                    return JsonResponse({'valid': False, 'message': "Bu yuz allaqachon mavjud, qayta rasm oling."})

            # Yuzni saqlash (agar yangi bo‘lsa)
            new_user_id = f"USER{int(time.time())}"
            users_ref.document(new_user_id).set({
                'user_id': new_user_id,
                'face_encoding': new_encoding.tolist(),
                'face_hash': new_face_hash,
            })

            return JsonResponse({'valid': True, 'message': "Yuz muvaffaqiyatli saqlandi."})
        except Exception as e:
            return JsonResponse({'valid': False, 'message': f"Xatolik: {str(e)}"})

    return JsonResponse({'valid': False, 'message': "Noto‘g‘ri so‘rov turi."})


def save_image_to_temp_file(image):
    """Rasmni vaqtinchalik faylga saqlash va fayl manzilini qaytarish."""
    file_name = 'temp_image.jpg'
    file_path = default_storage.save(file_name, ContentFile(image.tobytes()))
    return default_storage.path(file_path)


def check_face_match(saved_image_path, captured_image_path):
    saved_image = face_recognition.load_image_file(saved_image_path)
    captured_image = face_recognition.load_image_file(captured_image_path)

    saved_encoding = face_recognition.face_encodings(saved_image)
    captured_encoding = face_recognition.face_encodings(captured_image)

    if saved_encoding and captured_encoding:
        results = face_recognition.compare_faces(saved_encoding, captured_encoding)
        return results[0]  # Agar yuzlar mos kelsa True qaytadi
    return False


# Face Liveness Detection (ko'z harakati asosida)
def is_liveness_detected(frame):
    # Yuzni aniqlash
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = detector(gray)
    if len(faces) > 0:
        for face in faces:
            landmarks = predictor(gray, face)
            left_eye = landmarks.part(36).x, landmarks.part(36).y
            right_eye = landmarks.part(45).x, landmarks.part(45).y
            # Ko'zlar orasidagi masofa - tiriklik belgilari
            if abs(left_eye[0] - right_eye[0]) > 20:  # Masofa tahlili (simulyativ)
                return True
    return False


# Face Landmarks aniqlash
def get_face_landmarks(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = detector(gray)
    landmarks_list = []
    for face in faces:
        landmarks = predictor(gray, face)
        points = [(landmarks.part(n).x, landmarks.part(n).y) for n in range(68)]
        landmarks_list.append(points)
    return landmarks_list


# Yuzni aniqlash va tiriklik tekshiruvi
def process_face_image(captured_image, saved_image):
    try:
        # Yuzni aniqlash
        captured_faces = face_recognition.face_locations(captured_image)
        saved_faces = face_recognition.face_locations(saved_image)

        if len(captured_faces) > 0 and len(saved_faces) > 0:
            # Yuzni tanib olish
            captured_encoding = face_recognition.face_encodings(captured_image, captured_faces)[0]
            saved_encoding = face_recognition.face_encodings(saved_image, saved_faces)[0]
            match = face_recognition.compare_faces([saved_encoding], captured_encoding)

            if match[0]:
                # Tiriklik tekshiruvi
                if is_liveness_detected(captured_image):
                    return "SUCCESS", "Yuz tiriklik bilan mos keldi!"
                else:
                    return "LIVENESS_FAIL", "Tiriklik aniqlanmadi!"
            else:
                return "FACE_FAIL", "Yuz mos kelmadi!"
        else:
            return "NO_FACE", "Yuz aniqlanmadi!"
    except Exception as e:
        return "ERROR", str(e)


# Kirish sahifasi
# Logger sozlamalari
logger = logging.getLogger(__name__)

@csrf_exempt
def signin_view(request):
    if request.method == 'POST':
        if 'signin_password' in request.POST:  # Parol orqali kirish
            student_id = request.POST.get('student_id')
            password = request.POST.get('password')

            # Firestore'dan foydalanuvchini tekshirish
            users_ref = db.collection('students')  # Talabalar collectioni
            user_ref = users_ref.document(student_id)
            doc = user_ref.get()

            if doc.exists and doc.to_dict().get('password') == password:
                messages.success(request, "Xush kelibsiz!")
                request.session['student_id'] = student_id
                return redirect('home')
            else:
                messages.error(request, "Noto'g'ri ID yoki parol.")
                return render(request, 'signin.html')

        elif 'signin_face' in request.POST:  # Yuzni tanib olish orqali kirish
            student_id = request.POST.get('student_id')
            captured_photo_base64 = request.POST.get('captured_photo')

            try:
                # Firestore'dan foydalanuvchini tekshirish
                users_ref = db.collection('students')  # Talabalar collectioni
                user_ref = users_ref.document(student_id)
                doc = user_ref.get()

                if doc.exists:
                    user_data = doc.to_dict()
                    saved_photo_base64 = user_data.get('photo')

                    # Olingan rasmni va saqlangan rasmni tanib olish
                    if saved_photo_base64:
                        saved_photo_bytes = base64.b64decode(saved_photo_base64.split(',')[1])
                        saved_image = cv2.imdecode(np.frombuffer(saved_photo_bytes, np.uint8), cv2.IMREAD_COLOR)
                        captured_photo_bytes = base64.b64decode(captured_photo_base64.split(',')[1])
                        captured_image = cv2.imdecode(np.frombuffer(captured_photo_bytes, np.uint8), cv2.IMREAD_COLOR)

                        saved_encodings = face_recognition.face_encodings(saved_image)
                        captured_encodings = face_recognition.face_encodings(captured_image)

                        if saved_encodings and captured_encodings:
                            match = face_recognition.compare_faces([saved_encodings[0]], captured_encodings[0])
                            if match[0]:
                                messages.success(request, f"Xush kelibsiz, {user_data.get('firstname')}!")
                                request.session['student_id'] = student_id
                                return redirect('home')
                            else:
                                messages.error(request, "Yuzlar mos kelmadi.")
                        else:
                            messages.error(request, "Yuzni tanib olish imkoni bo'lmadi.")
                    else:
                        messages.error(request, "Foydalanuvchi rasmi mavjud emas.")
                else:
                    messages.error(request, "Foydalanuvchi topilmadi.")
            except Exception as e:
                messages.error(request, f"Xatolik yuz berdi: {str(e)}")
            return render(request, 'signin.html')

    return render(request, 'signin.html')



@csrf_exempt
def home_view(request):
    student_id = request.session.get('student_id')

    if not student_id:
        return redirect('signin')

    try:
        users_ref = db.collection('students').document(student_id)  # Firestore'dan olish
        user = users_ref.get()

        if user.exists:
            user_data = user.to_dict()
            profile_image = user_data.get('photo', '/static/images/default-avatar.png')
            firstname = user_data.get('firstname', 'Ism topilmadi')
            lastname = user_data.get('lastname', 'Familiya topilmadi')
        else:
            profile_image = '/static/images/default-avatar.png'
            firstname = "Ism topilmadi"
            lastname = "Familiya topilmadi"

        context = {
            'profile_image': profile_image,
            'fullname': f"{firstname} {lastname}"
        }
        return render(request, 'talaba/home.html', context)

    except Exception as e:
        return render(request, 'talaba/home.html', {"error": f"Xatolik yuz berdi: {str(e)}"})



def decode_base64_image(base64_string):
    """
    Base64 formatidagi rasmni dekodlash va OpenCV formatiga aylantirish
    """
    try:
        image_data = base64.b64decode(base64_string.split(',')[1])  # "data:image/png;base64," qismini ajratib olish
        np_image = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(np_image, cv2.IMREAD_COLOR)
        return image
    except Exception as e:
        print(f"Rasmni dekodlashda xatolik: {str(e)}")
        return None


# Talaba ma'lumotlarini olish
def get_student_data(student_id):
    try:
        students_ref = db.collection('students')
        student_doc = students_ref.document(student_id).get()

        if student_doc.exists:
            return student_doc.to_dict()  # Foydalanuvchi ma'lumotlarini qaytaradi
        else:
            return None  # Foydalanuvchi topilmadi
    except Exception as e:
        return f"Xatolik yuz berdi: {str(e)}"


# O'qituvchi ma'lumotlarini olish
def get_teacher_data(username):
    try:
        teachers_ref = db.collection('teachers')
        teacher_doc = teachers_ref.document(username).get()

        if teacher_doc.exists:
            return teacher_doc.to_dict()  # O'qituvchining ma'lumotlarini qaytaradi
        else:
            return None  # O'qituvchi topilmadi
    except Exception as e:
        return f"Xatolik yuz berdi: {str(e)}"


def base64_to_image(base64_str):
    img_data = base64.b64decode(base64_str.split(',')[1])
    return cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)


def compare_faces(saved_image, captured_image):
    saved_encodings = face_recognition.face_encodings(saved_image)
    captured_encodings = face_recognition.face_encodings(captured_image)

    if saved_encodings and captured_encodings:
        return face_recognition.compare_faces([saved_encodings[0]], captured_encodings[0])[0]
    return False

@csrf_exempt
def create_exam(request):
    if request.method == "POST":
        exam_id = str(random.randint(10000000, 99999999))  # Tasodifiy 8 xonali ID
        student_id = request.POST.get("student_id")  # Talaba ID
        teacher_id = request.POST.get("teacher_id")  # O'qituvchi ID
        face_id = request.POST.get("face_id")  # Face ID
        fan_id = request.POST.get("fan_id")  # Fan ID
        start_time = request.POST.get("start_time")  # Imtihon boshlanish vaqti

        try:
            # Firestore'da `exam` kolleksiyasiga ma'lumotlarni yozish
            db.collection("exam").document(exam_id).set({
                "exam_id": exam_id,
                "student_id": student_id,
                "teacher_id": teacher_id,
                "face_id": face_id,
                "fan_id": fan_id,
                "start_time": start_time
            })
            return redirect("create_exam")
        except Exception as e:
            return render(request, "admin/imtihon_yaratish.html", {"error": f"Xatolik: {str(e)}"})

    # Ma'lumotlarni boshqa kolleksiyalardan olish
    students = db.collection("students").stream()
    teachers = db.collection("teachers").stream()
    face_ids = db.collection("faceID").stream()
    subjects = db.collection("subjects").stream()  # Fanlar

    context = {
        "students": [{"id": s.id, **s.to_dict()} for s in students],
        "teachers": [{"id": t.id, **t.to_dict()} for t in teachers],
        "face_ids": [{"id": f.id, **f.to_dict()} for f in face_ids],
        "subjects": [{"id": subj.id, **subj.to_dict()} for subj in subjects],
    }
    return render(request, "admin/imtihon_yaratish.html", context)

@csrf_exempt
def create_questions(request):
    if request.method == "POST":
        question_text = request.POST.get("question_text")
        options = [
            request.POST.get("option1"),
            request.POST.get("option2"),
            request.POST.get("option3"),
            request.POST.get("option4"),
        ]
        correct_option = request.POST.get("correct_option")
        fan_id = request.POST.get("fan_id")  # Tanlangan fan_id

        question_id = str(random.randint(10000000, 99999999))  # 8 xonali tasodifiy ID

        try:
            # Savol ma'lumotlarini Firestore'ga yozish
            db.collection("examQuestions").document(question_id).set({
                "id": question_id,
                "question_text": question_text,
                "options": options,
                "correct_option": correct_option,
                "fan_id": fan_id
            })
            return redirect("create_questions")
        except Exception as e:
            return render(request, "admin/create_questions.html", {"error": f"Xatolik: {str(e)}"})

    # Subjects kolleksiyasidan ma'lumotlarni olish
    subjects = db.collection("subjects").stream()
    context = {
        "subjects": [{"id": subject.id, **subject.to_dict()} for subject in subjects]
    }
    return render(request, "admin/create_questions.html", context)

@csrf_exempt
def exam_view(request):
    student_id = request.session.get("student_id")

    if not student_id:
        return redirect("signin")  # Foydalanuvchi tizimga kirmagan bo'lsa, login sahifasiga yo'naltirish

    try:
        # Firestore'dan barcha savollarni olish
        questions_ref = db.collection("examQuestions").stream()
        all_questions = [q.to_dict() for q in questions_ref]

        # Tasodifiy 10 ta savolni tanlash
        selected_questions = random.sample(all_questions, min(len(all_questions), 10))

        # Savollarni sahifaga uzatish
        context = {
            "questions": selected_questions,
        }
        return render(request, "talaba/exam.html", context)

    except Exception as e:
        return render(request, "talaba/exam.html", {"error": f"Xatolik yuz berdi: {str(e)}"})

@csrf_exempt
def exam_submission(request):
    # Sessiyadan foydalanuvchi ID'sini olish
    student_id = request.session.get("student_id")

    if not student_id:
        return redirect("signin")  # Foydalanuvchi tizimga kirmagan bo'lsa, login sahifasiga yo'naltirish

    try:
        # Firestore'dan foydalanuvchi ma'lumotlarini olish
        user_ref = db.collection("students").document(student_id)
        user_doc = user_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict()
            profile_image = user_data.get("photo", "/static/images/default-avatar.png")
            fullname = f"{user_data.get('firstname', 'Ism topilmadi')} {user_data.get('lastname', 'Familiya topilmadi')}"
        else:
            profile_image = "/static/images/default-avatar.png"
            fullname = "Ism va familiya topilmadi"

        # Firestore'dan barcha savollarni olish
        questions_ref = db.collection("examQuestions").stream()
        all_questions = [{"id": q.id, **q.to_dict()} for q in questions_ref]

        # Tasodifiy 10 ta savolni tanlash
        selected_questions = random.sample(all_questions, min(len(all_questions), 10))

        if request.method == "POST":
            # Foydalanuvchining tanlagan javoblarini yig'ish va baholash
            answers = {}
            score = 0
            for question in selected_questions:
                question_id = question.get("id")
                user_answer = request.POST.get(f"question_{question_id}")
                correct_option = question.get("correct_option")

                if user_answer:
                    answers[question_id] = user_answer
                    # To'g'ri javobni baholash
                    if user_answer == correct_option:
                        score += 5

            try:
                # Javoblarni Firestore'ga saqlash
                db.collection("examAnswers").add({
                    "student_id": student_id,
                    "answers": answers,
                    "score": score,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })

                # Muvaffaqiyatli saqlangandan so'ng natijalar sahifasiga yo'naltirish
                return redirect("exam_results")
            except Exception as e:
                return render(request, "talaba/exam.html", {
                    "error": f"Ma'lumotni saqlashda xatolik: {str(e)}",
                    "profile_image": profile_image,
                    "fullname": fullname,
                    "questions": selected_questions
                })

        # GET so'rov bo'lsa, tasodifiy 10 ta savol bilan sahifani yuklash
        return render(request, "talaba/exam.html", {
            "profile_image": profile_image,
            "fullname": fullname,
            "questions": selected_questions
        })

    except Exception as e:
        # Xatolik yuz bersa, sahifaga xabar chiqarish
        return render(request, "talaba/exam.html", {
            "error": f"Xatolik yuz berdi: {str(e)}"
        })

@csrf_exempt
def exam_results(request):
    student_id = request.session.get("student_id")

    if not student_id:
        return redirect("signin")  # Foydalanuvchi tizimga kirmagan bo'lsa, tizimga kirish sahifasiga yo'naltirish

    if request.method == "POST":
        try:
            # Imtihon ma'lumotlarini olish
            exam_id = request.POST.get("exam_id")
            violations = int(request.POST.get("violations", 0))  # Qoidabuzarliklar soni
            answers = {}
            score = 0
            correct_answers = 0
            incorrect_answers = 0

            # Agar qoidabuzarliklar 10 yoki undan ko'p bo'lsa, imtihon muvaffaqiyatsiz tugaydi
            if violations >= 10:
                score = 0  # To‘plangan ball 0 qilinadi
            else:
                # Javoblarni hisoblash
                for key, value in request.POST.items():
                    if key.startswith("question_"):
                        question_id = key.split("_")[1]
                        user_answer = value

                        # Savolni Firestore'dan olish
                        question_ref = db.collection("examQuestions").document(question_id)
                        question_doc = question_ref.get()

                        if question_doc.exists:
                            question_data = question_doc.to_dict()
                            correct_option = question_data.get("correct_option")

                            if user_answer == correct_option:
                                correct_answers += 1
                                score += 5  # Har bir to‘g‘ri javob uchun 5 ball
                            else:
                                incorrect_answers += 1

                        # Javoblarni saqlash
                        answers[question_id] = user_answer

            # Javoblarni va natijalarni Firestore'ga saqlash
            db.collection("examAnswers").add({
                "student_id": student_id,
                "exam_id": exam_id,
                "score": score,
                "violations": violations,
                "correct_answers": correct_answers,
                "incorrect_answers": incorrect_answers,
                "answers": answers,
                "timestamp": firestore.SERVER_TIMESTAMP,
            })

            # Natijalar sahifasiga yo'naltirish
            context = {
                "fullname": f"{request.POST.get('firstname', 'Ism')} {request.POST.get('lastname', 'Familiya')}",
                "student_id": student_id,
                "profile_image": request.POST.get("profile_image", "/static/images/default-avatar.png"),
                "correct_answers": correct_answers,
                "incorrect_answers": incorrect_answers,
                "total_score": score,
                "violations": violations,
            }
            return render(request, "talaba/natija.html", context)

        except Exception as e:
            return render(request, "talaba/natija.html", {"error": f"Xatolik yuz berdi: {str(e)}"})

            # GET so'rovlar uchun sahifani qayta yuklash
        return redirect("exam_results")


def create_questions_with_pdf(request):
    if request.method == "POST":
        # Yuklangan faylni olish
        pdf_file = request.FILES.get("pdf_file")
        num_questions = int(request.POST.get("num_questions", 10))  # Foydalanuvchi kiritgan savollar soni

        if not pdf_file:
            return render(request, "admin/create_questions.html", {"error": "PDF fayl yuklanmagan"})

        try:
            # PDF Faylni saqlash
            fs = FileSystemStorage()
            pdf_path = fs.save(pdf_file.name, pdf_file)
            absolute_pdf_path = fs.path(pdf_path)

            # PDF Fayldan matnni chiqarish
            extracted_text = extract_text_with_pdfplumber(absolute_pdf_path)

            # Tizimni o‘qitish va savollar yaratish
            question_answer_model = pipeline("question-generation")  # HuggingFace pipeline
            questions = question_answer_model(extracted_text)

            # Tasodifiy savollarni tanlash
            generated_questions = random.sample(questions, min(len(questions), num_questions))

            # Savollarni Firestore'ga saqlash
            for question in generated_questions:
                db.collection("examQuestions").add({
                    "question_text": question["question"],
                    "options": question["options"],
                    "correct_option": question["correct_option"]
                })

            # Natija sahifasiga yo‘naltirish
            return redirect("create_questions")
        except Exception as e:
            return render(request, "admin/create_questions.html", {"error": f"Xatolik yuz berdi: {str(e)}"})

    return render(request, "admin/create_questions.html")


def extract_text_with_pdfplumber(pdf_path):
    """
    pdfplumber yordamida PDF dan matnni chiqarish.

    Parameters:
        pdf_path (str): PDF fayl yo'li.

    Returns:
        str: PDF dan chiqarilgan matn.
    """
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text()
        return text if text.strip() else "pdfplumber yordamida matn topilmadi."
    except Exception as e:
        return f"Xatolik yuz berdi: {e}"

# Ishlatish:
pdf_path = "test.pdf"  # Fayl yo'li
print(extract_text_with_pdfplumber(pdf_path))


def face_recognition_algorithm(saved_image, captured_image):
    # Yuzlarni tanish va solishtirish
    saved_encodings = face_recognition.face_encodings(saved_image)
    captured_encodings = face_recognition.face_encodings(captured_image)

    if saved_encodings and captured_encodings:
        match = face_recognition.compare_faces([saved_encodings[0]], captured_encodings[0])
        return match[0]  # True yoki False

    return False

@csrf_exempt
# Talabaning Imtihonlar Sahifasi
def student_exams(request):
    # Sessiyadan foydalanuvchi ID'sini olish
    student_id = request.session.get("student_id")

    if not student_id:
        return redirect("signin")  # Agar foydalanuvchi tizimga kirmagan bo'lsa, login sahifasiga yo'naltirish

    try:
        # Talaba ma'lumotlarini olish
        student_ref = db.collection("students").document(student_id)
        student_doc = student_ref.get()

        if not student_doc.exists:
            return render(request, "talaba/student_exams.html", {"error": "Talaba ma'lumotlari topilmadi."})

        student_data = student_doc.to_dict()
        fullname = f'{student_data.get("firstname", "Ism")} {student_data.get("lastname", "Familiya")}'
        profile_image = student_data.get("photo", "/static/images/default-avatar.png")

        # Foydalanuvchi bilan bog‘liq barcha imtihonlarni olish
        exams_ref = db.collection("exam").where("student_id", "==", student_id).stream()
        exams = []

        for exam in exams_ref:
            exam_data = exam.to_dict()

            # Fan ma'lumotlarini olish
            subject_ref = db.collection("subjects").document(exam_data["fan_id"])
            subject_doc = subject_ref.get()
            subject_name = subject_doc.to_dict().get("fan_nomi", "Fan nomi topilmadi") if subject_doc.exists else "Fan nomi topilmadi"

            # O'qituvchi ma'lumotlarini olish
            teacher_ref = db.collection("teachers").document(exam_data["teacher_id"])
            teacher_doc = teacher_ref.get()
            teacher_name = f'{teacher_doc.to_dict().get("firstname", "Ism")} {teacher_doc.to_dict().get("lastname", "Familiya")}' if teacher_doc.exists else "O'qituvchi topilmadi"

            # Imtihon ma'lumotlarini ro‘yxatga qo‘shish
            exams.append({
                "exam_id": exam_data["exam_id"],
                "subject_name": subject_name,
                "teacher_name": teacher_name,
                "start_time": exam_data.get("start_time", "Boshlanish vaqti mavjud emas")
            })

        # Sahifaga ma'lumotlarni yuborish
        context = {
            "exams": exams,
            "fullname": fullname,
            "profile_image": profile_image,
        }
        return render(request, "talaba/student_exams.html", context)

    except Exception as e:
        # Xatolik yuz bersa, sahifaga xabar chiqarish
        return render(request, "talaba/student_exams.html", {"error": f"Xatolik yuz berdi: {str(e)}"})






# Ma'lumot yozish funksiyasi
def add_student_to_firestore(student_id, name, email):
    student_ref = db.collection('students').document(student_id)
    student_ref.set({
        'name': name,
        'email': email
    })


# Ma'lumot o‘qish funksiyasi
def get_student_from_firestore(student_id):
    student_ref = db.collection('students').document(student_id)
    doc = student_ref.get()
    if doc.exists:
        return doc.to_dict()
    else:
        return None


def get_student(request, student_id):
    student_data = get_student_from_firestore(student_id)
    return render(request, 'talaba/student_detail.html', {'student': student_data})


def exam_view(request):
    return render(request, 'talaba/exam.html', {'exam': exam_view})


def create_subject(request):
    if request.method == "POST":
        fan_id = str(random.randint(10000000, 99999999))  # 8 xonali tasodifiy ID
        fan_nomi = request.POST.get("fan_nomi")
        fan_turi = request.POST.get("fan_turi")
        teacher_id = request.POST.get("teacher_id")
        student_id = request.POST.getlist("student_id")  # Bir nechta talabalar
        savol_id = request.POST.getlist("savol_id")  # Bir nechta savollar

        try:
            # Fan ma'lumotlarini Firestore'ga yozish
            db.collection("subjects").document(fan_id).set({
                "fan_id": fan_id,
                "fan_nomi": fan_nomi,
                "fan_turi": fan_turi,
                "teacher_id": teacher_id,
                "student_id": student_id,
                "savol_id": savol_id
            })
            return redirect("create_subject")
        except Exception as e:
            return render(request, "admin/fan_yaratish.html", {"error": f"Xatolik: {str(e)}"})

    # Teachers va Students kolleksiyalarini olish
    teachers = db.collection("teachers").stream()
    students = db.collection("students").stream()
    exam_questions = db.collection("examQuestions").stream()

    context = {
        "teachers": [{"id": t.id, **t.to_dict()} for t in teachers],
        "students": [{"id": s.id, **s.to_dict()} for s in students],
        "exam_questions": [{"id": q.id, **q.to_dict()} for q in exam_questions],
    }

    return render(request, "admin/fan_yaratish.html", context)


# Faqat superuser uchun kirishni cheklash
def is_superuser(user):
    return user.is_superuser


# Login sahifasi
def admin_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_superuser:
                login(request, user)
                return redirect('admin_dashboard')
            else:
                messages.error(request, "You do not have permission to access this page.")
        else:
            messages.error(request, "Invalid username or password.")
    return render(request, 'admin/login.html')


# Admin Dashboard
@login_required
@user_passes_test(is_superuser)
def admin_dashboard(request):
    students_ref = db.collection('students')
    students = [
        doc.to_dict() for doc in students_ref.stream()
        if 'student_id' in doc.to_dict()  # student_id mavjudligini tekshirish
    ]
    teachers_ref = db.collection('teachers')
    teachers = [
        doc.to_dict() for doc in teachers_ref.stream()
    ]
    context = {
        'student_data': students,
        'teacher_data': teachers,
    }
    return render(request, 'admin/admin_dashboard.html', context)


# Talaba qo'shish funksiyasi
def add_student(request):
    if request.method == 'POST':
        # POST ma'lumotlarini olish
        firstname = request.POST.get('firstname')
        lastname = request.POST.get('lastname')
        email = request.POST.get('email')
        student_id = request.POST.get('student_id')
        photo = request.POST.get('photo')

        # Firestore'ga yangi hujjat qo'shish
        db.collection('students').document(student_id).set({
            'firstname': firstname,
            'lastname': lastname,
            'email': email,
            'student_id': student_id,
            'photo': photo,
        })
        return redirect('admin_dashboard')  # Sahifani qayta yuklash
    return redirect('admin_dashboard')


# Talaba o'chirish funksiyasi
def delete_student(request, student_id):
    if request.method == 'POST':
        # Firestore'dan talabani o'chirish
        db.collection('students').document(student_id).delete()
        return redirect('admin_dashboard')
    return redirect('admin_dashboard')


# O'qituvchi qo'shish funksiyasi
def add_teacher(request):
    if request.method == 'POST':
        # POST ma'lumotlarini olish
        firstname = request.POST.get('firstname')
        lastname = request.POST.get('lastname')
        email = request.POST.get('email')
        username = request.POST.get('username')
        photo = request.POST.get('photo')

        # Firestore'ga yangi hujjat qo'shish
        db.collection('teachers').document(username).set({
            'firstname': firstname,
            'lastname': lastname,
            'email': email,
            'username': username,
            'photo': photo,
        })
        return redirect('admin_dashboard')
    return redirect('admin_dashboard')


# O'qituvchi o'chirish funksiyasi
def delete_teacher(request, teacher_id):
    if request.method == 'POST':
        # Firestore'dan o'qituvchini o'chirish
        db.collection('teachers').document(teacher_id).delete()
        return redirect('admin_dashboard')
    return redirect('admin_dashboard')


@login_required
def redirect_based_on_role(request):
    try:
        # Foydalanuvchining emailini yoki student_id ni session orqali olish
        user_username = request.user.username

        # Firestore'dan foydalanuvchini qidirish
        users_ref = db.collection('students')
        query = users_ref.where('email', '==', user_username).limit(1).stream()

        user_data = None
        for doc in query:
            user_data = doc.to_dict()

        if not user_data:
            return redirect('home')  # Foydalanuvchi topilmasa, asosiy sahifaga yo'naltirish

        # Foydalanuvchi roli bo‘yicha yo‘naltirish
        if user_data.get('is_student', False):
            return redirect('student_profile')
        elif user_data.get('is_teacher', False):
            return redirect('teacher_profile')
        else:
            return redirect('home')

    except Exception as e:
        print(f"Xatolik yuz berdi: {e}")
        return redirect('home')


@login_required
def redirect_based_on_role(request):
    if hasattr(request.user, 'is_teacher') and request.user.is_teacher:
        return redirect('teacher_profile')  # Teacher Profile sahifasiga yo'naltirish
    elif hasattr(request.user, 'is_student') and request.user.is_student:
        return redirect('student_profile')  # Student Profile sahifasiga yo'naltirish
    else:
        return redirect('home')  # Home sahifasiga yo'naltirish
