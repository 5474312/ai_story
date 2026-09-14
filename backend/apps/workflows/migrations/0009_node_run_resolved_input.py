from django.db import migrations, models


def normalize_adopted_candidates(apps, schema_editor):
    Candidate = apps.get_model('workflows', 'WorkflowResultCandidate')
    adopted = Candidate.objects.filter(node_id__isnull=False, status='adopted').order_by(
        'node_id', '-adopted_at', '-created_at',
    )
    seen_nodes = set()
    demote_ids = []
    for candidate in adopted.iterator():
        if candidate.node_id in seen_nodes:
            demote_ids.append(candidate.id)
        else:
            seen_nodes.add(candidate.node_id)
    Candidate.objects.filter(id__in=demote_ids).update(status='alternate', adopted_at=None)


class Migration(migrations.Migration):
    dependencies = [('workflows', '0008_result_candidates')]

    operations = [
        migrations.AddField(
            model_name='workflownoderun',
            name='resolved_input_payload',
            field=models.JSONField(blank=True, default=dict, verbose_name='执行时有效输入快照'),
        ),
        migrations.RunPython(normalize_adopted_candidates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='workflowresultcandidate',
            constraint=models.UniqueConstraint(
                condition=models.Q(node__isnull=False, status='adopted'),
                fields=('node',),
                name='uniq_wf_adopted_candidate_per_node',
            ),
        ),
    ]
