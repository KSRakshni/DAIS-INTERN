from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Learner",
            fields=[
                (
                    "learner_id",
                    models.BigAutoField(
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("tenant_id", models.BigIntegerField()),
                ("learner_name", models.CharField(max_length=150)),
                ("email", models.CharField(max_length=150)),
                (
                    "phone",
                    models.CharField(
                        max_length=20,
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(blank=True, null=True),
                ),
            ],
            options={
                "db_table": "learners",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="LearnerProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("age", models.PositiveSmallIntegerField()),
                ("terms_accepted_at", models.DateTimeField()),
                (
                    "learner",
                    models.OneToOneField(
                        db_column="learner_id",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="profile",
                        to="learning_api.learner",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="learner_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "learner_profiles",
            },
        ),
    ]
