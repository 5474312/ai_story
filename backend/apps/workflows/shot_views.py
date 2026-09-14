"""Shot-level production API used by ai_story and linknow."""

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    ContinuityIssue,
    ProductionEntity,
    ProductionScene,
    Shot,
    ShotEntityBinding,
    ShotReference,
    ShotTake,
    WorkflowCanvas,
)
from .shot_serializers import (
    ContinuityIssueSerializer,
    ProductionEntitySerializer,
    ProductionSceneSerializer,
    ShotEntityBindingSerializer,
    ShotReferenceSerializer,
    ShotSerializer,
    ShotTakeSerializer,
)
from .shot_services import (
    check_project_continuity,
    prepare_bulk_rerender,
    shot_snapshot,
    sync_canvas_to_shots,
    sync_shots_to_canvas,
)


class ProductionEntityViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductionEntitySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['project', 'entity_type']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at', 'updated_at']

    def get_queryset(self):
        return ProductionEntity.objects.filter(project__user=self.request.user).select_related('project')


class ProductionSceneViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductionSceneSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['project', 'canvas']
    search_fields = ['name', 'synopsis']
    ordering_fields = ['number', 'created_at', 'updated_at']
    ordering = ['number']

    def get_queryset(self):
        return (
            ProductionScene.objects.filter(project__user=self.request.user)
            .select_related('project', 'canvas', 'location')
            .prefetch_related('shots__takes', 'shots__references', 'shots__entity_bindings__entity')
            .annotate(shot_count=Count('shots'))
        )


class ShotViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ShotSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['scene', 'scene__project', 'canvas', 'status', 'is_locked', 'shot_size']
    search_fields = ['title', 'description', 'prompt']
    ordering_fields = ['number', 'created_at', 'updated_at', 'duration_seconds']
    ordering = ['scene__number', 'number']

    def get_queryset(self):
        return (
            Shot.objects.filter(scene__project__user=self.request.user)
            .select_related('scene', 'scene__project', 'canvas')
            .prefetch_related('takes', 'references', 'entity_bindings__entity')
        )

    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        shot = self.get_object()
        if not shot.is_locked:
            shot.is_locked = True
            shot.locked_snapshot = shot_snapshot(shot)
            shot.locked_at = timezone.now()
            shot.status = 'approved'
            shot.save(update_fields=['is_locked', 'locked_snapshot', 'locked_at', 'status', 'updated_at'])
            if shot.canvas_id and shot.canvas_node_key:
                node = shot.canvas.nodes.filter(node_key=shot.canvas_node_key).first()
                if node:
                    node.config_data = {**(node.config_data or {}), 'is_locked': True}
                    node.status = 'completed'
                    node.save(update_fields=['config_data', 'status', 'updated_at'])
        return Response(self.get_serializer(shot).data)

    @action(detail=True, methods=['post'])
    def unlock(self, request, pk=None):
        shot = self.get_object()
        shot.is_locked = False
        shot.locked_at = None
        shot.save(update_fields=['is_locked', 'locked_at', 'updated_at'])
        if shot.canvas_id and shot.canvas_node_key:
            node = shot.canvas.nodes.filter(node_key=shot.canvas_node_key).first()
            if node:
                node.config_data = {**(node.config_data or {}), 'is_locked': False}
                node.save(update_fields=['config_data', 'updated_at'])
        return Response(self.get_serializer(shot).data)


class ShotTakeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ShotTakeSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['shot', 'status', 'is_final', 'model_key']
    ordering_fields = ['number', 'created_at', 'updated_at']
    ordering = ['number']

    def get_queryset(self):
        return ShotTake.objects.filter(shot__scene__project__user=self.request.user).select_related('shot')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def select_final(self, request, pk=None):
        take = self.get_queryset().select_for_update().get(pk=pk)
        ShotTake.objects.filter(shot=take.shot, is_final=True).exclude(pk=take.pk).update(is_final=False)
        take.is_final = True
        take.save(update_fields=['is_final', 'updated_at'])
        return Response(self.get_serializer(take).data)


class ShotReferenceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ShotReferenceSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['shot', 'reference_type']
    ordering_fields = ['sort_order', 'created_at']

    def get_queryset(self):
        return ShotReference.objects.filter(shot__scene__project__user=self.request.user).select_related('shot')

    def perform_create(self, serializer):
        shot = serializer.validated_data['shot']
        if shot.scene.project.user_id != self.request.user.id:
            raise serializers.ValidationError('不能使用其他用户的镜头')
        serializer.save()


class ShotEntityBindingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ShotEntityBindingSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['shot', 'entity']

    def get_queryset(self):
        return ShotEntityBinding.objects.filter(shot__scene__project__user=self.request.user).select_related('shot', 'entity')

    def perform_create(self, serializer):
        shot = serializer.validated_data['shot']
        entity = serializer.validated_data['entity']
        if shot.scene.project_id != entity.project_id or shot.scene.project.user_id != self.request.user.id:
            raise serializers.ValidationError('镜头与制作实体必须属于当前用户的同一项目')
        serializer.save()


class ContinuityIssueViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ContinuityIssueSerializer
    http_method_names = ['get', 'patch', 'head', 'options']
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['project', 'category', 'severity', 'status', 'from_shot', 'to_shot']
    ordering_fields = ['created_at', 'severity']

    def get_queryset(self):
        return ContinuityIssue.objects.filter(project__user=self.request.user).select_related('from_shot', 'to_shot')


class ShotProductionViewSet(viewsets.GenericViewSet):
    """Project/canvas-level semantic operations."""

    permission_classes = [IsAuthenticated]

    def _canvas(self, pk):
        return get_object_or_404(
            WorkflowCanvas, pk=pk,
            project__user=self.request.user, created_by=self.request.user,
        )

    @action(detail=True, methods=['post'], url_path='sync-to-canvas')
    def sync_to_canvas(self, request, pk=None):
        canvas = self._canvas(pk)
        return Response(sync_shots_to_canvas(canvas))

    @action(detail=True, methods=['post'], url_path='sync-from-canvas')
    def sync_from_canvas(self, request, pk=None):
        canvas = self._canvas(pk)
        return Response(sync_canvas_to_shots(canvas))

    @action(detail=True, methods=['post'], url_path='check-continuity')
    def check_continuity(self, request, pk=None):
        canvas = self._canvas(pk)
        issues = check_project_continuity(canvas.project)
        return Response(ContinuityIssueSerializer(issues, many=True, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='bulk-rerender')
    def bulk_rerender(self, request, pk=None):
        canvas = self._canvas(pk)
        result = prepare_bulk_rerender(
            canvas,
            model_key=str(request.data.get('model_key', '')).strip(),
            shot_ids=request.data.get('shot_ids') or None,
        )
        return Response(result, status=status.HTTP_200_OK)
