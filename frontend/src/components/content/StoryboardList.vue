<template>
  <div class="storyboard-list">
    <el-row :gutter="20">
      <el-col
        v-for="storyboard in storyboards"
        :key="storyboard.id"
        :xs="24"
        :sm="12"
        :md="8"
        :lg="6"
      >
        <el-card
          class="storyboard-card"
          shadow="hover"
        >
          <div class="storyboard-header">
            <span class="sequence-number">#{{ storyboard.sequence_number }}</span>
            <el-tag size="small">
              {{ formatDuration(storyboard.duration_seconds) }}
            </el-tag>
          </div>

          <div class="storyboard-content">
            <h4>场景描述</h4>
            <p>{{ storyboard.scene_description }}</p>

            <h4>旁白文本</h4>
            <p>{{ storyboard.narration_text }}</p>

            <h4>图片提示词</h4>
            <p class="image-prompt">
              {{ storyboard.image_prompt }}
            </p>
          </div>

          <div class="storyboard-footer">
            <el-button
              size="small"
              type="text"
              @click="handleViewImages(storyboard)"
            >
              查看图片
            </el-button>
            <el-button
              size="small"
              type="text"
              @click="handleViewVideos(storyboard)"
            >
              查看视频
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <div
      v-if="storyboards.length === 0"
      class="empty-state"
    >
      <el-empty description="暂无分镜数据" />
    </div>
  </div>
</template>

<script>
import { mapActions } from 'vuex';
import { formatDuration } from '@/utils/helpers';

export default {
  name: 'StoryboardList',
  props: {
    projectId: {
      type: [String, Number],
      required: true,
    },
  },
  data() {
    return {
      storyboards: [],
    };
  },
  created() {
    this.fetchData();
  },
  methods: {
    ...mapActions('content', ['fetchStoryboards']),
    formatDuration,

    async fetchData() {
      try {
        this.storyboards = await this.fetchStoryboards(this.projectId);
      } catch (error) {
        console.error('Failed to fetch storyboards:', error);
      }
    },

    handleViewImages() {
      // TODO: 实现查看图片功能
      this.$message.info('查看图片功能待实现');
    },

    handleViewVideos() {
      // TODO: 实现查看视频功能
      this.$message.info('查看视频功能待实现');
    },
  },
};
</script>

<style scoped>
.storyboard-card {
  margin-bottom: 20px;
}

.storyboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.sequence-number {
  font-size: 18px;
  font-weight: bold;
  color: #409eff;
}

.storyboard-content h4 {
  margin: 10px 0 5px;
  font-size: 14px;
  color: #606266;
}

.storyboard-content p {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.5;
  color: #909399;
}

.image-prompt {
  font-style: italic;
  background-color: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
}

.storyboard-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #ebeef5;
}

.empty-state {
  padding: 40px 0;
}
</style>
