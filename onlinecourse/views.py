from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from django.db import transaction

from .models import Course, Enrollment, Question, Choice, Submission


def registration_request(request):
    context = {}

    if request.method == 'GET':
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)

    username = request.POST['username']
    password = request.POST['psw']
    first_name = request.POST['firstname']
    last_name = request.POST['lastname']

    if not User.objects.filter(username=username).exists():
        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=password
        )
        login(request, user)
        return redirect('onlinecourse:index')

    context['message'] = 'User already exists.'
    return render(request, 'onlinecourse/user_registration_bootstrap.html', context)


def login_request(request):
    context = {}

    if request.method == 'POST':
        user = authenticate(
            username=request.POST['username'],
            password=request.POST['psw']
        )

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = 'Invalid username or password.'

    return render(request, 'onlinecourse/user_login_bootstrap.html', context)


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    return user.is_authenticated and Enrollment.objects.filter(
        user=user, course=course
    ).exists()


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        courses = Course.objects.order_by('-total_enrollment')[:10]

        for course in courses:
            course.is_enrolled = check_if_enrolled(
                self.request.user, course
            )

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    if request.user.is_authenticated:
        if not check_if_enrolled(request.user, course):
            Enrollment.objects.create(
                user=request.user,
                course=course,
                mode='honor'
            )
            course.total_enrollment += 1
            course.save()

    return HttpResponseRedirect(
        reverse('onlinecourse:course_details', args=(course.id,))
    )


def extract_answers(request):
    submitted_answers = []

    for key in request.POST:
        if key.startswith('choice_'):
            for value in request.POST.getlist(key):
                try:
                    submitted_answers.append(int(value))
                except (ValueError, TypeError):
                    pass

    return submitted_answers


@login_required
@require_POST
def submit(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    enrollment = get_object_or_404(
        Enrollment, user=request.user, course=course
    )

    selected_ids = extract_answers(request)

    selected_choices = Choice.objects.filter(
        id__in=selected_ids,
        question__course=course
    )

    with transaction.atomic():
        submission = Submission.objects.create(enrollment=enrollment)
        submission.choices.set(selected_choices)

    return redirect(
        'onlinecourse:show_exam_result',
        course_id=course.id,
        submission_id=submission.id
    )


@login_required
def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__course=course,
        enrollment__user=request.user
    )

    question_results = []
    total_score = 0
    total_possible_score = 0

    for question in Question.objects.filter(course=course):
        correct_choices = question.choice_set.filter(is_correct=True)
        selected_choices = submission.choices.filter(question=question)

        correct_ids = set(
            correct_choices.values_list('id', flat=True)
        )
        selected_ids = set(
            selected_choices.values_list('id', flat=True)
        )

        is_correct = bool(correct_ids) and correct_ids == selected_ids
        score = question.grade if is_correct else 0

        total_score += score
        total_possible_score += question.grade

        question_results.append({
            'question': question,
            'selected_choices': selected_choices,
            'is_correct': is_correct,
            'score': score,
        })

    grade = (
        round(total_score / total_possible_score * 100)
        if total_possible_score else 0
    )

    context = {
        'course': course,
        'submission': submission,
        'grade': grade,
        'total_score': total_score,
        'total_possible_score': total_possible_score,
        'question_results': question_results,
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context
    )