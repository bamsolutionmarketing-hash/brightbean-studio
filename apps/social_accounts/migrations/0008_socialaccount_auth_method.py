from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("social_accounts", "0007_increase_avatar_url_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialaccount",
            name="auth_method",
            field=models.CharField(
                choices=[("oauth", "OAuth"), ("browser", "Browser (Playwright)")],
                default="oauth",
                max_length=10,
            ),
        ),
    ]
