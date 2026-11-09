# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Channels(models.Model):
    channel_id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey('Tenants', models.DO_NOTHING)
    channel_name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'channels'
        unique_together = (('tenant', 'channel_id'),)


class Courses(models.Model):
    course_id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey('SubChannels', models.DO_NOTHING, to_field='tenant_id')
    sub_channel_id = models.BigIntegerField()
    course_name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'courses'
        unique_together = (('tenant', 'course_id'),)


class Documents(models.Model):
    document_id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Courses, models.DO_NOTHING, to_field='tenant_id')
    course_id = models.BigIntegerField()
    document_name = models.CharField(max_length=200)
    document_url = models.TextField()
    document_type = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'documents'


class Enrollments(models.Model):
    enrollment_id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey('Learners', models.DO_NOTHING, to_field='tenant_id')
    learner_id = models.BigIntegerField()
    course_id = models.BigIntegerField()
    enrollment_date = models.DateTimeField(blank=True, null=True)
    enrollment_status = models.CharField(max_length=30, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'enrollments'
        unique_together = (('tenant', 'enrollment_id'), ('tenant', 'learner_id', 'course_id'),)


class Learners(models.Model):
    learner_id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey('Tenants', models.DO_NOTHING)
    learner_name = models.CharField(max_length=150)
    email = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'learners'
        unique_together = (('tenant', 'email'), ('tenant', 'learner_id'),)


class Payments(models.Model):
    payment_id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Enrollments, models.DO_NOTHING, to_field='tenant_id')
    enrollment_id = models.BigIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    payment_status = models.CharField(max_length=30, blank=True, null=True)
    transaction_id = models.CharField(max_length=150, blank=True, null=True)
    payment_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'payments'


class SubChannels(models.Model):
    sub_channel_id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Channels, models.DO_NOTHING, to_field='tenant_id')
    channel_id = models.BigIntegerField()
    sub_channel_name = models.CharField(max_length=150)

    class Meta:
        managed = False
        db_table = 'sub_channels'
        unique_together = (('tenant', 'sub_channel_id'),)


class Tenants(models.Model):
    tenant_id = models.BigAutoField(primary_key=True)
    tenant_name = models.CharField(max_length=150)
    domain = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tenants'


class Transcripts(models.Model):
    transcript_id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey('Videos', models.DO_NOTHING, to_field='tenant_id')
    video_id = models.BigIntegerField()
    transcript_content = models.TextField(blank=True, null=True)
    language = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'transcripts'


class Videos(models.Model):
    video_id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Courses, models.DO_NOTHING, to_field='tenant_id')
    course_id = models.BigIntegerField()
    video_title = models.CharField(max_length=200)
    video_url = models.TextField()
    duration_minutes = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'videos'
        unique_together = (('tenant', 'video_id'),)
