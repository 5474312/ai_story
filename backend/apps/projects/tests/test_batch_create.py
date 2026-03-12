from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.content.models import ContentRewrite
from apps.projects.models import Project, ProjectStage, Series
from apps.prompts.models import PromptTemplateSet


User = get_user_model()


class ProjectBatchCreateAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='secret123')
        self.client.force_authenticate(self.user)
        self.series = Series.objects.create(name='西游记', description='神话冒险', user=self.user)
        self.prompt_set = PromptTemplateSet.objects.create(
            name='默认提示词集',
            description='测试用',
            created_by=self.user,
            is_active=True,
        )

    def test_batch_create_projects_success(self):
        response = self.client.post(
            reverse('project-batch-create'),
            {
                'series': str(self.series.id),
                'description': '同一套基础设定',
                'prompt_template_set': str(self.prompt_set.id),
                'start_episode_number': 3,
                'episodes': [
                    {
                        'episode_title': '三打白骨精上',
                        'original_topic': '第一集文案',
                    },
                    {
                        'episode_title': '三打白骨精中',
                        'original_topic': '第二集文案',
                        'name': '白骨风波',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['count'], 2)

        projects = Project.objects.filter(series=self.series).order_by('episode_number')
        self.assertEqual(projects.count(), 2)
        self.assertEqual(list(projects.values_list('episode_number', flat=True)), [3, 4])
        self.assertEqual(projects[0].name, '第3集')
        self.assertEqual(projects[1].name, '白骨风波')
        self.assertTrue(all(project.prompt_template_set_id == self.prompt_set.id for project in projects))
        self.assertTrue(all(project.description == '同一套基础设定' for project in projects))
        self.assertEqual(ProjectStage.objects.filter(project__in=projects).count(), 10)
        self.assertEqual(ContentRewrite.objects.filter(project__in=projects).count(), 2)

    def test_batch_create_uses_latest_episode_defaults(self):
        latest = Project.objects.create(
            user=self.user,
            series=self.series,
            episode_number=5,
            sort_order=5,
            episode_title='前情提要',
            name='第5集',
            description='旧描述',
            original_topic='旧文案',
            prompt_template_set=self.prompt_set,
        )
        for stage_type in ['rewrite', 'storyboard', 'image_generation', 'camera_movement', 'video_generation']:
            ProjectStage.objects.create(project=latest, stage_type=stage_type, status='pending')
        ContentRewrite.objects.create(project=latest, original_text=latest.original_topic)

        response = self.client.post(
            reverse('project-batch-create'),
            {
                'series': str(self.series.id),
                'episodes': [
                    {'episode_title': '新篇章一', 'original_topic': '文案一'},
                    {'episode_title': '新篇章二', 'original_topic': '文案二'},
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Project.objects.filter(series=self.series).exclude(id=latest.id).order_by('episode_number')
        self.assertEqual(list(created.values_list('episode_number', flat=True)), [6, 7])
        self.assertTrue(all(project.prompt_template_set_id == self.prompt_set.id for project in created))

    def test_batch_create_rejects_existing_episode_number(self):
        Project.objects.create(
            user=self.user,
            series=self.series,
            episode_number=2,
            sort_order=2,
            episode_title='已存在分集',
            name='第2集',
            original_topic='旧文案',
        )

        response = self.client.post(
            reverse('project-batch-create'),
            {
                'series': str(self.series.id),
                'start_episode_number': 2,
                'episodes': [
                    {'episode_title': '冲突分集', 'original_topic': '新文案'},
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('start_episode_number', response.data)
        self.assertEqual(Project.objects.filter(series=self.series).count(), 1)
