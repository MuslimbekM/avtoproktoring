import base64
import os.path
import random

import cv2
import dlib
import face_recognition
import numpy as np
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from firebase_admin import firestore, storage

# Firestore obyekti
db = firestore.client()
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

def save_captured_photo_to_firestore(captured_photo, email):
    # Base64 ma'lumotni faylga aylantirish
    format, imgstr = captured_photo.split(';base64,')
    ext = format.split('/')[-1]
    photo_data = base64.b64decode(imgstr)

    # Firebase Storage papkasida fayl nomi
    bucket = storage.bucket()
    blob = bucket.blob(f"user_photos/{email}.{ext}")
    blob.upload_from_string(photo_data, content_type=f"image/{ext}")

    # Fayl URL'sini qaytarish
    return blob.public_url

@csrf_exempt
def signup_view(request):
    if request.method == 'POST':
        role = request.POST.get('role')  # "student" yoki "teacher"
        firstname = request.POST.get('firstname')
        lastname = request.POST.get('lastname')
        email = request.POST.get('email')
        password = request.POST.get('pass')
        re_password = request.POST.get('re_pass')
        photo_base64 = request.POST.get('captured_photo')

        if password != re_password:
            messages.error(request, "Parollar bir xil bo'lishi kerak.")
            return render(request, 'signup.html')

        try:
            if role == 'student':
                # Talabalar kolleksiyasiga yozish
                student_id = generate_student_id()  # Tasodifiy ID
                students_ref = db.collection('students')
                existing_students = students_ref.where('email', '==', email).stream()

                if any(existing_students):  # Email mavjudligini tekshirish
                    messages.error(request, "Bunday email allaqachon mavjud.")
                    return render(request, 'signup.html')

                students_ref.document(student_id).set({
                    'student_id': student_id,
                    'firstname': firstname,
                    'lastname': lastname,
                    'email': email,
                    'password': password,
                    'photo': photo_base64
                })
                messages.success(request, "Talaba sifatida muvaffaqiyatli ro'yxatdan o'tdingiz!")
                return redirect('signin')

            elif role == 'teacher':
                # O'qituvchilar kolleksiyasiga yozish
                username = f"{firstname.lower()}_{lastname.lower()}"  # Username yaratish
                teachers_ref = db.collection('teachers')
                existing_teachers = teachers_ref.where('email', '==', email).stream()

                if any(existing_teachers):  # Email mavjudligini tekshirish
                    messages.error(request, "Bunday email allaqachon mavjud.")
                    return render(request, 'signup.html')

                teachers_ref.document(username).set({
                    'username': username,
                    'firstname': firstname,
                    'lastname': lastname,
                    'email': email,
                    'password': password,
                    'photo': photo_base64
                })
                messages.success(request, "O'qituvchi sifatida muvaffaqiyatli ro'yxatdan o'tdingiz!")
                return redirect('signin')

        except Exception as e:
            messages.error(request, f"Xatolik yuz berdi: {str(e)}")

    return render(request, 'signup.html')


@csrf_exempt
# Kirish funksiyasi
def signin_view(request):
    if request.method == 'POST':
        # Parol orqali kirish
        if 'signin_password' in request.POST:
            student_id = request.POST.get('student_id')
            password = request.POST.get('password')

            try:
                # Talaba yoki o'qituvchini Firestore'dan tekshirish
                user_ref = db.collection('students').document(student_id)
                user = user_ref.get()

                if user.exists:
                    user_data = user.to_dict()
                    if user_data.get('password') == password:  # Parolni tekshirish
                        # Foydalanuvchi ma'lumotlarini saqlash (session yoki cookie orqali)
                        request.session['student_id'] = student_id
                        messages.success(request, f"Xush kelibsiz, {user_data.get('firstname')} {user_data.get('lastname')}!")
                        return redirect('home')  # Home sahifaga yo'naltirish
                    else:
                        messages.error(request, "Noto'g'ri parol.")
                else:
                    messages.error(request, "Foydalanuvchi topilmadi.")
            except Exception as e:
                messages.error(request, f"Xatolik yuz berdi: {str(e)}")

        # Yuzni tanib olish orqali kirish
        elif 'signin_face' in request.POST:
            student_id = request.POST.get('student_id_face')
            captured_photo_base64 = request.POST.get('captured_photo')

            try:
                # Firestore'dan foydalanuvchini olish
                user_ref = db.collection('students').document(student_id)
                user = user_ref.get()

                if user.exists:
                    user_data = user.to_dict()
                    saved_photo_base64 = user_data.get('photo')

                    # Saqlangan rasmni va olingan rasmni tanib olish
                    if saved_photo_base64:
                        saved_photo_bytes = base64.b64decode(saved_photo_base64.split(',')[1])
                        saved_image = cv2.imdecode(np.frombuffer(saved_photo_bytes, np.uint8), cv2.IMREAD_COLOR)
                        captured_photo_bytes = base64.b64decode(captured_photo_base64.split(',')[1])
                        captured_image = cv2.imdecode(np.frombuffer(captured_photo_bytes, np.uint8), cv2.IMREAD_COLOR)

                        saved_encodings = face_recognition.face_encodings(saved_image)
                        captured_encodings = face_recognition.face_encodings(captured_image)

                        if saved_encodings and captured_encodings:
                            match = face_recognition.compare_faces([saved_encodings[0]], captured_encodings[0])
                            if match[0]:  # Yuzlar mos kelsa
                                request.session['student_id'] = student_id
                                messages.success(request, f"Xush kelibsiz, {user_data.get('firstname')} {user_data.get('lastname')}!")
                                return redirect('home')  # Home sahifaga yo'naltirish
                            else:
                                messages.error(request, "Yuzlar mos kelmadi.")
                        else:
                            messages.error(request, "Yuzni tanib olish imkoni bo'lmadi.")
                else:
                    messages.error(request, "Foydalanuvchi topilmadi.")
            except Exception as e:
                messages.error(request, f"Xatolik yuz berdi: {str(e)}")

    return render(request, 'signin.html')

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


def exam_submission(request):
    if request.method == "POST":
        # Formadan kelgan javoblarni olish
        question1 = request.POST.get("question1")
        question2 = request.POST.get("question2")

        try:
            # Ma'lumotlarni Firestore'ga yozish
            db.collection("examAnswers").add({
                "question1": question1,
                "question2": question2,
                "timestamp": firestore.SERVER_TIMESTAMP
            })

            # Muvaffaqiyatli saqlangandan so'ng 'exam_results' sahifasiga yo'naltirish
            return redirect("exam_results")
        except Exception as e:
            return render(request, "talaba/exam.html", {"error": f"Ma'lumotni saqlashda xatolik: {e}"})

    return render(request, "talaba/exam.html")


def exam_results(request):
    try:
        # Firestore'dan barcha hujjatlarni olish
        results_ref = db.collection("examAnswers").stream()
        results = []

        for doc in results_ref:
            data = doc.to_dict()
            results.append({
                "question": data.get("question1", "Savol yo'q"),
                "answer": data.get("answer1", "Javob yo'q")
            })

        # Ma'lumotlarni 'natija.html' fayliga uzatish
        return render(request, "talaba/natija.html", {"results": results})
    except Exception as e:
        return render(request, "talaba/natija.html", {"error": f"Natijalarni olishda xatolik: {e}"})


def face_recognition_algorithm(saved_image, captured_image):
    # Yuzlarni tanish va solishtirish
    saved_encodings = face_recognition.face_encodings(saved_image)
    captured_encodings = face_recognition.face_encodings(captured_image)

    if saved_encodings and captured_encodings:
        match = face_recognition.compare_faces([saved_encodings[0]], captured_encodings[0])
        return match[0]  # True yoki False

    return False


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


def home_view(request):
    # Sessiondan foydalanuvchi ID'sini olish
    student_id = request.session.get('student_id')

    # Agar foydalanuvchi ID mavjud bo'lmasa, tizimga kirish sahifasiga yo'naltirish
    if not student_id:
        return redirect('signin')

    try:
        # Firestore'dan foydalanuvchini student_id bo‘yicha qidirish
        users_ref = db.collection('students').document(student_id)
        user_info = users_ref.get()

        if user_info.exists:
            user_data = user_info.to_dict()

            # Foydalanuvchining rasm va ismi
            profile_image = user_data.get('photo', '/path/to/default/image.jpg')  # Agar rasm mavjud bo'lmasa, default rasm
            fullname = f"{user_data.get('firstname', 'Firstname')} {user_data.get('lastname', 'Lastname')}"
        else:
            profile_image = '/path/to/default/image.jpg'
            fullname = "Unknown User"

        context = {
            'profile_image': profile_image,
            'fullname': fullname
        }
        return render(request, 'talaba/home.html', context)

    except Exception as e:
        # Xatolik yuz bersa xatolik xabarini ko'rsatish
        return render(request, 'talaba/home.html', {"error": f"Xatolik yuz berdi: {str(e)}"})


def exam_view(request):
    return render(request, 'talaba/exam.html', {'exam': exam_view})


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
    return render(request, 'admin/admin_dashboard.html')


@login_required
def redirect_based_on_role(request):
    try:
        # Foydalanuvchining emailini yoki student_id ni session orqali olish
        user_username = request.user.username

        # Firestore'dan foydalanuvchini qidirish
        users_ref = db.collection('users')
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
