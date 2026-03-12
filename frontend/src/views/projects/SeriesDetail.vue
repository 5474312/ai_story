<template>
  <div class="page-shell project-series-detail">
    <div class="page-header">
      <div class="page-header-main">
        <button class="back-link" @click="$router.push({ name: 'SeriesList' })">← 返回作品列表</button>
        <h1 class="page-title">{{ currentSeries?.name || '作品详情' }}</h1>
        <p class="page-subtitle">{{ currentSeries?.description || '管理作品下的全部分集' }}</p>
      </div>
      <div class="header-actions">
        <button class="primary-action" @click="goCreateEpisode">
          <span>创建分集</span>
        </button>
      </div>
    </div>

    <LoadingContainer :loading="loading">
      <div v-if="!loading && episodes.length === 0" class="empty-state">
        <div class="empty-hero">这个作品还没有分集</div>
        <p class="empty-hint">先创建第一集，再进入分集详情继续生成文案、分镜和视频。</p>
        <div class="empty-actions">
          <button class="secondary-action" @click="goBatchCreateEpisode">批量创建</button>
          <button class="secondary-action" @click="goCreateEpisode">创建第一集</button>
        </div>
      </div>

      <div v-else class="card-grid">
        <article
          v-for="episode in episodes"
          :key="episode.id"
          class="data-card"
          role="button"
          tabindex="0"
          @click="goEpisode(episode.id)"
          @keyup.enter="goEpisode(episode.id)"
        >
          <div class="card-top">
            <div>
              <h2 class="card-title">
                {{ episode.display_name || episode.name }}
                <span class="pill">第{{ episode.episode_number || '-' }}集</span>
              </h2>
              <p class="card-desc">{{ episode.description || '暂无分集描述' }}</p>
            </div>
            <span class="status-pill">{{ episode.status_display }}</span>
          </div>

          <div class="card-meta">
            <div class="meta-item">
              <span class="meta-label">阶段进度</span>
              <span class="meta-value">{{ episode.completed_stages_count }}/{{ episode.stages_count }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">所属作品</span>
              <span class="meta-value">{{ currentSeries?.name || '-' }}</span>
            </div>
          </div>

          <div class="card-footer">
            <span class="meta-time">更新于 {{ formatDate(episode.updated_at) }}</span>
            <div class="project-card-actions">
              <button class="project-card-action" @click.stop="goEditEpisode(episode.id)">编辑</button>
              <button
                class="project-card-action project-card-action--danger"
                :disabled="deletingEpisodeId === episode.id"
                @click.stop="handleDeleteEpisode(episode)"
              >
                {{ deletingEpisodeId === episode.id ? '删除中...' : '删除' }}
              </button>
            </div>
          </div>
        </article>
      </div>
    </LoadingContainer>
  </div>
</template>

<script>
import { mapActions, mapState } from 'vuex';
import LoadingContainer from '@/components/common/LoadingContainer.vue';
import { formatDate } from '@/utils/helpers';

export default {
  name: 'SeriesDetail',
  components: { LoadingContainer },
  data() {
    return {
      loading: false,
      deletingEpisodeId: null,
    };
  },
  computed: {
    ...mapState('projects', ['currentSeries']),
    episodes() {
      return this.currentSeries?.episodes || [];
    },
  },
  created() {
    this.fetchData();
  },
  methods: {
    ...mapActions('projects', ['fetchSeriesDetail', 'deleteProject']),
    formatDate,
    async fetchData() {
      this.loading = true;
      try {
        await this.fetchSeriesDetail(this.$route.params.id);
      } finally {
        this.loading = false;
      }
    },
    goCreateEpisode() {
      this.$router.push({
        name: 'ProjectCreate',
        query: { series_id: this.$route.params.id },
      });
    },
    goBatchCreateEpisode() {
      this.$router.push({
        name: 'ProjectCreate',
        query: { series_id: this.$route.params.id, mode: 'batch' },
      });
    },
    goEpisode(id) {
      this.$router.push({ name: 'ProjectDetail', params: { id } });
    },
    goEditEpisode(id) {
      this.$router.push({ name: 'ProjectEdit', params: { id } });
    },
    async handleDeleteEpisode(episode) {
      const displayName = episode.display_name || episode.name || `第${episode.episode_number || '-'}集`;
      const confirmed = window.confirm(`确定删除分集「${displayName}」吗？此操作不可恢复。`);
      if (!confirmed) {
        return;
      }

      this.deletingEpisodeId = episode.id;
      try {
        await this.deleteProject(episode.id);
        this.$message.success('分集已删除');
      } catch (error) {
        console.error('Failed to delete episode:', error);
        this.$message.error('删除分集失败');
      } finally {
        this.deletingEpisodeId = null;
      }
    },
  },
};
</script>

<style scoped>
.page-shell {
  min-height: 100%;
  padding: 2.5rem 3.5rem 3rem;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.page-header-main {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.back-link {
  border: none;
  background: transparent;
  padding: 0;
  text-align: left;
  color: #64748b;
  cursor: pointer;
}

.page-title {
  font-size: 2.2rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0;
  letter-spacing: -0.02em;
}

.layout-shell.theme-dark .page-title {
  color: #e2e8f0;
}

.page-subtitle {
  font-size: 0.95rem;
  color: #64748b;
  margin: 0;
}

.header-actions,
.empty-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.primary-action,
.secondary-action {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border-radius: 999px;
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.primary-action {
  background: #ffffff;
  color: #0f172a;
  border: 1px solid rgba(15, 23, 42, 0.12);
}

.secondary-action {
  background: rgba(255, 255, 255, 0.72);
  color: #0f172a;
  border: 1px solid rgba(15, 23, 42, 0.12);
}

.layout-shell.theme-dark .primary-action {
  background: rgba(15, 23, 42, 0.9);
  border-color: rgba(148, 163, 184, 0.25);
  color: #e2e8f0;
}

.layout-shell.theme-dark .secondary-action {
  background: rgba(15, 23, 42, 0.8);
  border-color: rgba(148, 163, 184, 0.25);
  color: #e2e8f0;
}

.primary-action:hover,
.secondary-action:hover {
  border-color: rgba(20, 184, 166, 0.6);
  box-shadow: 0 12px 24px rgba(20, 184, 166, 0.18);
  transform: translateY(-1px);
}

.layout-shell.theme-dark .primary-action:hover,
.layout-shell.theme-dark .secondary-action:hover {
  border-color: rgba(94, 234, 212, 0.6);
  box-shadow: 0 12px 24px rgba(2, 6, 23, 0.55);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
}

.data-card {
  background: linear-gradient(90deg, rgba(20, 184, 166, 0.7) 0%, rgba(14, 165, 233, 0.7) 100%)
      0 0 / 0 3px no-repeat,
    rgba(255, 255, 255, 0.92);
  border-radius: 18px;
  padding: 1.5rem;
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.layout-shell.theme-dark .data-card {
  background: linear-gradient(90deg, rgba(94, 234, 212, 0.5) 0%, rgba(56, 189, 248, 0.5) 100%)
      0 0 / 0 3px no-repeat,
    rgba(15, 23, 42, 0.92);
  border-color: rgba(148, 163, 184, 0.2);
  box-shadow: 0 16px 32px rgba(2, 6, 23, 0.55);
}

.data-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 18px 36px rgba(15, 23, 42, 0.12);
  background-size: 100% 3px, auto;
}

.layout-shell.theme-dark .data-card:hover {
  box-shadow: 0 18px 36px rgba(2, 6, 23, 0.68);
}

.card-top,
.card-meta,
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.card-top {
  align-items: flex-start;
}

.card-title {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 0.65rem;
  font-size: 1.1rem;
  color: #0f172a;
}

.layout-shell.theme-dark .card-title {
  color: #f8fafc;
}

.card-desc {
  margin: 0.55rem 0 0;
  color: #64748b;
  line-height: 1.6;
}

.pill,
.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.35rem 0.75rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
}

.pill {
  background: rgba(15, 23, 42, 0.06);
  color: #0f172a;
}

.status-pill {
  background: rgba(20, 184, 166, 0.12);
  color: #0f766e;
}

.layout-shell.theme-dark .pill {
  background: rgba(148, 163, 184, 0.14);
  color: #e2e8f0;
}

.layout-shell.theme-dark .status-pill {
  background: rgba(94, 234, 212, 0.12);
  color: #99f6e4;
}

.card-meta {
  padding: 1rem 0;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.meta-label,
.meta-time {
  color: #94a3b8;
  font-size: 0.85rem;
}

.meta-value {
  color: #0f172a;
  font-weight: 600;
}

.layout-shell.theme-dark .meta-value {
  color: #e2e8f0;
}

.project-card-actions {
  justify-content: flex-end;
}

.secondary-action {
  border-radius: 999px;
  padding: 0.34rem 0.78rem;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(255, 255, 255, 0.72);
  color: #0f172a;
  font-size: 0.78rem;
  line-height: 1.2;
  cursor: pointer;
  transition: all 0.2s ease;
}

.layout-shell.theme-dark .secondary-action {
  background: rgba(15, 23, 42, 0.82);
  color: #e2e8f0;
  border-color: rgba(148, 163, 184, 0.24);
}

.secondary-action:hover {
  border-color: rgba(20, 184, 166, 0.45);
  box-shadow: 0 8px 18px rgba(20, 184, 166, 0.1);
  transform: translateY(-1px);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.85rem;
  padding: 4rem 1.5rem;
  text-align: center;
  border-radius: 22px;
  border: 1px dashed rgba(148, 163, 184, 0.25);
  background: rgba(255, 255, 255, 0.72);
}

.layout-shell.theme-dark .empty-state {
  background: rgba(15, 23, 42, 0.68);
  border-color: rgba(148, 163, 184, 0.2);
}

.empty-hero {
  font-size: 1.4rem;
  font-weight: 600;
  color: #0f172a;
}

.layout-shell.theme-dark .empty-hero {
  color: #f8fafc;
}

.empty-hint {
  margin: 0;
  max-width: 520px;
  color: #64748b;
  line-height: 1.7;
}

@media (max-width: 960px) {
  .page-shell {
    padding: 1.5rem;
  }

  .page-header,
  .card-top,
  .card-meta,
  .card-footer {
    flex-direction: column;
    align-items: flex-start;
  }

  .card-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
