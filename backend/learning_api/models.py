from django.db import models


class Tenant(models.Model):
    tenant_id = models.BigAutoField(primary_key=True)
    tenant_name = models.CharField(max_length=150)
    domain = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "tenants"


class Learner(models.Model):
    learner_id = models.BigAutoField(primary_key=True)
    tenant_id = models.BigIntegerField()
    learner_name = models.CharField(max_length=150)
    email = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "learners"


class Channel(models.Model):
    channel_id = models.BigAutoField(primary_key=True)
    tenant_id = models.BigIntegerField()
    channel_name = models.CharField(max_length=150)
    description = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "channels"


class SubChannel(models.Model):
    sub_channel_id = models.BigAutoField(primary_key=True)
    tenant_id = models.BigIntegerField()
    channel_id = models.BigIntegerField()
    sub_channel_name = models.CharField(max_length=150)

    class Meta:
        managed = False
        db_table = "sub_channels"


class Course(models.Model):
    course_id = models.BigAutoField(primary_key=True)
    tenant_id = models.BigIntegerField()
    sub_channel_id = models.BigIntegerField()
    course_name = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "courses"


class Enrollment(models.Model):
    enrollment_id = models.BigAutoField(primary_key=True)
    tenant_id = models.BigIntegerField()
    learner_id = models.BigIntegerField()
    course_id = models.BigIntegerField()
    enrollment_date = models.DateTimeField(null=True, blank=True)
    enrollment_status = models.CharField(
        max_length=30, null=True, blank=True
    )

    class Meta:
        managed = False
        db_table = "enrollments"


class Payment(models.Model):
    payment_id = models.BigAutoField(primary_key=True)
    tenant_id = models.BigIntegerField()
    enrollment_id = models.BigIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    payment_status = models.CharField(
        max_length=30, null=True, blank=True
    )
    transaction_id = models.CharField(
        max_length=150, null=True, blank=True
    )
    razorpay_order_id = models.CharField(
        max_length=150, null=True, blank=True
    )
    payment_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "payments"


class Video(models.Model):
    video_id = models.BigAutoField(primary_key=True)
    tenant_id = models.BigIntegerField()
    course_id = models.BigIntegerField()
    video_title = models.CharField(max_length=200)
    video_url = models.TextField()
    duration_minutes = models.IntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "videos"


class Document(models.Model):
    document_id = models.BigAutoField(primary_key=True)
    tenant_id = models.BigIntegerField()
    course_id = models.BigIntegerField()
    document_name = models.CharField(max_length=200)
    document_url = models.TextField()
    document_type = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "documents"


class Transcript(models.Model):
    transcript_id = models.BigAutoField(primary_key=True)
    tenant_id = models.BigIntegerField()
    video_id = models.BigIntegerField()
    transcript_content = models.TextField(null=True, blank=True)
    language = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "transcripts"


class LearnerProfile(models.Model):
    learner = models.OneToOneField(
        Learner,
        on_delete=models.PROTECT,
        db_column="learner_id",
        related_name="profile",
    )
    age = models.PositiveSmallIntegerField()
    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="learner_profile",
    )
    terms_accepted_at = models.DateTimeField()

    class Meta:
        db_table = "learner_profiles"

    def __str__(self):
        return f"{self.learner.learner_name} - Profile"


class TenantAdminProfile(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        db_column="tenant_id",
        related_name="admin_profiles",
    )
    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="tenant_admin_profile",
    )

    class Meta:
        db_table = "tenant_admin_profiles"

    def __str__(self):
        return f"{self.user.email} - {self.tenant.tenant_name}"
