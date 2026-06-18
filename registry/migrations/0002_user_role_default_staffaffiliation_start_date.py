import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registry", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("regulator", "Regulator (KMPDC)"),
                    ("hospital_admin", "Hospital Administrator"),
                    ("practitioner", "Medical Practitioner"),
                ],
                default="practitioner",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="staffaffiliation",
            name="start_date",
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
    ]
