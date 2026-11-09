import os
from decimal import Decimal
import razorpay
import re

from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes
from django.contrib.auth import get_user_model, authenticate, login as auth_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db import IntegrityError
from django.db.models import Count, Sum
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import (
    Tenant,
    Channel,
    SubChannel,
    Course,
    Learner,
    Enrollment,
    Payment,
    Video,
    Document,
    Transcript,
    LearnerProfile,
    TenantAdminProfile,
)


# ==========================================
# TENANT API
# ==========================================

@api_view(["GET"])
def tenant_list(request):
    tenants = Tenant.objects.values(
        "tenant_id",
        "tenant_name",
        "domain",
        "created_at",
    )
    return Response(list(tenants))


# ==========================================
# COURSE API
# ==========================================

@api_view(["GET"])
def course_list(request):
    courses = list(Course.objects.values(
        "course_id",
        "tenant_id",
        "sub_channel_id",
        "course_name",
        "description",
        "price",
        "created_at",
    ))

    subchannels = {
        item["sub_channel_id"]: item
        for item in SubChannel.objects.values(
            "sub_channel_id", "channel_id", "sub_channel_name"
        )
    }

    channels = {
        item["channel_id"]: item["channel_name"]
        for item in Channel.objects.values("channel_id", "channel_name")
    }

    video_summaries = {
        item["course_id"]: item
        for item in Video.objects.values("course_id").annotate(
            video_count=Count("video_id"),
            total_video_minutes=Sum("duration_minutes"),
        )
    }

    for course in courses:
        subchannel = subchannels.get(course["sub_channel_id"], {})
        channel_id = subchannel.get("channel_id")
        video_info = video_summaries.get(course["course_id"], {})

        course["category"] = subchannel.get("sub_channel_name")
        course["channel"] = channels.get(channel_id)
        course["video_count"] = video_info.get("video_count", 0)
        course["total_video_minutes"] = (
            video_info.get("total_video_minutes") or 0
        )

    return Response(courses)


# ==========================================
# LEARNER API
# ==========================================

@api_view(["GET"])
def learner_list(request):
    learners = Learner.objects.values(
        "learner_id",
        "tenant_id",
        "learner_name",
        "email",
        "phone",
        "created_at",
    )
    return Response(list(learners))


# ==========================================
# ENROLLMENT API
# ==========================================


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def enrollment_list(request):
    try:
        profile = LearnerProfile.objects.select_related(
            "learner"
        ).get(user=request.user)

    except LearnerProfile.DoesNotExist:
        return Response(
            {"error": "Learner profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    learner = profile.learner
    tenant_id = learner.tenant_id

    # GET: Retrieve the learner's existing enrolments
    if request.method == "GET":
        enrollments = list(
            Enrollment.objects.filter(
                learner_id=learner.learner_id,
                tenant_id=tenant_id,
            ).values(
                'enrollment_id',
                'tenant_id',
                'learner_id',
                'course_id',
                'enrollment_date',
                'enrollment_status',
            )
        )

        enrollment_ids = [item['enrollment_id'] for item in enrollments]
        course_ids = [item['course_id'] for item in enrollments]

        courses = {
            course.course_id: course
            for course in Course.objects.filter(
                tenant_id=tenant_id,
                course_id__in=course_ids,
            )
        }

        payments = Payment.objects.filter(
            tenant_id=tenant_id,
            enrollment_id__in=enrollment_ids,
        ).order_by('-payment_id').values(
            'enrollment_id',
            'payment_status',
            'amount',
            'payment_method',
            'payment_date',
        )

        latest_payments = {}
        for payment in payments:
            latest_payments.setdefault(payment['enrollment_id'], payment)

        for enrollment in enrollments:
            course = courses.get(enrollment['course_id'])
            payment = latest_payments.get(enrollment['enrollment_id'])
            enrollment.update({
                'course_name': course.course_name if course else None,
                'course_description': course.description if course else None,
                'course_price': course.price if course else None,
                'payment_status': payment['payment_status'] if payment else None,
                'payment_amount': payment['amount'] if payment else None,
                'payment_method': payment['payment_method'] if payment else None,
                'payment_date': payment['payment_date'] if payment else None,
            })

        return Response(enrollments)

    # POST: Create a new pending enrolment
    course_id = request.data.get("course_id")

    if not course_id:
        return Response(
            {"error": "Course ID is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        course = Course.objects.get(
            course_id=course_id,
            tenant_id=tenant_id,
        )

    except (Course.DoesNotExist, ValueError, TypeError):
        return Response(
            {"error": "Invalid course for this learner."},
            status=status.HTTP_404_NOT_FOUND,
        )

    existing = Enrollment.objects.filter(
        tenant_id=tenant_id,
        learner_id=learner.learner_id,
        course_id=course.course_id,
    ).first()

    if existing:
        return Response(
            {
                "message": "You are already enrolled or have a pending enrolment.",
                "enrollment_id": existing.enrollment_id,
                "enrollment_status": existing.enrollment_status,
            },
            status=status.HTTP_409_CONFLICT,
        )

    try:
        enrollment = Enrollment.objects.create(
            tenant_id=tenant_id,
            learner_id=learner.learner_id,
            course_id=course.course_id,
            enrollment_date=timezone.now(),
            enrollment_status="pending",
        )

    except IntegrityError:
        return Response(
            {"error": "An enrolment for this course already exists."},
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        {
            "message": "Enrolment created. Payment is pending.",
            "enrollment_id": enrollment.enrollment_id,
            "course_id": course.course_id,
            "course_name": course.course_name,
            "amount": str(course.price or 0),
            "enrollment_status": enrollment.enrollment_status,
        },
        status=status.HTTP_201_CREATED,
    )



# ==========================================
# PAYMENT GATEWAY CONFIGURATION API
# ==========================================

@api_view(["GET"])
def payment_config(request):
    return Response({
        "gateway": settings.PAYMENT_GATEWAY
    })


# ==========================================
# PAYMENT API
# ==========================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def payment_list(request):

    try:
        profile = LearnerProfile.objects.select_related(
            "learner"
        ).get(user=request.user)

    except LearnerProfile.DoesNotExist:
        return Response(
            {"error": "Learner profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    learner = profile.learner
    tenant_id = learner.tenant_id

    # GET: Show only this learner's payments
    if request.method == "GET":

        enrollment_ids = Enrollment.objects.filter(
            tenant_id=tenant_id,
            learner_id=learner.learner_id,
        ).values_list("enrollment_id", flat=True)

        payments = Payment.objects.filter(
            tenant_id=tenant_id,
            enrollment_id__in=enrollment_ids,
        ).values(
            "payment_id",
            "tenant_id",
            "enrollment_id",
            "amount",
            "payment_method",
            "payment_status",
            "transaction_id",
            "payment_date",
        )

        return Response(list(payments))

    # POST: Create a pending payment record
    enrollment_id = request.data.get("enrollment_id")

    if not enrollment_id:
        return Response(
            {"error": "Enrollment ID is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    payment_method = request.data.get("payment_method")

    if payment_method is not None:
        payment_method = str(payment_method).strip()

        if not payment_method or len(payment_method) > 50:
            return Response(
                {"error": "Invalid payment method."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    try:
        with transaction.atomic():

            enrollment = Enrollment.objects.select_for_update().get(
                enrollment_id=enrollment_id,
                tenant_id=tenant_id,
                learner_id=learner.learner_id,
                enrollment_status="pending",
            )

            course = Course.objects.get(
                course_id=enrollment.course_id,
                tenant_id=tenant_id,
            )

            existing = Payment.objects.filter(
                tenant_id=tenant_id,
                enrollment_id=enrollment.enrollment_id,
            ).first()

            if existing:
                return Response(
                    {
                        "error": "A payment record already exists.",
                        "payment_id": existing.payment_id,
                        "payment_status": existing.payment_status,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            payment = Payment.objects.create(
                tenant_id=tenant_id,
                enrollment_id=enrollment.enrollment_id,
                amount=course.price or 0,
                payment_method=payment_method,
                payment_status="pending",
                payment_date=timezone.now(),
            )

    except Enrollment.DoesNotExist:
        return Response(
            {"error": "Pending enrolment not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    except Course.DoesNotExist:
        return Response(
            {"error": "Course not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "message": "Payment record created. Payment is pending.",
            "payment_id": payment.payment_id,
            "enrollment_id": payment.enrollment_id,
            "amount": str(payment.amount),
            "payment_method": payment.payment_method,
            "payment_status": payment.payment_status,
        },
        status=status.HTTP_201_CREATED,
    )

# ==========================================
# RAZORPAY ORDER CREATION API
# ==========================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_razorpay_order(request):
    try:
        profile = LearnerProfile.objects.select_related(
            "learner"
        ).get(user=request.user)
    except LearnerProfile.DoesNotExist:
        return Response(
            {"error": "Learner profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    learner = profile.learner
    tenant_id = learner.tenant_id
    enrollment_id = request.data.get("enrollment_id")

    if not enrollment_id:
        return Response(
            {"error": "Enrollment ID is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")

    if not key_id or not key_secret:
        return Response(
            {"error": "Razorpay is not configured."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        with transaction.atomic():
            enrollment = Enrollment.objects.select_for_update().get(
                enrollment_id=enrollment_id,
                tenant_id=tenant_id,
                learner_id=learner.learner_id,
                enrollment_status="pending",
            )

            course = Course.objects.get(
                course_id=enrollment.course_id,
                tenant_id=tenant_id,
            )

            payment = Payment.objects.select_for_update().filter(
                tenant_id=tenant_id,
                enrollment_id=enrollment.enrollment_id,
            ).first()

            if payment and payment.payment_status == "completed":
                return Response(
                    {"error": "This enrollment is already paid."},
                    status=status.HTTP_409_CONFLICT,
                )

            if payment and payment.razorpay_order_id:
                return Response(
                    {
                        "key_id": key_id,
                        "order_id": payment.razorpay_order_id,
                        "amount": int(
                            payment.amount * Decimal("100")
                        ),
                        "currency": "INR",
                        "payment_id": payment.payment_id,
                        "enrollment_id": enrollment.enrollment_id,
                        "name": learner.learner_name,
                        "email": learner.email,
                        "contact": learner.phone or "",
                    },
                    status=status.HTTP_200_OK,
                )

            if not payment:
                payment = Payment.objects.create(
                    tenant_id=tenant_id,
                    enrollment_id=enrollment.enrollment_id,
                    amount=course.price or 0,
                    payment_method="razorpay",
                    payment_status="pending",
                    payment_date=timezone.now(),
                )

            amount = Decimal(str(payment.amount))
            amount_paise = int(
                (amount * Decimal("100")).quantize(Decimal("1"))
            )

            if amount_paise <= 0:
                return Response(
                    {"error": "Invalid course amount."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            client = razorpay.Client(
                auth=(key_id, key_secret)
            )

            order = client.order.create(data={
                "amount": amount_paise,
                "currency": "INR",
                "receipt": f"dais_payment_{payment.payment_id}",
                "notes": {
                    "payment_id": str(payment.payment_id),
                    "enrollment_id": str(enrollment.enrollment_id),
                    "learner_id": str(learner.learner_id),
                    "tenant_id": str(tenant_id),
                },
            })

            payment.razorpay_order_id = order["id"]
            payment.payment_method = "razorpay"
            payment.save(update_fields=[
                "razorpay_order_id",
                "payment_method",
            ])

    except Enrollment.DoesNotExist:
        return Response(
            {"error": "Pending enrollment not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Course.DoesNotExist:
        return Response(
            {"error": "Course not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as exc:
        print("Razorpay order creation failed:", type(exc).__name__, str(exc))
        return Response(
            {"error": "Unable to create Razorpay order. Please try again."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(
        {
            "key_id": key_id,
            "order_id": order["id"],
            "amount": amount_paise,
            "currency": "INR",
            "payment_id": payment.payment_id,
            "enrollment_id": enrollment.enrollment_id,
            "name": learner.learner_name,
            "email": learner.email,
            "contact": learner.phone or "",
        },
        status=status.HTTP_201_CREATED,
    )
# ==========================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def demo_payment(request):
    if settings.PAYMENT_GATEWAY != "demo":
        return Response(
            {"error": "Demo payments are disabled."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    outcome = request.data.get("outcome")
    enrollment_id = request.data.get("enrollment_id")

    if outcome not in ("success", "failure", "cancel"):
        return Response(
            {"error": "Invalid demo payment outcome."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not enrollment_id:
        return Response(
            {"error": "Enrollment ID is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        profile = LearnerProfile.objects.select_related(
            "learner"
        ).get(user=request.user)
    except LearnerProfile.DoesNotExist:
        return Response(
            {"error": "Learner profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    learner = profile.learner
    tenant_id = learner.tenant_id

    try:
        with transaction.atomic():
            enrollment = Enrollment.objects.select_for_update().get(
                enrollment_id=enrollment_id,
                tenant_id=tenant_id,
                learner_id=learner.learner_id,
                enrollment_status="pending",
            )

            course = Course.objects.get(
                course_id=enrollment.course_id,
                tenant_id=tenant_id,
            )

            payment = Payment.objects.select_for_update().filter(
                tenant_id=tenant_id,
                enrollment_id=enrollment.enrollment_id,
            ).first()

            if payment and payment.payment_status == "completed":
                return Response(
                    {"error": "This enrollment is already paid."},
                    status=status.HTTP_409_CONFLICT,
                )

            if payment and payment.razorpay_order_id:
                return Response(
                    {"error": "A Razorpay order already exists for this payment."},
                    status=status.HTTP_409_CONFLICT,
                )

            if not payment:
                payment = Payment.objects.create(
                    tenant_id=tenant_id,
                    enrollment_id=enrollment.enrollment_id,
                    amount=course.price or 0,
                    payment_method="demo",
                    payment_status="pending",
                )
            else:
                payment.payment_method = "demo"

            if outcome == "success":
                payment.payment_status = "completed"
                payment.transaction_id = (
                    f"DEMO-{payment.payment_id}-{os.urandom(6).hex()}"
                )
                payment.payment_date = timezone.now()
                payment.save(update_fields=[
                    "payment_method",
                    "payment_status",
                    "transaction_id",
                    "payment_date",
                ])

                enrollment.enrollment_status = "active"
                enrollment.save(update_fields=["enrollment_status"])
            else:
                payment.save(update_fields=["payment_method"])

    except Enrollment.DoesNotExist:
        return Response(
            {"error": "Pending enrollment not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Course.DoesNotExist:
        return Response(
            {"error": "Course not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({
        "message": (
            "Demo payment successful."
            if outcome == "success"
            else "Demo payment was not completed."
        ),
        "outcome": outcome,
        "payment_id": payment.payment_id,
        "enrollment_id": enrollment.enrollment_id,
        "amount": str(payment.amount),
        "payment_status": payment.payment_status,
        "enrollment_status": enrollment.enrollment_status,
        "transaction_id": payment.transaction_id,
    }, status=status.HTTP_200_OK)


# RAZORPAY PAYMENT VERIFICATION API
# ==========================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_razorpay_payment(request):
    order_id = request.data.get("razorpay_order_id")
    razorpay_payment_id = request.data.get("razorpay_payment_id")
    signature = request.data.get("razorpay_signature")

    if not all([order_id, razorpay_payment_id, signature]):
        return Response(
            {"error": "Payment verification details are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")

    if not key_id or not key_secret:
        return Response(
            {"error": "Razorpay is not configured."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        profile = LearnerProfile.objects.select_related(
            "learner"
        ).get(user=request.user)
    except LearnerProfile.DoesNotExist:
        return Response(
            {"error": "Learner profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    learner = profile.learner
    tenant_id = learner.tenant_id

    enrollment_ids = Enrollment.objects.filter(
        tenant_id=tenant_id,
        learner_id=learner.learner_id,
    ).values_list("enrollment_id", flat=True)

    try:
        payment = Payment.objects.get(
            tenant_id=tenant_id,
            enrollment_id__in=enrollment_ids,
            razorpay_order_id=order_id,
        )
    except Payment.DoesNotExist:
        return Response(
            {"error": "Payment order not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    client = razorpay.Client(
        auth=(key_id, key_secret)
    )

    # Verify Razorpay signature
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": signature,
        })
    except Exception:
        return Response(
            {"error": "Invalid payment signature."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Confirm payment directly with Razorpay
    try:
        gateway_payment = client.payment.fetch(
            razorpay_payment_id
        )
    except Exception:
        return Response(
            {"error": "Unable to verify payment with Razorpay."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    expected_amount = int(
        (Decimal(str(payment.amount)) * Decimal("100")).quantize(
            Decimal("1")
        )
    )

    if (
        gateway_payment.get("order_id") != order_id
        or gateway_payment.get("amount") != expected_amount
        or gateway_payment.get("currency") != "INR"
    ):
        return Response(
            {"error": "Payment details do not match the order."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if gateway_payment.get("status") != "captured":
        return Response(
            {"error": "Payment has not been captured yet. Please retry."},
            status=status.HTTP_409_CONFLICT,
        )

    try:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(
                payment_id=payment.payment_id,
                tenant_id=tenant_id,
                razorpay_order_id=order_id,
            )

            enrollment = Enrollment.objects.select_for_update().get(
                enrollment_id=payment.enrollment_id,
                tenant_id=tenant_id,
                learner_id=learner.learner_id,
            )

            # Allow safe repeated verification of the same payment
            if payment.payment_status == "completed":
                if payment.transaction_id == razorpay_payment_id:
                    return Response({
                        "message": "Payment already verified.",
                        "payment_id": payment.payment_id,
                        "enrollment_id": enrollment.enrollment_id,
                        "payment_status": payment.payment_status,
                        "enrollment_status": enrollment.enrollment_status,
                    })

                return Response(
                    {"error": "A different payment is already recorded."},
                    status=status.HTTP_409_CONFLICT,
                )

            if payment.transaction_id:
                return Response(
                    {"error": "Another transaction is already recorded."},
                    status=status.HTTP_409_CONFLICT,
                )

            payment.transaction_id = razorpay_payment_id
            payment.payment_status = "completed"
            payment.payment_method = "razorpay"
            payment.payment_date = timezone.now()

            payment.save(update_fields=[
                "transaction_id",
                "payment_status",
                "payment_method",
                "payment_date",
            ])

            enrollment.enrollment_status = "active"
            enrollment.save(update_fields=[
                "enrollment_status",
            ])

    except Enrollment.DoesNotExist:
        return Response(
            {"error": "Enrollment not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "message": "Payment verified successfully!",
            "payment_id": payment.payment_id,
            "enrollment_id": enrollment.enrollment_id,
            "amount": str(payment.amount),
            "payment_status": payment.payment_status,
            "enrollment_status": enrollment.enrollment_status,
        },
        status=status.HTTP_200_OK,
    )
# ==========================================
# VIDEO, DOCUMENT AND TRANSCRIPT APIs
# ==========================================

def _authorized_course_scope(request):
    try:
        profile = LearnerProfile.objects.select_related(
            "learner"
        ).get(user=request.user)
    except LearnerProfile.DoesNotExist:
        return None, [], Response(
            {"error": "Learner profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    learner = profile.learner
    tenant_id = learner.tenant_id

    enrollments = list(
        Enrollment.objects.filter(
            tenant_id=tenant_id,
            learner_id=learner.learner_id,
            enrollment_status="active",
        ).values("enrollment_id", "course_id")
    )

    enrollment_ids = [item["enrollment_id"] for item in enrollments]

    payments = Payment.objects.filter(
        tenant_id=tenant_id,
        enrollment_id__in=enrollment_ids,
    ).order_by("-payment_id").values(
        "enrollment_id",
        "payment_status",
    )

    latest_payments = {}
    for payment in payments:
        latest_payments.setdefault(
            payment["enrollment_id"],
            payment["payment_status"],
        )

    authorized_course_ids = list({
        item["course_id"]
        for item in enrollments
        if latest_payments.get(item["enrollment_id"]) == "completed"
    })

    return tenant_id, authorized_course_ids, None


def _requested_course_filter(request, authorized_course_ids):
    requested_id = request.query_params.get("course_id")

    if requested_id is None:
        return authorized_course_ids, None

    try:
        requested_id = int(requested_id)
        if requested_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return [], Response(
            {"error": "Invalid course ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if requested_id not in authorized_course_ids:
        return [], Response(
            {"error": "Course access not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return [requested_id], None


# VIDEO API
# ==========================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def video_list(request):
    tenant_id, course_ids, error = _authorized_course_scope(request)
    if error:
        return error

    course_ids, error = _requested_course_filter(request, course_ids)
    if error:
        return error

    videos = Video.objects.filter(
        tenant_id=tenant_id,
        course_id__in=course_ids,
    ).values(
        "video_id",
        "course_id",
        "video_title",
        "video_url",
        "duration_minutes",
    )

    return Response(list(videos))


# DOCUMENT API
# ==========================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def document_list(request):
    tenant_id, course_ids, error = _authorized_course_scope(request)
    if error:
        return error

    course_ids, error = _requested_course_filter(request, course_ids)
    if error:
        return error

    documents = Document.objects.filter(
        tenant_id=tenant_id,
        course_id__in=course_ids,
    ).values(
        "document_id",
        "course_id",
        "document_name",
        "document_url",
        "document_type",
    )

    return Response(list(documents))


# TRANSCRIPT API
# ==========================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transcript_list(request):
    tenant_id, course_ids, error = _authorized_course_scope(request)
    if error:
        return error

    course_ids, error = _requested_course_filter(request, course_ids)
    if error:
        return error

    video_ids = Video.objects.filter(
        tenant_id=tenant_id,
        course_id__in=course_ids,
    ).values_list("video_id", flat=True)

    transcripts = Transcript.objects.filter(
        tenant_id=tenant_id,
        video_id__in=video_ids,
    ).values(
        "transcript_id",
        "video_id",
        "transcript_content",
        "language",
    )

    return Response(list(transcripts))


# ==========================================

# LEARNER REGISTRATION API
# ==========================================

@api_view(["POST"])
def learner_register(request):

    data = request.data

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    phone = str(data.get("phone", "")).strip()

    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")

    age = data.get("age")
    terms_accepted = data.get("terms_accepted")

    if not name or len(name) < 2 or len(name) > 150:
        return Response(
            {"error": "Enter a valid name."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not email or len(email) > 150 or "@" not in email:
        return Response(
            {"error": "Enter a valid email address."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not re.fullmatch(r"[6-9]\d{9}", phone):
        return Response(
            {"error": "Enter a valid 10-digit Indian phone number."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        age = int(age)
    except (TypeError, ValueError):
        return Response(
            {"error": "Enter a valid age."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not 13 <= age <= 120:
        return Response(
            {"error": "Age must be between 13 and 120."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(password, str) or len(password) < 8:
        return Response(
            {"error": "Password must contain at least 8 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if password != confirm_password:
        return Response(
            {"error": "Passwords do not match."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_password(password)
    except ValidationError as error:
        return Response(
            {"error": list(error.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if terms_accepted is not True:
        return Response(
            {"error": "Please accept the Terms and Conditions."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    User = get_user_model()

    try:
        with transaction.atomic():

            if Learner.objects.filter(
                tenant_id=1,
                email__iexact=email,
            ).exists():
                return Response(
                    {"error": "An account with this email already exists."},
                    status=status.HTTP_409_CONFLICT,
                )

            if User.objects.filter(email__iexact=email).exists():
                return Response(
                    {"error": "This email is already registered."},
                    status=status.HTTP_409_CONFLICT,
                )

            learner = Learner.objects.create(
                tenant_id=1,
                learner_name=name,
                email=email,
                phone=phone,
            )

            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=name,
            )

            LearnerProfile.objects.create(
                learner=learner,
                user=user,
                age=age,
                terms_accepted_at=timezone.now(),
            )

    except Exception:
        return Response(
            {
                "error": (
                    "Registration could not be completed. "
                    "Please try again."
                )
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {"message": "Account created successfully."},
        status=status.HTTP_201_CREATED,
    )


# ==========================================
# TENANT ADMIN LOGIN API
# ==========================================

@api_view(["POST"])
def tenant_login(request):
    password = request.data.get("password", "")

    if not isinstance(password, str) or not password:
        return Response(
            {"error": "Password is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    User = get_user_model()
    username = "dais_tenant_admin"

    user = authenticate(
        request,
        username=username,
        password=password,
    )

    if user is None:
        return Response(
            {"error": "Invalid password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        return Response(
            {"error": "This account is inactive."},
            status=status.HTTP_403_FORBIDDEN,
        )

    profile = TenantAdminProfile.objects.select_related(
        "tenant"
    ).filter(user=user).first()

    if profile is None:
        return Response(
            {"error": "Tenant admin account is not configured."},
            status=status.HTTP_403_FORBIDDEN,
        )

    auth_login(request._request, user)

    return Response(
        {
            "message": "Tenant login successful.",
            "role": "tenant_admin",
            "user_id": user.id,
            "tenant_id": profile.tenant.tenant_id,
            "tenant_name": profile.tenant.tenant_name,
        },
        status=status.HTTP_200_OK,
    )


# ==========================================
# LEARNER LOGIN API
# ==========================================

@api_view(["POST"])
def learner_login(request):

    email = str(request.data.get("email", "")).strip().lower()
    password = request.data.get("password", "")

    if not email or not isinstance(password, str) or not password:
        return Response(
            {"error": "Email and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    User = get_user_model()

    user_record = User.objects.filter(
        email__iexact=email
    ).first()

    if not user_record:
        return Response(
            {"error": "Invalid email or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    user = authenticate(
        request,
        username=user_record.username,
        password=password,
    )

    if user is None:
        return Response(
            {"error": "Invalid email or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        return Response(
            {"error": "This account is inactive."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        profile = LearnerProfile.objects.select_related(
            "learner"
        ).get(user=user)

    except LearnerProfile.DoesNotExist:
        return Response(
            {"error": "Learner profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    auth_login(request._request, user)



    return Response(
        {
            "message": "Login successful.",
            "user_id": user.id,
            "learner_id": profile.learner.learner_id,
            "tenant_id": profile.learner.tenant_id,
            "name": profile.learner.learner_name,
            "email": profile.learner.email,
            "age": profile.age,
        },
        status=status.HTTP_200_OK,
    )


# ==========================================
# TENANT COURSE MANAGEMENT API
# ==========================================

@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def tenant_course_management(request):

    try:
        profile = TenantAdminProfile.objects.select_related(
            "tenant"
        ).get(user=request.user)
    except TenantAdminProfile.DoesNotExist:
        return Response(
            {"error": "Tenant administrator access required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    tenant_id = profile.tenant.tenant_id

    # GET: List courses belonging only to this tenant
    if request.method == "GET":

        courses = list(
            Course.objects.filter(
                tenant_id=tenant_id
            ).order_by("-course_id").values(
                "course_id",
                "tenant_id",
                "sub_channel_id",
                "course_name",
                "description",
                "price",
                "created_at",
            )
        )

        subchannels = {
            item["sub_channel_id"]: item
            for item in SubChannel.objects.filter(
                tenant_id=tenant_id
            ).values("sub_channel_id", "channel_id", "sub_channel_name")
        }

        channels = {
            item["channel_id"]: item["channel_name"]
            for item in Channel.objects.filter(
                tenant_id=tenant_id
            ).values("channel_id", "channel_name")
        }

        for course in courses:
            subchannel = subchannels.get(course["sub_channel_id"], {})
            course["category"] = subchannel.get("sub_channel_name")
            course["channel"] = channels.get(
                subchannel.get("channel_id")
            )

        return Response(courses)

    # POST: Create a course for this tenant
    if request.method == "POST":

        course_name = str(
            request.data.get("course_name", "")
        ).strip()

        sub_channel_id = request.data.get("sub_channel_id")
        description = str(
            request.data.get("description", "")
        ).strip()

        if not course_name:
            return Response(
                {"error": "Course name is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(course_name) > 200:
            return Response(
                {"error": "Course name must be 200 characters or fewer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sub_channel_id = int(sub_channel_id)
        except (TypeError, ValueError):
            return Response(
                {"error": "A valid course category is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        category = SubChannel.objects.filter(
            sub_channel_id=sub_channel_id,
            tenant_id=tenant_id,
        ).first()

        if category is None:
            return Response(
                {"error": "Invalid course category for this tenant."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_price = request.data.get("price")
        try:
            price = Decimal(str(raw_price)) if raw_price not in (None, "") else None
            if price is not None and (
                not price.is_finite() or price < 0 or price > Decimal("99999999.99")
            ):
                raise ValueError
        except Exception:
            return Response(
                {"error": "Enter a valid non-negative course price."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        course = Course.objects.create(
            tenant_id=tenant_id,
            sub_channel_id=sub_channel_id,
            course_name=course_name,
            description=description or None,
            price=price,
            created_at=timezone.now(),
        )

        return Response(
            {
                "message": "Course created successfully.",
                "course_id": course.course_id,
                "course_name": course.course_name,
                "sub_channel_id": course.sub_channel_id,
                "category": category.sub_channel_name,
                "price": str(course.price) if course.price is not None else None,
            },
            status=status.HTTP_201_CREATED,
        )

    # DELETE: Delete only a course belonging to this tenant
    if request.method == "DELETE":

        try:
            course_id = int(request.data.get("course_id"))
        except (TypeError, ValueError):
            return Response(
                {"error": "A valid course ID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deleted_count, _ = Course.objects.filter(
            course_id=course_id,
            tenant_id=tenant_id,
        ).delete()

        if not deleted_count:
            return Response(
                {"error": "Course not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"message": "Course deleted successfully."},
            status=status.HTTP_200_OK,
        )


# ==========================================
# TENANT COURSE CATEGORIES API
# ==========================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tenant_category_list(request):

    try:
        profile = TenantAdminProfile.objects.select_related(
            "tenant"
        ).get(user=request.user)
    except TenantAdminProfile.DoesNotExist:
        return Response(
            {"error": "Tenant administrator access required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    tenant_id = profile.tenant.tenant_id

    categories = list(
        SubChannel.objects.filter(
            tenant_id=tenant_id
        ).order_by("sub_channel_name").values(
            "sub_channel_id",
            "sub_channel_name",
            "channel_id",
        )
    )

    return Response(categories)
