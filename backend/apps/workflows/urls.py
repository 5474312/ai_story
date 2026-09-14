"""工作流路由。"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    WorkflowBindingViewSet,
    WorkflowCallbackEventViewSet,
    WorkflowCanvasViewSet,
    WorkflowDefinitionViewSet,
    WorkflowEdgeViewSet,
    WorkflowNodeViewSet,
    WorkflowNodeSchemaViewSet,
    WorkflowNodeRunEventViewSet,
    WorkflowNodeRunViewSet,
    WorkflowRunViewSet,
)


router = DefaultRouter()
router.register(r'definitions', WorkflowDefinitionViewSet, basename='workflow-definition')
router.register(r'node-schemas', WorkflowNodeSchemaViewSet, basename='workflow-node-schema')
router.register(r'canvases', WorkflowCanvasViewSet, basename='workflow-canvas')
router.register(r'nodes', WorkflowNodeViewSet, basename='workflow-node')
router.register(r'edges', WorkflowEdgeViewSet, basename='workflow-edge')
router.register(r'runs', WorkflowRunViewSet, basename='workflow-run')
router.register(r'node-runs', WorkflowNodeRunViewSet, basename='workflow-node-run')
router.register(r'node-run-events', WorkflowNodeRunEventViewSet, basename='workflow-node-run-event')
router.register(r'bindings', WorkflowBindingViewSet, basename='workflow-binding')
router.register(r'callbacks', WorkflowCallbackEventViewSet, basename='workflow-callback')

urlpatterns = [
    path('', include(router.urls)),
]
