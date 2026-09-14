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
    WorkflowResultCandidateViewSet,
    WorkflowRunViewSet,
)
from .shot_views import (
    ContinuityIssueViewSet,
    ProductionEntityViewSet,
    ProductionSceneViewSet,
    ShotEntityBindingViewSet,
    ShotProductionViewSet,
    ShotReferenceViewSet,
    ShotTakeViewSet,
    ShotViewSet,
)


router = DefaultRouter()
router.register(r'definitions', WorkflowDefinitionViewSet, basename='workflow-definition')
router.register(r'node-schemas', WorkflowNodeSchemaViewSet, basename='workflow-node-schema')
router.register(r'canvases', WorkflowCanvasViewSet, basename='workflow-canvas')
router.register(r'nodes', WorkflowNodeViewSet, basename='workflow-node')
router.register(r'edges', WorkflowEdgeViewSet, basename='workflow-edge')
router.register(r'runs', WorkflowRunViewSet, basename='workflow-run')
router.register(r'node-runs', WorkflowNodeRunViewSet, basename='workflow-node-run')
router.register(r'candidates', WorkflowResultCandidateViewSet, basename='workflow-result-candidate')
router.register(r'node-run-events', WorkflowNodeRunEventViewSet, basename='workflow-node-run-event')
router.register(r'bindings', WorkflowBindingViewSet, basename='workflow-binding')
router.register(r'callbacks', WorkflowCallbackEventViewSet, basename='workflow-callback')
router.register(r'production-entities', ProductionEntityViewSet, basename='production-entity')
router.register(r'production-scenes', ProductionSceneViewSet, basename='production-scene')
router.register(r'shots', ShotViewSet, basename='shot')
router.register(r'shot-takes', ShotTakeViewSet, basename='shot-take')
router.register(r'shot-references', ShotReferenceViewSet, basename='shot-reference')
router.register(r'shot-entity-bindings', ShotEntityBindingViewSet, basename='shot-entity-binding')
router.register(r'continuity-issues', ContinuityIssueViewSet, basename='continuity-issue')
router.register(r'shot-production', ShotProductionViewSet, basename='shot-production')

urlpatterns = [
    path('', include(router.urls)),
]
