# Generated by Django 4.2.11 on 2025-04-12 13:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Movies', '0007_alter_movie_trailer_url'),
    ]

    operations = [
        migrations.AlterField(
            model_name='movie',
            name='trailer_url',
            field=models.URLField(blank=True, max_length=5000, null=True),
        ),
    ]
