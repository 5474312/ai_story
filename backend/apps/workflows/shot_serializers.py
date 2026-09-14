"""API serializers for shot-level video semantics."""

from rest_framework import serializers

from .models import (
    ContinuityIssue,
    ProductionEntity,
    ProductionScene,
    Shot,
    ShotEntityBinding,
    ShotReference,
    ShotTake,
)


class ProductionEntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductionEntity
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_project(self, project):
        if project.user_id != self.context['request'].user.id:
            raise serializers.ValidationError('不能使用其他用户的项目')
        return project


class ShotReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShotReference
        fields = '__all__'
        read_only_fields = ['id', 'created_at']

    def validate_shot(self, shot):
        if shot.scene.project.user_id != self.context['request'].user.id:
            raise serializers.ValidationError('不能使用其他用户的镜头')
        return shot


class ShotTakeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShotTake
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        shot = attrs.get('shot') or getattr(self.instance, 'shot', None)
        if shot and shot.scene.project.user_id != self.context['request'].user.id:
            raise serializers.ValidationError('不能使用其他用户的镜头')
        return attrs

    def create(self, validated_data):
        if validated_data.get('is_final'):
            ShotTake.objects.filter(shot=validated_data['shot'], is_final=True).update(is_final=False)
        return super().create(validated_data)


class ShotEntityBindingSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source='entity.name', read_only=True)
    entity_type = serializers.CharField(source='entity.entity_type', read_only=True)

    class Meta:
        model = ShotEntityBinding
        fields = ['id', 'shot', 'entity', 'entity_name', 'entity_type', 'state_data', 'created_at']
        read_only_fields = ['id', 'entity_name', 'entity_type', 'created_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        shot = attrs.get('shot') or getattr(self.instance, 'shot', None)
        entity = attrs.get('entity') or getattr(self.instance, 'entity', None)
        if shot and entity and (
            shot.scene.project_id != entity.project_id
            or shot.scene.project.user_id != self.context['request'].user.id
        ):
            raise serializers.ValidationError('镜头与制作实体必须属于当前用户的同一项目')
        return attrs


class ShotSerializer(serializers.ModelSerializer):
    references = ShotReferenceSerializer(many=True, read_only=True)
    takes = ShotTakeSerializer(many=True, read_only=True)
    entity_bindings = ShotEntityBindingSerializer(many=True, read_only=True)
    scene_name = serializers.CharField(source='scene.name', read_only=True)
    scene_number = serializers.IntegerField(source='scene.number', read_only=True)
    final_take = serializers.SerializerMethodField()

    class Meta:
        model = Shot
        fields = [
            'id', 'scene', 'scene_name', 'scene_number', 'canvas', 'number',
            'title', 'description', 'prompt', 'shot_size', 'camera_angle',
            'focal_length_mm', 'camera_movement', 'duration_seconds',
            'frame_rate', 'aspect_ratio', 'pacing', 'status', 'canvas_node_key',
            'continuity_data', 'is_locked', 'locked_snapshot', 'locked_at',
            'version', 'references', 'takes', 'final_take', 'entity_bindings',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'is_locked', 'locked_snapshot', 'locked_at', 'version',
            'created_at', 'updated_at',
        ]

    def get_final_take(self, obj):
        take = next((item for item in obj.takes.all() if item.is_final), None)
        return ShotTakeSerializer(take, context=self.context).data if take else None

    def validate(self, attrs):
        attrs = super().validate(attrs)
        scene = attrs.get('scene') or getattr(self.instance, 'scene', None)
        canvas = attrs.get('canvas') or getattr(self.instance, 'canvas', None)
        if scene and scene.project.user_id != self.context['request'].user.id:
            raise serializers.ValidationError('不能使用其他用户的场景')
        if canvas and scene and canvas.project_id != scene.project_id:
            raise serializers.ValidationError({'canvas': '画板与场景不属于同一项目'})
        if self.instance and self.instance.is_locked:
            mutable = set(attrs) - {'status'}
            if mutable:
                raise serializers.ValidationError('镜头已锁定，请先解锁再编辑')
        return attrs

    def update(self, instance, validated_data):
        instance.version += 1
        return super().update(instance, validated_data)


class ProductionSceneSerializer(serializers.ModelSerializer):
    shots = ShotSerializer(many=True, read_only=True)
    shot_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductionScene
        fields = [
            'id', 'project', 'canvas', 'number', 'name', 'synopsis', 'location',
            'time_of_day', 'interior_exterior', 'continuity_data', 'shot_count',
            'shots', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'shot_count', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        project = attrs.get('project') or getattr(self.instance, 'project', None)
        canvas = attrs.get('canvas') or getattr(self.instance, 'canvas', None)
        location = attrs.get('location') or getattr(self.instance, 'location', None)
        if project and project.user_id != self.context['request'].user.id:
            raise serializers.ValidationError('不能使用其他用户的项目')
        if canvas and project and canvas.project_id != project.id:
            raise serializers.ValidationError({'canvas': '画板与项目不匹配'})
        if location and (location.project_id != project.id or location.entity_type != 'location'):
            raise serializers.ValidationError({'location': '必须使用当前项目的场景设定'})
        return attrs


class ContinuityIssueSerializer(serializers.ModelSerializer):
    from_shot_label = serializers.CharField(source='from_shot.__str__', read_only=True)
    to_shot_label = serializers.CharField(source='to_shot.__str__', read_only=True)

    class Meta:
        model = ContinuityIssue
        fields = '__all__'
        read_only_fields = [
            'id', 'project', 'from_shot', 'to_shot', 'category', 'severity',
            'message', 'expected_value', 'actual_value', 'created_at', 'updated_at',
        ]
