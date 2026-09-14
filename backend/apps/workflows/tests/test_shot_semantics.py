from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.projects.models import Project, Series
from apps.workflows.models import (
    ContinuityIssue,
    ProductionScene,
    Shot,
    ShotTake,
    WorkflowCanvas,
    WorkflowNode,
)
from apps.workflows.shot_services import (
    check_project_continuity,
    prepare_bulk_rerender,
    sync_canvas_to_shots,
    sync_shots_to_canvas,
)
from apps.workflows.serializers import WorkflowCanvasGraphSerializer


User = get_user_model()


class ShotSemanticsTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='director', password='secret123')
        self.client.force_authenticate(self.user)
        self.series = Series.objects.create(name='影片', user=self.user)
        self.project = Project.objects.create(
            name='第一集', original_topic='故事', user=self.user,
            series=self.series, episode_number=1,
        )
        self.canvas = WorkflowCanvas.objects.create(
            name='镜头画布', project=self.project, series=self.series,
            created_by=self.user, status='active',
        )
        self.scene = ProductionScene.objects.create(
            project=self.project, canvas=self.canvas, number=1, name='车站',
        )
        self.shot = Shot.objects.create(
            scene=self.scene, canvas=self.canvas, number=1, title='人物入场',
            shot_size='wide', focal_length_mm=35,
        )

    def test_shot_list_and_canvas_sync_both_directions(self):
        result = sync_shots_to_canvas(self.canvas)
        self.assertEqual(result['created'], 1)
        node = WorkflowNode.objects.get(canvas=self.canvas, node_type='shot')
        self.assertEqual(node.config_data['shot_id'], str(self.shot.id))
        self.assertEqual(node.config_data['focal_length_mm'], 35)

        node.config_data = {**node.config_data, 'shot_size': 'close_up', 'duration_seconds': 3.5}
        node.save(update_fields=['config_data'])
        result = sync_canvas_to_shots(self.canvas)
        self.assertEqual(result['updated'], 1)
        self.shot.refresh_from_db()
        self.assertEqual(self.shot.shot_size, 'close_up')
        self.assertEqual(float(self.shot.duration_seconds), 3.5)

    def test_lock_protects_canvas_sync_and_bulk_rerender(self):
        sync_shots_to_canvas(self.canvas)
        response = self.client.post(reverse('shot-lock', args=[self.shot.id]), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        node = WorkflowNode.objects.get(canvas=self.canvas, node_key=f'shot:{self.shot.id}')
        node.config_data = {**node.config_data, 'description': '不应覆盖', 'model': 'old-model'}
        node.save(update_fields=['config_data'])
        sync_canvas_to_shots(self.canvas)
        self.shot.refresh_from_db()
        self.assertNotEqual(self.shot.description, '不应覆盖')

        result = prepare_bulk_rerender(self.canvas, model_key='new-model')
        self.assertEqual(result['eligible'], [])
        self.assertEqual(result['skipped'][0]['reason'], 'locked')
        node.refresh_from_db()
        self.assertEqual(node.config_data['model'], 'old-model')

        graph = WorkflowCanvasGraphSerializer(
            data={'nodes': [], 'edges': []},
            context={'canvas': self.canvas, 'request': None},
        )
        self.assertTrue(graph.is_valid(), graph.errors)
        graph.save()
        self.assertTrue(WorkflowNode.objects.filter(pk=node.id).exists())

    def test_selecting_final_take_replaces_previous_selection(self):
        first = ShotTake.objects.create(shot=self.shot, number=1, status='completed', is_final=True)
        second = ShotTake.objects.create(shot=self.shot, number=2, status='completed')

        response = self.client.post(reverse('shot-take-select-final', args=[second.id]), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_final)
        self.assertTrue(second.is_final)

    def test_continuity_check_tracks_and_resolves_adjacent_mismatch(self):
        self.shot.continuity_data = {'costume_end': 'red coat', 'action_end': 'left foot forward'}
        self.shot.save(update_fields=['continuity_data'])
        next_shot = Shot.objects.create(
            scene=self.scene, canvas=self.canvas, number=2,
            continuity_data={'costume_start': 'blue coat', 'action_start': 'right foot forward'},
        )

        issues = check_project_continuity(self.project)
        self.assertEqual({issue.category for issue in issues}, {'costume', 'action'})
        self.assertEqual(ContinuityIssue.objects.filter(status='open').count(), 2)

        next_shot.continuity_data = {'costume_start': 'red coat', 'action_start': 'left foot forward'}
        next_shot.save(update_fields=['continuity_data'])
        self.assertEqual(check_project_continuity(self.project), [])
        self.assertEqual(ContinuityIssue.objects.filter(status='resolved').count(), 2)

    def test_sync_endpoint_materializes_shot_node(self):
        response = self.client.post(
            reverse('shot-production-sync-to-canvas', args=[self.canvas.id]),
            {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['created'], 1)
