from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cours", "0005_correctionquizitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="correctionquizitem",
            name="propositions_json",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
