from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0005_project_asset_binding'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='project',
            constraint=models.UniqueConstraint(
                condition=models.Q(('episode_number__isnull', False), ('series__isnull', False)),
                fields=('series', 'episode_number'),
                name='uniq_series_episode_number',
            ),
        ),
    ]
