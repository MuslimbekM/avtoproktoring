import base64
import io
import json
import os.path
import random
import time

import cv2
import dlib
import face_recognition
import numpy as np
import requests
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.messages.storage import default_storage
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from firebase_admin import firestore, storage
from io import BytesIO
from PIL import Image
import face_recognition

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


def upload_image_to_storage(image_base64):
    # Rasmni Base64 formatidan faylga aylantirish
    image_data = base64.b64decode(image_base64.split(',')[1])
    image = Image.open(BytesIO(image_data))

    # Foydalanuvchi nomi asosida rasmni saqlash
    image_name = f"user_{generate_student_id()}.png"
    blob = bucket.blob(image_name)

    # Faylni yuklash
    blob.upload_from_string(image_data, content_type='image/png')

    # Rasm URL'sini olish
    return blob.public_url


def compare_faces(saved_photo_url, captured_photo_base64):
    # Saqlangan rasmni URL'dan olish
    saved_photo_data = requests.get(saved_photo_url).content
    saved_image = Image.open(BytesIO(saved_photo_data))
    saved_encodings = face_recognition.face_encodings(saved_image)

    if not saved_encodings:
        return False

    # Yangi olingan rasmni Base64 formatidan dekodlash
    captured_photo_data = base64.b64decode(captured_photo_base64.split(',')[1])
    captured_image = Image.open(BytesIO(captured_photo_data))
    captured_encodings = face_recognition.face_encodings(captured_image)

    if not captured_encodings:
        return False

    # Yuzni solishtirish
    match = face_recognition.compare_faces([saved_encodings[0]], captured_encodings[0])
    return match[0]


@csrf_exempt
def signup_view(request):
    if request.method == 'POST':
        role = request.POST.get('role')  # "student" yoki "teacher"
        firstname = request.POST.get('firstname')
        lastname = request.POST.get('lastname')
        middlename = request.POST.get('middlename')
        email = request.POST.get('email')
        password = request.POST.get('pass')
        re_password = request.POST.get('re_pass')
        photo_base64 = request.POST.get('captured_photo')
        subject = request.POST.get('subject', None)  # Only for teacher role

        # Parollarni tekshirish
        if password != re_password:
            messages.error(request, "Parollar bir xil bo'lishi kerak.")
            return render(request, 'signup.html')

        try:


            # Talaba yoki o'qituvchi roli bo'yicha tekshirish
            if role == 'student':
                # Talaba kolleksiyasiga yozish
                students_ref = db.collection('students')
                student_id = f"ST{str(int(time.time()))}"  # Yangi student_id yaratish
                # Bunday foydalanuvchi mavjudligini tekshirish
                existing_user = students_ref.where('firstname', '==', firstname).where('lastname', '==',
                                                                                                 lastname).where(
                    'middlename', '==', middlename).where('email', '==', email).stream()

                if any(existing_user):  # Foydalanuvchi allaqachon mavjud
                    messages.error(request, "Bunday foydalanuvchi ma'lumotlar bazasida mavjud.")
                    return render(request, 'signup.html')

                students_ref.document(student_id).set({
                    'student_id': student_id,
                    'firstname': firstname,
                    'lastname': lastname,
                    'middlename': middlename,
                    'email': email,
                    'password': password,
                    'photo': photo_base64
                })

                messages.success(request, "Talaba sifatida muvaffaqiyatli ro'yxatdan o'tdingiz!")
                return redirect('signin')

            elif role == 'teacher':
                # O'qituvchilar kolleksiyasiga yozish
                teachers_ref = db.collection('teachers')
                username = f"{firstname.lower()}_{lastname.lower()}"

                # Bunday foydalanuvchi mavjudligini tekshirish
                existing_user = teachers_ref.where('firstname', '==', firstname).where('lastname', '==',
                                                                                       lastname).where(
                    'middlename', '==', middlename).where('email', '==', email).stream()

                if any(existing_user):  # Foydalanuvchi allaqachon mavjud
                    messages.error(request, "Bunday foydalanuvchi ma'lumotlar bazasida mavjud.")
                    return render(request, 'signup.html')

                teachers_ref.document(username).set({
                    'username': username,
                    'firstname': firstname,
                    'lastname': lastname,
                    'middlename': middlename,
                    'email': email,
                    'password': password,
                    'subject': subject,
                    'photo': photo_base64
                })

                messages.success(request, "O'qituvchi sifatida muvaffaqiyatli ro'yxatdan o'tdingiz!")
                return redirect('signin')

        except Exception as e:
            messages.error(request, f"Xatolik yuz berdi: {str(e)}")

    return render(request, 'signup.html')


def check_face(request):
    if request.method == "POST":
        # Rasmni olish
        data = json.loads(request.body)
        captured_photo_base64 = data.get("captured_image")
        student_id_face = data.get("student_id_face")

        # Base64 rasmni dekodlash
        image_data = base64.b64decode(captured_photo_base64.split(',')[1])
        image = Image.open(BytesIO(image_data))

        # Rasmni vaqtinchalik faylga saqlash
        image_path = save_image_to_temp_file(image)

        try:
            # Firestore'dan foydalanuvchini olish
            user_ref = db.collection('students').document(student_id_face)
            user = user_ref.get()

            if user.exists:
                user_data = user.to_dict()
                saved_photo_base64 = user_data.get('photo')

                # Saqlangan rasmni va olingan rasmni tanib olish
                if saved_photo_base64:
                    saved_photo_bytes = base64.b64decode(saved_photo_base64.split(',')[1])
                    saved_image = face_recognition.load_image_file(BytesIO(saved_photo_bytes))
                    captured_image = face_recognition.load_image_file(image_path)

                    saved_encodings = face_recognition.face_encodings(saved_image)
                    captured_encodings = face_recognition.face_encodings(captured_image)

                    if saved_encodings and captured_encodings:
                        match = face_recognition.compare_faces([saved_encodings[0]], captured_encodings[0])
                        return JsonResponse({'match': match[0]})
                    else:
                        return JsonResponse({'error': 'Yuzni tanib olishda xatolik yuz berdi.'})
                else:
                    return JsonResponse({'error': 'Foydalanuvchi rasmi mavjud emas.'})
            else:
                return JsonResponse({'error': 'Foydalanuvchi topilmadi.'})
        except Exception as e:
            return JsonResponse({'error': f'Xatolik yuz berdi: {str(e)}'})

    return JsonResponse({'error': 'Invalid request'}, status=400)


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


@csrf_exempt
def signin_view(request):
    if request.method == 'POST':
        # Talaba va o'qituvchi uchun rolni tanlash
        role = request.POST.get('role')

        # Parol orqali kirish (Student ID va Parol)
        if 'signin_password' in request.POST:
            student_id = request.POST.get('student_id')
            password = request.POST.get('password')

            try:
                if role == 'student':
                    # Talaba uchun ma'lumotlarni olish
                    users_ref = db.collection('students').document(student_id)
                elif role == 'teacher':
                    # O'qituvchi uchun ma'lumotlarni olish
                    users_ref = db.collection('teachers').document(student_id)

                doc = users_ref.get()
                if doc.exists:
                    user_data = doc.to_dict()
                    if user_data.get('password') == password:
                        messages.success(request, f"Xush kelibsiz, {user_data.get('firstname')} {user_data.get('lastname')}!")
                        return redirect('home')  # Home pagega redirect qilish
                    else:
                        messages.error(request, "Noto'g'ri parol.")
                else:
                    messages.error(request, "Foydalanuvchi topilmadi.")
            except Exception as e:
                messages.error(request, f"Xatolik yuz berdi: {str(e)}")

        # Yuzni tanib olish orqali kirish (Student ID va Yuzni tanish)
        elif 'signin_face' in request.POST:
            student_id_face = request.POST.get('student_id_face')
            captured_photo_base64 = request.POST.get('captured_photo')

            try:
                if role == 'student':
                    # Talaba uchun ma'lumotlarni olish
                    users_ref = db.collection('students').document(student_id_face)
                elif role == 'teacher':
                    # O'qituvchi uchun ma'lumotlarni olish
                    users_ref = db.collection('teachers').document(student_id_face)

                doc = users_ref.get()
                if doc.exists:
                    user_data = doc.to_dict()
                    saved_photo_base64 = user_data.get('photo')

                    # Yuzni solishtirish
                    if saved_photo_base64:
                        # Saqlangan rasmni dekodlash
                        saved_photo_bytes = base64.b64decode(saved_photo_base64.split(',')[1])
                        saved_image = cv2.imdecode(np.frombuffer(saved_photo_bytes, np.uint8), cv2.IMREAD_COLOR)
                        captured_photo_bytes = base64.b64decode(captured_photo_base64.split(',')[1])
                        captured_image = cv2.imdecode(np.frombuffer(captured_photo_bytes, np.uint8), cv2.IMREAD_COLOR)

                        saved_encodings = face_recognition.face_encodings(saved_image)
                        captured_encodings = face_recognition.face_encodings(captured_image)

                        if saved_encodings and captured_encodings:
                            match = face_recognition.compare_faces([saved_encodings[0]], captured_encodings[0])
                            if match[0]:  # Yuzlar mos kelsa
                                messages.success(request, f"Xush kelibsiz, {user_data.get('firstname')} {user_data.get('lastname')}!")
                                return redirect('home')
                            else:
                                messages.error(request, "Yuzlar mos kelmadi.")
                        else:
                            messages.error(request, "Yuzni tanib olish imkoni bo'lmadi.")
                else:
                    messages.error(request, "Foydalanuvchi topilmadi.")
            except Exception as e:
                messages.error(request, f"Xatolik yuz berdi: {str(e)}")

    return render(request, 'signin.html')


def home_view(request):
    # Sessiondan foydalanuvchi ID'sini olish
    student_id = request.session.get('student_id')

    # Agar foydalanuvchi ID mavjud bo'lmasa, tizimga kirish sahifasiga yo'naltirish
    if not student_id:
        return redirect('signin')

    try:
        # Firestore'dan foydalanuvchini student_id bo‘yicha qidirish
        users_ref = db.collection('students').where('student_id', '==', student_id).stream()
        user_info = None

        # Hujjatlar ichidan birinchi mos keladigan foydalanuvchini olish
        for user in users_ref:
            user_info = user.to_dict()
            break

        if user_info:
            # Foydalanuvchi mavjud bo'lsa, rasm va ismini olish
            profile_image = user_info.get('photo', '/path/to/default/image.jpg')
            firstname = user_info.get('firstname', 'Firstname')
            lastname = user_info.get('lastname', 'Lastname')
            fullname = f"{lastname} {firstname}"
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
    try:
        # Talabalar va o'qituvchilar kolleksiyalarini olish
        students_ref = db.collection('students')
        teachers_ref = db.collection('teachers')

        # Talabalar va o'qituvchilarni olish
        students = students_ref.stream()
        teachers = teachers_ref.stream()

        # Talabalar va o'qituvchilarni ro'yxatga olish
        student_data = [student.to_dict() for student in students]
        teacher_data = [teacher.to_dict() for teacher in teachers]

        context = {
            'student_data': student_data,
            'teacher_data': teacher_data
        }

        return render(request, 'admin/admin_dashboard.html', context)

    except Exception as e:
        messages.error(request, f"Xatolik yuz berdi: {str(e)}")
        return render(request, 'admin/admin_dashboard.html')


def add_student(request):
    if request.method == 'POST':
        firstname = request.POST.get('firstname')
        lastname = request.POST.get('lastname')
        student_id = request.POST.get('student_id')
        email = request.POST.get('email')
        password = request.POST.get('password')
        photo = request.POST.get('photo')

        try:
            student_ref = db.collection('students').document(student_id)
            student_ref.set({
                'firstname': firstname,
                'lastname': lastname,
                'student_id': student_id,
                'email': email,
                'password': password,
                'photo': photo
            })
            messages.success(request, "Talaba muvaffaqiyatli qo'shildi.")
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Xatolik yuz berdi: {str(e)}")

    return render(request, 'admin/add_student.html')


def edit_student(request, student_id):
    student_ref = db.collection('students').document(student_id)
    student = student_ref.get()

    if student.exists:
        student_data = student.to_dict()
        if request.method == 'POST':
            student_ref.update({
                'firstname': request.POST.get('firstname'),
                'lastname': request.POST.get('lastname'),
                'email': request.POST.get('email'),
                'password': request.POST.get('password')
            })
            messages.success(request, "Talaba ma'lumotlari yangilandi.")
            return redirect('admin_dashboard')

        return render(request, 'edit_student.html', {'student': student_data})

    messages.error(request, "Talaba topilmadi.")
    return redirect('admin_dashboard')


def delete_student(request, student_id):
    try:
        student_ref = db.collection('students').document(student_id)
        student_ref.delete()
        messages.success(request, "Talaba muvaffaqiyatli o'chirildi.")
    except Exception as e:
        messages.error(request, f"Xatolik yuz berdi: {str(e)}")
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
